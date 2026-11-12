from __future__ import annotations

import copy
import json
from types import SimpleNamespace

from topo_agent.collector import (
    KubernetesCollector,
    _pod_template_fingerprint,
)
from topo_agent.config import AgentConfig


def _template_payload() -> dict:
    return {
        "metadata": {
            "labels": {"app": "orders-api"},
            "annotations": {},
        },
        "spec": {
            "containers": [
                {
                    "name": "orders-api",
                    "image": "nginx:1.27-alpine",
                    "command": ["nginx"],
                    "args": ["-g", "daemon off;"],
                    "env": [
                        {
                            "name": "DATABASE_PASSWORD",
                            "value": "raw-environment-secret",
                        },
                        {
                            "name": "API_TOKEN",
                            "value_from": {
                                "secret_key_ref": {
                                    "name": "orders-api-secret",
                                    "key": "api-token",
                                }
                            },
                        },
                    ],
                    "resources": {
                        "limits": {"memory": "64Mi"},
                        "requests": {"memory": "32Mi"},
                    },
                    "readiness_probe": {
                        "http_get": {
                            "path": "/ready",
                            "port": 8080,
                        }
                    },
                }
            ],
            "init_containers": [
                {
                    "name": "database-migration",
                    "image": "orders-migration:v1",
                    "command": ["migrate"],
                }
            ],
            "restart_policy": "Always",
            "service_account_name": "orders-api",
        },
    }


def _fingerprint(payload: dict) -> str:
    return _pod_template_fingerprint(
        SimpleNamespace(
            to_dict=lambda: copy.deepcopy(payload)
        )
    )


def test_pod_template_fingerprint_is_stable_and_image_independent() -> None:
    baseline = _template_payload()
    reordered = {
        "spec": copy.deepcopy(baseline["spec"]),
        "metadata": copy.deepcopy(baseline["metadata"]),
    }
    changed_image = copy.deepcopy(baseline)
    changed_image["spec"]["containers"][0]["image"] = (
        "nginx:topo-invalid"
    )

    assert _fingerprint(baseline) == _fingerprint(baseline)
    assert _fingerprint(reordered) == _fingerprint(baseline)
    assert _fingerprint(changed_image) == _fingerprint(baseline)


def test_init_container_image_change_changes_pod_template_fingerprint() -> None:
    baseline = _template_payload()
    changed = copy.deepcopy(baseline)
    changed["spec"]["init_containers"][0]["image"] = (
        "orders-migration:v2"
    )

    assert _fingerprint(changed) != _fingerprint(baseline)


def test_command_change_changes_pod_template_fingerprint() -> None:
    baseline = _template_payload()
    changed = copy.deepcopy(baseline)
    changed["spec"]["containers"][0]["command"] = [
        "sh",
        "-c",
        "exit 3",
    ]

    assert _fingerprint(changed) != _fingerprint(baseline)


def test_resource_memory_change_changes_pod_template_fingerprint() -> None:
    baseline = _template_payload()
    changed = copy.deepcopy(baseline)
    changed["spec"]["containers"][0]["resources"]["limits"][
        "memory"
    ] = "6Mi"

    assert _fingerprint(changed) != _fingerprint(baseline)


def test_environment_change_changes_fingerprint_without_returning_values() -> None:
    baseline = _template_payload()
    changed = copy.deepcopy(baseline)
    changed["spec"]["containers"][0]["env"][0]["value"] = (
        "different-environment-secret"
    )

    fingerprint = _fingerprint(changed)

    assert fingerprint != _fingerprint(baseline)
    assert fingerprint.startswith("sha256:")
    assert "environment-secret" not in fingerprint
    assert "orders-api-secret" not in fingerprint
    assert "api-token" not in fingerprint


def test_probe_change_changes_pod_template_fingerprint() -> None:
    baseline = _template_payload()
    changed = copy.deepcopy(baseline)
    changed["spec"]["containers"][0]["readiness_probe"]["http_get"][
        "path"
    ] = "/healthz"

    assert _fingerprint(changed) != _fingerprint(baseline)


