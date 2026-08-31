from __future__ import annotations
from domain_tenant_fixtures import TEST_TENANT, seed_domain_tenant

import importlib
import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.repositories.change_event_repository as change_events
from app.db.database import Base
from app.db.models import IncidentRecord, SnapshotRecord
from app.models.change_events import (
    ChangeEventCreate,
    ChangeEventEntityReference,
    ChangeEventKind,
    ChangeEventSource,
)
from app.models.signals import (
    NormalizedSignal,
    SignalCategory,
    SignalSeverity,
    SignalType,
)
from app.models.temporal import (
    TEMPORAL_VERSION,
    TemporalMetadata,
    TemporalStatus,
    TimeOrigin,
    TimeQuality,
)
from app.models.topology import (
    Entity,
    EntityType,
    GraphSnapshot,
    Relationship,
    RelationshipType,
)
from app.repositories.change_event_repository import (
    change_event_view,
    ingest_change_event,
    load_change_event,
)
from app.repositories.signal_repository import save_signals
from app.repositories.snapshot_repository import load_snapshot, save_snapshot
from app.services.causal_rca import ALGORITHM_VERSION, _snapshot_for_incident
from app.services.external_change_normalizers import (
    normalize_github,
    normalize_terraform_cloud,
)
from app.services.incident_change_analysis import analyze_incident_change_events
from app.services.snapshot_diff import compare_snapshots
from app.services.change_normalizer import normalize_snapshot_changes
from app.services.temporal_semantics import (
    build_temporal_metadata,
    change_event_temporal,
    incident_operational_time,
    legacy_temporal_metadata,
    parse_utc,
    safe_snapshot_record_at_or_before,
)

UTC = timezone.utc
CHANGE_AT = datetime(2026, 8, 20, 10, 1, tzinfo=UTC)
SNAPSHOT_AT = datetime(2026, 8, 20, 10, 2, tzinfo=UTC)
INCIDENT_AT = datetime(2026, 8, 20, 10, 3, tzinfo=UTC)
RECEIVED_AT = datetime(2026, 8, 20, 10, 8, tzinfo=UTC)


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine)
    return Session(engine)


def _snapshot(
    snapshot_id: str,
    collected_at: datetime,
    *,
    cluster: str = "prod",
    namespace: str = "payments",
    temporal_offset: int = 0,
) -> GraphSnapshot:
    observed = collected_at + timedelta(seconds=temporal_offset)
    return GraphSnapshot(
        snapshot_id=snapshot_id,
        collected_at=collected_at,
        collector_name="tc3-test",
        collector_version="1",
        scope={"cluster": cluster, "namespace": namespace},
        entities=[
            Entity(
                id="entity:deployment:payments",
                entity_type=EntityType.WORKLOAD,
                kind="KubernetesDeployment",
                name="payments",
                source_system="kubernetes",
                external_id="deployment-uid",
                observed_at=observed,
                properties={"namespace": namespace, "image": "pay:v1"},
            )
        ],
        relationships=[],
        evidence=[],
    )


def _signal() -> NormalizedSignal:
    return NormalizedSignal(
        signal_id="signal:tc3",
        fingerprint="signal-fingerprint:tc3",
        signal_type=SignalType.KUBERNETES_EVENT,
        severity=SignalSeverity.ERROR,
        category=SignalCategory.HEALTH,
        source_system="kubernetes",
        title="CrashLoopBackOff on payments",
        summary="payments failed",
        reason="CrashLoopBackOff",
        first_observed_at=INCIDENT_AT,
        last_observed_at=INCIDENT_AT,
        cluster_name="prod",
        namespace="payments",
        topology_snapshot_id="snapshot:incident",
        involved_entity_id="entity:deployment:payments",
        involved_object_kind="Deployment",
        involved_object_name="payments",
        temporal=TemporalMetadata(
            effective_at=INCIDENT_AT,
            source_event_at=INCIDENT_AT,
            observed_at=INCIDENT_AT + timedelta(seconds=20),
            time_origin=TimeOrigin.SOURCE_REPORTED,
            time_quality=TimeQuality.EXACT,
            source_field="KubernetesEvent.first_timestamp",
            source_time_authoritative=True,
            status=TemporalStatus.PARTIAL,
        ),
    )


