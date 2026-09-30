from __future__ import annotations

import importlib.util
import base64
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


def accepted_migration_receipt() -> dict[str, object]:
    return {
        "schema_version": "cx0a.terraform-migration-receipt.v2",
        "backend_type": "s3",
        "backend_bucket": BUCKET,
        "backend_key": KEY,
        "backend_region": "us-east-1",
        "locking_model": "S3_NATIVE_USE_LOCKFILE",
        "remote_state_authority": "DURABLE_EXTERNAL_AUTHORITY",
        "workspace": "default",
        "resource_address_count": 80,
        "representative_addresses": [
            "aws_vpc.golden",
            "aws_eks_cluster.golden",
            "aws_db_instance.postgres",
            "aws_lb.edge",
            "aws_ecr_repository.topo",
        ],
        "state_object_version_id": "migration-version",
        "state_object_encryption": "AES256",
        "source_state_lineage": "13c78cf7-912f-cacc-74eb-15c7ee33112f",
        "source_state_serial": 97,
        "destination_state_lineage": "dc5223d7-8ffe-cacf-e04f-f1f42a8bc584",
        "destination_state_serial": 1,
        "state_payloads_stored": False,
        "secret_values_stored": False,
        "migration_semantic_equivalence": {
            "resources_match": True,
            "outputs_match": True,
            "non_check_state_match": True,
            "check_results_unordered_match": True,
            "check_results_count_source": 18,
            "check_results_count_destination": 18,
            "check_results_kinds_source": {"resource": 1, "var": 17},
            "check_results_kinds_destination": {"resource": 1, "var": 17},
            "check_results_statuses_source": {"pass": 18},
            "check_results_statuses_destination": {"pass": 18},
        },
    }


