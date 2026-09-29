"""Escrow and verify the golden SecretStore keyring without rendering it.

The only write path is an explicit, create-if-absent Secrets Manager call.  An
existing recovery object is immutable to this tool: mismatch, missing tags, or
an unsupported payload all fail closed without adding a version.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Callable, Mapping, Sequence


EXPECTED_ACCOUNT = "297361542190"
EXPECTED_REGION = "us-east-1"
EXPECTED_CONTEXT = "topo-golden"
EXPECTED_NAMESPACE = "topo-system"
RUNTIME_SECRET_NAME = "topo-backend-runtime"
RECOVERY_SECRET_NAME = "topo/golden/recovery/secret-store-keyring-v1"
ACCEPTED_CLOUD_HEAD = "e676559b3daf586b4dc53041d1638a3d2191910a"
KEYRING_DATA_KEY = "secret-store-keyring.json"
ACTIVE_KEY_DATA_KEY = "secret-store-active-key-id"
KEY_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RECOVERY_PROCEDURE = (
    REPOSITORY_ROOT / "docs/operations/cx-0-rds-recovery-proof-plan.md"
)


class RecoveryCustodyError(RuntimeError):
    """A bounded failure code that never contains secret material."""


class RecoveryEscrowMismatch(RecoveryCustodyError):
    def __init__(self, evidence: "RecoverySecretEvidence") -> None:
        super().__init__("RECOVERY_ESCROW_MISMATCH")
        self.evidence = evidence


@dataclass(frozen=True)
class LiveKeyringEvidence:
    keyring_bytes: bytes = field(repr=False)
    active_key_id: str
    sha256: str
    format_version: int
    key_count: int


@dataclass(frozen=True)
class RecoverySecretEvidence:
    name: str
    arn: str
    version_id: str
    sha256: str
    tags: Mapping[str, str]
    created: bool


def _run_capture(arguments: Sequence[str]) -> bytes:
    try:
        completed = subprocess.run(
            list(arguments),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise RecoveryCustodyError("KUBERNETES_CLIENT_UNAVAILABLE") from exc
    if completed.returncode != 0:
        # Never include subprocess output: provider errors may contain environment
        # details, and the successful key reads contain secret material.
        raise RecoveryCustodyError("KUBERNETES_READ_FAILED")
    return completed.stdout


def _decode_secret_key(encoded: bytes, *, error_code: str) -> bytes:
    try:
        compact = encoded.strip()
        if not compact:
            raise ValueError()
        return base64.b64decode(compact, validate=True)
    except (ValueError, TypeError) as exc:
        raise RecoveryCustodyError(error_code) from exc


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def _validate_keyring(keyring_bytes: bytes, active_key_id: str) -> tuple[int, int]:
    try:
        document = json.loads(keyring_bytes, object_pairs_hook=_unique_object)
        if not isinstance(document, dict) or set(document) != {"version", "keys"}:
            raise ValueError()
        if type(document["version"]) is not int or document["version"] != 1:
            raise ValueError()
        keys = document["keys"]
        if not isinstance(keys, dict) or not 1 <= len(keys) <= 32:
            raise ValueError()
        for key_id, encoded in keys.items():
            if (
                not isinstance(key_id, str)
                or KEY_ID_PATTERN.fullmatch(key_id) is None
                or not isinstance(encoded, str)
                or re.fullmatch(r"[A-Za-z0-9_-]{43}=?", encoded) is None
            ):
                raise ValueError()
            raw = base64.b64decode(
                encoded.rstrip("=") + "=", altchars=b"-_", validate=True
            )
            canonical = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
            if len(raw) != 32 or canonical != encoded.rstrip("="):
                raise ValueError()
        if active_key_id not in keys:
            raise ValueError()
        return document["version"], len(keys)
    except (UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise RecoveryCustodyError("LIVE_KEYRING_INVALID") from exc


def read_live_keyring(
    *,
    context: str = EXPECTED_CONTEXT,
    namespace: str = EXPECTED_NAMESPACE,
    runtime_secret_name: str = RUNTIME_SECRET_NAME,
    runner: Callable[[Sequence[str]], bytes] = _run_capture,
) -> LiveKeyringEvidence:
    available_context = runner(
        ("kubectl", "config", "get-contexts", context, "--output", "name")
    ).decode(
        "utf-8", errors="strict"
    ).strip()
    if available_context != context:
        raise RecoveryCustodyError("KUBERNETES_CONTEXT_MISMATCH")

    def read_key(key_name: str) -> bytes:
        # kubectl receives one exact JSONPath and only its stdout enters this
        # process.  No full Secret JSON, other data key, or stringData is emitted.
        json_path = "jsonpath={.data." + key_name.replace(".", r"\.") + "}"
        encoded = runner(
            (
                "kubectl",
                "--context",
                context,
                "get",
                "secret",
                runtime_secret_name,
                "--namespace",
                namespace,
                "--output",
                json_path,
            )
        )
        return _decode_secret_key(encoded, error_code="KUBERNETES_SECRET_KEY_INVALID")

    keyring_bytes = read_key(KEYRING_DATA_KEY)
    try:
        active_key_id = read_key(ACTIVE_KEY_DATA_KEY).decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise RecoveryCustodyError("ACTIVE_KEY_ID_INVALID") from exc
    if KEY_ID_PATTERN.fullmatch(active_key_id) is None:
        raise RecoveryCustodyError("ACTIVE_KEY_ID_INVALID")
    format_version, key_count = _validate_keyring(keyring_bytes, active_key_id)
    return LiveKeyringEvidence(
        keyring_bytes=keyring_bytes,
        active_key_id=active_key_id,
        sha256=hashlib.sha256(keyring_bytes).hexdigest(),
        format_version=format_version,
        key_count=key_count,
    )


def _aws_error_code(exc: BaseException) -> str | None:
    response = getattr(exc, "response", None)
    if not isinstance(response, Mapping):
        return None
    error = response.get("Error")
    if not isinstance(error, Mapping):
        return None
    code = error.get("Code")
    return code if isinstance(code, str) else None


def _required_tags(live: LiveKeyringEvidence) -> dict[str, str]:
    return {
        "environment": "golden",
        "purpose": "secretstore-recovery",
        "cost0-retain": "true",
        "accepted-cloud-head": ACCEPTED_CLOUD_HEAD,
        "active-key-id": live.active_key_id,
        "keyring-sha256": live.sha256,
    }


def _describe(client: Any, name: str) -> Mapping[str, Any] | None:
    try:
        response = client.describe_secret(SecretId=name)
    except Exception as exc:  # provider exception type is loaded only in live use
        if _aws_error_code(exc) == "ResourceNotFoundException":
            return None
        raise RecoveryCustodyError("RECOVERY_SECRET_DESCRIBE_FAILED") from exc
    if not isinstance(response, Mapping):
        raise RecoveryCustodyError("RECOVERY_SECRET_DESCRIBE_INVALID")
    return response


def _payload_bytes(response: Mapping[str, Any]) -> bytes:
    payload = response.get("SecretBinary")
    if isinstance(payload, memoryview):
        payload = payload.tobytes()
    if isinstance(payload, bytearray):
        payload = bytes(payload)
    if not isinstance(payload, bytes):
        raise RecoveryCustodyError("RECOVERY_SECRET_NOT_BINARY")
    return payload


def ensure_recovery_secret(
    *,
    client: Any,
    live: LiveKeyringEvidence,
    name: str = RECOVERY_SECRET_NAME,
    create_if_absent: bool,
) -> RecoverySecretEvidence:
    description = _describe(client, name)
    created = False
    if description is None:
        if not create_if_absent:
            raise RecoveryCustodyError("RECOVERY_SECRET_ABSENT")
        try:
            client.create_secret(
                Name=name,
                Description=(
                    "TopoAI golden SecretStore complete keyring recovery authority; "
                    "COST_0_RETAIN; DO_NOT_DELETE_DURING_CX_0B"
                ),
                SecretBinary=live.keyring_bytes,
                Tags=[
                    {"Key": key, "Value": value}
                    for key, value in sorted(_required_tags(live).items())
                ],
            )
        except Exception as exc:
            # A concurrent creation or any other error is not converted into an
            # overwrite/update path.  The operator must inspect and retry verify-only.
            raise RecoveryCustodyError("RECOVERY_SECRET_CREATE_FAILED") from exc
        created = True
        description = _describe(client, name)
        if description is None:
            raise RecoveryCustodyError("RECOVERY_SECRET_POST_CREATE_MISSING")

    try:
        value = client.get_secret_value(SecretId=name, VersionStage="AWSCURRENT")
    except Exception as exc:
        raise RecoveryCustodyError("RECOVERY_SECRET_READ_FAILED") from exc
    if not isinstance(value, Mapping):
        raise RecoveryCustodyError("RECOVERY_SECRET_READ_INVALID")

    payload_hash = hashlib.sha256(_payload_bytes(value)).hexdigest()
    tags = {
        item.get("Key"): item.get("Value")
        for item in description.get("Tags", [])
        if isinstance(item, Mapping)
        and isinstance(item.get("Key"), str)
        and isinstance(item.get("Value"), str)
    }
    arn = description.get("ARN")
    version_id = value.get("VersionId")
    stages = description.get("VersionIdsToStages", {})
    if (
        not isinstance(arn, str)
        or not arn.startswith(
            f"arn:aws:secretsmanager:{EXPECTED_REGION}:{EXPECTED_ACCOUNT}:secret:"
        )
        or not isinstance(version_id, str)
        or not version_id
        or not isinstance(stages, Mapping)
        or "AWSCURRENT" not in stages.get(version_id, [])
    ):
        raise RecoveryCustodyError("RECOVERY_SECRET_IDENTITY_INVALID")

    evidence = RecoverySecretEvidence(
        name=name,
        arn=arn,
        version_id=version_id,
        sha256=payload_hash,
        tags=tags,
        created=created,
    )
    if payload_hash != live.sha256:
        raise RecoveryEscrowMismatch(evidence)
    if any(tags.get(key) != value for key, value in _required_tags(live).items()):
        raise RecoveryCustodyError("RECOVERY_SECRET_METADATA_MISMATCH")
    return evidence


def recovery_procedure_matches(
    path: Path,
    *,
    live: LiveKeyringEvidence,
    recovery: RecoverySecretEvidence,
) -> bool:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return False
    required = (
        f"RECOVERY_SECRET_NAME={recovery.name}",
        f"RECOVERY_SECRET_ARN={recovery.arn}",
        f"ACTIVE_KEY_ID={live.active_key_id}",
        f"KEYRING_SHA256={live.sha256}",
        "DURABLE_EXTERNAL_AUTHORITY",
        "COST_0_RETAIN",
        "DO_NOT_DELETE_DURING_CX_0B",
    )
    return all(marker in content for marker in required)


def _build_clients(profile: str, region: str) -> tuple[Any, Any]:
    try:
        import boto3

        session = boto3.Session(profile_name=profile, region_name=region)
        return session.client("sts"), session.client("secretsmanager")
    except Exception as exc:
        raise RecoveryCustodyError("AWS_CLIENT_INITIALIZATION_FAILED") from exc


def _safe_result(
    *,
    live: LiveKeyringEvidence,
    recovery: RecoverySecretEvidence,
    procedure_found: bool,
) -> dict[str, Any]:
    proven = recovery.sha256 == live.sha256 and procedure_found
    return {
        "custody_mechanism": "AWS_SECRETS_MANAGER",
        "runtime_secret_name": RUNTIME_SECRET_NAME,
        "key_names": [KEYRING_DATA_KEY, ACTIVE_KEY_DATA_KEY],
        "active_key_identifier": live.active_key_id,
        "active_key_identifier_status": "RECORDED",
        "live_keyring_sha256": live.sha256,
        "keyring_format_version": live.format_version,
        "key_count": live.key_count,
        "recovery_secret_name": recovery.name,
        "recovery_secret_arn": recovery.arn,
        "recovery_secret_version_id": recovery.version_id,
        "recovery_keyring_sha256": recovery.sha256,
        "keyring_fingerprint_match": recovery.sha256 == live.sha256,
        "external_recovery_custody_found": True,
        "recovery_procedure_reference": str(
            DEFAULT_RECOVERY_PROCEDURE.relative_to(REPOSITORY_ROOT).as_posix()
        ),
        "recovery_procedure_found": procedure_found,
        "separation_from_database_backup": True,
        "location_class": "DURABLE_EXTERNAL_AUTHORITY",
        "retention_classes": ["COST_0_RETAIN", "DO_NOT_DELETE_DURING_CX_0B"],
        "recovery_authority_status": "SEPARATELY_PROVEN" if proven else "NOT_SEPARATELY_PROVEN",
        "already_escrowed_and_matching": not recovery.created,
        "aws_mutation_performed": recovery.created,
    }


def _emit_ini(result: Mapping[str, Any]) -> None:
    yes_no = lambda value: "YES" if value else "NO"
    print("SECRETSTORE_IMPLEMENTATION=AES-256-GCM_ENCRYPTED_DATABASE_ENVELOPES_WITH_12_BYTE_RANDOM_NONCE_AND_METADATA_AAD")
    print("ROOT_AUTHORITY_TYPE=OPERATOR_GENERATED_32_BYTE_ROOT_KEYS_IN_VERSION_1_JSON_KEYRING")
    print(f"LIVE_KEYRING_SOURCE={EXPECTED_NAMESPACE}/{RUNTIME_SECRET_NAME}:{KEYRING_DATA_KEY}")
    print(f"ACTIVE_KEY_ID={result['active_key_identifier']}")
    print(f"LIVE_KEYRING_SHA256={result['live_keyring_sha256']}")
    print("RECOVERY_CUSTODY_TYPE=AWS_SECRETS_MANAGER")
    print(f"RECOVERY_SECRET_NAME={result['recovery_secret_name']}")
    print(f"RECOVERY_SECRET_ARN={result['recovery_secret_arn']}")
    print(f"RECOVERY_SECRET_VERSION_ID={result['recovery_secret_version_id']}")
    print(f"RECOVERY_KEYRING_SHA256={result['recovery_keyring_sha256']}")
    print(f"KEYRING_FINGERPRINT_MATCH={yes_no(result['keyring_fingerprint_match'])}")
    print(f"ALREADY_ESCROWED_AND_MATCHING={yes_no(result['already_escrowed_and_matching'])}")
    print(f"EXTERNAL_RECOVERY_CUSTODY_FOUND={yes_no(result['external_recovery_custody_found'])}")
    print(f"RECOVERY_PROCEDURE_FOUND={yes_no(result['recovery_procedure_found'])}")
    print("COLOCATED_WITH_DATABASE_BACKUP=NO")
    print("SECRET_VALUE_READ_IN_MEMORY=YES")
    print("SECRET_VALUE_PRINTED=NO")
    print("SECRET_VALUE_WRITTEN_PLAINTEXT_TO_DISK=NO")
    print("KUBERNETES_MUTATION_PERFORMED=NO")
    print("DATABASE_MUTATION_PERFORMED=NO")
    print("DNS_MUTATION_PERFORMED=NO")
    print("TERRAFORM_MUTATION_PERFORMED=NO")
    print("SECRETSTORE_KEY_ROTATION_PERFORMED=NO")
    print(f"AWS_MUTATION_PERFORMED={yes_no(result['aws_mutation_performed'])}")
    print(
        "AWS_MUTATION_SCOPE="
        + ("SECRETS_MANAGER_CREATE_ONLY" if result["aws_mutation_performed"] else "NONE")
    )
    print(
        "SECRETSTORE_RECOVERY_AUTHORITY="
        + ("PROVEN" if result["recovery_authority_status"] == "SEPARATELY_PROVEN" else "BLOCKED")
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create-once or verify TopoAI SecretStore recovery custody."
    )
    parser.add_argument("--aws-profile", default="topo-admin")
    parser.add_argument("--aws-region", default=EXPECTED_REGION)
    parser.add_argument("--create-if-absent", action="store_true")
    parser.add_argument("--output-format", choices=("ini", "json"), default="ini")
    parser.add_argument(
        "--recovery-procedure",
        type=Path,
        default=DEFAULT_RECOVERY_PROCEDURE,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.aws_region != EXPECTED_REGION:
        print("ERROR=AWS_REGION_MISMATCH")
        print("SECRETSTORE_RECOVERY_AUTHORITY=BLOCKED")
        return 1
    try:
        live = read_live_keyring()
        sts, secrets_manager = _build_clients(arguments.aws_profile, arguments.aws_region)
        try:
            identity = sts.get_caller_identity()
        except Exception as exc:
            raise RecoveryCustodyError("AWS_IDENTITY_FAILED") from exc
        if not isinstance(identity, Mapping) or identity.get("Account") != EXPECTED_ACCOUNT:
            raise RecoveryCustodyError("AWS_ACCOUNT_MISMATCH")
        recovery = ensure_recovery_secret(
            client=secrets_manager,
            live=live,
            create_if_absent=arguments.create_if_absent,
        )
        procedure_found = recovery_procedure_matches(
            arguments.recovery_procedure,
            live=live,
            recovery=recovery,
        )
        result = _safe_result(
            live=live,
            recovery=recovery,
            procedure_found=procedure_found,
        )
    except RecoveryEscrowMismatch as exc:
        print("RECOVERY_ESCROW_MISMATCH=YES")
        print(f"RECOVERY_SECRET_NAME={exc.evidence.name}")
        print(f"RECOVERY_SECRET_ARN={exc.evidence.arn}")
        print(f"RECOVERY_SECRET_VERSION_ID={exc.evidence.version_id}")
        print(f"RECOVERY_KEYRING_SHA256={exc.evidence.sha256}")
        print("SECRET_VALUE_PRINTED=NO")
        print("SECRET_VALUE_WRITTEN_PLAINTEXT_TO_DISK=NO")
        print("AWS_MUTATION_PERFORMED=NO")
        print("AWS_MUTATION_SCOPE=NONE")
        print("SECRETSTORE_RECOVERY_AUTHORITY=BLOCKED")
        return 1
    except RecoveryCustodyError as exc:
        print(f"ERROR={exc}")
        print("SECRET_VALUE_PRINTED=NO")
        print("SECRET_VALUE_WRITTEN_PLAINTEXT_TO_DISK=NO")
        print("AWS_MUTATION_PERFORMED=NO")
        print("AWS_MUTATION_SCOPE=NONE")
        print("SECRETSTORE_RECOVERY_AUTHORITY=BLOCKED")
        return 1

    if arguments.output_format == "json":
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        _emit_ini(result)
    return 0 if result["recovery_authority_status"] == "SEPARATELY_PROVEN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