def _incident(*, snapshot_id: str | None = "snapshot:incident") -> IncidentRecord:
    return IncidentRecord(
        incident_id="incident:tc3",
        fingerprint="incident-fingerprint:tc3",
        status="investigating",
        severity="error",
        title="payments unavailable",
        summary="payments failed",
        cluster_name="prod",
        namespace="payments",
        primary_signal_id="signal:tc3",
        latest_signal_id="signal:tc3",
        topology_snapshot_id=snapshot_id,
        affected_entity_id="entity:deployment:payments",
        affected_object_kind="Deployment",
        affected_object_name="payments",
        first_observed_at=INCIDENT_AT.isoformat(),
        last_observed_at=INCIDENT_AT.isoformat(),
        created_at=(INCIDENT_AT + timedelta(minutes=1)).isoformat(),
        updated_at=(INCIDENT_AT + timedelta(minutes=1)).isoformat(),
        tenant_id=TEST_TENANT,
    )


def _event(
    *,
    external_id: str,
    occurred_at: datetime,
    source: ChangeEventSource = ChangeEventSource.GITHUB,
) -> ChangeEventCreate:
    return ChangeEventCreate(
        source=source,
        kind=ChangeEventKind.DEPLOYMENT,
        external_id=external_id,
        title="payments deployment",
        occurred_at=occurred_at.isoformat(),
        cluster_name="prod",
        namespace="payments",
        entity_refs=[
            ChangeEventEntityReference(
                entity_id="entity:deployment:payments",
                kind="KubernetesDeployment",
                name="payments",
                namespace="payments",
                cluster_name="prod",
            )
        ],
    )


def _persist_incident_fixture(session: Session) -> IncidentRecord:
    save_snapshot(
        session, _snapshot("snapshot:incident", SNAPSHOT_AT), tenant_id=TEST_TENANT
    )
    save_signals(session, [_signal()], tenant_id=TEST_TENANT)
    incident = _incident()
    session.add(incident)
    session.commit()
    return incident


def test_source_observed_and_recorded_times_are_distinct(monkeypatch) -> None:
    session = _session()
    recorded_at = RECEIVED_AT + timedelta(seconds=30)
    monkeypatch.setattr(
        change_events,
        "utc_now_iso",
        lambda: recorded_at.isoformat(),
    )
    receipt = ingest_change_event(
        session,
        request=_event(external_id="github:late", occurred_at=CHANGE_AT),
        source_time_trusted=True,
        observed_at=RECEIVED_AT.isoformat(),
        auto_correlate=False,
        tenant_id=TEST_TENANT,
    )
    record = load_change_event(
        session, event_id=receipt.event_id, tenant_id=TEST_TENANT
    )
    assert record is not None
    temporal = change_event_temporal(record)
    assert temporal.source_event_at == CHANGE_AT
    assert temporal.effective_at == CHANGE_AT
    assert temporal.observed_at == RECEIVED_AT
    assert temporal.recorded_at == recorded_at
    assert record.occurred_at == CHANGE_AT.isoformat()
    assert record.received_at == RECEIVED_AT.isoformat()


def test_untrusted_client_time_is_preserved_but_not_authoritative(
    monkeypatch,
) -> None:
    session = _session()
    monkeypatch.setattr(
        change_events,
        "utc_now_iso",
        lambda: RECEIVED_AT.isoformat(),
    )
    receipt = ingest_change_event(
        session,
        request=_event(external_id="manual:claim", occurred_at=CHANGE_AT),
        auto_correlate=False,
        tenant_id=TEST_TENANT,
    )
    record = load_change_event(
        session, event_id=receipt.event_id, tenant_id=TEST_TENANT
    )
    assert record is not None
    temporal = change_event_temporal(record)
    assert temporal.source_event_at == CHANGE_AT
    assert temporal.source_time_authoritative is False
    assert temporal.effective_at == RECEIVED_AT
    assert temporal.time_origin == TimeOrigin.INGESTION_FALLBACK
    assert temporal.time_quality == TimeQuality.FALLBACK


