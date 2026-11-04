from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from authorization_test_support import tenant_admin_authorization
from domain_tenant_fixtures import TEST_TENANT, seed_domain_tenant
from app.db.database import Base
from app.db.models import (
    ChangeEntityLinkRecord,
    ChangeEventRecord,
    ChangeRecord,
    IncidentRecord,
    SignalRecord,
    SnapshotRecord,
)
from app.demo_seed import (
    BASELINE_SNAPSHOT_ID,
    DEPLOYMENT_CHANGE_SNAPSHOT_ID,
    FAILURE_SNAPSHOT_ID,
    PAYMENT_DEPLOYMENT_ID,
    PAYMENT_POD_ID,
    _deployment_change_snapshot,
    _failure_snapshot,
)
from app.models.changes import ChangeCategory, ChangeImportance
from app.models.change_events import ChangeEventKind
from app.models.lifecycle_automation import TopologyCheckpointReason
from app.models.topology import RelationshipType
from app.repositories.causal_analysis_repository import latest_causal_analysis
from app.repositories.snapshot_repository import load_snapshot
from app.security.authorization_enforcement import bind_authorization_context
from app.services.continuous_lifecycle import (
    failure_signals_from_snapshot,
    ingest_failure_signal_batch,
)
from app.services.sample_topology import build_sample_snapshot
from app.services.topology_checkpoint import persist_topology_checkpoint


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine)
    session = Session(engine)
    bind_authorization_context(
        tenant_admin_authorization(session, TEST_TENANT)
    )
    return session


def _entity(snapshot, entity_id: str):
    return next(entity for entity in snapshot.entities if entity.id == entity_id)


def test_demo_seed_models_deployment_change_before_runtime_failure() -> None:
    baseline = build_sample_snapshot().model_copy(
        update={"snapshot_id": BASELINE_SNAPSHOT_ID}
    )
    deployment_change = _deployment_change_snapshot(baseline)
    failure = _failure_snapshot(deployment_change)

    assert [
        baseline.snapshot_id,
        deployment_change.snapshot_id,
        failure.snapshot_id,
    ] == [
        BASELINE_SNAPSHOT_ID,
        DEPLOYMENT_CHANGE_SNAPSHOT_ID,
        FAILURE_SNAPSHOT_ID,
    ]
    assert (
        baseline.collected_at
        < deployment_change.collected_at
        < failure.collected_at
    )
    assert _entity(baseline, PAYMENT_DEPLOYMENT_ID).properties[
        "containers"
    ][0]["image"] == "payment-service:v1"
    assert _entity(deployment_change, PAYMENT_DEPLOYMENT_ID).properties[
        "containers"
    ][0]["image"] == "payment-service:v2"
    assert _entity(failure, PAYMENT_DEPLOYMENT_ID).properties[
        "containers"
    ][0]["image"] == "payment-service:v2"
    assert _entity(failure, PAYMENT_POD_ID).properties[
        "container_statuses"
    ] == [{"waiting_reason": "CrashLoopBackOff"}]
    assert any(
        relationship.source_entity_id == PAYMENT_DEPLOYMENT_ID
        and relationship.target_entity_id == PAYMENT_POD_ID
        and relationship.relationship_type == RelationshipType.RUNS
        for relationship in failure.relationships
    )


def test_demo_seed_persists_deployment_evidence_then_evaluates_it_for_failure() -> None:
    session = _session()
    baseline = build_sample_snapshot().model_copy(
        update={"snapshot_id": BASELINE_SNAPSHOT_ID}
    )
    deployment_change = _deployment_change_snapshot(baseline)
    failure = _failure_snapshot(deployment_change)

    baseline_checkpoint = persist_topology_checkpoint(
        session,
        snapshot=baseline,
        reason=TopologyCheckpointReason.MANUAL,
        derive_changes=False,
        force=True,
        tenant_id=TEST_TENANT,
    )
    deployment_checkpoint = persist_topology_checkpoint(
        session,
        snapshot=deployment_change,
        reason=TopologyCheckpointReason.MANUAL,
        derive_changes=True,
        force=True,
        tenant_id=TEST_TENANT,
    )
    failure_checkpoint = persist_topology_checkpoint(
        session,
        snapshot=failure,
        reason=TopologyCheckpointReason.MANUAL,
        derive_changes=True,
        force=True,
        tenant_id=TEST_TENANT,
    )

    assert baseline_checkpoint.created is True
    assert deployment_checkpoint.created is True
    assert failure_checkpoint.created is True
    assert session.scalars(select(SnapshotRecord)).all()
    assert len(session.scalars(select(SnapshotRecord)).all()) == 3

    deployment_record = next(
        record
        for record in session.scalars(select(ChangeRecord)).all()
        if record.entity_id == PAYMENT_DEPLOYMENT_ID
    )
    assert deployment_record.category == ChangeCategory.DEPLOYMENT.value
    assert deployment_record.importance == ChangeImportance.HIGH.value
    assert deployment_record.from_snapshot_id == BASELINE_SNAPSHOT_ID
    assert deployment_record.to_snapshot_id == DEPLOYMENT_CHANGE_SNAPSHOT_ID

    deployment_event = session.scalar(
        select(ChangeEventRecord).where(
            ChangeEventRecord.origin_change_id == deployment_record.change_id
        )
    )
    assert deployment_event is not None
    assert deployment_event.kind == ChangeEventKind.DEPLOYMENT.value
    assert deployment_event.risk_score == 80
    assert session.scalar(
        select(ChangeEntityLinkRecord).where(
            ChangeEntityLinkRecord.event_id == deployment_event.event_id,
            ChangeEntityLinkRecord.entity_id == PAYMENT_DEPLOYMENT_ID,
        )
    ) is not None

    persisted_failure = load_snapshot(
        session,
        FAILURE_SNAPSHOT_ID,
        tenant_id=TEST_TENANT,
    )
    assert persisted_failure is not None
    signals = failure_signals_from_snapshot(persisted_failure)
    assert len(signals) == 1
    assert signals[0].reason == "CrashLoopBackOff"
    assert signals[0].first_observed_at == failure.collected_at

    batch = ingest_failure_signal_batch(
        session,
        signals=signals,
        tenant_id=TEST_TENANT,
    )
    assert batch.incident_created_count == 1
    assert len(session.scalars(select(SignalRecord)).all()) == 1

    incident = session.scalar(select(IncidentRecord))
    assert incident is not None
    assert incident.topology_snapshot_id == FAILURE_SNAPSHOT_ID
    assert incident.affected_entity_id == PAYMENT_POD_ID

    analysis = latest_causal_analysis(
        session,
        incident_id=incident.incident_id,
        tenant_id=TEST_TENANT,
    )
    assert analysis is not None
    deployment_audit = next(
        audit
        for audit in analysis.candidate_selection_audit
        if audit.origin_change_id == deployment_record.change_id
    )
    assert deployment_audit.selected_for_hypothesis is True
    assert analysis.top_hypothesis is not None
    assert analysis.top_hypothesis.target_event_id == deployment_event.event_id
    assert analysis.top_hypothesis.affected_entity_id == PAYMENT_POD_ID
    assert analysis.top_hypothesis.hypothesis_id in analysis.supported_hypothesis_ids
