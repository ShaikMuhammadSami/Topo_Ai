from __future__ import annotations

import importlib.util
import hashlib
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from botocore.exceptions import ClientError


ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAP = ROOT / "scripts/cloud/cx0/bootstrap_terraform_state_backend.py"
MIGRATION = ROOT / "scripts/cloud/cx0/migrate_golden_terraform_state.ps1"
LOCAL_STATE_INSPECTOR = ROOT / "scripts/cloud/cx0/inspect_local_terraform_state.py"
VERSIONS = ROOT / "infrastructure/aws/golden/versions.tf"
INVENTORY = ROOT / "scripts/cloud/cx0/capture_reproducibility_inventory.ps1"
COMPARATOR = ROOT / "scripts/cloud/cx0/compare_source_live_reproducibility.ps1"
RECREATION = ROOT / "docs/operations/cx-0-recreation-authority.md"
TEARDOWN = ROOT / "docs/operations/cx-0-teardown-plan.md"

BUCKET = "topo-tfstate-297361542190-us-east-1"
KEY = "golden/terraform.tfstate"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


SPEC = importlib.util.spec_from_file_location("cx0_terraform_backend", BOOTSTRAP)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load Terraform backend bootstrap utility")
BACKEND = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BACKEND
SPEC.loader.exec_module(BACKEND)

INSPECTOR_SPEC = importlib.util.spec_from_file_location("cx0_local_state_inspector", LOCAL_STATE_INSPECTOR)
if INSPECTOR_SPEC is None or INSPECTOR_SPEC.loader is None:
    raise RuntimeError("Unable to load bounded local-state inspector")
INSPECTOR = importlib.util.module_from_spec(INSPECTOR_SPEC)
sys.modules[INSPECTOR_SPEC.name] = INSPECTOR
INSPECTOR_SPEC.loader.exec_module(INSPECTOR)


def client_error(code: str, operation: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "bounded test error"}}, operation)


def backend_object_result(contents_expression: str) -> dict[str, object]:
    source = text(MIGRATION)
    match = re.search(
        r"function Get-BackendObjects \{.*?\n\}\n\nfunction Invoke-Precheck",
        source,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError("Get-BackendObjects function was not found")
    function_source = match.group(0).rsplit("\n\nfunction Invoke-Precheck", 1)[0]
    script = f"""
Set-StrictMode -Version Latest
$BackendBucket = "{BUCKET}"
$BackendKey = "{KEY}"
$LockKey = "$BackendKey.tflock"
$ExpectedAccount = "297361542190"
$script:MockResponse = {contents_expression}
function Invoke-AwsJson {{
    param($Service, $Operation, $Arguments)
    return $script:MockResponse
}}
{function_source}
$objects = @(Get-BackendObjects)
$stateExists = @($objects | Where-Object {{ $_.Key -eq $BackendKey }}).Count -gt 0
$lockExists = @($objects | Where-Object {{ $_.Key -eq $LockKey }}).Count -gt 0
[pscustomobject]@{{
    object_count = $objects.Count
    state_object_exists = $stateExists
    lock_object_exists = $lockExists
    precheck_can_continue = -not $lockExists -and -not $stateExists
}} | ConvertTo-Json -Compress
"""
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-NonInteractive", "-Command", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return json.loads(result.stdout)


class ExactBucket:
    def __init__(self, *, configured: bool = True) -> None:
        self.configured = configured
        self.mutations: list[str] = []

    def head_bucket(self, **kwargs):
        return {}

    def get_bucket_location(self, **kwargs):
        return {"LocationConstraint": None}

    def get_bucket_versioning(self, **kwargs):
        return {"Status": "Enabled" if self.configured else "Suspended"}

    def get_public_access_block(self, **kwargs):
        return {"PublicAccessBlockConfiguration": dict(BACKEND.PUBLIC_ACCESS_BLOCK)}

    def get_bucket_ownership_controls(self, **kwargs):
        return {"OwnershipControls": {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]}}

    def get_bucket_encryption(self, **kwargs):
        return {
            "ServerSideEncryptionConfiguration": {
                "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
            }
        }

    def get_bucket_policy(self, **kwargs):
        return {"Policy": BACKEND._non_tls_policy()}

    def get_bucket_lifecycle_configuration(self, **kwargs):
        raise client_error("NoSuchLifecycleConfiguration", "GetBucketLifecycleConfiguration")

    def get_bucket_tagging(self, **kwargs):
        return {
            "TagSet": [
                {"Key": key, "Value": value}
                for key, value in BACKEND.REQUIRED_TAGS.items()
            ]
        }

    def head_object(self, **kwargs):
        raise client_error("404", "HeadObject")

    def __getattr__(self, name: str):
        if name.startswith("put_") or name == "create_bucket":
            def mutate(**kwargs):
                self.mutations.append(name)
            return mutate
        raise AttributeError(name)