class _ListApi:
    def __init__(
        self,
        *,
        deployments: list[object] | None = None,
    ) -> None:
        self.deployments = deployments or []

    def list_namespace(self):
        return SimpleNamespace(items=[])

    def list_node(self):
        return SimpleNamespace(items=[])

    def list_deployment_for_all_namespaces(self):
        return SimpleNamespace(items=self.deployments)

    def list_namespaced_deployment(self, namespace: str):
        return SimpleNamespace(items=self.deployments)

    def list_replica_set_for_all_namespaces(self):
        return SimpleNamespace(items=[])

    def list_namespaced_replica_set(self, namespace: str):
        return SimpleNamespace(items=[])

    def list_pod_for_all_namespaces(self):
        return SimpleNamespace(items=[])

    def list_namespaced_pod(self, namespace: str):
        return SimpleNamespace(items=[])

    def list_service_for_all_namespaces(self):
        return SimpleNamespace(items=[])

    def list_namespaced_service(self, namespace: str):
        return SimpleNamespace(items=[])

    def list_ingress_for_all_namespaces(self):
        return SimpleNamespace(items=[])

    def list_namespaced_ingress(self, namespace: str):
        return SimpleNamespace(items=[])

    def list_endpoint_slice_for_all_namespaces(self):
        return SimpleNamespace(items=[])

    def list_namespaced_endpoint_slice(self, namespace: str):
        return SimpleNamespace(items=[])

    def list_daemon_set_for_all_namespaces(self):
        return SimpleNamespace(items=[])

    def list_namespaced_daemon_set(self, namespace: str):
        return SimpleNamespace(items=[])

    def list_stateful_set_for_all_namespaces(self):
        return SimpleNamespace(items=[])

    def list_namespaced_stateful_set(self, namespace: str):
        return SimpleNamespace(items=[])

    def list_job_for_all_namespaces(self):
        return SimpleNamespace(items=[])

    def list_namespaced_job(self, namespace: str):
        return SimpleNamespace(items=[])

    def list_cron_job_for_all_namespaces(self):
        return SimpleNamespace(items=[])

    def list_namespaced_cron_job(self, namespace: str):
        return SimpleNamespace(items=[])

    def list_config_map_for_all_namespaces(self):
        return SimpleNamespace(items=[])

    def list_namespaced_config_map(self, namespace: str):
        return SimpleNamespace(items=[])


def test_collector_submits_only_image_and_template_fingerprint() -> None:
    payload = _template_payload()
    template = SimpleNamespace(
        spec=SimpleNamespace(
            containers=[
                SimpleNamespace(
                    image="nginx:1.27-alpine"
                )
            ]
        ),
        to_dict=lambda: copy.deepcopy(payload),
    )
    deployment = SimpleNamespace(
        metadata=SimpleNamespace(
            uid="deployment-uid",
            name="orders-api",
            namespace="orders",
            labels={"app": "orders-api"},
        ),
        spec=SimpleNamespace(
            template=template,
            selector=SimpleNamespace(
                match_labels={"app": "orders-api"}
            ),
            replicas=1,
        ),
        status=SimpleNamespace(
            available_replicas=1
        ),
    )
    api = _ListApi(deployments=[deployment])
    collector = object.__new__(KubernetesCollector)
    collector.config = AgentConfig(
        cluster_name="docker-desktop",
        namespaces=[],
    )
    collector.access_mode = "test"
    collector.core = api
    collector.apps = api
    collector.networking = api
    collector.discovery = api
    collector.batch = api

    first = collector.collect()["inventory"]["deployments"][0]
    second = collector.collect()["inventory"]["deployments"][0]
    serialized = json.dumps(first, sort_keys=True)

    assert first == second
    assert first["images"] == ["nginx:1.27-alpine"]
    assert first["pod_template_fingerprint"].startswith("sha256:")
    assert "raw-environment-secret" not in serialized
    assert "orders-api-secret" not in serialized
    assert "api-token" not in serialized
    assert "command" not in first
    assert "resources" not in first
    assert "env" not in first
