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

    def test_rejects_current_outbound_and_client_credential_shapes_safely(self) -> None:
        candidates = {
            "OpenAI credential candidate": "s" + "k-" + ("A" * 28),
            "Groq credential candidate": "g" + "sk_" + ("B" * 28),
            "Topo credential candidate": "topo_" + "agent_" + ("C" * 28),
            "Literal basic credential": "Basic " + ("D" * 28),
            "Credential-bearing database URL": "postgresql://operator:" + ("E" * 28) + "@db.example/topo",
        }
        for category, candidate in candidates.items():
            with self.subTest(category=category):
                findings = SCANNER.scan_text("synthetic.txt", candidate)
                rendered = SCANNER.render_findings(findings)
                self.assertTrue(any(item.category == category for item in findings))
                self.assertNotIn(candidate, rendered)

    def test_detects_groq_assignment_but_accepts_placeholder(self) -> None:
        name = "GROQ_" + "API_KEY"
        findings = SCANNER.scan_text("synthetic.env", f"{name}={'x' * 32}\n")
        self.assertTrue(findings)
        self.assertEqual(SCANNER.scan_text("placeholder.env", f"{name}=replace-me\n"), [])

    def test_accepts_explicit_database_url_password_placeholders(self) -> None:
        for value in ("password", "<password>", "replace-me"):
            with self.subTest(value=value):
                candidate = "postgresql://" + f"topo:{value}@127.0.0.1:5432/topo"
                self.assertEqual(SCANNER.scan_text("example.md", candidate), [])

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

    def test_ph4e_hostile_positive_and_negative_corpus_never_prints_values(self) -> None:
        import secrets

        positive = {
            "OpenAI credential candidate": "s" + "k-" + secrets.token_hex(20),
            "Groq credential candidate": "g" + "sk_" + secrets.token_hex(20),
            "GitHub credential candidate": "gh" + "p_" + secrets.token_hex(20),
            "Topo credential candidate": "topo_" + "api_" + secrets.token_hex(20),
            "Literal basic credential": "Basic " + secrets.token_hex(20),
            "Credential-bearing database URL": (
                "postgresql://operator:" + secrets.token_hex(20) + "@db.example/topo"
            ),
        }
        for category, value in positive.items():
            with self.subTest(category=category):
                findings = SCANNER.scan_text("ph4e-hostile.txt", value)
                rendered = SCANNER.render_findings(findings)
                self.assertTrue(any(item.category == category for item in findings))
                self.assertNotIn(value, rendered)

        negative = "\n".join(
            (
                "OPENAI_API_KEY=${OPENAI_API_KEY}",
                "GROQ_API_KEY=<groq-api-key>",
                "TOPO_GITHUB_TOKEN=replace-me",
                "postgresql://topo:<password>@127.0.0.1:5432/topo",
                "token_count=42",
                "secret_ref=secret:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            )
        )
        self.assertEqual(SCANNER.scan_text("ph4e-placeholders.txt", negative), [])


if __name__ == "__main__":
    unittest.main()
