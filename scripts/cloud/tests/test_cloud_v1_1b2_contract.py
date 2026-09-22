from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[3]
MANIFEST_DIR = ROOT / "infrastructure/kubernetes/golden"
MANIFEST_PATH = MANIFEST_DIR / "frontend.yaml"
DOCUMENT_PATH = (
    ROOT / "docs/architecture/cloud-v1-1b2-frontend-kubernetes-runtime-v1.md"
)
IMAGE = (
    "297361542190.dkr.ecr.us-east-1.amazonaws.com/topo-golden/topo@"
    "sha256:ba86d89733b552cd3ced4792f40b59032524f83275b806ffc20f3249b8b1bdf1"
)
SELECTOR = {
    "app.kubernetes.io/name": "topo-frontend",
    "app.kubernetes.io/component": "web",
}


def _documents(path: Path = MANIFEST_PATH) -> list[dict[str, Any]]:
    return [
        document
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))
        if isinstance(document, dict)
    ]


def _all_documents() -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for path in sorted(MANIFEST_DIR.glob("*.yaml")):
        documents.extend(_documents(path))
    return documents


def _resource(kind: str, name: str) -> dict[str, Any]:
    matches = [
        document
        for document in _all_documents()
        if document.get("kind") == kind
        and document.get("metadata", {}).get("name") == name
    ]
    if len(matches) != 1:
        raise AssertionError(f"Expected one {kind}/{name}; found {len(matches)}")
    return matches[0]


def _container() -> dict[str, Any]:
    deployment = _resource("Deployment", "topo-frontend")
    containers = deployment["spec"]["template"]["spec"]["containers"]
    if len(containers) != 1:
        raise AssertionError(f"Expected one frontend container; found {len(containers)}")
    return containers[0]


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return {str(key) for key in value} | {
            nested_key for nested in value.values() for nested_key in _keys(nested)
        }
    if isinstance(value, list):
        return {nested_key for item in value for nested_key in _keys(item)}
    return set()


