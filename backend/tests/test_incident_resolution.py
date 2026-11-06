from datetime import datetime, timedelta, timezone

from app.models.incident_records import (
    IncidentRecordView,
    IncidentSeverity,
    IncidentStatus,
)
from app.models.recovery import (
    RecoveryCheckStatus,
    RecoveryStatus,
)
from app.models.topology import (
    Entity,
    EntityType,
    GraphSnapshot,
    Relationship,
    RelationshipType,
)
from app.services.incident_resolution import (
    build_incident_resolution_plan,
    evaluate_incident_resolution,
    select_resolution_snapshot,
)


NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
INCIDENT_AT = NOW - timedelta(minutes=5)
TENANT_ID = "tenant:check-resolve"
DEPLOYMENT_ID = "k8s:deployment:payment"
REPLICA_SET_ID = "k8s:replicaset:payment"
POD_ID = "k8s:pod:payment"


def _entity(
    entity_id: str,
    *,
    kind: str,
    name: str,
    properties: dict | None = None,
) -> Entity:
    return Entity(
        id=entity_id,
        entity_type=(
            EntityType.RUNTIME_INSTANCE
            if kind == "KubernetesPod"
            else EntityType.WORKLOAD
        ),
        kind=kind,
        name=name,
        source_system="kubernetes",
        external_id=entity_id,
        environment="local",
        observed_at=NOW,
        properties={
            "namespace": "topo-live-test",
            **(properties or {}),
        },
    )


def _relationship(
    relationship_id: str,
    source: str,
    target: str,
) -> Relationship:
    return Relationship(
        id=relationship_id,
        source_entity_id=source,
        target_entity_id=target,
        relationship_type=RelationshipType.OWNS,
        source_system="kubernetes",
        observed_at=NOW,
    )


def _snapshot(
    snapshot_id: str,
    *,
    collected_at: datetime,
    deployment_id: str = DEPLOYMENT_ID,
    cluster_name: str = "docker-desktop",
    failure_reason: str | None = None,
    include_ready: bool = True,
    include_pod_ready: bool = True,
    last_terminated_reason: str | None = None,
) -> GraphSnapshot:
    deployment = _entity(
        deployment_id,
        kind="KubernetesDeployment",
        name="payment-service",
        properties={
            "replicas": 1,
            "available_replicas": 1,
            "selector": {"app": "payment-service"},
        },
    )
    replica_set = _entity(
        REPLICA_SET_ID,
        kind="KubernetesReplicaSet",
        name="payment-service-abc",
        properties=(
            {"ready_replicas": 1}
            if include_ready
            else {}
        ),
    )
    pod_properties = {
        "phase": "Running",
        "container_statuses": [
            {
                "name": "payment-service",
                "ready": failure_reason is None,
                "waiting_reason": failure_reason,
                "last_terminated_reason": (
                    last_terminated_reason
                ),
            }
        ],
    }

    if include_pod_ready:
        pod_properties["ready"] = (
            failure_reason is None
        )

    pod = _entity(
        POD_ID,
        kind="KubernetesPod",
        name="payment-service-abc-123",
        properties=pod_properties,
    )
    return GraphSnapshot(
        snapshot_id=snapshot_id,
        collected_at=collected_at,
        collector_name="topo-agent-kubernetes",
        collector_version="0.7.0",
        scope={
            "cluster": cluster_name,
            "namespace": "topo-live-test",
        },
        entities=[deployment, replica_set, pod],
        relationships=[
            _relationship(
                "relationship:deployment-rs",
                deployment_id,
                REPLICA_SET_ID,
            ),
            _relationship(
                "relationship:rs-pod",
                REPLICA_SET_ID,
                POD_ID,
            ),
        ],
    )


def _incident() -> IncidentRecordView:
    return IncidentRecordView(
        incident_id="incident:payment",
        fingerprint="fingerprint:payment",
        status=IncidentStatus.OPEN,
        severity=IncidentSeverity.ERROR,
        title="Payment image pull failure",
        summary="The payment Pod cannot pull its image.",
        cluster_name="docker-desktop",
        namespace="topo-live-test",
        primary_signal_id="signal:payment",
        latest_signal_id="signal:payment",
        topology_snapshot_id="snapshot:incident",
        affected_entity_id=POD_ID,
        affected_object_kind="KubernetesPod",
        affected_object_name="payment-service-abc-123",
        first_observed_at=INCIDENT_AT,
        last_observed_at=INCIDENT_AT,
        latest_analysis_id="analysis:payment",
        top_hypothesis_title="Deployment image changed",
        top_hypothesis_score=0.9,
        occurrence_count=1,
        created_at=INCIDENT_AT,
        updated_at=INCIDENT_AT,
    )


