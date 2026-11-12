from __future__ import annotations

import json
from types import SimpleNamespace

from topo_agent.collector import (
    KubernetesCollector,
)
from topo_agent.config import AgentConfig


class _Api:
    def __init__(self, pod: object) -> None:
        self.pod = pod

    def __getattr__(self, name: str):
        def list_resources(*args, **kwargs):
            items = (
                [self.pod]
                if name
                in {
                    "list_pod_for_all_namespaces",
                    "list_namespaced_pod",
                }
                else []
            )
            return SimpleNamespace(items=items)

        return list_resources


def _container_status(
    *,
    name: str,
    waiting_reason: str | None = None,
    terminated_reason: str | None = None,
    last_terminated_reason: str | None = None,
) -> SimpleNamespace:
    def detail(reason: str | None):
        return (
            SimpleNamespace(
                reason=reason,
                message=(
                    "SECRET_TOKEN=must-never-be-persisted"
                ),
            )
            if reason
            else None
        )

    return SimpleNamespace(
        name=name,
        image="example.invalid/payment:v2",
        ready=False,
        restart_count=3,
        container_id=None,
        state=SimpleNamespace(
            waiting=detail(waiting_reason),
            terminated=detail(terminated_reason),
        ),
        last_state=SimpleNamespace(
            terminated=detail(
                last_terminated_reason
            )
        ),
    )


def _collector() -> KubernetesCollector:
    pod = SimpleNamespace(
        metadata=SimpleNamespace(
            uid="pod-uid",
            name="payment-api-abc-123",
            namespace="payments",
            labels={"app": "payment-api"},
            owner_references=[],
        ),
        spec=SimpleNamespace(
            node_name="worker-1",
            containers=[
                SimpleNamespace(
                    image="example.invalid/payment:v2"
                )
            ],
        ),
        status=SimpleNamespace(
            phase="Running",
            pod_ip="10.0.0.8",
            conditions=[],
            container_statuses=[
                _container_status(
                    name="payment-api",
                    waiting_reason=(
                        "CrashLoopBackOff"
                    ),
                    last_terminated_reason=(
                        "OOMKilled"
                    ),
                )
            ],
            init_container_statuses=[
                _container_status(
                    name="migration",
                    waiting_reason=(
                        "CreateContainerConfigError"
                    ),
                )
            ],
            ephemeral_container_statuses=[
                _container_status(
                    name="debugger",
                    terminated_reason=(
                        "CreateContainerError"
                    ),
                )
            ],
        ),
    )
    api = _Api(pod)
    collector = object.__new__(
        KubernetesCollector
    )
    collector.config = AgentConfig(
        cluster_name="production",
        namespaces=[],
    )
    collector.access_mode = "test"
    collector.core = api
    collector.apps = api
    collector.networking = api
    collector.discovery = api
    collector.batch = api
    return collector


def test_collector_preserves_structured_container_failure_reasons() -> None:
    collector = _collector()

    first = collector.collect()["inventory"]["pods"][0]
    second = collector.collect()["inventory"]["pods"][0]
    statuses = first["container_statuses"]

    assert first == second
    assert statuses == [
        {
            "name": "payment-api",
            "container_type": "container",
            "image": "example.invalid/payment:v2",
            "ready": False,
            "restart_count": 3,
            "waiting_reason": "CrashLoopBackOff",
            "terminated_reason": None,
            "last_terminated_reason": "OOMKilled",
        },
        {
            "name": "migration",
            "container_type": "init_container",
            "image": "example.invalid/payment:v2",
            "ready": False,
            "restart_count": 3,
            "waiting_reason": (
                "CreateContainerConfigError"
            ),
            "terminated_reason": None,
            "last_terminated_reason": None,
        },
        {
            "name": "debugger",
            "container_type": (
                "ephemeral_container"
            ),
            "image": "example.invalid/payment:v2",
            "ready": False,
            "restart_count": 3,
            "waiting_reason": None,
            "terminated_reason": (
                "CreateContainerError"
            ),
            "last_terminated_reason": None,
        },
    ]
    serialized = json.dumps(
        first,
        sort_keys=True,
    )
    assert "SECRET_TOKEN" not in serialized
    assert "must-never-be-persisted" not in serialized
    assert "message" not in serialized