def test_missing_source_time_has_explicit_fallback() -> None:
    temporal = build_temporal_metadata(
        source_event_at=None,
        observed_at=RECEIVED_AT,
        recorded_at=RECEIVED_AT + timedelta(seconds=1),
        source_time_trusted=True,
        source_field="provider.missing",
    )
    assert temporal.effective_at == RECEIVED_AT
    assert temporal.source_event_at is None
    assert temporal.time_origin == TimeOrigin.INGESTION_FALLBACK
    assert temporal.time_quality == TimeQuality.FALLBACK


def test_naive_new_timestamp_is_not_authoritative() -> None:
    temporal = build_temporal_metadata(
        source_event_at="2026-08-20T10:01:00",
        observed_at=RECEIVED_AT,
        recorded_at=RECEIVED_AT,
        source_time_trusted=True,
    )
    assert temporal.source_event_at is None
    assert temporal.effective_at == RECEIVED_AT
    assert temporal.source_time_authoritative is False


def test_temporal_model_rejects_naive_times() -> None:
    with pytest.raises(ValidationError):
        TemporalMetadata(
            effective_at=datetime(2026, 8, 20, 10, 1),
            time_origin=TimeOrigin.SOURCE_REPORTED,
            time_quality=TimeQuality.EXACT,
        )


def test_aware_offsets_normalize_to_utc() -> None:
    parsed = parse_utc("2026-08-20T15:31:00+05:30")
    assert parsed == CHANGE_AT
    assert parsed.tzinfo == UTC


def test_legacy_time_is_readable_without_fabricated_source_time() -> None:
    temporal = legacy_temporal_metadata(
        effective_at="2026-08-20T10:01:00"
    )
    assert temporal.effective_at == CHANGE_AT
    assert temporal.source_event_at is None
    assert temporal.status == TemporalStatus.LEGACY_UNSPECIFIED
    assert temporal.time_origin == TimeOrigin.LEGACY_UNKNOWN


def test_snapshot_collection_and_persistence_are_distinct() -> None:
    session = _session()
    save_snapshot(
        session, _snapshot("snapshot:temporal", SNAPSHOT_AT), tenant_id=TEST_TENANT
    )
    record = session.get(SnapshotRecord, (TEST_TENANT, "snapshot:temporal"))
    loaded = load_snapshot(session, "snapshot:temporal", tenant_id=TEST_TENANT)
    assert record is not None and loaded is not None
    assert loaded.collected_at == SNAPSHOT_AT
    assert loaded.temporal is not None
    assert loaded.temporal.observed_at == SNAPSHOT_AT
    assert loaded.temporal.recorded_at == parse_utc(record.created_at)
    assert loaded.temporal.time_quality == TimeQuality.BOUNDED


def test_relationship_observation_does_not_invent_validity() -> None:
    session = _session()
    snapshot = _snapshot("snapshot:edge", SNAPSHOT_AT)
    snapshot.relationships.append(
        Relationship(
            id="relationship:owner",
            source_entity_id="entity:deployment:payments",
            target_entity_id="entity:deployment:payments",
            relationship_type=RelationshipType.OWNS,
            source_system="kubernetes",
            observed_at=SNAPSHOT_AT,
        )
    )
    save_snapshot(session, snapshot, tenant_id=TEST_TENANT)
    edge = load_snapshot(session, "snapshot:edge", tenant_id=TEST_TENANT).relationships[
        0
    ]
    assert edge.temporal is not None
    assert edge.temporal.observed_at == SNAPSHOT_AT
    assert edge.temporal.valid_from is None
    assert edge.temporal.valid_to is None


def test_signal_source_observation_and_backend_record_time() -> None:
    session = _session()
    save_snapshot(session, _snapshot("snapshot:incident", SNAPSHOT_AT), tenant_id=TEST_TENANT)
    save_signals(session, [_signal()], tenant_id=TEST_TENANT)
    from app.db.models import SignalRecord

    record = session.get(SignalRecord, (TEST_TENANT, "signal:tc3"))
    payload = NormalizedSignal.model_validate_json(record.payload_json)
    assert payload.temporal is not None
    assert payload.temporal.source_event_at == INCIDENT_AT
    assert payload.temporal.observed_at == INCIDENT_AT + timedelta(seconds=20)
    assert payload.temporal.recorded_at == parse_utc(record.created_at)


