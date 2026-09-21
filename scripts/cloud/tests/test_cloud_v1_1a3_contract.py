from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
MANIFEST_DIR = ROOT / "infrastructure/kubernetes/golden"
DOCUMENT_PATH = (
    ROOT / "docs/architecture/cloud-v1-1a3-kubernetes-runtime-contract-v1.md"
)
DATABASE_PATH = ROOT / "backend/app/db/database.py"
RUNTIME_HEALTH_PATH = ROOT / "backend/app/services/runtime_health.py"
KEYRING_STAGING_PATH = ROOT / "backend/app/security/keyring_staging.py"
IMAGE_REFERENCE = re.compile(r"^[^\s:@]+(?:/[^\s:@]+)+@sha256:[0-9a-f]{64}$")


def _documents() -> list[dict]:
    documents: list[dict] = []
    for path in sorted(MANIFEST_DIR.glob("*.yaml")):
        documents.extend(
            document
            for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))
            if isinstance(document, dict)
        )
    return documents


def _resource(kind: str, name: str) -> dict:
    matches = [
        document
        for document in _documents()
        if document.get("kind") == kind
        and document.get("metadata", {}).get("name") == name
    ]
    if len(matches) != 1:
        raise AssertionError(f"Expected one {kind}/{name}; found {len(matches)}")
    return matches[0]


def _container(workload: dict) -> dict:
    return workload["spec"]["template"]["spec"]["containers"][0]


def _integer_constant(path: Path, name: str) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    matches = [
        node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == name
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, int)
    ]
    if len(matches) != 1:
        raise AssertionError(f"Expected one integer constant named {name}")
    return matches[0]


