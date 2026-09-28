from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PROBE = ROOT / "scripts/cloud/cx0/prove_database_migration_head.ps1"
INVENTORY = ROOT / "scripts/cloud/cx0/capture_reproducibility_inventory.ps1"
COMPARATOR = ROOT / "scripts/cloud/cx0/compare_source_live_reproducibility.ps1"
SCHEMA = ROOT / "scripts/cloud/cx0/reproducibility_inventory.schema.json"
RECREATION = ROOT / "docs/operations/cx-0-recreation-authority.md"
TEARDOWN = ROOT / "docs/operations/cx-0-teardown-plan.md"
ARCHITECTURE = ROOT / "docs/architecture/cx-0-cost-0-reproducibility-freeze-v1.md"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def resolve_status(source_heads: list[str], live_heads: list[str], completed: bool) -> dict:
    def array(values: list[str]) -> str:
        quoted = ",".join("'" + value.replace("'", "''") + "'" for value in values)
        return f"@({quoted})"

    command = (
        f". '{PROBE.as_posix()}' -ContractOnly; "
        "$result = Resolve-DatabaseMigrationHeadStatus "
        f"-SourceHeads {array(source_heads)} -LiveHeads {array(live_heads)} "
        f"-ProbeCompleted ${str(completed).lower()}; "
        "$result | ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return json.loads(result.stdout)


class Cx0DatabaseMigrationHeadTests(unittest.TestCase):
    def test_exact_source_and_live_head_match(self) -> None:
        result = resolve_status(["0015_security_audit"], ["0015_security_audit"], True)
        self.assertEqual(result["status"], "MATCH")
        self.assertTrue(result["match"])
        self.assertEqual(result["source_count"], 1)
        self.assertEqual(result["live_count"], 1)

    def test_differing_head_is_not_match(self) -> None:
        result = resolve_status(["0015_security_audit"], ["0014_minimum_authority_bundles"], True)
        self.assertEqual(result["status"], "DIFFERENT")
        self.assertFalse(result["match"])

    def test_missing_live_head_is_unknown_required(self) -> None:
        result = resolve_status(["0015_security_audit"], [], False)
        self.assertEqual(result["status"], "UNKNOWN_REQUIRED")
        self.assertFalse(result["match"])

    def test_multiple_source_heads_are_rejected(self) -> None:
        result = resolve_status(["head-a", "head-b"], ["head-a"], True)
        self.assertEqual(result["status"], "SOURCE_HEADS_NOT_UNIQUE")
        self.assertFalse(result["match"])

    def test_multiple_live_heads_are_rejected(self) -> None:
        result = resolve_status(["head-a"], ["head-a", "head-b"], True)
        self.assertEqual(result["status"], "LIVE_HEADS_NOT_UNIQUE")
        self.assertFalse(result["match"])

    def test_backend_selector_is_derived_from_deployment(self) -> None:
        source = text(PROBE)
        self.assertIn('"get", "deployment", $Deployment', source)
        self.assertIn('"spec") "selector") "matchLabels"', source)
        self.assertIn('"--selector", $selector', source)
        self.assertIn('selector_source = "Deployment.spec.selector.matchLabels"', source)
        self.assertNotIn("app=topo-backend", source)

    def test_probe_uses_only_credential_name_and_never_emits_value(self) -> None:
        source = text(PROBE)
        self.assertIn('os.environ["TOPO_DATABASE_URL"]', source)
        self.assertIn('"credential_environment_variable": "TOPO_DATABASE_URL"', source)
        self.assertNotRegex(source, r"print\([^\n]*os\.environ")
        self.assertNotRegex(source, r"Write-(?:Host|Output)[^\n]*(?:database-url|TOPO_DATABASE_URL).*Value")
        self.assertIn("database_secret_printed = $false", source)
        self.assertIn("database_secret_written_to_disk = $false", source)

    def test_database_program_is_read_only_and_rolls_back(self) -> None:
        source = text(PROBE)
        match = re.search(r"\$databaseProbe\s*=\s*@'(.*?)'@", source, re.DOTALL)
        self.assertIsNotNone(match)
        program = match.group(1)
        self.assertIn('cursor.execute("BEGIN READ ONLY")', program)
        self.assertIn(
            'cursor.execute("SELECT version_num FROM alembic_version ORDER BY version_num")',
            program,
        )
        self.assertIn("connection.rollback()", program)
        self.assertIn('"transaction_completion": "ROLLBACK"', program)
        self.assertNotRegex(
            program,
            r"(?i)\b(?:ALTER|INSERT|UPDATE|DELETE|TRUNCATE|CREATE|DROP|GRANT|REVOKE)\b",
        )
        self.assertNotRegex(source, r"(?i)alembic\s+(?:upgrade|downgrade|stamp)")

    def test_inventory_and_comparator_fail_closed(self) -> None:
        inventory = text(INVENTORY)
        comparator = text(COMPARATOR)
        for field in (
            "source_database_migration_head",
            "live_database_migration_head",
            "database_migration_head_status",
            "database_migration_head_probe_mode",
            "database_migration_head_probe_completed",
        ):
            self.assertIn(field, inventory)
            self.assertIn(field, text(SCHEMA))
        for status in (
            "MATCH",
            "DIFFERENT",
            "UNKNOWN_REQUIRED",
            "SOURCE_HEADS_NOT_UNIQUE",
            "LIVE_HEADS_NOT_UNIQUE",
        ):
            self.assertIn(status, inventory + comparator)
        self.assertIn('$migrationStatus -eq "UNKNOWN_REQUIRED"', comparator)
        self.assertIn('"LIVE_ONLY_REQUIRED"', comparator)

    def test_docs_preserve_schema_authority_without_teardown_authority(self) -> None:
        combined = "\n".join(text(path) for path in (RECREATION, TEARDOWN, ARCHITECTURE))
        self.assertIn("DATABASE_SCHEMA_AUTHORITY=0015_security_audit", combined)
        self.assertIn("DATABASE_MIGRATION_HEAD=MATCH", combined)
        self.assertIn("TEARDOWN_AUTHORIZED=NO", text(TEARDOWN))
        self.assertIn("does not authorize teardown", text(RECREATION))


if __name__ == "__main__":
    unittest.main()
