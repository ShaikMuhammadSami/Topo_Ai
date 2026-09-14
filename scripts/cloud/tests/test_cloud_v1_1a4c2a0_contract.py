from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[3]
GENERATOR_PATH = ROOT / "scripts/cloud/generate_runtime_secret_material.py"
DOCUMENT_PATH = (
    ROOT / "docs/architecture/cloud-v1-1a4c2a0-runtime-secret-material-v1.md"
)
GENERATED_FILENAMES = {
    "bootstrap-token.txt",
    "bootstrap-token-hashes.json",
    "secret-store-keyring.json",
    "secret-store-active-key-id.txt",
}


class CloudV1RuntimeSecretMaterialContractTests(unittest.TestCase):
    def test_generator_reuses_production_digest_and_validation_contracts(self) -> None:
        source = GENERATOR_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }

        self.assertTrue(
            {"token_digest", "load_token_registry", "load_keyring"}.issubset(imported)
        )
        self.assertTrue(
            {"token_digest", "load_token_registry", "load_keyring"}.issubset(calls)
        )

    def test_generator_has_no_cloud_kubernetes_or_database_secret_behavior(self) -> None:
        source = GENERATOR_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_roots = {
            node.module.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        } | {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }

        self.assertTrue(
            {"subprocess", "boto3", "kubernetes", "requests", "psycopg", "sqlalchemy"}
            .isdisjoint(imported_roots)
        )
        self.assertNotIn("kubectl", source.casefold())
        self.assertNotIn("terraform", source.casefold())
        self.assertNotIn("rds", source.casefold())
        self.assertNotIn("master-password", source.casefold())

    def test_generated_material_filenames_are_not_git_tracked(self) -> None:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--cached", "-z"],
            check=True,
            stdout=subprocess.PIPE,
        )
        tracked = {
            Path(item.decode("utf-8")).name
            for item in result.stdout.split(b"\0")
            if item
        }

        self.assertTrue(GENERATED_FILENAMES.isdisjoint(tracked))

    def test_documentation_preserves_initial_generation_boundary(self) -> None:
        document = " ".join(DOCUMENT_PATH.read_text(encoding="utf-8").split())
        for required in (
            "production validators are authoritative",
            "outside the Git worktree",
            "does not create a Kubernetes Secret",
            "initial generation",
            "does not grant PH-5 permissions",
            "Windows ACL",
            "C2-A1",
            "C2-B",
            "C2-C",
            "No live environment was changed",
        ):
            self.assertIn(required, document)


if __name__ == "__main__":
    unittest.main()
