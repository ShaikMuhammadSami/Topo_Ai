from __future__ import annotations

import json
import importlib.util
import re
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ARCHITECTURE = ROOT / "docs/architecture/cx-0-cost-0-reproducibility-freeze-v1.md"
OPERATIONS = (
    ROOT / "docs/operations/cx-0-recreation-authority.md",
    ROOT / "docs/operations/cx-0-dns-transition-plan.md",
    ROOT / "docs/operations/cx-0-rds-recovery-proof-plan.md",
    ROOT / "docs/operations/cx-0-teardown-plan.md",
)
INVENTORY = ROOT / "scripts/cloud/cx0/capture_reproducibility_inventory.ps1"
COMPARATOR = ROOT / "scripts/cloud/cx0/compare_source_live_reproducibility.ps1"
IMAGE_AUTHORITY = ROOT / "scripts/cloud/cx0/cloud_v1_1b_image_authority.json"
OBSERVER_MANIFEST = ROOT / "infrastructure/kubernetes/golden/observer.yaml"
DATABASE_MIGRATION_PROBE = ROOT / "scripts/cloud/cx0/prove_database_migration_head.ps1"
SECRETSTORE_RECOVERY = ROOT / "scripts/cloud/cx0/escrow_secretstore_keyring.py"
TERRAFORM_BACKEND_BOOTSTRAP = ROOT / "scripts/cloud/cx0/bootstrap_terraform_state_backend.py"
TERRAFORM_STATE_MIGRATION = ROOT / "scripts/cloud/cx0/migrate_golden_terraform_state.ps1"
TERRAFORM_LOCAL_STATE_INSPECTOR = ROOT / "scripts/cloud/cx0/inspect_local_terraform_state.py"
SECRETSTORE_REQUIREMENTS = ROOT / "scripts/cloud/cx0/requirements.txt"
SCHEMA = ROOT / "scripts/cloud/cx0/reproducibility_inventory.schema.json"
GITIGNORE = ROOT / ".gitignore"
SECRET_SCANNER_PATH = ROOT / "scripts/security/check_tracked_secrets.py"

SECRET_SCANNER_SPEC = importlib.util.spec_from_file_location(
    "cx0_check_tracked_secrets",
    SECRET_SCANNER_PATH,
)
if SECRET_SCANNER_SPEC is None or SECRET_SCANNER_SPEC.loader is None:
    raise RuntimeError("Unable to load the repository secret scanner.")
SECRET_SCANNER = importlib.util.module_from_spec(SECRET_SCANNER_SPEC)
sys.modules[SECRET_SCANNER_SPEC.name] = SECRET_SCANNER
SECRET_SCANNER_SPEC.loader.exec_module(SECRET_SCANNER)

