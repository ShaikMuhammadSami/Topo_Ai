from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCANNER_PATH = REPOSITORY_ROOT / "scripts" / "security" / "check_tracked_secrets.py"
SPEC = importlib.util.spec_from_file_location("check_tracked_secrets", SCANNER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load tracked-tree secret scanner.")
SCANNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SCANNER
SPEC.loader.exec_module(SCANNER)


class TrackedSecretScannerTests(unittest.TestCase):
    def test_rejects_synthetic_github_credential_without_rendering_value(self) -> None:
        candidate = "gh" + "p_" + ("A" * 36)

        findings = SCANNER.scan_text("synthetic.txt", f"TOKEN={candidate}\n")
        rendered = SCANNER.render_findings(findings)

        self.assertTrue(
            any(finding.category == "GitHub credential candidate" for finding in findings)
        )
        self.assertNotIn(candidate, rendered)
        self.assertIn("path=synthetic.txt", rendered)

    def test_rejects_synthetic_aws_access_key_id(self) -> None:
        candidate = "AK" + "IA" + ("A" * 16)

        findings = SCANNER.scan_text("synthetic.txt", f"AWS_ACCESS_KEY_ID={candidate}\n")

        self.assertTrue(
            any(finding.category == "AWS access-key ID candidate" for finding in findings)
        )

    def test_rejects_literal_provider_credential_assignment(self) -> None:
        name = "AZURE_CLIENT_" + "SECRET"
        candidate = "s" * 32

        findings = SCANNER.scan_text(
            "synthetic.env",
            name + "=" + candidate + "\n",
        )

        self.assertTrue(
            any(
                finding.category == "Literal provider credential assignment"
                for finding in findings
            )
        )

    def test_ignores_unquoted_runtime_reference_in_source_code(self) -> None:
        findings = SCANNER.scan_text(
            "configuration.py",
            "GITHUB_TOKEN = credentials.token\n",
        )

        self.assertEqual(findings, [])

    def test_rejects_quoted_provider_credential_in_source_code(self) -> None:
        name = "AZURE_CLIENT_" + "SECRET"
        candidate = "s" * 32

        findings = SCANNER.scan_text(
            "configuration.py",
            name + ' = "' + candidate + '"\n',
        )

        self.assertTrue(
            any(
                finding.category == "Literal provider credential assignment"
                for finding in findings
            )
        )

    def test_accepts_explicit_placeholders_and_runtime_references(self) -> None:
        values = (
            "",
            "example",
            "replace-me",
            "replace-with-github-token",
            "changeme",
            "redacted",
            "dummy",
            "test-only",
            "your-github-token",
            "<github-token>",
            "${GITHUB_TOKEN}",
            "${{ secrets.GITHUB_TOKEN }}",
        )
        text = "\n".join(f"TOPO_GITHUB_TOKEN={value}" for value in values)

        self.assertEqual(SCANNER.scan_text("placeholders.env", text), [])

    def test_skips_binary_content(self) -> None:
        candidate = "gh" + "p_" + ("A" * 36)

        self.assertEqual(
            SCANNER.scan_bytes("artifact.bin", b"\x00" + candidate.encode("ascii")),
            [],
        )

    def test_ignored_backend_env_is_not_a_tracked_scan_target(self) -> None:
        tracked = set(SCANNER.get_tracked_paths(REPOSITORY_ROOT))

        self.assertNotIn("backend/.env", tracked)


if __name__ == "__main__":
    unittest.main()