def test_incident_operational_time_uses_primary_signal_without_rewrite() -> None:
    session = _session()
    save_snapshot(session, _snapshot("snapshot:incident", SNAPSHOT_AT), tenant_id=TEST_TENANT)
    save_signals(session, [_signal()], tenant_id=TEST_TENANT)
    incident = _incident(snapshot_id=None)
    original = incident.first_observed_at
    session.add(incident)
    session.commit()
    assert (
        incident_operational_time(session, incident, tenant_id=TEST_TENANT)
        == INCIDENT_AT
    )
    assert incident.first_observed_at == original


def test_late_but_causal_change_is_pre_incident(monkeypatch) -> None:
    session = _session()
    incident = _persist_incident_fixture(session)
    original_pin = incident.topology_snapshot_id
    original_start = incident.first_observed_at
    monkeypatch.setattr(
        change_events,
        "utc_now_iso",
        lambda: RECEIVED_AT.isoformat(),
    )
    ingest_change_event(
        session,
        request=_event(external_id="cloudtrail:late", occurred_at=CHANGE_AT),
        source_time_trusted=True,
        observed_at=RECEIVED_AT.isoformat(),
        correlation_snapshot_id="snapshot:incident",
        tenant_id=TEST_TENANT,
    )
    result = analyze_incident_change_events(
        session, incident_id=incident.incident_id, tenant_id=TEST_TENANT
    )
    candidate = result.candidates[0]
    assert candidate.minutes_before_incident == 2.0
    assert candidate.event.temporal.source_event_at == CHANGE_AT
    session.refresh(incident)
    assert incident.first_observed_at == original_start
    assert incident.topology_snapshot_id == original_pin


def test_received_early_but_effective_late_is_post_incident(monkeypatch) -> None:
    session = _session()
    incident = _persist_incident_fixture(session)
    queued_at = CHANGE_AT
    effective_at = INCIDENT_AT + timedelta(minutes=2)
    monkeypatch.setattr(
        change_events,
        "utc_now_iso",
        lambda: (effective_at + timedelta(minutes=1)).isoformat(),
    )
    ingest_change_event(
        session,
        request=_event(external_id="pipeline:late-effective", occurred_at=effective_at),
        source_time_trusted=True,
        observed_at=queued_at.isoformat(),
        correlation_snapshot_id="snapshot:incident",
        tenant_id=TEST_TENANT,
    )
    result = analyze_incident_change_events(
        session, incident_id=incident.incident_id, tenant_id=TEST_TENANT
    )
    assert result.candidates[0].minutes_before_incident == -2.0


def test_explicit_incident_snapshot_has_priority_over_later_topology() -> None:
    session = _session()
    incident = _persist_incident_fixture(session)
    save_snapshot(
        session,
        _snapshot("snapshot:future", INCIDENT_AT + timedelta(minutes=5)),
        tenant_id=TEST_TENANT,
    )
    record, snapshot = _snapshot_for_incident(
        session, incident=incident, incident_time=INCIDENT_AT, tenant_id=TEST_TENANT
    )
    assert record.snapshot_id == "snapshot:incident"
    assert snapshot.snapshot_id == "snapshot:incident"
    assert incident.topology_snapshot_id == "snapshot:incident"


def test_safe_snapshot_selection_never_uses_future_latest() -> None:
    session = _session()
    save_snapshot(
        session,
        _snapshot("snapshot:future", INCIDENT_AT + timedelta(minutes=1)),
        tenant_id=TEST_TENANT,
    )
    assert (
        safe_snapshot_record_at_or_before(
            session,
            cluster_name="prod",
            namespace="payments",
            boundary_at=INCIDENT_AT,
            tenant_id=TEST_TENANT,
        )
        is None
    )


def test_safe_snapshot_selection_is_scope_bounded() -> None:
    session = _session()
    save_snapshot(
        session,
        _snapshot("snapshot:other", SNAPSHOT_AT, namespace="checkout"),
        tenant_id=TEST_TENANT,
    )
    assert (
        safe_snapshot_record_at_or_before(
            session,
            cluster_name="prod",
            namespace="payments",
            boundary_at=INCIDENT_AT,
            tenant_id=TEST_TENANT,
        )
        is None
    )