class TerraformBackendMigrationContractTests(unittest.TestCase):
    def test_backend_source_is_exact_and_uses_native_s3_locking(self) -> None:
        source = text(VERSIONS)
        self.assertRegex(source, r'required_version\s*=\s*">= 1\.10, < 2\.0"')
        self.assertIn('backend "s3"', source)
        self.assertIn(f'bucket       = "{BUCKET}"', source)
        self.assertIn(f'key          = "{KEY}"', source)
        self.assertIn('region       = "us-east-1"', source)
        self.assertIn("encrypt      = true", source)
        self.assertIn("use_lockfile = true", source)
        self.assertNotIn("dynamodb_table", source)
        self.assertNotRegex(source, r"(?m)^\s*(?:profile|access_key|secret_key)\s*=")

    def test_bootstrap_defaults_to_read_only_precheck_and_exact_identity(self) -> None:
        args = BACKEND.parse_args([])
        self.assertEqual("PRECHECK", args.mode)
        self.assertEqual(BUCKET, BACKEND.BACKEND_BUCKET)
        self.assertEqual(KEY, BACKEND.BACKEND_KEY)
        self.assertEqual("us-east-1", BACKEND.EXPECTED_REGION)
        self.assertEqual("297361542190", BACKEND.EXPECTED_ACCOUNT)

    def test_exact_existing_bucket_is_idempotent(self) -> None:
        s3 = ExactBucket()
        result = BACKEND.create_once(s3)
        self.assertTrue(result.configuration_matches)
        self.assertEqual([], s3.mutations)

    def test_existing_mismatched_bucket_fails_closed_without_repair(self) -> None:
        s3 = ExactBucket(configured=False)
        with self.assertRaises(BACKEND.ContractError):
            BACKEND.create_once(s3)
        self.assertEqual([], s3.mutations)

    def test_bucket_contract_requires_retention_and_all_security_controls(self) -> None:
        source = text(BOOTSTRAP)
        for marker in (
            '"Status": "Enabled"',
            '"SSEAlgorithm": "AES256"',
            'ObjectOwnership="BucketOwnerEnforced"',
            '"BlockPublicAcls": True',
            '"IgnorePublicAcls": True',
            '"BlockPublicPolicy": True',
            '"RestrictPublicBuckets": True',
            '"aws:SecureTransport": "false"',
            '"authority": "DURABLE_EXTERNAL_AUTHORITY"',
            '"cost0-retain": "true"',
            '"cx0b-delete": "forbidden"',
        ):
            self.assertIn(marker, source)
        self.assertNotIn("put_bucket_lifecycle", source)
        self.assertNotIn("delete_bucket", source)
        self.assertNotIn("put_object", source)

    def test_migration_is_default_precheck_and_execute_is_doubly_guarded(self) -> None:
        source = text(MIGRATION)
        self.assertIn('[string]$Mode = "PRECHECK"', source)
        self.assertIn("[switch]$ExecuteMigration", source)
        self.assertIn('"MIGRATE_GOLDEN_STATE_TO_S3"', source)
        self.assertIn("if (-not $ExecuteMigration -or $Confirmation -ne $RequiredConfirmation)", source)
        self.assertIn('init -migrate-state', source)
        self.assertIn("Preserve operator control", source)

    def test_precheck_is_independent_of_initialized_backend(self) -> None:
        source = text(MIGRATION)
        match = re.search(
            r"function Invoke-Precheck \{(.*?)\n\}\n\nfunction Invoke-PostMigrationVerification",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        precheck = match.group(1)
        self.assertNotIn('"workspace", "show"', precheck)
        self.assertNotIn('"state", "list"', precheck)
        self.assertNotRegex(precheck, r'&\s*terraform[^\n]*\binit\b')
        self.assertIn("inspect_local_terraform_state.py", source)

        postcheck = source[match.end():]
        self.assertIn('"workspace", "show"', postcheck)
        self.assertIn('"state", "list"', postcheck)

    def test_empty_s3_response_is_a_valid_zero_object_precheck(self) -> None:
        result = backend_object_result("[pscustomobject]@{}")
        self.assertEqual(0, result["object_count"])
        self.assertFalse(result["state_object_exists"])
        self.assertFalse(result["lock_object_exists"])
        self.assertTrue(result["precheck_can_continue"])

    def test_state_object_is_detected(self) -> None:
        result = backend_object_result(
            f'[pscustomobject]@{{ Contents = @([pscustomobject]@{{ Key = "{KEY}" }}) }}'
        )
        self.assertEqual(1, result["object_count"])
        self.assertTrue(result["state_object_exists"])
        self.assertFalse(result["lock_object_exists"])
        self.assertFalse(result["precheck_can_continue"])

    def test_lock_object_is_detected_as_blocking(self) -> None:
        result = backend_object_result(
            f'[pscustomobject]@{{ Contents = @([pscustomobject]@{{ Key = "{KEY}.tflock" }}) }}'
        )
        self.assertEqual(1, result["object_count"])
        self.assertFalse(result["state_object_exists"])
        self.assertTrue(result["lock_object_exists"])
        self.assertFalse(result["precheck_can_continue"])

    def test_real_local_state_emits_only_approved_metadata(self) -> None:
        result = INSPECTOR.inspect_accepted_state()
        self.assertEqual(80, result["resource_address_count"])
        self.assertTrue(result["all_representative_addresses_present"])
        self.assertFalse(result["raw_state_emitted"])
        self.assertFalse(result["resource_attributes_emitted"])
        self.assertFalse(result["outputs_emitted"])
        self.assertEqual(
            {
                "state_format_version",
                "terraform_version",
                "lineage",
                "serial",
                "resource_address_count",
                "representative_addresses_present",
                "all_representative_addresses_present",
                "local_state_sha256",
                "local_state_size_bytes",
                "state_payload_read_in_memory",
                "raw_state_emitted",
                "resource_attributes_emitted",
                "outputs_emitted",
            },
            set(result),
        )

    def test_inspector_does_not_project_arbitrary_state_fields(self) -> None:
        state = {
            "version": 4,
            "terraform_version": "1.16.2",
            "lineage": "12345678-1234-4234-8234-123456789abc",
            "serial": 7,
            "outputs": {"password": {"value": "must-not-escape"}},
            "resources": [
                {
                    "mode": "managed",
                    "type": address.split(".", 1)[0],
                    "name": address.split(".", 1)[1],
                    "provider": "must-not-escape",
                    "instances": [{"attributes": {"password": "must-not-escape"}}],
                }
                for address in INSPECTOR.REPRESENTATIVE_ADDRESSES
            ],
        }
        payload = json.dumps(state).encode("utf-8")
        result = INSPECTOR.inspect_state_bytes(payload, hashlib.sha256(payload).hexdigest())
        rendered = json.dumps(result, sort_keys=True)
        self.assertNotIn("must-not-escape", rendered)
        self.assertNotIn("password", rendered)
        self.assertNotIn("provider", rendered)
        self.assertEqual(5, result["resource_address_count"])
        self.assertTrue(result["all_representative_addresses_present"])

    def test_migration_has_no_forbidden_state_or_lock_bypass(self) -> None:
        source = text(MIGRATION)
        compact = source.lower()
        for forbidden in (
            "-force-copy",
            "-lock=false",
            '"state", "push"',
            '"state", "pull"',
            "put-object",
            '"apply"',
            '"destroy"',
        ):
            self.assertNotIn(forbidden, compact)
        self.assertNotIn('"dynamodb"', compact)
        self.assertNotRegex(source, r"Get-Content\s+[^\n]*\$LocalStatePath")
        self.assertNotRegex(source, r'(?i)(aws_access_key_id|aws_secret_access_key|AKIA[0-9A-Z]{16})')

    def test_precheck_and_postcheck_enforce_complete_identity(self) -> None:
        source = text(MIGRATION)
        for marker in (
            "297361542190",
            "us-east-1",
            "default",
            "1.10.0",
            "b3321648facd8506f322b7f91ad3ad04dd8b1a017ba89124c5f382e4abd48994",
            "$ExpectedResourceCount = 80",
            "backend state object already exists before first migration",
            "unexpected Terraform lock object exists",
            "NON_AUTHORITATIVE_LOCAL_RECOVERY_COPY",
            "state_object_version_id",
            "aws_vpc.golden",
            "aws_eks_cluster.golden",
            "aws_db_instance.postgres",
            "aws_lb.edge",
            "aws_ecr_repository.topo",
        ):
            self.assertIn(marker, source)

    def test_reconciliation_requires_every_remote_authority_gate(self) -> None:
        combined = text(INVENTORY) + "\n" + text(COMPARATOR)
        for marker in (
            "TERRAFORM_REMOTE_STATE_NOT_PROVEN",
            "backend_source_contract_matches",
            "backend_source_versioned",
            "bucket_configuration_matches",
            "state_object_exists",
            "state_object_version_id",
            "resource_address_count -eq 80",
            "use_lockfile",
            "NON_AUTHORITATIVE_LOCAL_RECOVERY_COPY",
        ):
            self.assertIn(marker, combined)

    def test_backend_is_explicitly_retained_outside_cx0b(self) -> None:
        combined = text(RECREATION) + "\n" + text(TEARDOWN)
        for marker in (
            BUCKET,
            KEY,
            "DURABLE_EXTERNAL_AUTHORITY",
            "COST_0_RETAIN",
            "DO_NOT_DELETE_DURING_CX_0B",
            "NON_AUTHORITATIVE_LOCAL_RECOVERY_COPY",
        ):
            self.assertIn(marker, combined)

    def test_powershell_migration_source_parses(self) -> None:
        command = (
            "$tokens=$null;$errors=$null;"
            "[void][System.Management.Automation.Language.Parser]::ParseFile("
            f"'{MIGRATION.as_posix()}',[ref]$tokens,[ref]$errors);"
            "if($errors.Count){$errors|% Message;exit 1}"
        )
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-NonInteractive", "-Command", command],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