class CloudV1KubernetesRuntimeContractTests(unittest.TestCase):
    def test_backend_init_and_migration_consume_one_digest_not_latest(self) -> None:
        deployment = _resource("Deployment", "topo-backend")
        migration = _resource("Job", "topo-backend-migrate")
        backend_image = _container(deployment)["image"]
        init_containers = deployment["spec"]["template"]["spec"]["initContainers"]
        migration_image = _container(migration)["image"]

        self.assertEqual(len(init_containers), 1)
        staging_image = init_containers[0]["image"]
        self.assertRegex(backend_image, IMAGE_REFERENCE)
        self.assertEqual(backend_image, migration_image)
        self.assertEqual(backend_image, staging_image)
        self.assertNotIn(":latest", backend_image.casefold())
        self.assertIn("@sha256:", backend_image)

    def test_backend_two_replica_rollout_preserves_availability(self) -> None:
        deployment = _resource("Deployment", "topo-backend")
        strategy = deployment["spec"]["strategy"]

        self.assertEqual(deployment["spec"]["replicas"], 2)
        self.assertEqual(strategy["type"], "RollingUpdate")
        self.assertEqual(
            strategy["rollingUpdate"],
            {
                "maxUnavailable": 0,
                "maxSurge": 1,
            },
        )
        self.assertGreaterEqual(deployment["spec"]["minReadySeconds"], 1)

        budget = _resource("PodDisruptionBudget", "topo-backend")
        self.assertEqual(budget["spec"]["minAvailable"], 1)

    def test_backend_security_context_and_soft_spread_are_restricted(self) -> None:
        deployment = _resource("Deployment", "topo-backend")
        pod = deployment["spec"]["template"]["spec"]
        container = _container(deployment)

        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertFalse(pod.get("hostNetwork", False))
        self.assertFalse(pod.get("hostPID", False))
        self.assertFalse(pod.get("hostIPC", False))
        self.assertTrue(pod["securityContext"]["runAsNonRoot"])
        self.assertEqual(
            pod["securityContext"]["seccompProfile"]["type"],
            "RuntimeDefault",
        )
        self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual(container["securityContext"]["capabilities"]["drop"], ["ALL"])
        self.assertFalse(container["securityContext"].get("privileged", False))
        self.assertTrue(
            all(volume.get("hostPath") is None for volume in pod.get("volumes", []))
        )
        constraints = pod["topologySpreadConstraints"]
        self.assertEqual(
            {item["topologyKey"] for item in constraints},
            {"topology.kubernetes.io/zone", "kubernetes.io/hostname"},
        )
        self.assertTrue(
            all(item["whenUnsatisfiable"] == "ScheduleAnyway" for item in constraints)
        )

    def test_probe_semantics_are_distinct_and_bounded(self) -> None:
        container = _container(_resource("Deployment", "topo-backend"))
        startup = container["startupProbe"]
        liveness = container["livenessProbe"]
        readiness = container["readinessProbe"]

        self.assertEqual(startup["httpGet"]["path"], "/startup")
        self.assertEqual(liveness["httpGet"]["path"], "/health")
        self.assertEqual(readiness["httpGet"]["path"], "/ready")
        self.assertLessEqual(startup["timeoutSeconds"], 2)
        self.assertLessEqual(liveness["timeoutSeconds"], 2)
        self.assertEqual(readiness["timeoutSeconds"], 8)
        application_database_wait = _integer_constant(
            DATABASE_PATH, "POSTGRES_CONNECT_TIMEOUT_SECONDS"
        ) + _integer_constant(
            DATABASE_PATH,
            "POSTGRES_POOL_TIMEOUT_SECONDS",
        )
        readiness_database_wait = (
            _integer_constant(
                RUNTIME_HEALTH_PATH,
                "READINESS_CONNECT_TIMEOUT_SECONDS",
            )
            + _integer_constant(
                RUNTIME_HEALTH_PATH,
                "READINESS_STATEMENT_TIMEOUT_MILLISECONDS",
            )
            / 1_000
        )
        self.assertLess(
            max(application_database_wait, readiness_database_wait),
            readiness["timeoutSeconds"],
        )
        self.assertGreaterEqual(
            startup["periodSeconds"] * startup["failureThreshold"],
            300,
        )

    def test_backend_service_is_internal_and_selector_exact(self) -> None:
        service = _resource("Service", "topo-backend")
        deployment = _resource("Deployment", "topo-backend")
        selector = service["spec"]["selector"]

        self.assertEqual(service["spec"]["type"], "ClusterIP")
        self.assertNotIn("externalIPs", service["spec"])
        self.assertNotIn("loadBalancerIP", service["spec"])
        self.assertTrue(
            all("nodePort" not in port for port in service["spec"]["ports"])
        )
        self.assertEqual(selector, deployment["spec"]["selector"]["matchLabels"])

    def test_database_and_root_material_are_secret_referenced(self) -> None:
        deployment = _resource("Deployment", "topo-backend")
        migration = _resource("Job", "topo-backend-migrate")
        environment = {item["name"]: item for item in _container(deployment)["env"]}

        self.assertEqual(
            environment["TOPO_DATABASE_URL"]["valueFrom"]["secretKeyRef"],
            {"name": "topo-backend-runtime", "key": "database-url"},
        )
        self.assertEqual(
            _container(migration)["env"][0]["valueFrom"]["secretKeyRef"],
            {
                "name": "topo-backend-runtime",
                "key": "migration-database-url",
            },
        )
        self.assertEqual(
            environment["TOPO_SECRET_STORE_BACKEND"]["value"], "encrypted_db"
        )
        self.assertNotIn("value", environment["TOPO_API_TOKEN_HASHES_JSON"])

        config = _resource("ConfigMap", "topo-runtime-config")["data"]
        sensitive_names = ("password", "token", "secret", "database-url", "keyring")
        self.assertFalse(
            any(
                sensitive in key.casefold()
                for key in config
                for sensitive in sensitive_names
            )
        )

    def test_keyring_secret_is_staged_into_an_isolated_memory_volume(self) -> None:
        deployment = _resource("Deployment", "topo-backend")
        pod = deployment["spec"]["template"]["spec"]
        backend = _container(deployment)
        init_containers = pod["initContainers"]
        self.assertEqual(len(init_containers), 1)
        staging = init_containers[0]
        self.assertEqual(staging["name"], "stage-secret-keyring")

        volumes = {volume["name"]: volume for volume in pod["volumes"]}
        raw = volumes["secret-store-keyring-source"]["secret"]
        self.assertEqual(raw["secretName"], "topo-backend-runtime")
        self.assertEqual(raw["defaultMode"], 0o440)
        self.assertEqual(
            raw["items"],
            [{"key": "secret-store-keyring.json", "path": "keyring.json"}],
        )
        self.assertEqual(
            volumes["secret-store-keyring-staged"]["emptyDir"],
            {"medium": "Memory", "sizeLimit": "128Ki"},
        )

        backend_mounts = {mount["name"]: mount for mount in backend["volumeMounts"]}
        staging_mounts = {mount["name"]: mount for mount in staging["volumeMounts"]}
        self.assertNotIn("secret-store-keyring-source", backend_mounts)
        self.assertEqual(
            staging_mounts["secret-store-keyring-source"],
            {
                "name": "secret-store-keyring-source",
                "mountPath": "/var/run/secrets/topo/keyring-source",
                "readOnly": True,
            },
        )
        self.assertNotIn("readOnly", staging_mounts["secret-store-keyring-staged"])
        self.assertEqual(
            backend_mounts["secret-store-keyring-staged"],
            {
                "name": "secret-store-keyring-staged",
                "mountPath": "/run/topo/keyring",
                "readOnly": True,
            },
        )
        self.assertEqual(
            staging_mounts["secret-store-keyring-staged"]["mountPath"],
            "/run/topo/keyring",
        )
        environment = {item["name"]: item for item in backend["env"]}
        self.assertEqual(
            environment["TOPO_SECRET_KEYRING_FILE"]["value"],
            "/run/topo/keyring/keyring.json",
        )
        trusted_paths = (
            environment["TOPO_SECRET_KEYRING_FILE"]["value"],
            staging_mounts["secret-store-keyring-staged"]["mountPath"],
            backend_mounts["secret-store-keyring-staged"]["mountPath"],
        )
        self.assertTrue(all(path.startswith("/run/topo/") for path in trusted_paths))
        self.assertTrue(all("/var/run" not in path for path in trusted_paths))
        self.assertNotIn("migration-database-url", yaml.safe_dump(pod))

    def test_keyring_staging_init_container_is_hardened_and_bounded(self) -> None:
        deployment = _resource("Deployment", "topo-backend")
        pod = deployment["spec"]["template"]["spec"]
        staging = pod["initContainers"][0]
        security = staging["securityContext"]

        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(pod["securityContext"]["runAsUser"], 10001)
        self.assertEqual(pod["securityContext"]["runAsGroup"], 10001)
        self.assertTrue(security["runAsNonRoot"])
        self.assertEqual(security["runAsUser"], 10001)
        self.assertEqual(security["runAsGroup"], 10001)
        self.assertFalse(security["allowPrivilegeEscalation"])
        self.assertTrue(security["readOnlyRootFilesystem"])
        self.assertEqual(security["capabilities"]["drop"], ["ALL"])
        self.assertFalse(security.get("privileged", False))
        self.assertEqual(
            staging["command"],
            ["python", "-m", "app.security.keyring_staging"],
        )
        self.assertEqual(staging.get("env", []), [])
        self.assertEqual(staging.get("envFrom", []), [])
        serialized = yaml.safe_dump(staging).casefold()
        for forbidden in ("aws_", "migration-database-url", "serviceaccounttoken"):
            self.assertNotIn(forbidden.casefold(), serialized)

        source = KEYRING_STAGING_PATH.read_text(encoding="utf-8")
        self.assertIn(
            'STAGED_KEYRING_PATH = Path("/run/topo/keyring/keyring.json")',
            source,
        )
        self.assertNotIn(
            'STAGED_KEYRING_PATH = Path("/var/run',
            source,
        )
        self.assertIn("MAX_KEYRING_BYTES + 1", source)
        self.assertIn("os.O_EXCL", source)
        self.assertIn("os.O_NOFOLLOW", source)
        self.assertIn("os.fchmod(descriptor, 0o600)", source)
        self.assertIn("stat.S_ISREG", source)
        self.assertIn("stat.S_ISLNK", source)
        self.assertIn('print("KEYRING_STAGE=PASS")', source)

    def test_documented_trusted_keyring_path_forbids_var_run(self) -> None:
        document = " ".join(DOCUMENT_PATH.read_text(encoding="utf-8").split())

        self.assertIn("/run/topo/keyring/keyring.json", document)
        self.assertIn("/var/run", document)
        self.assertIn("intentionally forbidden", document)
        self.assertIn("entire trusted path", document)

    def test_backend_has_no_kubernetes_api_authority(self) -> None:
        service_account = _resource("ServiceAccount", "topo-backend")
        self.assertFalse(service_account["automountServiceAccountToken"])

        bound_subjects = [
            subject
            for document in _documents()
            if document.get("kind") in {"RoleBinding", "ClusterRoleBinding"}
            for subject in document.get("subjects", [])
        ]
        self.assertNotIn(
            "topo-backend", {subject.get("name") for subject in bound_subjects}
        )

    def test_observer_rbac_matches_actual_list_calls_only(self) -> None:
        role = _resource("ClusterRole", "topo-observer-readonly")
        expected = {
            "": {"namespaces", "nodes", "pods", "services", "events"},
            "apps": {"deployments", "replicasets"},
            "networking.k8s.io": {"ingresses"},
            "discovery.k8s.io": {"endpointslices"},
        }
        actual: dict[str, set[str]] = {}
        for rule in role["rules"]:
            self.assertEqual(rule["verbs"], ["list"])
            self.assertNotIn("*", rule["apiGroups"])
            self.assertNotIn("*", rule["resources"])
            self.assertNotIn("secrets", rule["resources"])
            self.assertNotIn("configmaps", rule["resources"])
            self.assertNotIn("pods/exec", rule["resources"])
            for api_group in rule["apiGroups"]:
                actual.setdefault(api_group, set()).update(rule["resources"])
        self.assertEqual(actual, expected)

        observer = _resource("Deployment", "topo-observer")
        self.assertEqual(observer["spec"]["replicas"], 1)
        self.assertEqual(observer["spec"]["strategy"]["type"], "Recreate")
        service_account = _resource("ServiceAccount", "topo-observer")
        self.assertFalse(bool(service_account.get("metadata", {}).get("annotations")))

    def test_migrations_are_a_distinct_non_privileged_job(self) -> None:
        migration = _resource("Job", "topo-backend-migrate")
        pod = migration["spec"]["template"]["spec"]
        container = _container(migration)

        self.assertEqual(pod["restartPolicy"], "Never")
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(container["command"], ["/bin/sh", "-eu", "-c"])
        command_text = "\n".join(container["args"])
        self.assertIn(
            "python -m alembic -c /opt/topo/alembic.ini upgrade head",
            command_text,
        )
        self.assertIn(
            "python /opt/topo-admin/topo_database_admin.py reconcile",
            command_text,
        )
        self.assertLess(
            command_text.index("upgrade head"),
            command_text.index("topo_database_admin.py reconcile"),
        )
        self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
        self.assertNotIn(
            "alembic", str(_container(_resource("Deployment", "topo-backend")))
        )

    def test_rds_worker_security_group_limitation_is_explicit(self) -> None:
        document = " ".join(
            DOCUMENT_PATH.read_text(encoding="utf-8").casefold().split()
        )
        self.assertIn("node-level, not pod-specific", document)
        self.assertIn("any workload", document)
        self.assertIn("could attempt tcp 5432", document)
        self.assertIn("accepted blast radius", document)


if __name__ == "__main__":
    unittest.main()
