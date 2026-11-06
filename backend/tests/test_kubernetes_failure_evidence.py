from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.collectors.kubernetes_event_collector import (
    KubernetesEventCollector,
)
from app.models.signals import (
    SignalCategory,
    SignalSeverity,
)
from app.models.topology import (
    Entity,
    EntityType,
    GraphSnapshot,
)


NOW = datetime(
    2026,
    11,
    6,
    12,
    0,
    tzinfo=timezone.utc,
)


def test_incident_eligible_kubernetes_event_omits_raw_message() -> None:
    event = SimpleNamespace(
        reason="CreateContainerConfigError",
        type="Warning",
        action=None,
        message=(
            "couldn't find key PRIVATE_MODE in "
            "ConfigMap customer-private-config"
        ),
        event_time=NOW,
        first_timestamp=NOW,
        last_timestamp=NOW,
        series=None,
        count=1,
        reporting_controller="kubelet",
        reporting_component="kubelet",
        reporting_instance="worker-1",
        source=None,
        involved_object=SimpleNamespace(
            uid="pod-uid",
            kind="Pod",
            name="payment-api-abc-123",
            namespace="payments",
            api_version="v1",
            field_path="spec.containers{payment-api}",
        ),
        metadata=SimpleNamespace(
            uid="event-uid",
            namespace="payments",
            creation_timestamp=NOW,
        ),
    )

    class _CoreApi:
        def list_namespaced_event(self, namespace):
            assert namespace == "payments"
            return SimpleNamespace(items=[event])

    snapshot = GraphSnapshot(
        snapshot_id="snapshot:failure",
        collected_at=NOW,
        collector_name="test",
        collector_version="1",
        scope={
            "cluster": "production",
            "namespace": "payments",
        },
        entities=[
            Entity(
                id="entity:pod",
                entity_type=(
                    EntityType.RUNTIME_INSTANCE
                ),
                kind="KubernetesPod",
                name="payment-api-abc-123",
                source_system="kubernetes",
                external_id="pod-uid",
                observed_at=NOW,
                properties={
                    "namespace": "payments"
                },
            )
        ],
        relationships=[],
        evidence=[],
        metadata={},
    )
    collector = KubernetesEventCollector(
        core_api=_CoreApi(),
        cluster_name="production",
        namespace="payments",
    )

    signals = collector.collect(snapshot)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.reason == (
        "CreateContainerConfigError"
    )
    assert signal.severity == SignalSeverity.ERROR
    assert signal.category == (
        SignalCategory.CONFIGURATION
    )
    assert signal.involved_entity_id == "entity:pod"
    assert signal.raw_payload == {}
    assert "PRIVATE_MODE" not in signal.summary
    assert "customer-private-config" not in signal.summary
    assert signal.summary == (
        "Topo observed Kubernetes event reason "
        "CreateContainerConfigError on "
        "Pod/payment-api-abc-123."
    )
