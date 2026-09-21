from __future__ import annotations

import ast
import hashlib
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
MANIFEST_DIR = ROOT / "infrastructure/kubernetes/golden"
BOOTSTRAP_PATH = MANIFEST_DIR / "database-bootstrap-job.yaml"
MIGRATION_PATH = MANIFEST_DIR / "backend-migration-job.yaml"
BACKEND_PATH = MANIFEST_DIR / "backend.yaml"
ADMIN_PATH = ROOT / "scripts/cloud/topo_database_admin.py"
GENERATOR_PATH = ROOT / "scripts/cloud/generate_database_role_material.py"
DOCUMENT_PATH = ROOT / "docs/architecture/cloud-v1-1a4c2-database-bootstrap-v1.md"
MIGRATION_DIRECTORY = ROOT / "backend/alembic/versions"

BOOTSTRAP_SECRET_KEYS = {
    "database-host",
    "database-port",
    "database-name",
    "master-username",
    "master-password",
    "topo-app-password",
    "topo-migrator-password",
}
MIGRATION_BLOB_SHA256 = {
    "0001_current_schema_baseline.py": "b13506d8bd25c1018a3516395d2ed3b8994db76a70113be29fd2d656eb0f6efd",
    "0002_auth_sessions.py": "db13af3cce4d85afb210040b76d30f3231d3f02a175b00f34fef8df82c80ce92",
    "0003_auth_api_credentials.py": "907f0f815fc907786675f347226002568d9e04863c8d1f4ca225e1323fc7426f",
    "0004_tenant_foundation.py": "d2f1a673d51ba76883d5b81c62669a730b19fab9951188ca0c1903b0b55bccd3",
    "0005_domain_tenant_ownership.py": "14f7e50b3a82ffbd99fefb041d63d4710c0ed1e20d2442457a3922b0ba899333",
    "0006_domain_tenant_enforcement.py": "d17dd14445072e5b3c3bfa0822516f5232ed1bc9e1b8e280989910d26bbc3728",
    "0007_machine_tenant_binding.py": "8f2b0d16c0c55d650bc9d2dd740a588e7f2c93dfae6255ac0faff6f1b1309b84",
    "0008_tenant_scoped_identity_namespace.py": "9f69829593e49f53ad5d3d47ad3f7dfa94ef8437681ea3e7f06d86ab1e1553a7",
    "0009_secret_store_foundation.py": "20b1109d75e78f511b346f1d85da8fa7fb9f6caa8b8a92347a2859ba2d35ca5c",
    "0010_secret_consumer_refs.py": "4303d0826dce3e8fb0750a376cb68b8abcba7e1d62296bee23a1782eaa3edcf4",
    "0011_secret_consumer_enforcement.py": "15e89a6b4bdf00fc7334e7a7d0128251b378803a98771700066568683f234df8",
    "0012_principal_identity_foundation.py": "c5028edb83d75542494619eee267940955b54ac1a6284873a4a8a7c5a46f440d",
    "0013_principal_identity_enforcement.py": "7388cbfd71b0ec35f945545b813bdb08d177c263ab34348e36449bf44da91b29",
    "0014_minimum_authority_bundles.py": "864328578509aea48b28f2fe6b705da3d8f609424c553db9b0070253b751bc9f",
    "0015_security_admin_audit.py": "c6c57fd42ac84bb46aacba3f927f10ff77269937a4b5a44f0725a3e9be95da8d",
}


def _load(path: Path) -> dict:
    documents = [
        item
        for item in yaml.safe_load_all(path.read_text(encoding="utf-8"))
        if isinstance(item, dict)
    ]
    if len(documents) != 1:
        raise AssertionError(f"Expected one document in {path}")
    return documents[0]


def _resource(path: Path, kind: str, name: str) -> dict:
    matches = [
        item
        for item in yaml.safe_load_all(path.read_text(encoding="utf-8"))
        if isinstance(item, dict)
        and item.get("kind") == kind
        and item.get("metadata", {}).get("name") == name
    ]
    if len(matches) != 1:
        raise AssertionError(f"Expected one {kind}/{name} in {path}")
    return matches[0]


def _container(document: dict) -> dict:
    return document["spec"]["template"]["spec"]["containers"][0]


def _environment(container: dict) -> dict[str, dict]:
    return {item["name"]: item for item in container.get("env", [])}


def _function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if len(matches) != 1:
        raise AssertionError(f"Expected one function named {name}")
    segment = ast.get_source_segment(source, matches[0])
    if segment is None:
        raise AssertionError(f"Unable to extract function named {name}")
    return " ".join(segment.split())