@pytest.mark.parametrize(
    "source",
    [
        ChangeEventSource.AWS_CLOUDTRAIL,
        ChangeEventSource.AZURE_ACTIVITY_LOG,
        ChangeEventSource.GCP_AUDIT_LOG,
    ],
)
def test_delayed_cloud_provider_time_orders_before_incident(
    monkeypatch,
    source: ChangeEventSource,
) -> None:
    session = _session()
    incident = _persist_incident_fixture(session)
    monkeypatch.setattr(
        change_events,
        "utc_now_iso",
        lambda: RECEIVED_AT.isoformat(),
    )
    ingest_change_event(
        session,
        request=_event(
            external_id=f"{source.value}:delayed",
            occurred_at=CHANGE_AT,
            source=source,
        ),
        source_time_trusted=True,
        observed_at=RECEIVED_AT.isoformat(),
        correlation_snapshot_id="snapshot:incident",
        tenant_id=TEST_TENANT,
    )
    result = analyze_incident_change_events(
        session, incident_id=incident.incident_id, tenant_id=TEST_TENANT
    )
    assert result.candidates[0].minutes_before_incident == 2.0


def test_github_source_time_is_distinct_from_webhook_receipt(monkeypatch) -> None:
    event = normalize_github(
        event_type="push",
        payload={
            "after": "abc",
            "ref": "refs/heads/main",
            "repository": {"full_name": "acme/payments"},
            "head_commit": {"id": "abc", "message": "deploy", "timestamp": CHANGE_AT.isoformat()},
        },
        config={},
    )[0]
    assert event.occurred_at == CHANGE_AT.isoformat()
    assert event.metadata["_temporal"]["source_time_available"] is True
    session = _session()
    monkeypatch.setattr(change_events, "utc_now_iso", lambda: RECEIVED_AT.isoformat())
    receipt = ingest_change_event(
        session,
        request=event,
        source_time_trusted=True,
        observed_at=RECEIVED_AT.isoformat(),
        auto_correlate=False,
        tenant_id=TEST_TENANT,
    )
    temporal = change_event_temporal(
        load_change_event(session, event_id=receipt.event_id, tenant_id=TEST_TENANT)
    )
    assert temporal.source_event_at == CHANGE_AT
    assert temporal.observed_at == RECEIVED_AT


def test_github_actions_and_terraform_preserve_source_fields() -> None:
    workflow = normalize_github(
        event_type="workflow_run",
        payload={
            "repository": {"full_name": "acme/payments"},
            "workflow_run": {"id": 5, "name": "deploy", "status": "completed", "updated_at": CHANGE_AT.isoformat()},
        },
        config={},
    )[0]
    terraform = normalize_terraform_cloud(
        payload={
            "run_id": "run-1",
            "workspace_name": "prod",
            "run_created_at": CHANGE_AT.isoformat(),
            "notifications": [{"trigger": "run:completed", "run_status": "applied"}],
        },
        config={},
    )[0]
    assert workflow.occurred_at == CHANGE_AT.isoformat()
    assert "GitHubActions" in workflow.metadata["_temporal"]["source_field"]
    assert terraform.occurred_at == CHANGE_AT.isoformat()
    assert "Terraform" in terraform.metadata["_temporal"]["source_field"]


def test_temporal_metadata_does_not_change_entity_or_relationship_id() -> None:
    entity = _snapshot("snapshot:a", SNAPSHOT_AT).entities[0]
    enriched = entity.model_copy(
        update={
            "temporal": build_temporal_metadata(
                source_event_at=None,
                observed_at=SNAPSHOT_AT,
                recorded_at=RECEIVED_AT,
                source_time_trusted=False,
            )
        }
    )
    assert enriched.id == entity.id
    edge = Relationship(
        id="relationship:stable",
        source_entity_id=entity.id,
        target_entity_id=entity.id,
        relationship_type=RelationshipType.OWNS,
        source_system="kubernetes",
        observed_at=SNAPSHOT_AT,
    )
    assert edge.model_copy(update={"temporal": enriched.temporal}).id == edge.id


def test_temporal_metadata_does_not_create_snapshot_diff_or_change() -> None:
    before = _snapshot("snapshot:before", SNAPSHOT_AT, temporal_offset=0)
    after = _snapshot(
        "snapshot:after",
        SNAPSHOT_AT + timedelta(minutes=1),
        temporal_offset=30,
    )
    diff = compare_snapshots(before=before, after=after)
    assert diff.summary == {
        "added_entities": 0,
        "removed_entities": 0,
        "changed_entities": 0,
        "added_relationships": 0,
        "removed_relationships": 0,
        "changed_relationships": 0,
    }
    assert normalize_snapshot_changes(before, after) == []


