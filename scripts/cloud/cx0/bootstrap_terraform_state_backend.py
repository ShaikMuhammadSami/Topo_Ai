"""Guarded bootstrap for the CX-0 durable Terraform state bucket.

PRECHECK is the default and is read-only.  EXECUTE can create exactly the
approved, absent bucket and configure it once; it never repairs, replaces, or
renames an existing bucket.  This utility never reads or writes Terraform
state objects.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from typing import Any

import boto3
from botocore.exceptions import ClientError


EXPECTED_ACCOUNT = "297361542190"
EXPECTED_REGION = "us-east-1"
BACKEND_BUCKET = "topo-tfstate-297361542190-us-east-1"
BACKEND_KEY = "golden/terraform.tfstate"
LOCK_KEY = f"{BACKEND_KEY}.tflock"
EXECUTE_CONFIRMATION = "CREATE_GOLDEN_TERRAFORM_BACKEND"

REQUIRED_TAGS = {
    "environment": "golden",
    "purpose": "terraform-state",
    "authority": "DURABLE_EXTERNAL_AUTHORITY",
    "cost0-retain": "true",
    "cx0b-delete": "forbidden",
}

PUBLIC_ACCESS_BLOCK = {
    "BlockPublicAcls": True,
    "IgnorePublicAcls": True,
    "BlockPublicPolicy": True,
    "RestrictPublicBuckets": True,
}


class ContractError(RuntimeError):
    """A fail-closed backend contract error."""


@dataclass(frozen=True)
class Inspection:
    bucket: str
    region: str
    exists: bool
    configuration_matches: bool
    versioning_enabled: bool
    public_access_blocked: bool
    ownership_bucket_owner_enforced: bool
    encryption_aes256: bool
    non_tls_denied: bool
    lifecycle_expiration_absent: bool
    required_tags_match: bool
    state_object_exists: bool
    state_object_version_id: str | None
    state_object_etag: str | None
    state_object_size_bytes: int | None
    lock_object_exists: bool


def _error_code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", ""))


def _is_missing(error: ClientError, *codes: str) -> bool:
    return _error_code(error) in set(codes)


def _session(profile: str | None = None) -> Any:
    return boto3.session.Session(profile_name=profile or None, region_name=EXPECTED_REGION)


def _assert_identity(sts: Any) -> None:
    identity = sts.get_caller_identity()
    if str(identity.get("Account", "")) != EXPECTED_ACCOUNT:
        raise ContractError("STOP: AWS account does not match the approved account")


def _head_metadata(s3: Any, key: str) -> dict[str, Any] | None:
    try:
        return s3.head_object(
            Bucket=BACKEND_BUCKET,
            Key=key,
            ExpectedBucketOwner=EXPECTED_ACCOUNT,
        )
    except ClientError as error:
        if _is_missing(error, "404", "NoSuchKey", "NotFound"):
            return None
        raise ContractError(f"STOP: unable to inspect approved object metadata ({_error_code(error)})") from error


def inspect_bucket(s3: Any) -> Inspection:
    try:
        s3.head_bucket(Bucket=BACKEND_BUCKET, ExpectedBucketOwner=EXPECTED_ACCOUNT)
    except ClientError as error:
        if _is_missing(error, "404", "NoSuchBucket", "NotFound"):
            return Inspection(
                bucket=BACKEND_BUCKET,
                region=EXPECTED_REGION,
                exists=False,
                configuration_matches=False,
                versioning_enabled=False,
                public_access_blocked=False,
                ownership_bucket_owner_enforced=False,
                encryption_aes256=False,
                non_tls_denied=False,
                lifecycle_expiration_absent=False,
                required_tags_match=False,
                state_object_exists=False,
                state_object_version_id=None,
                state_object_etag=None,
                state_object_size_bytes=None,
                lock_object_exists=False,
            )
        # A globally occupied bucket owned by another account normally returns
        # AccessDenied.  It is a naming conflict, never authority to improvise.
        raise ContractError(f"STOP: approved bucket name is unavailable or inaccessible ({_error_code(error)})") from error

    location = s3.get_bucket_location(
        Bucket=BACKEND_BUCKET,
        ExpectedBucketOwner=EXPECTED_ACCOUNT,
    ).get("LocationConstraint") or "us-east-1"
    if location != EXPECTED_REGION:
        raise ContractError("STOP: approved bucket exists in an unexpected region")

    versioning = s3.get_bucket_versioning(
        Bucket=BACKEND_BUCKET,
        ExpectedBucketOwner=EXPECTED_ACCOUNT,
    ).get("Status") == "Enabled"

    try:
        public = s3.get_public_access_block(
            Bucket=BACKEND_BUCKET,
            ExpectedBucketOwner=EXPECTED_ACCOUNT,
        ).get("PublicAccessBlockConfiguration", {})
    except ClientError as error:
        if not _is_missing(error, "NoSuchPublicAccessBlockConfiguration", "404"):
            raise
        public = {}
    public_blocked = all(public.get(key) is value for key, value in PUBLIC_ACCESS_BLOCK.items())

    try:
        ownership_rules = s3.get_bucket_ownership_controls(
            Bucket=BACKEND_BUCKET,
            ExpectedBucketOwner=EXPECTED_ACCOUNT,
        ).get("OwnershipControls", {}).get("Rules", [])
    except ClientError as error:
        if not _is_missing(error, "OwnershipControlsNotFoundError", "NoSuchOwnershipControls", "404"):
            raise
        ownership_rules = []
    owner_enforced = any(rule.get("ObjectOwnership") == "BucketOwnerEnforced" for rule in ownership_rules)

    try:
        encryption_rules = s3.get_bucket_encryption(
            Bucket=BACKEND_BUCKET,
            ExpectedBucketOwner=EXPECTED_ACCOUNT,
        ).get("ServerSideEncryptionConfiguration", {}).get("Rules", [])
    except ClientError as error:
        if not _is_missing(error, "ServerSideEncryptionConfigurationNotFoundError", "404"):
            raise
        encryption_rules = []
    encryption_aes256 = any(
        rule.get("ApplyServerSideEncryptionByDefault", {}).get("SSEAlgorithm") == "AES256"
        for rule in encryption_rules
    )

    try:
        policy = json.loads(
            s3.get_bucket_policy(
                Bucket=BACKEND_BUCKET,
                ExpectedBucketOwner=EXPECTED_ACCOUNT,
            ).get("Policy", "{}")
        )
    except ClientError as error:
        if not _is_missing(error, "NoSuchBucketPolicy", "404"):
            raise
        policy = {}
    non_tls_denied = any(
        statement.get("Effect") == "Deny"
        and statement.get("Condition", {}).get("Bool", {}).get("aws:SecureTransport") == "false"
        for statement in policy.get("Statement", [])
    )

    try:
        lifecycle_rules = s3.get_bucket_lifecycle_configuration(
            Bucket=BACKEND_BUCKET,
            ExpectedBucketOwner=EXPECTED_ACCOUNT,
        ).get("Rules", [])
    except ClientError as error:
        if not _is_missing(error, "NoSuchLifecycleConfiguration", "404"):
            raise
        lifecycle_rules = []
    no_expiration = not any(
        rule.get("Expiration") or rule.get("NoncurrentVersionExpiration")
        for rule in lifecycle_rules
    )

    try:
        tag_set = s3.get_bucket_tagging(
            Bucket=BACKEND_BUCKET,
            ExpectedBucketOwner=EXPECTED_ACCOUNT,
        ).get("TagSet", [])
    except ClientError as error:
        if not _is_missing(error, "NoSuchTagSet", "404"):
            raise
        tag_set = []
    tags = {str(item.get("Key")): str(item.get("Value")) for item in tag_set}
    tags_match = all(tags.get(key) == value for key, value in REQUIRED_TAGS.items())

    checks = (
        versioning,
        public_blocked,
        owner_enforced,
        encryption_aes256,
        non_tls_denied,
        no_expiration,
        tags_match,
    )
    state_metadata = _head_metadata(s3, BACKEND_KEY)
    lock_metadata = _head_metadata(s3, LOCK_KEY)
    return Inspection(
        bucket=BACKEND_BUCKET,
        region=location,
        exists=True,
        configuration_matches=all(checks),
        versioning_enabled=versioning,
        public_access_blocked=public_blocked,
        ownership_bucket_owner_enforced=owner_enforced,
        encryption_aes256=encryption_aes256,
        non_tls_denied=non_tls_denied,
        lifecycle_expiration_absent=no_expiration,
        required_tags_match=tags_match,
        state_object_exists=state_metadata is not None,
        state_object_version_id=(
            str(state_metadata.get("VersionId"))
            if state_metadata is not None and state_metadata.get("VersionId") is not None
            else None
        ),
        state_object_etag=(
            str(state_metadata.get("ETag"))
            if state_metadata is not None and state_metadata.get("ETag") is not None
            else None
        ),
        state_object_size_bytes=(
            int(state_metadata.get("ContentLength"))
            if state_metadata is not None and state_metadata.get("ContentLength") is not None
            else None
        ),
        lock_object_exists=lock_metadata is not None,
    )


def _non_tls_policy() -> str:
    bucket_arn = f"arn:aws:s3:::{BACKEND_BUCKET}"
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "DenyInsecureTransport",
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": "s3:*",
                    "Resource": [bucket_arn, f"{bucket_arn}/*"],
                    "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                }
            ],
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def create_once(s3: Any) -> Inspection:
    before = inspect_bucket(s3)
    if before.exists:
        if not before.configuration_matches:
            raise ContractError("STOP: existing approved bucket configuration differs; automatic repair is forbidden")
        return before

    # us-east-1 intentionally omits CreateBucketConfiguration.
    s3.create_bucket(Bucket=BACKEND_BUCKET, ObjectOwnership="BucketOwnerEnforced")
    s3.put_public_access_block(
        Bucket=BACKEND_BUCKET,
        ExpectedBucketOwner=EXPECTED_ACCOUNT,
        PublicAccessBlockConfiguration=PUBLIC_ACCESS_BLOCK,
    )
    s3.put_bucket_encryption(
        Bucket=BACKEND_BUCKET,
        ExpectedBucketOwner=EXPECTED_ACCOUNT,
        ServerSideEncryptionConfiguration={
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
        },
    )
    s3.put_bucket_versioning(
        Bucket=BACKEND_BUCKET,
        ExpectedBucketOwner=EXPECTED_ACCOUNT,
        VersioningConfiguration={"Status": "Enabled"},
    )
    s3.put_bucket_policy(
        Bucket=BACKEND_BUCKET,
        ExpectedBucketOwner=EXPECTED_ACCOUNT,
        Policy=_non_tls_policy(),
    )
    s3.put_bucket_tagging(
        Bucket=BACKEND_BUCKET,
        ExpectedBucketOwner=EXPECTED_ACCOUNT,
        Tagging={"TagSet": [{"Key": key, "Value": value} for key, value in sorted(REQUIRED_TAGS.items())]},
    )
    after = inspect_bucket(s3)
    if not after.configuration_matches:
        raise ContractError("STOP: newly created bucket did not satisfy the complete backend contract")
    return after


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("PRECHECK", "EXECUTE"), default="PRECHECK")
    parser.add_argument("--confirmation", default="")
    parser.add_argument("--profile", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        session = _session(args.profile)
        sts = session.client("sts", region_name=EXPECTED_REGION)
        s3 = session.client("s3", region_name=EXPECTED_REGION)
        _assert_identity(sts)
        if args.mode == "EXECUTE":
            if args.confirmation != EXECUTE_CONFIRMATION:
                raise ContractError("STOP: EXECUTE requires the exact creation confirmation")
            result = create_once(s3)
        else:
            if args.confirmation:
                raise ContractError("STOP: PRECHECK does not accept a mutation confirmation")
            result = inspect_bucket(s3)
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
        return 0
    except ContractError as error:
        print(str(error), file=sys.stderr)
        return 1
    except ClientError as error:
        # Provider text is deliberately suppressed so request/environment
        # details cannot escape this metadata-only boundary.
        print(f"STOP: AWS backend metadata operation failed ({_error_code(error)})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
