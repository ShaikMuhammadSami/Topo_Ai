from datetime import datetime, timezone

import pytest

from app.models.topology import (
    Entity,
    EntityType,
    GraphSnapshot,
)
from app.services import network_dependency_analysis
from app.services.network_dependency_analysis import (
    _endpoint_slice_counts,
    analyze_network_dependencies,
)

OBSERVED_AT = datetime(2026, 11, 6, tzinfo=timezone.utc)


def _entity(entity_id, kind, name, properties):
    return Entity(
        id=entity_id,
        entity_type=EntityType.NETWORK,
        kind=kind,
        name=name,
        source_system="kubernetes",
        observed_at=OBSERVED_AT,
        properties=properties,
    )


def _analyze(monkeypatch, entities):
    snapshot = GraphSnapshot(
        snapshot_id="snapshot:network-test",
        collected_at=OBSERVED_AT,
        collector_name="test",
        collector_version="0",
        entities=entities,
    )
    monkeypatch.setattr(
        network_dependency_analysis,
        "load_snapshot",
        lambda **_: snapshot,
    )
    result = analyze_network_dependencies(
        session=None,
        snapshot_id=snapshot.snapshot_id,
        tenant_id="tenant:test",
    )
    return {(issue.code, issue.entity_name) for issue in result.issues}


@pytest.mark.parametrize(
    ("properties", "expected"),
    [
        ({"ready_endpoint_count": 2, "total_endpoint_count": 3}, (2, 3)),
        ({"endpoints": [{"ready": True}, {"ready": None}, {"ready": False}]}, (2, 3)),
        ({"endpoints": []}, (0, 0)),
        ({}, (0, 0)),
    ],
)
def test_endpoint_slice_counts(properties, expected):
    assert _endpoint_slice_counts(properties) == expected


def test_agent_endpoint_slices_use_endpoint_ready_conditions(monkeypatch):
    issues = _analyze(
        monkeypatch,
        [
            _entity(
                "slice:healthy",
                "KubernetesEndpointSlice",
                "kube-dns-abcde",
                {
                    "namespace": "kube-system",
                    "service_name": "kube-dns",
                    "endpoints": [{"ready": True}, {"ready": True}],
                },
            ),
            _entity(
                "slice:down",
                "KubernetesEndpointSlice",
                "checkout-api-fghij",
                {
                    "namespace": "shop",
                    "service_name": "checkout-api",
                    "endpoints": [{"ready": False}],
                },
            ),
        ],
    )

    assert ("no_ready_endpoints", "kube-dns-abcde") not in issues
    assert ("no_ready_endpoints", "checkout-api-fghij") in issues


def test_selectorless_service_with_ready_slice_has_backends(monkeypatch):
    issues = _analyze(
        monkeypatch,
        [
            _entity(
                "service:kubernetes",
                "KubernetesService",
                "kubernetes",
                {"namespace": "default", "selector": {}},
            ),
            _entity(
                "slice:kubernetes",
                "KubernetesEndpointSlice",
                "kubernetes",
                {
                    "namespace": "default",
                    "service_name": "kubernetes",
                    "endpoints": [{"ready": True, "target_uid": None}],
                },
            ),
            _entity(
                "service:orphan",
                "KubernetesService",
                "orphan",
                {"namespace": "default", "selector": {"app": "orphan"}},
            ),
        ],
    )

    assert ("service_without_backends", "kubernetes") not in issues
    assert ("service_without_backends", "orphan") in issues