ACCEPTED_HEAD = "e676559b3daf586b4dc53041d1638a3d2191910a"
ACCEPTED_TREE = "c4389d7613afeb7f908e87ed5c4e6c04e599fc0c"
ACCEPTED_ORIGIN = '["https://app.topoai.io"]'
APPLICATION_HOST = "https://app.topoai.io"
IMAGE_REPOSITORY = "297361542190.dkr.ecr.us-east-1.amazonaws.com/topo-golden/topo"
BACKEND_DIGEST = "sha256:ef4731bc03aab04bdabd8b525a27f4c765c860e11a553aca66ac20650feeb56b"
BACKEND_PUBLICATION_SOURCE_COMMIT = "a6aee9725bea774336704faa9a77980b73bd05cb"
BACKEND_PUBLICATION_SOURCE_TREE = "8154b50bbfb8c46533acf368ba70e3329f497832"
BACKEND_REPAIR_COMMIT = "537692e7fe9e0b86e30de87ba43c8d4ca7d1c4c4"
FRONTEND_DIGEST = "sha256:ba86d89733b552cd3ced4792f40b59032524f83275b806ffc20f3249b8b1bdf1"
OBSERVER_DIGEST = "sha256:b482df847d453ac6128348a3fc5570210d20299a3421ebc6a3e9fb7ec05348b3"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class Cx0Cost0ContractTests(unittest.TestCase):
    def test_required_contract_surface_exists(self) -> None:
        for path in (
            ARCHITECTURE, INVENTORY, COMPARATOR, IMAGE_AUTHORITY,
            OBSERVER_MANIFEST, DATABASE_MIGRATION_PROBE, SECRETSTORE_RECOVERY,
            SECRETSTORE_REQUIREMENTS, TERRAFORM_BACKEND_BOOTSTRAP,
            TERRAFORM_STATE_MIGRATION, TERRAFORM_LOCAL_STATE_INSPECTOR, SCHEMA,
            *OPERATIONS,
        ):
            self.assertTrue(path.is_file(), path)

    def test_powershell_sources_parse(self) -> None:
        for path in (
            INVENTORY, COMPARATOR, DATABASE_MIGRATION_PROBE,
            TERRAFORM_STATE_MIGRATION,
        ):
            command = (
                "$tokens=$null;$errors=$null;"
                "[void][System.Management.Automation.Language.Parser]::ParseFile("
                f"'{path.as_posix()}',[ref]$tokens,[ref]$errors);"
                "if($errors.Count){$errors|% Message;exit 1}"
            )
            result = subprocess.run(
                ["pwsh", "-NoProfile", "-NonInteractive", "-Command", command],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_aws_executable_allowlist_is_read_only(self) -> None:
        source = text(INVENTORY)
        block = re.search(
            r"\$script:AwsReadOnlyOperations\s*=\s*@\((.*?)\n\)",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(block)
        operations = re.findall(r'^\s+"([a-z0-9-]+) ([a-z0-9-]+)"', block.group(1), re.MULTILINE)
        self.assertGreater(len(operations), 20)
        for service, operation in operations:
            self.assertRegex(operation, r"^(get|list|describe)-", (service, operation))

        # Every AWS execution is routed through the checked allowlist helper.
        self.assertEqual(source.count('FilePath "aws"'), 2)
        self.assertIn('if ($script:AwsReadOnlyOperations -notcontains $key)', source)
        self.assertNotRegex(
            source,
            r'"(?:delete|terminate|deregister|disassociate|release|remove|revoke|modify|update|put|create|restore|reboot|stop|start)-[a-z0-9-]+"',
        )

    def test_terraform_and_kubernetes_executable_paths_are_read_only(self) -> None:
        inventory = text(INVENTORY)
        comparator = text(COMPARATOR)
        combined = inventory + "\n" + comparator

        self.assertIn('"state", "list"', inventory)
        self.assertIn('"providers"', inventory)
        self.assertIn('"workspace", "show"', inventory)
        self.assertNotIn('"state", "pull"', combined)
        self.assertNotIn('"show", "-json"', combined)
        self.assertNotIn('"output", "-json"', combined)
        self.assertNotRegex(combined, r'"(?:apply|destroy|import)"')

        kubernetes_allowlist = re.search(
            r"\$script:KubernetesReadOnlyOperations\s*=\s*@\((.*?)\n\)",
            inventory,
            re.DOTALL,
        )
        self.assertIsNotNone(kubernetes_allowlist)
        allowed = set(re.findall(r'^\s+"([^"]+)"', kubernetes_allowlist.group(1), re.MULTILINE))
        self.assertEqual(
            allowed,
            {"config current-context", "config view", "get resources", "version client"},
        )
        for verb in (
            "apply", "create", "delete", "edit", "patch", "replace", "scale",
            "rollout", "set", "label", "annotate", "drain", "cordon", "uncordon",
        ):
            self.assertNotRegex(inventory, rf'@\("{verb}"(?:,|\))')

    def test_secret_and_configmap_projection_is_allowlisted(self) -> None:
        source = text(INVENTORY)
        self.assertIn("Get-SecretMetadataContracts", source)
        data_projection = re.search(
            r"\{\{range \$k,\$v := \.data\}\}(.*?)\{\{end\}\}",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(data_projection)
        self.assertIn('{{$k}}', data_projection.group(1))
        self.assertNotIn('{{$v}}', data_projection.group(1))
        self.assertNotIn('Invoke-KubectlGetJson "secrets"', source)
        self.assertNotIn("stringData", source)
        self.assertIn(
            '@("browser-allowed-origins-json", "cluster-name", "environment", "installation-id")',
            source,
        )
        self.assertIn("secret_values_emitted = $false", source)

    def test_output_is_ignored_and_bounded_to_artifacts_cx0(self) -> None:
        ignore = text(GITIGNORE)
        source = text(INVENTORY)
        comparator = text(COMPARATOR)
        self.assertIn("/artifacts/cx0/", ignore)
        self.assertIn('OutputDirectory = "artifacts/cx0"', source)
        self.assertIn('OutputDirectory = "artifacts/cx0"', comparator)
        self.assertIn('Join-Path $RepoRoot "artifacts/cx0"', source)
        self.assertIn('Join-Path $RepoRoot "artifacts/cx0"', comparator)

    def test_accepted_authority_and_browser_contract_are_recorded(self) -> None:
        combined = text(ARCHITECTURE) + "\n" + text(INVENTORY)
        self.assertIn(ACCEPTED_HEAD, combined)
        self.assertIn(ACCEPTED_TREE, combined)
        self.assertIn(ACCEPTED_ORIGIN, combined)
        self.assertIn(APPLICATION_HOST, combined)
        self.assertIn("accepted_predecessor_head", text(SCHEMA))
        self.assertIn("accepted_predecessor_tree", text(SCHEMA))

    def test_machine_readable_image_authority_uses_exact_digests_only(self) -> None:
        authority = json.loads(text(IMAGE_AUTHORITY))
        self.assertEqual(authority["schema_version"], "cx0.image-authority.v1")
        self.assertEqual(authority["aws_account_id"], "297361542190")
        self.assertEqual(authority["region"], "us-east-1")
        self.assertEqual(authority["repository"], "topo-golden/topo")
        self.assertEqual(authority["accepted_cloud_head"], ACCEPTED_HEAD)
        self.assertEqual(
            authority["images"],
            {
                "backend": {
                    "digest": BACKEND_DIGEST,
                    "publication_source_commit": BACKEND_PUBLICATION_SOURCE_COMMIT,
                    "publication_source_tree": BACKEND_PUBLICATION_SOURCE_TREE,
                    "repair_commit": BACKEND_REPAIR_COMMIT,
                },
                "frontend": {"digest": FRONTEND_DIGEST},
                "observer": {"digest": OBSERVER_DIGEST},
            },
        )
        serialized = json.dumps(authority).casefold()
        self.assertNotIn("latest", serialized)
        self.assertNotIn("image_tag", serialized)

    def test_observer_source_is_pinned_to_exact_authority_digest(self) -> None:
        manifest = text(OBSERVER_MANIFEST)
        expected = f"image: {IMAGE_REPOSITORY}@{OBSERVER_DIGEST}"
        self.assertIn(expected, manifest)
        self.assertNotIn("example.invalid", manifest)
        self.assertNotIn(":latest", manifest.casefold())

    def test_observer_reconciliation_requires_every_authority_gate(self) -> None:
        inventory = text(INVENTORY)
        comparator = text(COMPARATOR)
        for gate in (
            "$observerAuthorityMatches",
            "$observerLiveMatches",
            "$observerEcrMatches",
            "$observerSourcePinned",
            "$observerRetentionSafe",
            "$observerRetentionDocumented",
        ):
            self.assertIn(gate, comparator)
        self.assertIn("$observer.running_digest -eq $observerDigest", comparator)
        self.assertIn("$observer.ready -eq $true", comparator)
        self.assertIn("$observer.ecr_digest_exists -eq $true", comparator)
        self.assertIn("accepted_observer_digest_retention_safe", comparator)
        self.assertNotIn("Test-DigestInVersionedSource", comparator)
        self.assertIn('"ecr describe-repositories"', inventory)
        self.assertIn('"ecr get-lifecycle-policy"', inventory)
        self.assertIn("LifecyclePolicyNotFoundException", inventory)
        self.assertIn("$observerImageRetentionSafe = -not $lifecyclePolicyExists", inventory)

    def test_observer_retention_and_deletion_prohibition_are_documented(self) -> None:
        operations = "\n".join(text(path) for path in (OPERATIONS[0], OPERATIONS[3]))
        exact_ref = f"{IMAGE_REPOSITORY}@{OBSERVER_DIGEST}"
        self.assertIn(exact_ref, operations)
        for marker in (
            "DURABLE_IMMUTABLE_ARTIFACT_AUTHORITY",
            "COST_0_RETAIN",
            "DO_NOT_DELETE_DURING_CX_0B",
        ):
            self.assertIn(marker, text(OPERATIONS[0]))
            self.assertIn(marker, text(OPERATIONS[3]))
        self.assertIn("tags are discovery metadata only", text(OPERATIONS[0]))
        teardown = " ".join(text(OPERATIONS[3]).split())
        self.assertIn("outside CX-0B deletion authority", teardown)

    def test_image_schema_requires_observer_ecr_and_retention_evidence(self) -> None:
        schema = json.loads(text(SCHEMA))["properties"]["images"]
        self.assertTrue(
            {
                "authority",
                "accepted_observer",
                "observer",
                "running_pods",
                "ecr_images",
                "ecr_repository_contract",
            }.issubset(schema["required"])
        )
        observer_required = set(schema["properties"]["observer"]["required"])
        self.assertTrue(
            {"running_digest", "ready", "source_pinned", "ecr_digest_exists", "retention_safe"}.issubset(
                observer_required
            )
        )

    def test_acm_validation_record_is_durable_external_authority(self) -> None:
        combined = text(ARCHITECTURE) + "\n" + text(OPERATIONS[1]) + "\n" + text(INVENTORY)
        self.assertIn("DURABLE_EXTERNAL_AUTHORITY", combined)
        self.assertIn(
            "DO_NOT_REMOVE_DURING_COST_TEARDOWN_UNLESS_CERTIFICATE_STRATEGY_IS_INTENTIONALLY_ABANDONED",
            combined,
        )
        self.assertIn("_ae02df53f40f7c96b34bc6e98fb69e1d.app.topoai.io.", combined)
        self.assertIn("_fd79c652992203959600f955507f54f4.wzccmgtwzk.acm-validations.aws.", combined)

    def test_rds_restore_proof_precedes_any_original_deletion_authority(self) -> None:
        architecture = text(ARCHITECTURE)
        recovery = text(OPERATIONS[2])
        self.assertIn("A backup is not accepted until a restore is proven.", architecture)
        self.assertIn("RDS_RESTORE_PROVEN=NO", architecture)
        self.assertIn("ORIGINAL_RDS_DELETION_AUTHORIZED=NO", architecture)
        self.assertIn("RDS_RESTORE_PROVEN=NO", recovery)
        self.assertIn("original accepted RDS instance remained unchanged", recovery)

    def test_cx0b_is_separate_and_architect_gated(self) -> None:
        architecture = text(ARCHITECTURE)
        teardown = text(OPERATIONS[3])
        self.assertIn("Only a separately contracted CX-0B may perform teardown.", architecture)
        self.assertIn("An architect reviews the evidence.", architecture)
        self.assertIn("TEARDOWN_AUTHORIZED=NO", architecture)
        self.assertIn("TEARDOWN_AUTHORIZED=NO", teardown)

    def test_schema_requires_all_domains_and_false_safety_markers(self) -> None:
        schema = json.loads(text(SCHEMA))
        required = set(schema["required"])
        self.assertTrue(
            {
                "source", "eks", "kubernetes", "images", "network", "edge", "waf",
                "acm", "dns", "rds", "migrations", "secretstore_recovery",
                "terraform", "iam", "logging", "cost_relevant_resources",
                "reproducibility", "fingerprints", "safety",
            }.issubset(required)
        )
        for marker in (
            "aws_mutation_performed", "kubernetes_mutation_performed",
            "dns_mutation_performed", "database_mutation_performed",
            "deletion_performed", "secret_values_emitted",
        ):
            self.assertIs(schema["properties"]["safety"]["properties"][marker]["const"], False)

    def test_comparator_uses_exact_classification_and_fail_closed_counts(self) -> None:
        source = text(COMPARATOR)
        for classification in (
            "MATCH", "CODIFIED_DIFFERENTLY", "LIVE_ONLY_REQUIRED",
            "INTENTIONALLY_DISPOSABLE", "UNKNOWN",
        ):
            self.assertIn(classification, source)
        self.assertIn("live_only_required_count", source)
        self.assertIn("unknown_required_count", source)
        self.assertIn("TEARDOWN_AUTHORIZED=NO", source)
        self.assertNotIn("Invoke-AwsReadOnlyJson", source)
        self.assertNotIn("Invoke-KubectlReadOnlyText", source)
        self.assertNotIn("Resolve-DnsName", source)

    def test_terraform_remote_state_requires_complete_durable_authority(self) -> None:
        inventory = text(INVENTORY)
        comparator = text(COMPARATOR)
        self.assertIn('else { "local" }', inventory)
        self.assertIn('backend_location_class', inventory)
        self.assertIn('TERRAFORM_REMOTE_STATE_NOT_PROVEN', inventory)
        self.assertIn('$inventory.terraform.backend_type -eq "s3"', comparator)
        self.assertIn(
            "Durable S3 authority is not accepted until",
            comparator,
        )
        self.assertIn("NON_AUTHORITATIVE_EMPTY_PRIMARY", inventory + comparator)
        self.assertIn("NON_AUTHORITATIVE_LOCAL_RECOVERY_ARTIFACT", inventory + comparator)
        self.assertIn("DURABLE_EXTERNAL_AUTHORITY", inventory + comparator)

    def test_secretstore_recovery_requires_all_independent_authority_gates(self) -> None:
        inventory = text(INVENTORY)
        comparator = text(COMPARATOR)
        verifier = text(SECRETSTORE_RECOVERY)
        for marker in (
            "DURABLE_EXTERNAL_AUTHORITY",
            "external_recovery_custody_found",
            "keyring_fingerprint_match",
            "active_key_identifier_status",
            "recovery_secret_version_id",
            "recovery_procedure_found",
            "separation_from_database_backup",
        ):
            self.assertIn(marker, comparator + "\n" + verifier)
        self.assertIn('"--output-format", "json"', inventory)
        self.assertNotIn('"--create-if-absent"', inventory)
        self.assertIn('backend/.venv/Scripts/python.exe', inventory)
        self.assertIn("SecretBinary=live.keyring_bytes", verifier)
        self.assertNotIn("SecretString=", verifier)

        operations = "\n".join(text(path) for path in OPERATIONS)
        for marker in (
            "topo/golden/recovery/secret-store-keyring-v1",
            "DURABLE_EXTERNAL_AUTHORITY",
            "COST_0_RETAIN",
            "DO_NOT_DELETE_DURING_CX_0B",
            "KEYRING_SHA256=adb0bf496822d35043eeb7355a00f6819f095ca77179488d56f14c521ac058ff",
            "ACTIVE_KEY_ID=runtime-v1",
        ):
            self.assertIn(marker, operations)

    def test_first_gate_markers_do_not_claim_cost_closure(self) -> None:
        source = text(INVENTORY)
        for marker in (
            "CX_0A1_SOURCE_CONTRACT=PASS",
            "CX_0A1_STATIC_SAFETY=PASS",
            "CX_0A1_INVENTORY_SCHEMA=PASS",
            "CX_0A1_REPRODUCIBILITY_INVENTORY=PASS",
            "AWS_MUTATION_PERFORMED=NO",
            "KUBERNETES_MUTATION_PERFORMED=NO",
            "DNS_MUTATION_PERFORMED=NO",
            "DATABASE_MUTATION_PERFORMED=NO",
            "DELETION_PERFORMED=NO",
            "SECRET_VALUES_EMITTED=NO",
            "COST_0_A_REPRODUCIBILITY_INVENTORY_COMPLETE=PASS",
            "TEARDOWN_AUTHORIZED=NO",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("COST-0=CLOSED", source)
        self.assertNotIn("TEARDOWN_AUTHORIZED=YES", source)

    def test_new_cx0_sources_pass_repository_secret_patterns(self) -> None:
        paths = (
            ARCHITECTURE, *OPERATIONS, INVENTORY, COMPARATOR, IMAGE_AUTHORITY,
            OBSERVER_MANIFEST, DATABASE_MIGRATION_PROBE,
            SECRETSTORE_RECOVERY, SECRETSTORE_REQUIREMENTS,
            TERRAFORM_BACKEND_BOOTSTRAP, TERRAFORM_STATE_MIGRATION,
            TERRAFORM_LOCAL_STATE_INSPECTOR, SCHEMA,
        )
        findings = []
        for path in paths:
            findings.extend(
                SECRET_SCANNER.scan_bytes(
                    path.relative_to(ROOT).as_posix(),
                    path.read_bytes(),
                )
            )
        self.assertEqual([], findings, SECRET_SCANNER.render_findings(findings))


if __name__ == "__main__":
    unittest.main()