def test_fresh_scoped_snapshot_allows_operator_resolution():
    incident = _incident()
    pinned = _snapshot(
        "snapshot:incident",
        collected_at=INCIDENT_AT,
        failure_reason="ImagePullBackOff",
    )
    healthy = _snapshot(
        "snapshot:healthy",
        collected_at=NOW - timedelta(minutes=1),
        last_terminated_reason="OOMKilled",
    )

    plan = build_incident_resolution_plan(
        tenant_id=TENANT_ID,
        incident=incident,
        pinned_snapshot=pinned,
        candidate_snapshot=healthy,
    )
    result = evaluate_incident_resolution(
        tenant_id=TENANT_ID,
        incident=incident,
        pinned_snapshot=pinned,
        candidate_snapshot=healthy,
        now=NOW,
    )

    assert plan.can_check is True
    assert plan.target.tenant_id == TENANT_ID
    assert plan.target.workload_entity_id == DEPLOYMENT_ID
    assert plan.evidence is not None
    assert plan.evidence.live_collection_requested is False
    assert len(plan.kubectl_commands) == 3
    assert result.status == RecoveryStatus.VERIFIED
    assert result.eligible_to_resolve is True
    assert result.passed_count == len(result.checks) == 6
    assert result.failed_count == result.unknown_count == 0
    pod_check = next(
        check
        for check in result.checks
        if check.code == "affected_pods_healthy"
    )
    assert pod_check.status == RecoveryCheckStatus.PASS
    assert result.resolution_note is not None
    assert "did not modify infrastructure" in result.resolution_note
    assert {
        check.source_id
        for check in result.checks
    } >= {healthy.snapshot_id, DEPLOYMENT_ID}


def test_failure_stale_or_unknown_evidence_never_allows_resolution():
    incident = _incident()
    pinned = _snapshot(
        "snapshot:incident",
        collected_at=INCIDENT_AT,
        failure_reason="ImagePullBackOff",
    )
    still_failed = _snapshot(
        "snapshot:still-failed",
        collected_at=NOW - timedelta(minutes=1),
        failure_reason="CrashLoopBackOff",
    )
    failed = evaluate_incident_resolution(
        tenant_id=TENANT_ID,
        incident=incident,
        pinned_snapshot=pinned,
        candidate_snapshot=still_failed,
        now=NOW,
    )
    pod_check = next(
        check
        for check in failed.checks
        if check.code == "affected_pods_healthy"
    )
    assert pod_check.status == RecoveryCheckStatus.FAIL
    assert failed.eligible_to_resolve is False

    stale = evaluate_incident_resolution(
        tenant_id=TENANT_ID,
        incident=incident,
        pinned_snapshot=pinned,
        candidate_snapshot=_snapshot(
            "snapshot:stale",
            collected_at=NOW - timedelta(minutes=20),
        ),
        now=NOW,
    )
    freshness = next(
        check
        for check in stale.checks
        if check.code == "snapshot_fresh"
    )
    assert freshness.status == RecoveryCheckStatus.FAIL
    assert stale.eligible_to_resolve is False

    missing_ready = evaluate_incident_resolution(
        tenant_id=TENANT_ID,
        incident=incident,
        pinned_snapshot=pinned,
        candidate_snapshot=_snapshot(
            "snapshot:missing-ready",
            collected_at=NOW - timedelta(minutes=1),
            include_ready=False,
        ),
        now=NOW,
    )
    replica_check = next(
        check
        for check in missing_ready.checks
        if check.code == "workload_replicas_ready"
    )
    assert replica_check.status == RecoveryCheckStatus.UNKNOWN
    assert missing_ready.status == RecoveryStatus.INCONCLUSIVE
    assert missing_ready.eligible_to_resolve is False

    historical_without_current_health = (
        evaluate_incident_resolution(
            tenant_id=TENANT_ID,
            incident=incident,
            pinned_snapshot=pinned,
            candidate_snapshot=_snapshot(
                "snapshot:historical-unknown",
                collected_at=(
                    NOW - timedelta(minutes=1)
                ),
                include_pod_ready=False,
                last_terminated_reason="OOMKilled",
            ),
            now=NOW,
        )
    )
    historical_pod_check = next(
        check
        for check in (
            historical_without_current_health.checks
        )
        if check.code == "affected_pods_healthy"
    )
    assert historical_pod_check.status == (
        RecoveryCheckStatus.UNKNOWN
    )
    assert (
        historical_without_current_health
        .eligible_to_resolve
        is False
    )


def test_scope_and_exact_workload_identity_are_fail_closed():
    incident = _incident()
    pinned = _snapshot(
        "snapshot:incident",
        collected_at=INCIDENT_AT,
    )
    foreign_cluster = _snapshot(
        "snapshot:foreign",
        collected_at=NOW - timedelta(minutes=1),
        cluster_name="other-cluster",
    )
    assert select_resolution_snapshot(
        incident=incident,
        snapshots=[foreign_cluster],
    ) is None

    recreated = _snapshot(
        "snapshot:recreated",
        collected_at=NOW - timedelta(minutes=1),
        deployment_id="k8s:deployment:replacement-uid",
    )
    result = evaluate_incident_resolution(
        tenant_id=TENANT_ID,
        incident=incident,
        pinned_snapshot=pinned,
        candidate_snapshot=recreated,
        now=NOW,
    )
    target_check = next(
        check
        for check in result.checks
        if check.code == "target_present"
    )
    assert target_check.status == RecoveryCheckStatus.FAIL
    assert result.eligible_to_resolve is False


def test_missing_pinned_topology_keeps_plan_pending():
    plan = build_incident_resolution_plan(
        tenant_id=TENANT_ID,
        incident=_incident(),
        pinned_snapshot=None,
        candidate_snapshot=_snapshot(
            "snapshot:healthy",
            collected_at=NOW - timedelta(minutes=1),
        ),
    )
    assert plan.can_check is False
    assert plan.target.workload_entity_id is None
    assert "incident-time topology" in (plan.limitation or "")
    assert plan.infrastructure_mutation is False