def test_duplicate_source_event_dedupes_across_receipt_times(monkeypatch) -> None:
    session = _session()
    request = _event(external_id="github:stable", occurred_at=CHANGE_AT)
    monkeypatch.setattr(change_events, "utc_now_iso", lambda: RECEIVED_AT.isoformat())
    first = ingest_change_event(
        session,
        request=request,
        source_time_trusted=True,
        observed_at=RECEIVED_AT.isoformat(),
        auto_correlate=False,
        tenant_id=TEST_TENANT,
    )
    monkeypatch.setattr(
        change_events,
        "utc_now_iso",
        lambda: (RECEIVED_AT + timedelta(minutes=2)).isoformat(),
    )
    second = ingest_change_event(
        session,
        request=request,
        source_time_trusted=True,
        observed_at=(RECEIVED_AT + timedelta(minutes=2)).isoformat(),
        auto_correlate=False,
        tenant_id=TEST_TENANT,
    )
    assert second.event_id == first.event_id
    assert second.duplicate is True
    record = load_change_event(session, event_id=first.event_id, tenant_id=TEST_TENANT)
    assert change_event_temporal(record).observed_at == RECEIVED_AT


def test_legacy_change_event_view_does_not_fabricate_source_time() -> None:
    session = _session()
    request = _event(external_id="legacy:event", occurred_at=CHANGE_AT)
    receipt = ingest_change_event(
        session,
        request=request,
        source_time_trusted=True,
        auto_correlate=False,
        tenant_id=TEST_TENANT,
    )
    record = load_change_event(
        session, event_id=receipt.event_id, tenant_id=TEST_TENANT
    )
    metadata = json.loads(record.metadata_json)
    metadata.pop("temporal")
    record.metadata_json = json.dumps(metadata)
    session.commit()
    view = change_event_view(session, record=record, tenant_id=TEST_TENANT)
    assert view.occurred_at == record.occurred_at
    assert view.temporal.status == TemporalStatus.LEGACY_UNSPECIFIED
    assert view.temporal.source_event_at is None


def test_runtime_observation_temporal_contract_has_no_llm_dependency() -> None:
    import app.repositories.runtime_observability_repository as runtime_repo
    import app.services.temporal_semantics as temporal_service

    source = inspect.getsource(runtime_repo) + inspect.getsource(temporal_service)
    assert "llm" not in source.lower()
    assert "openai" not in source.lower()
    assert "TimeOrigin.RUNTIME_OBSERVED" in source


def test_rca_algorithm_and_non_temporal_weights_are_unchanged() -> None:
    import app.services.causal_rca as causal

    source = inspect.getsource(causal)
    assert ALGORITHM_VERSION == "13c-causal-v1"
    assert "candidate.score * 0.40" in source
    assert "+ topology_component * 25" in source
    assert "temporal_component * 15" in source
    assert "+ _kind_prior(" in source
    assert "+ lineage_component * 10" in source


def test_temporal_contract_json_is_valid_and_synchronized() -> None:
    path = (
        Path(__file__).parents[2]
        / "docs"
        / "architecture"
        / "truth-contract"
        / "temporal-semantics-contract.json"
    )
    contract = json.loads(path.read_text(encoding="utf-8"))
    assert contract["temporal_version"] == TEMPORAL_VERSION
    assert contract["snapshot_selection"]["latest_fallback"] is False
    for item in contract["critical_fields"]:
        module = importlib.import_module(item["module"])
        model = getattr(module, item["model"])
        field = item["field"]
        if hasattr(model, "model_fields"):
            assert field in model.model_fields, item
        else:
            assert field in model.__table__.columns, item


def test_contract_does_not_depend_on_execution_or_future_truth_blocks() -> None:
    import app.services.temporal_semantics as temporal_service

    source = inspect.getsource(temporal_service)
    assert "approval" not in source.lower()
    assert "execution" not in source.lower()
    assert "evidence_ledger" not in source.lower()