def receipt_contract_result(receipt: dict[str, object]) -> bool:
    source = text(INVENTORY)
    match = re.search(
        r"function Get-PropertyValue \{.*?\n\}\n\nfunction Test-TerraformMigrationReceiptContract \{.*?\n\}\n\nfunction Get-Sha256Text",
        source,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError("Terraform migration receipt validator was not found")
    function_source = match.group(0).rsplit("\n\nfunction Get-Sha256Text", 1)[0]
    encoded = base64.b64encode(json.dumps(receipt).encode("utf-8")).decode("ascii")
    script = f"""
Set-StrictMode -Version Latest
{function_source}
$json = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("{encoded}"))
$receipt = $json | ConvertFrom-Json -Depth 30
Test-TerraformMigrationReceiptContract $receipt | ConvertTo-Json -Compress
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
    return bool(json.loads(result.stdout))


class ExactBucket:
    def __init__(
        self,
        *,
        configured: bool = True,
        state_exists: bool = False,
        current_version: str | None = "current-version",
        migration_version: str = "migration-version",
        retain_migration: bool = True,
        current_latest: bool = True,
        lock_exists: bool = False,
    ) -> None:
        self.configured = configured
        self.state_exists = state_exists
        self.current_version = current_version
        self.migration_version = migration_version
        self.retain_migration = retain_migration
        self.current_latest = current_latest
        self.lock_exists = lock_exists
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
        if kwargs["Key"] == BACKEND.LOCK_KEY:
            if self.lock_exists:
                return {"VersionId": "lock-version", "ContentLength": 1}
            raise client_error("404", "HeadObject")
        if not self.state_exists:
            raise client_error("404", "HeadObject")
        return {
            "VersionId": self.current_version,
            "ETag": '"safe-etag"',
            "ContentLength": 10,
        }

    def list_object_versions(self, **kwargs):
        versions = []
        if self.state_exists and self.current_version is not None:
            versions.append(
                {
                    "Key": KEY,
                    "VersionId": self.current_version,
                    "IsLatest": self.current_latest,
                }
            )
        if (
            self.state_exists
            and self.retain_migration
            and self.migration_version != self.current_version
        ):
            versions.append(
                {
                    "Key": KEY,
                    "VersionId": self.migration_version,
                    "IsLatest": not self.current_latest,
                }
            )
        return {"Versions": versions, "IsTruncated": False}

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

    def test_migration_version_equal_to_current_passes_history_contract(self) -> None:
        s3 = ExactBucket(
            state_exists=True,
            current_version="migration-version",
            migration_version="migration-version",
        )
        result = BACKEND.inspect_bucket(s3, "migration-version")
        self.assertTrue(result.migration_version_retained)
        self.assertTrue(result.current_state_version_is_latest)
        self.assertTrue(result.current_equals_migration_version)

    def test_new_current_version_passes_when_migration_anchor_is_retained(self) -> None:
        result = BACKEND.inspect_bucket(
            ExactBucket(state_exists=True),
            "migration-version",
        )
        self.assertTrue(result.migration_version_retained)
        self.assertTrue(result.current_state_version_is_latest)
        self.assertFalse(result.current_equals_migration_version)

    def test_missing_migration_version_fails_history_contract(self) -> None:
        result = BACKEND.inspect_bucket(
            ExactBucket(state_exists=True, retain_migration=False),
            "migration-version",
        )
        self.assertFalse(result.migration_version_retained)

    def test_empty_current_version_and_non_latest_head_fail_closed(self) -> None:
        empty = BACKEND.inspect_bucket(
            ExactBucket(state_exists=True, current_version=None),
            "migration-version",
        )
        stale = BACKEND.inspect_bucket(
            ExactBucket(state_exists=True, current_latest=False),
            "migration-version",
        )
        self.assertIsNone(empty.state_object_version_id)
        self.assertFalse(empty.current_state_version_is_latest)
        self.assertFalse(stale.current_state_version_is_latest)

    def test_versioning_disabled_and_unexpected_lock_fail_remote_contract(self) -> None:
        suspended = BACKEND.inspect_bucket(
            ExactBucket(configured=False, state_exists=True),
            "migration-version",
        )
        locked = BACKEND.inspect_bucket(
            ExactBucket(state_exists=True, lock_exists=True),
            "migration-version",
        )
        self.assertFalse(suspended.versioning_enabled)
        self.assertFalse(suspended.configuration_matches)
        self.assertTrue(locked.lock_object_exists)

    def test_wrong_receipt_bucket_key_or_region_is_rejected(self) -> None:
        for field, value in (
            ("backend_bucket", "wrong-bucket"),
            ("backend_key", "wrong.tfstate"),
            ("backend_region", "us-west-2"),
        ):
            receipt = accepted_migration_receipt()
            receipt[field] = value
            self.assertFalse(receipt_contract_result(receipt), field)

    def test_post_apply_plan_drift_is_a_remote_authority_failure(self) -> None:
        source = text(INVENTORY)
        remote_gate = re.search(
            r"\$remoteStateProven\s*=\s*\((.*?)\n\)",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(remote_gate)
        gate = remote_gate.group(1)
        self.assertIn("$terraformPostApplyPlanExitCode -eq 0", gate)
        self.assertIn('$terraformPostApplyDrift -eq "NONE"', gate)
        self.assertIn('"-detailed-exitcode"', source)
        self.assertIn('"TERRAFORM_POST_APPLY_DRIFT_DETECTED"', source)

    def test_inventory_never_mutates_historical_migration_receipt(self) -> None:
        source = text(INVENTORY)
        self.assertNotRegex(source, r"Set-Content[^\n]*TerraformMigrationReceipt")
        self.assertNotRegex(source, r"Out-File[^\n]*TerraformMigrationReceipt")

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
            r"function Invoke-Precheck \{(.*?)\n\}\n\nfunction Get-RemoteStateMetadata",
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

    def test_lineage_change_and_destination_serial_restart_are_accepted(self) -> None:
        receipt = accepted_migration_receipt()
        self.assertNotEqual(receipt["source_state_lineage"], receipt["destination_state_lineage"])
        self.assertEqual(97, receipt["source_state_serial"])
        self.assertEqual(1, receipt["destination_state_serial"])
        self.assertTrue(receipt_contract_result(receipt))

    def test_resource_output_and_non_check_equivalence_are_mandatory(self) -> None:
        for field in ("resources_match", "outputs_match", "non_check_state_match"):
            receipt = accepted_migration_receipt()
            receipt["migration_semantic_equivalence"][field] = False
            self.assertFalse(receipt_contract_result(receipt), field)

    def test_check_result_order_only_difference_is_accepted(self) -> None:
        receipt = accepted_migration_receipt()
        equivalence = receipt["migration_semantic_equivalence"]
        self.assertTrue(equivalence["check_results_unordered_match"])
        self.assertTrue(receipt_contract_result(receipt))

    def test_different_check_result_contents_are_rejected(self) -> None:
        variants = []
        unordered = accepted_migration_receipt()
        unordered["migration_semantic_equivalence"]["check_results_unordered_match"] = False
        variants.append(unordered)
        count = accepted_migration_receipt()
        count["migration_semantic_equivalence"]["check_results_count_destination"] = 17
        variants.append(count)
        kinds = accepted_migration_receipt()
        kinds["migration_semantic_equivalence"]["check_results_kinds_destination"]["var"] = 16
        variants.append(kinds)
        statuses = accepted_migration_receipt()
        statuses["migration_semantic_equivalence"]["check_results_statuses_destination"]["pass"] = 17
        variants.append(statuses)
        for receipt in variants:
            self.assertFalse(receipt_contract_result(receipt))

    def test_reconcile_mode_cannot_rerun_state_migration(self) -> None:
        source = text(MIGRATION)
        match = re.search(
            r'if \(\$Mode -eq "RECONCILE"\) \{(.*?)\n\}\n\nif \(-not \$ExecuteMigration',
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        reconcile = match.group(1)
        self.assertNotIn("-migrate-state", reconcile)
        self.assertNotRegex(reconcile, r'&\s*terraform[^\n]*\binit\b')
        self.assertIn("Get-RemoteStateMetadata", reconcile)
        self.assertIn("New-AcceptedMigrationReceipt", reconcile)

    def test_empty_post_migration_local_primary_is_non_authoritative(self) -> None:
        payload = b""
        self.assertEqual(b"", payload)
        self.assertEqual(
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            hashlib.sha256(payload).hexdigest(),
        )
        combined = text(MIGRATION) + "\n" + text(INVENTORY) + "\n" + text(COMPARATOR)
        self.assertIn("NON_AUTHORITATIVE_EMPTY_PRIMARY", combined)
        self.assertIn('$localPrimarySize -eq 0', text(INVENTORY))
        self.assertIn("NON_AUTHORITATIVE_LOCAL_RECOVERY_ARTIFACT", combined)
        self.assertIn("remote_state_authority_class", combined)
        self.assertNotIn("local_state_original_sha256", text(INVENTORY) + "\n" + text(COMPARATOR))

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
            "NON_AUTHORITATIVE_EMPTY_PRIMARY",
            "NON_AUTHORITATIVE_LOCAL_RECOVERY_ARTIFACT",
            "DURABLE_EXTERNAL_AUTHORITY",
            "source_state_lineage",
            "destination_state_lineage",
            "migration_semantic_equivalence",
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
            "migration_state_version_id",
            "current_state_version_id",
            "migration_version_retained",
            "current_state_is_latest",
            "current_remote_state_proven",
            "terraform_post_apply_plan_exit_code",
            "terraform_post_apply_drift",
            "resource_address_count -eq 80",
            "use_lockfile",
            "NON_AUTHORITATIVE_EMPTY_PRIMARY",
            "NON_AUTHORITATIVE_LOCAL_RECOVERY_ARTIFACT",
            "DURABLE_EXTERNAL_AUTHORITY",
            "resources_match",
            "outputs_match",
            "non_check_state_match",
            "check_results_unordered_match",
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
            "NON_AUTHORITATIVE_EMPTY_PRIMARY",
            "NON_AUTHORITATIVE_LOCAL_RECOVERY_ARTIFACT",
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
