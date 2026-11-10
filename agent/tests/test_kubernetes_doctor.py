from __future__ import annotations

from types import SimpleNamespace

from kubernetes.client.exceptions import ApiException

from topo_agent.collector import KubernetesCollector
from topo_agent.config import AgentConfig
from topo_agent.plugins.kubernetes import KubernetesPlugin


def _response(count: int = 0) -> SimpleNamespace:
    return SimpleNamespace(items=[object() for _ in range(count)])


def _collector(
    *,
    namespaces: list[str],
    core: object,
    apps: object,
) -> KubernetesCollector:
    collector = object.__new__(KubernetesCollector)
    collector.config = AgentConfig(
        cluster_name="doctor-test",
        namespaces=namespaces,
    )
    collector.access_mode = "test"
    collector.core = core
    collector.apps = apps
    return collector


def test_doctor_requires_cluster_namespace_pod_and_deployment_reads() -> None:
    core = SimpleNamespace(
        list_namespace=lambda **_: _response(1),
        list_pod_for_all_namespaces=lambda **_: _response(1),
    )
    apps = SimpleNamespace(
        list_deployment_for_all_namespaces=lambda **_: _response(1),
    )

    result = _collector(namespaces=[], core=core, apps=apps).doctor()

    assert result["kubernetes_access"] == "available"
    assert result["required_checks"] == {
        "namespaces": "available",
        "pods": "available",
        "deployments": "available",
    }
    assert result["probe_count"] == 3


def test_doctor_uses_namespaced_reads_for_namespace_scoped_access() -> None:
    observed: list[tuple[str, str]] = []

    def pod_read(*, namespace: str, limit: int) -> SimpleNamespace:
        observed.append(("pods", namespace))
        assert limit == 1
        return _response()

    def deployment_read(*, namespace: str, limit: int) -> SimpleNamespace:
        observed.append(("deployments", namespace))
        assert limit == 1
        return _response()

    core = SimpleNamespace(
        list_namespace=lambda **_: (_ for _ in ()).throw(
            AssertionError("cluster-wide namespace read is not permitted")
        ),
        list_namespaced_pod=pod_read,
    )
    apps = SimpleNamespace(
        list_namespaced_deployment=deployment_read,
    )

    result = _collector(
        namespaces=["payments"],
        core=core,
        apps=apps,
    ).doctor()

    assert result["kubernetes_access"] == "available"
    assert observed == [
        ("pods", "payments"),
        ("deployments", "payments"),
    ]


def test_doctor_does_not_accept_namespace_only_permissions() -> None:
    def forbidden(**_: object) -> SimpleNamespace:
        raise ApiException(status=403, reason="Forbidden")

    result = _collector(
        namespaces=[],
        core=SimpleNamespace(
            list_namespace=lambda **_: _response(1),
            list_pod_for_all_namespaces=forbidden,
        ),
        apps=SimpleNamespace(
            list_deployment_for_all_namespaces=forbidden,
        ),
    ).doctor()

    assert result["kubernetes_access"] == "denied"
    assert result["required_checks"] == {
        "namespaces": "available",
        "pods": "denied",
        "deployments": "denied",
    }


def test_doctor_reports_denied_when_required_discovery_read_is_forbidden() -> None:
    marker = "topo_agent_SYNTHETIC_KUBERNETES_ERROR_1234567890"

    def forbidden(**_: object) -> SimpleNamespace:
        raise ApiException(
            status=403,
            reason=f"Authorization: Bearer {marker}",
        )

    collector = _collector(
        namespaces=["payments"],
        core=SimpleNamespace(list_namespaced_pod=forbidden),
        apps=SimpleNamespace(list_namespaced_deployment=forbidden),
    )

    result = collector.doctor()

    assert result["kubernetes_access"] == "denied"
    assert set(result["required_checks"].values()) == {"denied"}
    assert marker not in repr(result)

    plugin = object.__new__(KubernetesPlugin)
    plugin.collector = collector
    diagnostic = plugin.doctor()
    assert diagnostic.status == "denied"
    assert "required read checks" in str(diagnostic.message)
    assert marker not in repr(diagnostic)


def test_doctor_reports_degraded_without_exposing_connectivity_errors() -> None:
    marker = "topo_agent_SYNTHETIC_CONNECT_ERROR_1234567890"

    def unavailable(**_: object) -> SimpleNamespace:
        raise RuntimeError(f"https://user:{marker}@cluster.example")

    result = _collector(
        namespaces=["payments"],
        core=SimpleNamespace(
            list_namespaced_pod=lambda **_: _response(),
        ),
        apps=SimpleNamespace(
            list_namespaced_deployment=unavailable,
        ),
    ).doctor()

    assert result["kubernetes_access"] == "degraded"
    assert result["required_checks"] == {
        "pods:payments": "available",
        "deployments:payments": "unavailable",
    }
    assert marker not in repr(result)


def test_doctor_reports_unavailable_when_no_required_read_connects() -> None:
    def unavailable(**_: object) -> SimpleNamespace:
        raise ConnectionError("cluster unavailable")

    result = _collector(
        namespaces=["payments"],
        core=SimpleNamespace(list_namespaced_pod=unavailable),
        apps=SimpleNamespace(list_namespaced_deployment=unavailable),
    ).doctor()

    assert result["kubernetes_access"] == "unavailable"