class CloudV1DatabaseBootstrapContractTests(unittest.TestCase):
    def test_runtime_and_migration_have_separate_non_master_credentials(self) -> None:
        backend = _container(_resource(BACKEND_PATH, "Deployment", "topo-backend"))
        migration = _container(_load(MIGRATION_PATH))
        bootstrap = _container(_load(BOOTSTRAP_PATH))

        self.assertEqual(bootstrap["image"], backend["image"])
        self.assertEqual(bootstrap["image"], migration["image"])
        self.assertIn("@sha256:", bootstrap["image"])
        self.assertNotIn(":latest", bootstrap["image"].casefold())
        self.assertEqual(
            _environment(backend)["TOPO_DATABASE_URL"]["valueFrom"]["secretKeyRef"],
            {"name": "topo-backend-runtime", "key": "database-url"},
        )
        self.assertEqual(
            _environment(migration)["TOPO_DATABASE_URL"]["valueFrom"]["secretKeyRef"],
            {"name": "topo-backend-runtime", "key": "migration-database-url"},
        )
        serialized = yaml.safe_dump({"backend": backend, "migration": migration})
        self.assertNotIn("master-password", serialized)
        self.assertNotIn("master-username", serialized)
        self.assertNotIn("topo-database-bootstrap", serialized)

    def test_backend_never_runs_alembic_and_migration_reconciles_after_upgrade(
        self,
    ) -> None:
        backend = _container(_resource(BACKEND_PATH, "Deployment", "topo-backend"))
        migration = _container(_load(MIGRATION_PATH))
        command_text = "\n".join(
            [*migration.get("command", []), *migration.get("args", [])]
        )

        self.assertNotIn("alembic", yaml.safe_dump(backend).casefold())
        self.assertIn("alembic", command_text)
        self.assertIn("upgrade head", command_text)
        self.assertIn("topo_database_admin.py reconcile", command_text)
        self.assertLess(
            command_text.index("upgrade head"),
            command_text.index("topo_database_admin.py reconcile"),
        )

    def test_bootstrap_job_is_hardened_and_uses_only_temporary_files(self) -> None:
        job = _load(BOOTSTRAP_PATH)
        pod = job["spec"]["template"]["spec"]
        container = _container(job)

        self.assertEqual(job["kind"], "Job")
        self.assertEqual(job["metadata"]["namespace"], "topo-system")
        self.assertEqual(job["spec"]["backoffLimit"], 1)
        self.assertLessEqual(job["spec"]["activeDeadlineSeconds"], 600)
        self.assertEqual(pod["restartPolicy"], "Never")
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertTrue(pod["securityContext"]["runAsNonRoot"])
        self.assertEqual(pod["securityContext"]["runAsUser"], 10001)
        self.assertEqual(pod["securityContext"]["runAsGroup"], 10001)
        self.assertEqual(pod["securityContext"]["fsGroup"], 10001)
        self.assertEqual(
            pod["securityContext"]["fsGroupChangePolicy"],
            "OnRootMismatch",
        )
        self.assertEqual(
            pod["securityContext"]["seccompProfile"]["type"],
            "RuntimeDefault",
        )
        self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual(container["securityContext"]["capabilities"]["drop"], ["ALL"])
        self.assertEqual(container.get("envFrom", []), [])
        self.assertFalse(
            any("AWS_" in item["name"] for item in container.get("env", []))
        )
        self.assertNotIn("topo-backend-runtime", yaml.safe_dump(job))
        self.assertNotIn("projected", yaml.safe_dump(job))

    def test_temporary_secret_contract_contains_exactly_seven_keys(self) -> None:
        job = _load(BOOTSTRAP_PATH)
        volume = next(
            item
            for item in job["spec"]["template"]["spec"]["volumes"]
            if item["name"] == "database-bootstrap-secret"
        )
        secret = volume["secret"]

        self.assertEqual(secret["secretName"], "topo-database-bootstrap")
        self.assertEqual(secret["defaultMode"], 0o440)
        self.assertEqual(
            {item["key"] for item in secret["items"]},
            BOOTSTRAP_SECRET_KEYS,
        )
        self.assertEqual(
            {item["path"] for item in secret["items"]},
            BOOTSTRAP_SECRET_KEYS,
        )
        self.assertNotIn("bootstrap-token", yaml.safe_dump(secret))
        self.assertNotIn("keyring", yaml.safe_dump(secret))
        self.assertNotIn("aws", yaml.safe_dump(secret).casefold())

    def test_bootstrap_uses_catalog_checks_advisory_locks_and_safe_sql(self) -> None:
        source = ADMIN_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        execute_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
        ]

        self.assertIn("pg_catalog.pg_roles", source)
        self.assertNotIn("CREATE ROLE IF NOT EXISTS", source)
        self.assertIn("pg_try_advisory_lock", source)
        self.assertIn("pg_advisory_unlock", source)
        self.assertIn("sql.Identifier", source)
        self.assertIn("sql.Literal(verifier)", source)
        self.assertIn("encrypt_password", source)
        self.assertFalse(
            any(
                call.args and isinstance(call.args[0], ast.JoinedStr)
                for call in execute_calls
            ),
            "cursor.execute must not receive an interpolated f-string",
        )

    def test_roles_and_object_grants_are_minimum_and_reconcilable(self) -> None:
        source = " ".join(ADMIN_PATH.read_text(encoding="utf-8").split())

        for required in (
            "NOCREATEDB",
            "NOCREATEROLE",
            "rolsuper, rolreplication, rolbypassrls",
            "DATABASE_ROLE_UNSAFE_ELEVATED_ATTRIBUTE",
            "REVOKE CREATE ON SCHEMA",
            "GRANT USAGE ON SCHEMA",
            "GRANT USAGE, CREATE ON SCHEMA",
            "ALTER DEFAULT PRIVILEGES FOR ROLE",
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES",
            "GRANT USAGE ON SEQUENCES",
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES",
            "GRANT USAGE ON ALL SEQUENCES",
            "REVOKE ALL PRIVILEGES ON ALL FUNCTIONS",
        ):
            self.assertIn(required, source)
        self.assertNotIn("GRANT ALL PRIVILEGES", source)
        self.assertNotIn("GRANT SUPERUSER", source)

    def test_normal_role_convergence_does_not_toggle_restricted_attributes(
        self,
    ) -> None:
        source = _function_source(ADMIN_PATH, "_converge_role")

        self.assertIn("CREATE ROLE {} WITH LOGIN", source)
        self.assertIn("NOCREATEDB", source)
        self.assertIn("NOCREATEROLE", source)
        self.assertIn("INHERIT", source)
        self.assertIn("CONNECTION LIMIT -1", source)
        for restricted in ("SUPERUSER", "REPLICATION", "BYPASSRLS"):
            self.assertNotIn(restricted, source)

    def test_final_role_verification_retains_strict_safe_attribute_contract(
        self,
    ) -> None:
        source = _function_source(ADMIN_PATH, "_verify_role_attributes")
        catalog_source = _function_source(ADMIN_PATH, "_role_attributes")

        self.assertIn(
            "expected = (True, False, False, False, True, False, False, -1, True, True)",
            source,
        )
        for field in ("rolsuper", "rolreplication", "rolbypassrls"):
            self.assertIn(field, catalog_source)

    def test_alembic_metadata_is_read_only_for_application_role(self) -> None:
        source = " ".join(ADMIN_PATH.read_text(encoding="utf-8").split())

        self.assertIn("public.alembic_version", source)
        self.assertIn(
            "REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER",
            source,
        )
        self.assertIn("GRANT SELECT ON TABLE", source)

    def test_role_material_generator_has_no_master_or_cloud_mutation(self) -> None:
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

        self.assertIn("secrets", imported_roots)
        self.assertTrue(
            {"subprocess", "boto3", "kubernetes", "psycopg"}.isdisjoint(imported_roots)
        )
        self.assertNotIn("master-password", source.casefold())
        self.assertNotIn("kubectl", source.casefold())
        self.assertNotIn("terraform", source.casefold())
        self.assertIn('query={"sslmode": "require"}', source)

    def test_migrations_0001_through_0015_match_committed_authority(self) -> None:
        names = {
            path.name
            for path in MIGRATION_DIRECTORY.glob("*.py")
            if path.name[:4].isdigit() and 1 <= int(path.name[:4]) <= 15
        }
        self.assertEqual(names, set(MIGRATION_BLOB_SHA256))

        for filename, expected in MIGRATION_BLOB_SHA256.items():
            repository_path = f"backend/alembic/versions/{filename}"
            blob = subprocess.run(
                ["git", "-C", str(ROOT), "show", f"HEAD:{repository_path}"],
                check=True,
                stdout=subprocess.PIPE,
            ).stdout
            self.assertEqual(hashlib.sha256(blob).hexdigest(), expected)

        changed = subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "diff",
                "--name-only",
                "--",
                "backend/alembic/versions",
            ],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        self.assertEqual(changed, "")

    def test_documentation_preserves_database_authority_boundaries(self) -> None:
        document = " ".join(DOCUMENT_PATH.read_text(encoding="utf-8").split())
        for required in (
            "RDS master",
            "topo_migrator",
            "topo_app",
            "public schema",
            "alembic_version",
            "default privileges",
            "advisory lock",
            "ambiguous outcome",
            "C2-B",
            "C2-C",
            "No live environment was changed",
        ):
            self.assertIn(required, document)


if __name__ == "__main__":
    unittest.main()