class CloudV1FrontendKubernetesRuntimeContractTests(unittest.TestCase):
    def test_exact_resource_identities_and_namespace(self) -> None:
        expected = {
            ("ServiceAccount", "topo-frontend"),
            ("Deployment", "topo-frontend"),
            ("Service", "topo-frontend-internal"),
            ("PodDisruptionBudget", "topo-frontend"),
        }
        actual = {
            (document["kind"], document["metadata"]["name"])
            for document in _documents()
        }

        self.assertEqual(actual, expected)
        self.assertTrue(
            all(
                document["metadata"].get("namespace") == "topo-system"
                for document in _documents()
            )
        )

    def test_image_and_availability_are_immutable_and_bounded(self) -> None:
        deployment = _resource("Deployment", "topo-frontend")
        container = _container()
        strategy = deployment["spec"]["strategy"]

        self.assertEqual(container["image"], IMAGE)
        self.assertRegex(container["image"], r"@sha256:[0-9a-f]{64}$")
        self.assertNotIn(":latest", container["image"].casefold())
        self.assertNotRegex(container["image"], r"topo:[^@\s]+$")
        self.assertEqual(deployment["spec"]["replicas"], 2)
        self.assertEqual(strategy["type"], "RollingUpdate")
        self.assertEqual(
            strategy["rollingUpdate"],
            {"maxUnavailable": 0, "maxSurge": 1},
        )
        self.assertGreaterEqual(deployment["spec"]["minReadySeconds"], 1)
        budget = _resource("PodDisruptionBudget", "topo-frontend")
        self.assertGreaterEqual(budget["spec"]["minAvailable"], 1)
        self.assertEqual(budget["spec"]["selector"]["matchLabels"], SELECTOR)

    def test_service_account_has_no_token_or_aws_authority(self) -> None:
        service_account = _resource("ServiceAccount", "topo-frontend")
        deployment = _resource("Deployment", "topo-frontend")
        pod = deployment["spec"]["template"]["spec"]

        self.assertFalse(service_account["automountServiceAccountToken"])
        self.assertFalse(service_account["metadata"].get("annotations"))
        self.assertEqual(pod["serviceAccountName"], "topo-frontend")
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertNotIn("imagePullSecrets", pod)

        bound_subjects = [
            subject
            for document in _all_documents()
            if document.get("kind") in {"RoleBinding", "ClusterRoleBinding"}
            for subject in document.get("subjects", [])
        ]
        self.assertNotIn(
            "topo-frontend", {subject.get("name") for subject in bound_subjects}
        )

    def test_security_context_is_restricted_and_root_is_read_only(self) -> None:
        deployment = _resource("Deployment", "topo-frontend")
        pod = deployment["spec"]["template"]["spec"]
        container = _container()
        pod_security = pod["securityContext"]
        container_security = container["securityContext"]

        self.assertTrue(pod_security["runAsNonRoot"])
        self.assertEqual(pod_security["runAsUser"], 10001)
        self.assertEqual(pod_security["runAsGroup"], 10001)
        self.assertEqual(pod_security["seccompProfile"], {"type": "RuntimeDefault"})
        self.assertTrue(container_security["runAsNonRoot"])
        self.assertEqual(container_security["runAsUser"], 10001)
        self.assertEqual(container_security["runAsGroup"], 10001)
        self.assertFalse(container_security["allowPrivilegeEscalation"])
        self.assertTrue(container_security["readOnlyRootFilesystem"])
        self.assertEqual(container_security["capabilities"]["drop"], ["ALL"])
        self.assertFalse(container_security.get("privileged", False))
        for field in ("hostNetwork", "hostPID", "hostIPC"):
            self.assertFalse(pod.get(field, False))
        self.assertNotIn("volumes", pod)
        self.assertNotIn("volumeMounts", container)
        self.assertTrue(all("hostPort" not in port for port in container["ports"]))

    def test_health_probes_use_only_the_frontend_health_route(self) -> None:
        container = _container()

        self.assertEqual(container["ports"], [
            {"name": "http", "containerPort": 3000, "protocol": "TCP"}
        ])
        for probe_name in ("startupProbe", "readinessProbe", "livenessProbe"):
            probe = container[probe_name]
            self.assertEqual(probe["httpGet"]["path"], "/healthz")
            self.assertEqual(probe["httpGet"]["port"], "http")
            self.assertNotIn("/api/", probe["httpGet"]["path"])
            self.assertLessEqual(probe["timeoutSeconds"], 2)
        self.assertGreaterEqual(
            container["startupProbe"]["periodSeconds"]
            * container["startupProbe"]["failureThreshold"],
            60,
        )

    def test_internal_service_is_private_and_selects_only_frontend(self) -> None:
        service = _resource("Service", "topo-frontend-internal")
        deployment = _resource("Deployment", "topo-frontend")

        self.assertEqual(service["spec"]["type"], "ClusterIP")
        self.assertEqual(service["spec"]["selector"], SELECTOR)
        self.assertEqual(
            service["spec"]["selector"],
            deployment["spec"]["selector"]["matchLabels"],
        )
        self.assertEqual(
            service["spec"]["ports"],
            [{"name": "http", "port": 80, "targetPort": "http", "protocol": "TCP"}],
        )
        self.assertNotIn("externalIPs", service["spec"])
        self.assertNotIn("loadBalancerIP", service["spec"])
        self.assertTrue(
            all("nodePort" not in port for port in service["spec"]["ports"])
        )

    def test_resources_and_soft_fault_domain_spread_are_explicit(self) -> None:
        deployment = _resource("Deployment", "topo-frontend")
        pod = deployment["spec"]["template"]["spec"]
        resources = _container()["resources"]

        self.assertEqual(
            resources,
            {
                "requests": {"cpu": "100m", "memory": "256Mi"},
                "limits": {"cpu": "500m", "memory": "512Mi"},
            },
        )
        constraints = pod["topologySpreadConstraints"]
        self.assertEqual(
            {constraint["topologyKey"] for constraint in constraints},
            {"topology.kubernetes.io/zone", "kubernetes.io/hostname"},
        )
        self.assertTrue(
            all(
                constraint["whenUnsatisfiable"] == "ScheduleAnyway"
                for constraint in constraints
            )
        )
        self.assertTrue(
            all(
                constraint["labelSelector"]["matchLabels"] == SELECTOR
                for constraint in constraints
            )
        )

    def test_manifest_has_no_credentials_secret_configuration_or_public_edge(self) -> None:
        documents = _documents()
        deployment = _resource("Deployment", "topo-frontend")
        pod = deployment["spec"]["template"]["spec"]
        container = _container()

        self.assertNotIn("env", container)
        self.assertNotIn("envFrom", container)
        self.assertNotIn("initContainers", pod)
        self.assertNotIn("volumes", pod)
        self.assertTrue(
            _keys(documents).isdisjoint(
                {
                    "secretKeyRef",
                    "configMapKeyRef",
                    "secretRef",
                    "configMapRef",
                    "imagePullSecrets",
                    "hostPath",
                }
            )
        )
        self.assertFalse(
            {document["kind"] for document in documents}
            & {"Secret", "ConfigMap", "Ingress"}
        )
        services = [document for document in documents if document["kind"] == "Service"]
        self.assertEqual(len(services), 1)
        self.assertNotIn(
            services[0]["spec"]["type"],
            {"NodePort", "LoadBalancer", "ExternalName"},
        )

        serialized = yaml.safe_dump(documents, sort_keys=True)
        for forbidden in (
            "TOPO_BACKEND_URL",
            "NEXT_PUBLIC_TOPO_API_URL",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "database-url",
            "agent-token",
            "keyring",
            "eks.amazonaws.com/role-arn",
        ):
            self.assertNotIn(forbidden.casefold(), serialized.casefold())

    def test_document_records_provenance_and_all_live_handoff_steps(self) -> None:
        document = DOCUMENT_PATH.read_text(encoding="utf-8")

        for expected in (
            "2d43805820c65ffb7b12c3eff465535c70f6faac",
            "35771441512",
            "run attempt `1`",
            IMAGE,
            "topo-frontend-internal",
            "CLOUD-V1-1B.3",
            "readOnlyRootFilesystem: true",
            "no writable volumes",
            "No human credential",
        ):
            self.assertIn(expected, document)
        for step in range(1, 27):
            self.assertRegex(document, rf"(?m)^{step}\. ")


if __name__ == "__main__":
    unittest.main()
