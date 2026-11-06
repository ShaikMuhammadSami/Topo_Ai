from __future__ import annotations
from domain_tenant_fixtures import TEST_HEADERS, TEST_TENANT, seed_domain_tenant

import inspect
import json
from datetime import (
    datetime,
    timedelta,
    timezone,
)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.services.continuous_lifecycle as lifecycle
from app.db.database import Base
from app.db.models import (
    CausalAnalysisRecord,
    ChangeEventRecord,
    ChangeRecord,
    IncidentRecord,
    SignalRecord,
    SnapshotRecord,
    TopoAgentRecord,
    utc_now_iso,
)
from app.models.agents import AgentSnapshotSubmission
from app.main import app
from app.models.change_events import (
    ChangeEventCreate,
    ChangeEventKind,
    ChangeEventSource,
)
from app.models.incident_records import IncidentStatus
from app.models.lifecycle_automation import (
    AutomaticAnalysisState,
    AutomaticIncidentAction,
    TopologyCheckpointReason,
)
from app.models.signals import (
    NormalizedSignal,
    SignalCategory,
    SignalSeverity,
    SignalType,
)
from app.models.topology import (
    Entity,
    EntityType,
    GraphSnapshot,
)
from app.repositories.causal_analysis_repository import (
    latest_causal_analysis,
)
from app.repositories.incident_record_repository import (
    load_incident_record,
    update_incident_status,
)
from app.repositories.signal_repository import load_signal
from app.repositories.snapshot_repository import load_snapshot
from app.services.continuous_lifecycle import (
    failure_signals_from_snapshot,
    ingest_failure_signal_batch,
    reconcile_pending_incidents_for_checkpoint,
)
from app.services.agent_snapshot_ingest import (
    persist_agent_snapshot,
)
from app.services.incident_briefing import (
    build_incident_briefing,
)
from app.services.lifecycle_status import (
    build_incident_lifecycle_status,
)
from app.services.topology_checkpoint import (
    is_topology_affecting_change_event,
    persist_topology_checkpoint,
)
from app.security.authorization_enforcement import (
    authorize_agent_fixed_purpose,
    bind_authorization_context,
)
from authorization_test_support import tenant_admin_authorization

NOW = datetime(
    2026,
    8,
    17,
    10,
    0,
    tzinfo=timezone.utc,
)


def _session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine)
    session = Session(engine)
    bind_authorization_context(
        tenant_admin_authorization(session, TEST_TENANT)
    )
    return session


def _snapshot(
    snapshot_id: str,
    *,
    observed_at: datetime = NOW,
    image: str = "payment:v1",
    pod_name: str = "payment-api-abc-123",
    pod_uid: str = "pod-uid-1",
    failure_reason: str | None = None,
) -> GraphSnapshot:
    containers = [
        {
            "name": "payment",
            "image": image,
            "ready": (
                failure_reason is None
            ),
            "restart_count": (
                0 if failure_reason is None else 4
            ),
            "waiting_reason": failure_reason,
        }
    ]

    return GraphSnapshot(
        snapshot_id=snapshot_id,
        collected_at=observed_at,
        collector_name="test-agent",
        collector_version="1.0",
        scope={
            "cluster": "production",
            "namespace": "payments",
        },
        entities=[
            Entity(
                id="entity:deployment:payment",
                entity_type=EntityType.WORKLOAD,
                kind="KubernetesDeployment",
                name="payment-api",
                source_system="kubernetes",
                external_id="deployment-uid-1",
                observed_at=observed_at,
                properties={
                    "namespace": "payments",
                    "containers": [
                        {
                            "name": "payment",
                            "image": image,
                        }
                    ],
                },
            ),
            Entity(
                id=f"entity:pod:{pod_uid}",
                entity_type=(
                    EntityType.RUNTIME_INSTANCE
                ),
                kind="KubernetesPod",
                name=pod_name,
                source_system="kubernetes",
                external_id=pod_uid,
                observed_at=observed_at,
                properties={
                    "namespace": "payments",
                    "phase": "Running",
                    "ready": (
                        failure_reason is None
                    ),
                    "container_statuses": containers,
                },
            ),
        ],
        relationships=[],
        evidence=[],
        metadata={},
    )


def _signal(
    signal_id: str,
    *,
    observed_at: datetime = NOW,
    reason: str = "CrashLoopBackOff",
    pod_name: str = "payment-api-abc-123",
    pod_uid: str = "pod-uid-1",
    snapshot_id: str | None = "snapshot:one",
    severity: SignalSeverity = SignalSeverity.ERROR,
) -> NormalizedSignal:
    return NormalizedSignal(
        signal_id=signal_id,
        fingerprint=f"fingerprint:{signal_id}",
        signal_type=SignalType.KUBERNETES_EVENT,
        severity=severity,
        category=SignalCategory.HEALTH,
        source_system="kubernetes",
        title=f"{reason} on Pod/{pod_name}",
        summary=f"{pod_name} is failing.",
        reason=reason,
        first_observed_at=observed_at,
        last_observed_at=observed_at,
        occurrence_count=1,
        cluster_name="production",
        namespace="payments",
        topology_snapshot_id=snapshot_id,
        involved_object_uid=pod_uid,
        involved_object_kind="Pod",
        involved_object_name=pod_name,
    )


def _count(session: Session, model) -> int:
    return int(
        session.scalar(
            select(func.count()).select_from(model)
        )
        or 0
    )


def test_material_topology_change_checkpoints_and_promotes_change() -> None:
    session = _session()

    first = persist_topology_checkpoint(
        session,
        snapshot=_snapshot("snapshot:one"),
        reason=(TopologyCheckpointReason.PERIODIC_RECONCILE),
        tenant_id=TEST_TENANT,
    )
    second = persist_topology_checkpoint(
        session,
        snapshot=_snapshot(
            "snapshot:two",
            observed_at=(NOW + timedelta(seconds=45)),
            image="payment:v2",
        ),
        reason=(TopologyCheckpointReason.AUTOMATIC_CHANGE),
        trigger_event_ids=["event:deploy"],
        tenant_id=TEST_TENANT,
    )

    assert first.created is True
    assert second.created is True
    assert second.reason == (
        TopologyCheckpointReason.AUTOMATIC_CHANGE
    )
    assert second.detected_change_count > 0
    assert _count(session, SnapshotRecord) == 2
    assert _count(session, ChangeRecord) > 0
    assert _count(session, ChangeEventRecord) > 0


def test_identical_automatic_burst_reuses_checkpoint() -> None:
    session = _session()
    persist_topology_checkpoint(
        session,
        snapshot=_snapshot("snapshot:one"),
        reason=(TopologyCheckpointReason.AUTOMATIC_CHANGE),
        trigger_event_ids=["event:one"],
        tenant_id=TEST_TENANT,
    )
    result = persist_topology_checkpoint(
        session,
        snapshot=_snapshot(
            "snapshot:duplicate",
            observed_at=(NOW + timedelta(seconds=5)),
        ),
        reason=(TopologyCheckpointReason.AUTOMATIC_CHANGE),
        trigger_event_ids=[
            "event:one",
            "event:two",
        ],
        tenant_id=TEST_TENANT,
    )

    assert result.reused is True
    assert result.debounced is True
    assert result.snapshot_id == "snapshot:one"
    assert _count(session, SnapshotRecord) == 1


def test_correlated_failure_burst_reuses_safe_boundary_checkpoint() -> None:
    session = _session()
    first = persist_topology_checkpoint(
        session,
        snapshot=_snapshot("snapshot:boundary-one"),
        reason=(TopologyCheckpointReason.INCIDENT_BOUNDARY),
        trigger_signal_ids=["signal:one"],
        trigger_signal_observations={"signal:one": NOW.isoformat()},
        tenant_id=TEST_TENANT,
    )
    second = persist_topology_checkpoint(
        session,
        snapshot=_snapshot(
            "snapshot:boundary-two",
            observed_at=NOW + timedelta(seconds=10),
        ),
        reason=(TopologyCheckpointReason.INCIDENT_BOUNDARY),
        trigger_signal_ids=["signal:two"],
        trigger_signal_observations={
            "signal:two": (NOW + timedelta(seconds=5)).isoformat()
        },
        tenant_id=TEST_TENANT,
    )

    assert first.created is True
    assert second.reused is True
    assert second.snapshot_id == first.snapshot_id
    assert _count(session, SnapshotRecord) == 1


def test_non_topology_change_does_not_request_checkpoint(
) -> None:
    event = ChangeEventCreate(
        source=ChangeEventSource.GITHUB,
        kind=ChangeEventKind.CODE,
        title="README updated",
        occurred_at=NOW.isoformat(),
    )

    assert is_topology_affecting_change_event(
        event
    ) is False


def test_periodic_reconcile_and_manual_fallback_are_preserved() -> None:
    session = _session()
    periodic = persist_topology_checkpoint(
        session,
        snapshot=_snapshot("snapshot:periodic"),
        reason=(TopologyCheckpointReason.PERIODIC_RECONCILE),
        tenant_id=TEST_TENANT,
    )
    manual = persist_topology_checkpoint(
        session,
        snapshot=_snapshot(
            "snapshot:manual",
            observed_at=NOW + timedelta(minutes=1),
        ),
        reason=TopologyCheckpointReason.MANUAL,
        derive_changes=False,
        force=True,
        tenant_id=TEST_TENANT,
    )

    assert periodic.reason.value == (
        "periodic_reconcile"
    )
    assert manual.created is True
    assert manual.reason.value == "manual"
    assert _count(session, SnapshotRecord) == 2


def test_healthy_deployment_change_does_not_create_incident() -> None:
    session = _session()
    persist_topology_checkpoint(
        session,
        snapshot=_snapshot("snapshot:one"),
        reason=(TopologyCheckpointReason.PERIODIC_RECONCILE),
        tenant_id=TEST_TENANT,
    )
    persist_topology_checkpoint(
        session,
        snapshot=_snapshot(
            "snapshot:two",
            image="payment:v2",
            observed_at=NOW + timedelta(minutes=1),
        ),
        reason=(TopologyCheckpointReason.AUTOMATIC_CHANGE),
        tenant_id=TEST_TENANT,
    )

    assert _count(session, IncidentRecord) == 0


def test_supported_failure_state_creates_internal_incident_and_rca() -> None:
    session = _session()
    snapshot = _snapshot(
        "snapshot:one",
        failure_reason="CrashLoopBackOff",
    )
    persist_topology_checkpoint(
        session,
        snapshot=snapshot,
        reason=(TopologyCheckpointReason.INCIDENT_BOUNDARY),
        tenant_id=TEST_TENANT,
    )
    signals = failure_signals_from_snapshot(
        snapshot
    )
    result = ingest_failure_signal_batch(
        session, signals=signals, tenant_id=TEST_TENANT
    )

    assert len(signals) == 1
    assert result.incident_created_count == 1
    assert _count(session, IncidentRecord) == 1
    assert _count(session, CausalAnalysisRecord) == 1
    assert result.results[0].automatic_analysis_state in {
        AutomaticAnalysisState.COMPLETED,
        AutomaticAnalysisState
        .COMPLETED_NO_HYPOTHESIS,
    }


def test_snapshot_failure_reasons_include_supported_container_states() -> None:
    expected = {
        "CrashLoopBackOff",
        "CreateContainerConfigError",
        "CreateContainerError",
        "ErrImagePull",
        "ImagePullBackOff",
        "InvalidImageName",
    }

    for reason in expected:
        snapshot = _snapshot(
            f"snapshot:{reason}",
            failure_reason=reason,
        )
        assert {
            signal.reason
            for signal in failure_signals_from_snapshot(
                snapshot
            )
        } == {reason}

    recovered = _snapshot(
        "snapshot:recovered-oom"
    )
    recovered.entities[1].properties[
        "container_statuses"
    ][0]["last_terminated_reason"] = "OOMKilled"
    assert failure_signals_from_snapshot(
        recovered
    ) == []


def test_repeated_equivalent_failure_correlates_without_duplicate() -> None:
    session = _session()
    persist_topology_checkpoint(
        session,
        snapshot=_snapshot("snapshot:one"),
        reason=(TopologyCheckpointReason.INCIDENT_BOUNDARY),
        tenant_id=TEST_TENANT,
    )
    first = ingest_failure_signal_batch(
        session, signals=[_signal("signal:one")], tenant_id=TEST_TENANT
    )
    second = ingest_failure_signal_batch(
        session,
        signals=[
            _signal(
                "signal:two",
                observed_at=(NOW + timedelta(minutes=2)),
                reason="BackOff",
            )
        ],
        tenant_id=TEST_TENANT,
    )

    assert first.results[0].incident_created
    assert second.results[0].incident_correlated
    assert (
        first.results[0].incident_id
        == second.results[0].incident_id
    )
    assert _count(session, IncidentRecord) == 1
    incident = session.get(
        IncidentRecord,
        (TEST_TENANT, first.results[0].incident_id),
    )
    assert incident is not None
    assert incident.occurrence_count == 2


def test_unrelated_failure_creates_separate_incident() -> None:
    session = _session()
    persist_topology_checkpoint(
        session,
        snapshot=_snapshot("snapshot:one"),
        reason=(TopologyCheckpointReason.INCIDENT_BOUNDARY),
        tenant_id=TEST_TENANT,
    )
    first = _signal("signal:one")
    second = _signal(
        "signal:other",
        pod_name="ledger-api-def-456",
        pod_uid="pod-uid-2",
    )
    ingest_failure_signal_batch(session, signals=[first, second], tenant_id=TEST_TENANT)

    assert _count(session, IncidentRecord) == 2


def test_resolved_incident_does_not_absorb_later_recurrence() -> None:
    session = _session()
    persist_topology_checkpoint(
        session,
        snapshot=_snapshot("snapshot:one"),
        reason=(TopologyCheckpointReason.INCIDENT_BOUNDARY),
        tenant_id=TEST_TENANT,
    )
    first = ingest_failure_signal_batch(
        session, signals=[_signal("signal:first")], tenant_id=TEST_TENANT
    )
    first_id = first.results[0].incident_id
    assert first_id is not None
    update_incident_status(
        session,
        incident_id=first_id,
        status=IncidentStatus.RESOLVED,
        note="Recovered",
        tenant_id=TEST_TENANT,
    )
    later = ingest_failure_signal_batch(
        session,
        signals=[
            _signal(
                "signal:recurrence",
                observed_at=(NOW + timedelta(hours=8)),
            )
        ],
        tenant_id=TEST_TENANT,
    )

    assert later.results[0].incident_created
    assert later.results[0].incident_id != first_id
    assert _count(session, IncidentRecord) == 2


def test_resolved_incident_replay_does_not_create_recurrence() -> None:
    session = _session()
    persist_topology_checkpoint(
        session,
        snapshot=_snapshot("snapshot:one"),
        reason=(TopologyCheckpointReason.INCIDENT_BOUNDARY),
        tenant_id=TEST_TENANT,
    )
    signal = _signal("signal:replayed")
    first = ingest_failure_signal_batch(
        session, signals=[signal], tenant_id=TEST_TENANT
    )
    incident_id = first.results[0].incident_id
    assert incident_id is not None
    update_incident_status(
        session,
        incident_id=incident_id,
        status=IncidentStatus.RESOLVED,
        note="Recovered",
        tenant_id=TEST_TENANT,
    )
    replay = ingest_failure_signal_batch(
        session, signals=[signal], tenant_id=TEST_TENANT
    )

    assert replay.results[0].incident_created is False
    assert replay.results[0].incident_id == incident_id
    assert _count(session, IncidentRecord) == 1


def test_first_observed_and_signal_evidence_are_preserved() -> None:
    session = _session()
    persist_topology_checkpoint(
        session,
        snapshot=_snapshot("snapshot:one"),
        reason=(TopologyCheckpointReason.INCIDENT_BOUNDARY),
        tenant_id=TEST_TENANT,
    )
    first = ingest_failure_signal_batch(
        session, signals=[_signal("signal:stable")], tenant_id=TEST_TENANT
    )
    ingest_failure_signal_batch(
        session,
        signals=[
            _signal(
                "signal:stable",
                observed_at=(NOW + timedelta(minutes=3)),
            )
        ],
        tenant_id=TEST_TENANT,
    )
    incident = load_incident_record(
        session, first.results[0].incident_id or "", tenant_id=TEST_TENANT
    )
    stored_signal = load_signal(session, "signal:stable", tenant_id=TEST_TENANT)

    assert incident is not None
    assert incident.first_observed_at == NOW
    assert stored_signal is not None
    assert stored_signal.first_observed_at == NOW
    assert stored_signal.last_observed_at == (
        NOW + timedelta(minutes=3)
    )
    assert _count(session, SignalRecord) == 1


def test_repeated_checkpoint_failure_increments_evidence_count() -> None:
    session = _session()
    snapshot = _snapshot(
        "snapshot:one",
        failure_reason="CrashLoopBackOff",
    )
    persist_topology_checkpoint(
        session,
        snapshot=snapshot,
        reason=(TopologyCheckpointReason.INCIDENT_BOUNDARY),
        tenant_id=TEST_TENANT,
    )
    signals = failure_signals_from_snapshot(snapshot)
    first = ingest_failure_signal_batch(session, signals=signals, tenant_id=TEST_TENANT)
    second = ingest_failure_signal_batch(
        session,
        signals=[
            signals[0].model_copy(
                update={
                    "first_observed_at": (NOW + timedelta(minutes=2)),
                    "last_observed_at": (NOW + timedelta(minutes=2)),
                }
            )
        ],
        tenant_id=TEST_TENANT,
    )
    stored = load_signal(session, signals[0].signal_id, tenant_id=TEST_TENANT)
    incident = load_incident_record(
        session, first.results[0].incident_id or "", tenant_id=TEST_TENANT
    )

    assert second.results[0].incident_correlated
    assert stored is not None
    assert stored.occurrence_count == 2
    assert incident is not None
    assert incident.occurrence_count == 2


def test_stale_open_incident_is_not_reused_outside_window() -> None:
    session = _session()
    persist_topology_checkpoint(
        session,
        snapshot=_snapshot("snapshot:one"),
        reason=(TopologyCheckpointReason.INCIDENT_BOUNDARY),
        tenant_id=TEST_TENANT,
    )
    first = ingest_failure_signal_batch(
        session, signals=[_signal("signal:first")], tenant_id=TEST_TENANT
    )
    later = ingest_failure_signal_batch(
        session,
        signals=[
            _signal(
                "signal:later",
                observed_at=(NOW + timedelta(hours=8)),
            )
        ],
        tenant_id=TEST_TENANT,
    )

    assert later.results[0].incident_created
    assert (
        later.results[0].incident_id
        != first.results[0].incident_id
    )
    assert _count(session, IncidentRecord) == 2


def test_incident_pins_historical_snapshot_not_newest() -> None:
    session = _session()
    persist_topology_checkpoint(
        session,
        snapshot=_snapshot("snapshot:incident"),
        reason=(TopologyCheckpointReason.INCIDENT_BOUNDARY),
        tenant_id=TEST_TENANT,
    )
    persist_topology_checkpoint(
        session,
        snapshot=_snapshot(
            "snapshot:newest",
            image="payment:v9",
            observed_at=NOW + timedelta(hours=1),
        ),
        reason=(TopologyCheckpointReason.PERIODIC_RECONCILE),
        tenant_id=TEST_TENANT,
    )
    result = ingest_failure_signal_batch(
        session,
        signals=[
            _signal(
                "signal:historical",
                snapshot_id="snapshot:incident",
            )
        ],
        tenant_id=TEST_TENANT,
    )
    incident_id = result.results[0].incident_id
    analysis = latest_causal_analysis(
        session, incident_id=incident_id or "", tenant_id=TEST_TENANT
    )

    assert analysis is not None
    assert analysis.topology_snapshot_id == (
        "snapshot:incident"
    )


def test_invalid_pinned_snapshot_degrades_without_latest_fallback() -> None:
    session = _session()
    persist_topology_checkpoint(
        session,
        snapshot=_snapshot("snapshot:newest"),
        reason=(TopologyCheckpointReason.PERIODIC_RECONCILE),
        tenant_id=TEST_TENANT,
    )
    result = ingest_failure_signal_batch(
        session,
        signals=[
            _signal(
                "signal:bad-pin",
                snapshot_id="snapshot:missing",
            )
        ],
        tenant_id=TEST_TENANT,
    )

    assert result.results[0].action == (
        AutomaticIncidentAction.DEGRADED
    )
    assert result.results[0].topology_snapshot_id is None
    assert result.results[0].automatic_analysis_state == (
        AutomaticAnalysisState.PENDING_TOPOLOGY
    )


def test_cross_cluster_snapshot_is_never_used_for_incident() -> None:
    session = _session()
    foreign = _snapshot("snapshot:foreign").model_copy(
        update={
            "scope": {
                "cluster": "staging",
                "namespace": "payments",
            }
        }
    )
    persist_topology_checkpoint(
        session,
        snapshot=foreign,
        reason=(TopologyCheckpointReason.PERIODIC_RECONCILE),
        tenant_id=TEST_TENANT,
    )
    result = ingest_failure_signal_batch(
        session,
        signals=[
            _signal(
                "signal:foreign-pin",
                snapshot_id="snapshot:foreign",
            )
        ],
        tenant_id=TEST_TENANT,
    )

    assert result.results[0].topology_snapshot_id is None
    assert result.results[0].automatic_analysis_state == (
        AutomaticAnalysisState.PENDING_TOPOLOGY
    )


def test_info_signal_is_stored_but_never_creates_incident() -> None:
    session = _session()
    persist_topology_checkpoint(
        session,
        snapshot=_snapshot("snapshot:one"),
        reason=(TopologyCheckpointReason.PERIODIC_RECONCILE),
        tenant_id=TEST_TENANT,
    )
    result = ingest_failure_signal_batch(
        session,
        signals=[
            _signal(
                "signal:normal-rollout",
                reason="SuccessfulCreate",
                severity=SignalSeverity.INFO,
            )
        ],
        tenant_id=TEST_TENANT,
    )

    assert result.ignored_non_failure_count == 1
    assert result.results[0].action == (
        AutomaticIncidentAction.IGNORED
    )
    assert _count(session, SignalRecord) == 1
    assert _count(session, IncidentRecord) == 0


def test_automatic_lifecycle_has_no_llm_or_execution_dependency(
) -> None:
    source = inspect.getsource(lifecycle).lower()

    assert "llm" not in source
    assert "openai" not in source
    assert "execution_intent" not in source
    assert "action_approval" not in source


def test_automation_status_endpoint_uses_standard_authentication(
    required_auth_app,
) -> None:
    with TestClient(required_auth_app, headers=TEST_HEADERS) as client:
        automation_response = client.get("/api/v1/automation/status")
        incident_response = client.get(
            "/api/v1/incidents/incident%3Atest/lifecycle-status"
        )

    assert automation_response.status_code == 401
    assert incident_response.status_code == 401


def _agent(
    session: Session,
    *,
    agent_id: str = "agent:lifecycle-integration",
    name: str = "lifecycle-integration",
    token_hash: str = "a" * 64,
) -> TopoAgentRecord:
    now = utc_now_iso()
    record = TopoAgentRecord(
        tenant_id=TEST_TENANT,
        agent_id=agent_id,
        name=name,
        agent_type="kubernetes",
        cluster_name="production",
        environment="production",
        version="1.0",
        token_hash=token_hash,
        token_hint="test",
        status="online",
        collection_interval_seconds=300,
        heartbeat_interval_seconds=30,
        namespace_scope_json='["payments"]',
        capabilities_json="[]",
        labels_json="{}",
        metadata_json="{}",
        buffered_item_count=0,
        enrolled_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _agent_submission(
    submission_id: str,
    *,
    collected_at: datetime,
    image: str,
    pod_uid: str,
    pod_name: str,
    replica_uid: str,
    failure_reason: str | None = None,
    checkpoint_reason: str = "periodic_reconcile",
    trigger_signal_ids: list[str] | None = None,
    pod_template_fingerprint: str | None = None,
    last_terminated_reason: str | None = None,
    environment: str = "production",
) -> AgentSnapshotSubmission:
    return AgentSnapshotSubmission(
        submission_id=submission_id,
        collected_at=collected_at.isoformat(),
        cluster_name="production",
        environment=environment,
        namespace_scope=["payments"],
        collector_version="1.0",
        inventory={
            "namespaces": [
                {
                    "uid": "namespace-payments",
                    "name": "payments",
                }
            ],
            "deployments": [
                {
                    "uid": "deployment-payment",
                    "name": "payment-api",
                    "namespace": "payments",
                    "containers": [
                        {
                            "name": "payment-api",
                            "image": image,
                        }
                    ],
                    **(
                        {
                            "pod_template_fingerprint": (
                                pod_template_fingerprint
                            )
                        }
                        if pod_template_fingerprint
                        else {}
                    ),
                }
            ],
            "replicasets": [
                {
                    "uid": replica_uid,
                    "owner_uid": "deployment-payment",
                    "name": f"payment-api-{replica_uid}",
                    "namespace": "payments",
                }
            ],
            "pods": [
                {
                    "uid": pod_uid,
                    "owner_uid": replica_uid,
                    "name": pod_name,
                    "namespace": "payments",
                    "phase": "Running",
                    "container_statuses": [
                        {
                            "name": "payment-api",
                            "image": image,
                            "ready": failure_reason is None,
                            "waiting_reason": failure_reason,
                            "last_terminated_reason": (
                                last_terminated_reason
                            ),
                            "restart_count": (
                                0
                                if failure_reason is None
                                else 3
                            ),
                        }
                    ],
                }
            ],
        },
        metadata={
            "collection_status": "success",
            "checkpoint_reason": checkpoint_reason,
            "trigger_event_ids": [],
            "trigger_signal_ids": (
                trigger_signal_ids or []
            ),
        },
    )


def test_manual_snapshot_uses_oom_evidence_in_same_ingestion_cycle() -> None:
    session = _session()
    agent = _agent(session)
    authorization = authorize_agent_fixed_purpose(
        session,
        agent=agent,
        fixed_purpose="app.services.agent_snapshot_ingest.persist_agent_snapshot",
    )
    healthy_fingerprint = "sha256:" + "a" * 64
    failing_fingerprint = "sha256:" + "b" * 64
    persist_agent_snapshot(
        session,
        agent=agent,
        submission=_agent_submission(
            "submission:oom-healthy",
            collected_at=NOW - timedelta(minutes=1),
            image="payment:v1",
            pod_uid="pod-oom",
            pod_name="payment-api-oom",
            replica_uid="rs-oom",
            pod_template_fingerprint=(
                healthy_fingerprint
            ),
        ),
        authorization_context=authorization,
    )

    receipt = persist_agent_snapshot(
        session,
        agent=agent,
        submission=_agent_submission(
            "submission:oom-manual",
            collected_at=NOW,
            image="payment:v1",
            pod_uid="pod-oom",
            pod_name="payment-api-oom",
            replica_uid="rs-oom",
            failure_reason="CrashLoopBackOff",
            last_terminated_reason="OOMKilled",
            checkpoint_reason="manual",
            pod_template_fingerprint=(
                failing_fingerprint
            ),
        ),
        authorization_context=authorization,
    )

    incidents = list(
        session.scalars(
            select(IncidentRecord)
        ).all()
    )
    assert receipt.failure_signal_count == 2
    assert receipt.incident_created_count == 1
    assert len(incidents) == 1
    assert set(
        session.scalars(
            select(SignalRecord.reason)
        ).all()
    ) == {
        "CrashLoopBackOff",
        "OOMKilled",
    }
    incident = incidents[0]
    assert incident.title == (
        "OOMKilled on Pod/payment-api-oom"
    )
    assert incident.primary_signal_id is not None
    primary_signal = load_signal(
        session,
        incident.primary_signal_id,
        tenant_id=TEST_TENANT,
    )
    assert primary_signal is not None
    assert primary_signal.reason == "OOMKilled"
    assert incident.topology_snapshot_id == (
        receipt.snapshot_id
    )

    briefing = build_incident_briefing(
        session,
        incident_id=incident.incident_id,
        include_ai=False,
        tenant_id=TEST_TENANT,
    )
    assert briefing.incident.title == incident.title

    later = ingest_failure_signal_batch(
        session,
        signals=[
            _signal(
                "signal:kubernetes-event:generic-backoff",
                observed_at=NOW + timedelta(seconds=10),
                reason="BackOff",
                pod_name="payment-api-oom",
                pod_uid="pod-oom",
                snapshot_id=receipt.snapshot_id,
            )
        ],
        tenant_id=TEST_TENANT,
    )
    session.refresh(incident)
    assert later.incident_created_count == 0
    assert later.incident_correlated_count == 1
    assert _count(session, IncidentRecord) == 1
    assert incident.title == (
        "OOMKilled on Pod/payment-api-oom"
    )

    repeated = persist_agent_snapshot(
        session,
        agent=agent,
        submission=_agent_submission(
            "submission:oom-manual-repeat",
            collected_at=NOW + timedelta(seconds=20),
            image="payment:v1",
            pod_uid="pod-oom",
            pod_name="payment-api-oom",
            replica_uid="rs-oom",
            failure_reason="CrashLoopBackOff",
            last_terminated_reason="OOMKilled",
            checkpoint_reason="manual",
            pod_template_fingerprint=(
                failing_fingerprint
            ),
        ),
        authorization_context=authorization,
    )
    assert repeated.incident_created_count == 0
    assert _count(session, IncidentRecord) == 1

    update_incident_status(
        session,
        incident_id=incident.incident_id,
        status=IncidentStatus.RESOLVED,
        note="Recovered after memory limit correction",
        tenant_id=TEST_TENANT,
    )

    for index in range(2):
        healthy_receipt = persist_agent_snapshot(
            session,
            agent=agent,
            submission=_agent_submission(
                f"submission:oom-recovered-{index}",
                collected_at=(
                    NOW
                    + timedelta(
                        minutes=1,
                        seconds=index,
                    )
                ),
                image="payment:v1",
                pod_uid="pod-oom",
                pod_name="payment-api-oom",
                replica_uid="rs-oom",
                last_terminated_reason="OOMKilled",
                checkpoint_reason="manual",
                pod_template_fingerprint=(
                    healthy_fingerprint
                ),
            ),
            authorization_context=authorization,
        )
        assert healthy_receipt.failure_signal_count == 0
        assert healthy_receipt.incident_created_count == 0

    session.refresh(incident)
    assert incident.status == (
        IncidentStatus.RESOLVED.value
    )
    assert _count(session, IncidentRecord) == 1


def test_manual_snapshot_creates_config_error_incident_immediately() -> None:
    session = _session()
    agent = _agent(session)
    authorization = authorize_agent_fixed_purpose(
        session,
        agent=agent,
        fixed_purpose="app.services.agent_snapshot_ingest.persist_agent_snapshot",
    )

    receipt = persist_agent_snapshot(
        session,
        agent=agent,
        submission=_agent_submission(
            "submission:config-error-manual",
            collected_at=NOW,
            image="payment:v1",
            pod_uid="pod-config-error",
            pod_name="payment-api-config-error",
            replica_uid="rs-config-error",
            failure_reason=(
                "CreateContainerConfigError"
            ),
            checkpoint_reason="manual",
        ),
        authorization_context=authorization,
    )
    incident = session.scalar(
        select(IncidentRecord)
    )

    assert receipt.failure_signal_count == 1
    assert receipt.incident_created_count == 1
    assert incident is not None
    assert incident.title == (
        "CreateContainerConfigError on "
        "Pod/payment-api-config-error"
    )


def test_pending_topology_reconciles_only_with_safe_checkpoint() -> None:
    session = _session()
    pending = ingest_failure_signal_batch(
        session,
        signals=[
            _signal(
                "signal:pending-safe",
                snapshot_id=None,
            )
        ],
        tenant_id=TEST_TENANT,
    )
    incident_id = pending.results[0].incident_id
    assert incident_id is not None
    assert pending.results[0].automatic_analysis_state == (
        AutomaticAnalysisState.PENDING_TOPOLOGY
    )

    future_manual = _snapshot(
        "snapshot:future-manual",
        observed_at=NOW + timedelta(minutes=5),
    )
    persist_topology_checkpoint(
        session,
        snapshot=future_manual,
        reason=TopologyCheckpointReason.MANUAL,
        force=True,
        tenant_id=TEST_TENANT,
    )
    assert (
        reconcile_pending_incidents_for_checkpoint(
            session, snapshot_id=future_manual.snapshot_id, tenant_id=TEST_TENANT
        )
        == []
    )
    incident = session.get(IncidentRecord, (TEST_TENANT, incident_id))
    assert incident is not None
    assert incident.topology_snapshot_id is None

    safe = _snapshot(
        "snapshot:safely-delayed",
        observed_at=NOW - timedelta(seconds=1),
    )
    persist_topology_checkpoint(
        session,
        snapshot=safe,
        reason=(TopologyCheckpointReason.PERIODIC_RECONCILE),
        tenant_id=TEST_TENANT,
    )
    reconciled = reconcile_pending_incidents_for_checkpoint(
        session, snapshot_id=safe.snapshot_id, tenant_id=TEST_TENANT
    )
    session.refresh(incident)

    assert len(reconciled) == 1
    assert incident.topology_snapshot_id == safe.snapshot_id
    assert incident.affected_entity_id == (
        "entity:pod:pod-uid-1"
    )
    assert (
        latest_causal_analysis(session, incident_id=incident_id, tenant_id=TEST_TENANT)
        is not None
    )


def test_explicit_incident_boundary_reconciles_after_failure() -> None:
    session = _session()
    signal = _signal(
        "signal:explicit-boundary",
        snapshot_id=None,
    )
    result = ingest_failure_signal_batch(
        session, signals=[signal], tenant_id=TEST_TENANT
    )
    incident_id = result.results[0].incident_id
    assert incident_id is not None
    boundary = _snapshot(
        "snapshot:explicit-boundary",
        observed_at=NOW + timedelta(seconds=10),
    )
    persist_topology_checkpoint(
        session,
        snapshot=boundary,
        reason=(TopologyCheckpointReason.INCIDENT_BOUNDARY),
        trigger_signal_ids=[signal.signal_id],
        force=True,
        tenant_id=TEST_TENANT,
    )

    reconciled = reconcile_pending_incidents_for_checkpoint(
        session, snapshot_id=boundary.snapshot_id, tenant_id=TEST_TENANT
    )
    incident = session.get(IncidentRecord, (TEST_TENANT, incident_id))

    assert incident is not None
    assert len(reconciled) == 1
    assert incident.topology_snapshot_id == (
        boundary.snapshot_id
    )
    assert incident.affected_entity_id == (
        "entity:pod:pod-uid-1"
    )


def test_future_automatic_checkpoint_without_signal_link_is_rejected() -> None:
    session = _session()
    result = ingest_failure_signal_batch(
        session,
        signals=[
            _signal(
                "signal:no-latest-fallback",
                snapshot_id=None,
            )
        ],
        tenant_id=TEST_TENANT,
    )
    incident_id = result.results[0].incident_id
    future = _snapshot(
        "snapshot:future-automatic",
        observed_at=NOW + timedelta(seconds=30),
    )
    persist_topology_checkpoint(
        session,
        snapshot=future,
        reason=(TopologyCheckpointReason.AUTOMATIC_CHANGE),
        tenant_id=TEST_TENANT,
    )

    assert (
        reconcile_pending_incidents_for_checkpoint(
            session, snapshot_id=future.snapshot_id, tenant_id=TEST_TENANT
        )
        == []
    )
    incident = session.get(IncidentRecord, (TEST_TENANT, incident_id))
    assert incident is not None
    assert incident.topology_snapshot_id is None


def test_ephemeral_pod_resolves_by_uid_not_name_guessing() -> None:
    session = _session()
    snapshot = _snapshot(
        "snapshot:ephemeral",
        pod_name="lifecycle-demo-57dd8d5d5-7bkhv",
        pod_uid="pod-ephemeral-uid",
    )
    persist_topology_checkpoint(
        session,
        snapshot=snapshot,
        reason=(TopologyCheckpointReason.INCIDENT_BOUNDARY),
        tenant_id=TEST_TENANT,
    )
    signal = _signal(
        "signal:ephemeral",
        pod_name="lifecycle-demo-57dd8d5d5-7bkhv",
        pod_uid="pod-ephemeral-uid",
        snapshot_id=snapshot.snapshot_id,
    ).model_copy(
        update={
            "involved_entity_id": "entity:stale-reference"
        }
    )
    result = ingest_failure_signal_batch(
        session, signals=[signal], tenant_id=TEST_TENANT
    )
    incident = session.get(
        IncidentRecord,
        (TEST_TENANT, result.results[0].incident_id),
    )

    assert incident is not None
    assert incident.affected_entity_id == (
        "entity:pod:pod-ephemeral-uid"
    )


def test_pinned_snapshot_never_moves_on_later_correlated_signal() -> None:
    session = _session()
    first_snapshot = _snapshot("snapshot:first-pin")
    persist_topology_checkpoint(
        session,
        snapshot=first_snapshot,
        reason=(TopologyCheckpointReason.INCIDENT_BOUNDARY),
        tenant_id=TEST_TENANT,
    )
    first = ingest_failure_signal_batch(
        session,
        signals=[
            _signal(
                "signal:first-pin",
                snapshot_id=first_snapshot.snapshot_id,
            )
        ],
        tenant_id=TEST_TENANT,
    )
    later_snapshot = _snapshot(
        "snapshot:later-pin",
        observed_at=NOW + timedelta(minutes=1),
        image="payment:v2",
    )
    persist_topology_checkpoint(
        session,
        snapshot=later_snapshot,
        reason=(TopologyCheckpointReason.INCIDENT_BOUNDARY),
        trigger_signal_ids=["signal:later-pin"],
        force=True,
        tenant_id=TEST_TENANT,
    )
    ingest_failure_signal_batch(
        session,
        signals=[
            _signal(
                "signal:later-pin",
                observed_at=NOW + timedelta(minutes=1),
                snapshot_id=later_snapshot.snapshot_id,
            )
        ],
        tenant_id=TEST_TENANT,
    )
    incident = session.get(
        IncidentRecord,
        (TEST_TENANT, first.results[0].incident_id),
    )

    assert incident is not None
    assert incident.topology_snapshot_id == (
        first_snapshot.snapshot_id
    )


def test_real_agent_checkpoint_to_briefing_pipeline() -> None:
    session = _session()
    agent = _agent(session)
    agent_authorization = authorize_agent_fixed_purpose(
        session,
        agent=agent,
        fixed_purpose="app.services.agent_snapshot_ingest.persist_agent_snapshot",
    )
    persist_agent_snapshot(
        session,
        agent=agent,
        submission=_agent_submission(
            "submission:healthy",
            collected_at=NOW - timedelta(minutes=2),
            image="payment:v1",
            pod_uid="pod-old",
            pod_name="payment-api-old-7bkhv",
            replica_uid="rs-old",
            ),
        authorization_context=agent_authorization,
    )
    watcher_signal_id = "signal:kubernetes-event:boundary"
    receipt = persist_agent_snapshot(
        session,
        agent=agent,
        submission=_agent_submission(
            "submission:failure-boundary",
            collected_at=NOW,
            image="registry.invalid/payment:v2",
            pod_uid="pod-new",
            pod_name="payment-api-new-9zx2m",
            replica_uid="rs-new",
            failure_reason="ImagePullBackOff",
            checkpoint_reason="incident_boundary",
            trigger_signal_ids=[watcher_signal_id],
        ),
        authorization_context=agent_authorization,
    )
    watcher_signal = _signal(
        watcher_signal_id,
        reason="ImagePullBackOff",
        pod_name="payment-api-new-9zx2m",
        pod_uid="pod-new",
        snapshot_id=receipt.snapshot_id,
        severity=SignalSeverity.ERROR,
    ).model_copy(
        update={"category": SignalCategory.IMAGE}
    )
    watcher_result = ingest_failure_signal_batch(
        session, signals=[watcher_signal], tenant_id=TEST_TENANT
    )
    incident_id = watcher_result.results[0].incident_id
    assert incident_id is not None
    incident = session.get(IncidentRecord, (TEST_TENANT, incident_id))
    analysis = latest_causal_analysis(
        session, incident_id=incident_id, tenant_id=TEST_TENANT
    )

    assert incident is not None
    assert incident.topology_snapshot_id == receipt.snapshot_id
    assert incident.affected_entity_id == (
        "k8s:production:pod:pod-new"
    )
    assert analysis is not None
    assert analysis.analysis_id == incident.latest_analysis_id
    assert analysis.top_hypothesis is not None
    assert _count(session, CausalAnalysisRecord) == 1

    second = ingest_failure_signal_batch(
        session, signals=[watcher_signal], tenant_id=TEST_TENANT
    )
    reused = latest_causal_analysis(
        session, incident_id=incident_id, tenant_id=TEST_TENANT
    )
    assert second.results[0].automatic_analysis_state == (
        AutomaticAnalysisState.REUSED
    )
    assert reused is not None
    assert reused.analysis_id == analysis.analysis_id
    assert _count(session, CausalAnalysisRecord) == 1

    briefing = build_incident_briefing(
        session, incident_id=incident_id, include_ai=False, tenant_id=TEST_TENANT
    )
    assert briefing.incident.incident_id == incident_id
    assert briefing.root_cause.causal_analysis_id == (
        analysis.analysis_id
    )
    assert briefing.root_cause.topology_snapshot_id == (
        receipt.snapshot_id
    )


def test_image_change_remains_root_after_prior_deployment_creation() -> None:
    session = _session()
    agent = _agent(session)
    agent_authorization = authorize_agent_fixed_purpose(
        session,
        agent=agent,
        fixed_purpose="app.services.agent_snapshot_ingest.persist_agent_snapshot",
    )

    empty = _agent_submission(
        "submission:empty-before-deployment",
        collected_at=NOW - timedelta(minutes=4),
        image="nginx:1.27-alpine",
        pod_uid="unused-pod",
        pod_name="unused-pod",
        replica_uid="unused-rs",
    )
    empty.inventory["deployments"] = []
    empty.inventory["replicasets"] = []
    empty.inventory["pods"] = []
    persist_agent_snapshot(
        session,
        agent=agent,
        submission=empty,
        authorization_context=agent_authorization,
    )

    persist_agent_snapshot(
        session,
        agent=agent,
        submission=_agent_submission(
            "submission:healthy-deployment-created",
            collected_at=NOW - timedelta(minutes=3),
            image="nginx:1.27-alpine",
            pod_uid="pod-old",
            pod_name="payment-api-old",
            replica_uid="rs-old",
        ),
        authorization_context=agent_authorization,
    )

    image_change = _agent_submission(
        "submission:deployment-image-changed",
        collected_at=NOW - timedelta(minutes=2),
        image="nginx:topo-invalid",
        pod_uid="pod-old",
        pod_name="payment-api-old",
        replica_uid="rs-old",
    )
    # The old Pod remains healthy on v1 while the Deployment template has
    # changed. This isolates the initiating mutation from the later symptom.
    image_change.inventory["pods"][0]["container_statuses"][0]["image"] = (
        "nginx:1.27-alpine"
    )
    persist_agent_snapshot(
        session,
        agent=agent,
        submission=image_change,
        authorization_context=agent_authorization,
    )

    signal_id = "signal:kubernetes-event:err-image-pull"
    failure = persist_agent_snapshot(
        session,
        agent=agent,
        submission=_agent_submission(
            "submission:new-pod-err-image-pull",
            collected_at=NOW,
            image="nginx:topo-invalid",
            pod_uid="pod-new",
            pod_name="payment-api-new",
            replica_uid="rs-new",
            failure_reason="ErrImagePull",
            checkpoint_reason="incident_boundary",
            trigger_signal_ids=[signal_id],
        ),
        authorization_context=agent_authorization,
    )
    result = ingest_failure_signal_batch(
        session,
        signals=[
            _signal(
                signal_id,
                reason="ErrImagePull",
                pod_name="payment-api-new",
                pod_uid="pod-new",
                snapshot_id=failure.snapshot_id,
                severity=SignalSeverity.ERROR,
            ).model_copy(
                update={"category": SignalCategory.IMAGE}
            )
        ],
        tenant_id=TEST_TENANT,
    )
    incident_id = result.results[0].incident_id
    assert incident_id is not None

    deployment_changes = list(
        session.scalars(
            select(ChangeRecord)
            .where(
                ChangeRecord.entity_id
                == "k8s:production:deployment:deployment-payment"
            )
            .order_by(ChangeRecord.detected_at)
        ).all()
    )
    creation = next(
        change
        for change in deployment_changes
        if change.change_type == "entity_added"
    )
    configuration = next(
        change
        for change in deployment_changes
        if change.change_type == "entity_updated"
    )
    creation_event = session.scalar(
        select(ChangeEventRecord).where(
            ChangeEventRecord.origin_change_id
            == creation.change_id
        )
    )
    configuration_event = session.scalar(
        select(ChangeEventRecord).where(
            ChangeEventRecord.origin_change_id
            == configuration.change_id
        )
    )
    analysis = latest_causal_analysis(
        session,
        incident_id=incident_id,
        tenant_id=TEST_TENANT,
    )

    assert creation_event is not None
    assert configuration_event is not None
    assert analysis is not None
    assert analysis.top_hypothesis is not None
    assert analysis.top_hypothesis.target_event_id == (
        configuration_event.event_id
    )
    assert analysis.top_hypothesis.root_event_id == (
        configuration_event.event_id
    )
    assert analysis.top_hypothesis.root_title == (
        "Deployment configuration changed"
    )
    # Root presentation changes, not the established scoring heuristic or
    # the contextual event-lineage evidence retained in the causal graph.
    assert analysis.top_hypothesis.score == 68.98
    assert any(
        edge.source_node_id
        == f"event|{creation_event.event_id}"
        and edge.target_node_id
        == f"event|{configuration_event.event_id}"
        and edge.relation.value == "precedes"
        and round(edge.confidence, 2) == 0.65
        for edge in analysis.edges
    )
    assert analysis.top_hypothesis.support_gate is not None
    assert (
        analysis.top_hypothesis.support_gate.support_state.value
        == "supported_under_current_model"
    )
    assert [
        step.label
        for step in analysis.top_hypothesis.chain
        if step.node_type.value == "change_event"
    ] == ["Deployment configuration changed"]
    assert creation_event.event_id != (
        analysis.top_hypothesis.root_event_id
    )
    assert any(
        hypothesis.root_event_id
        == creation_event.event_id
        for hypothesis in analysis.hypotheses
    )


def test_command_change_is_supported_candidate_for_crash_loop() -> None:
    session = _session()
    agent = _agent(session)
    agent_authorization = authorize_agent_fixed_purpose(
        session,
        agent=agent,
        fixed_purpose="app.services.agent_snapshot_ingest.persist_agent_snapshot",
    )
    healthy_fingerprint = "sha256:" + "1" * 64
    command_fingerprint = "sha256:" + "2" * 64

    persist_agent_snapshot(
        session,
        agent=agent,
        submission=_agent_submission(
            "submission:command-healthy",
            collected_at=NOW - timedelta(minutes=3),
            image="nginx:1.27-alpine",
            pod_uid="pod-old",
            pod_name="payment-api-old",
            replica_uid="rs-old",
            pod_template_fingerprint=healthy_fingerprint,
        ),
        authorization_context=agent_authorization,
    )
    persist_agent_snapshot(
        session,
        agent=agent,
        submission=_agent_submission(
            "submission:command-changed",
            collected_at=NOW - timedelta(minutes=2),
            image="nginx:1.27-alpine",
            pod_uid="pod-old",
            pod_name="payment-api-old",
            replica_uid="rs-old",
            pod_template_fingerprint=command_fingerprint,
        ),
        authorization_context=agent_authorization,
    )

    signal_id = "signal:kubernetes-event:command-crash-loop"
    failure = persist_agent_snapshot(
        session,
        agent=agent,
        submission=_agent_submission(
            "submission:command-failure",
            collected_at=NOW,
            image="nginx:1.27-alpine",
            pod_uid="pod-new",
            pod_name="payment-api-new",
            replica_uid="rs-new",
            failure_reason="CrashLoopBackOff",
            checkpoint_reason="incident_boundary",
            trigger_signal_ids=[signal_id],
            pod_template_fingerprint=command_fingerprint,
        ),
        authorization_context=agent_authorization,
    )
    result = ingest_failure_signal_batch(
        session,
        signals=[
            _signal(
                signal_id,
                reason="CrashLoopBackOff",
                pod_name="payment-api-new",
                pod_uid="pod-new",
                snapshot_id=failure.snapshot_id,
                severity=SignalSeverity.ERROR,
            )
        ],
        tenant_id=TEST_TENANT,
    )
    incident_id = result.results[0].incident_id
    assert incident_id is not None

    deployment_changes = [
        record
        for record in session.scalars(
            select(ChangeRecord).where(
                ChangeRecord.entity_id
                == "k8s:production:deployment:deployment-payment"
            )
        ).all()
        if record.change_type == "entity_updated"
    ]
    assert len(deployment_changes) == 1
    change = json.loads(
        deployment_changes[0].payload_json
    )
    assert change["changed_fields"] == {
        "properties.pod_template_fingerprint": {
            "before": healthy_fingerprint,
            "after": command_fingerprint,
        }
    }
    event = session.scalar(
        select(ChangeEventRecord).where(
            ChangeEventRecord.origin_change_id
            == deployment_changes[0].change_id
        )
    )
    analysis = latest_causal_analysis(
        session,
        incident_id=incident_id,
        tenant_id=TEST_TENANT,
    )

    assert event is not None
    assert event.title == "Deployment configuration changed"
    assert analysis is not None
    assert analysis.top_hypothesis is not None
    assert analysis.top_hypothesis.root_event_id == event.event_id
    assert analysis.top_hypothesis.target_event_id == event.event_id
    assert analysis.top_hypothesis.support_gate is not None
    assert (
        analysis.top_hypothesis.support_gate.support_state.value
        == "supported_under_current_model"
    )


def test_identical_template_fingerprint_creates_no_deployment_change() -> None:
    session = _session()
    agent = _agent(session)
    agent_authorization = authorize_agent_fixed_purpose(
        session,
        agent=agent,
        fixed_purpose="app.services.agent_snapshot_ingest.persist_agent_snapshot",
    )
    fingerprint = "sha256:" + "3" * 64

    persist_agent_snapshot(
        session,
        agent=agent,
        submission=_agent_submission(
            "submission:template-stable-one",
            collected_at=NOW - timedelta(minutes=1),
            image="nginx:1.27-alpine",
            pod_uid="pod-stable",
            pod_name="payment-api-stable",
            replica_uid="rs-stable",
            pod_template_fingerprint=fingerprint,
        ),
        authorization_context=agent_authorization,
    )
    before_count = _count(session, ChangeRecord)
    persist_agent_snapshot(
        session,
        agent=agent,
        submission=_agent_submission(
            "submission:template-stable-two",
            collected_at=NOW,
            image="nginx:1.27-alpine",
            pod_uid="pod-stable",
            pod_name="payment-api-stable",
            replica_uid="rs-stable",
            pod_template_fingerprint=fingerprint,
        ),
        authorization_context=agent_authorization,
    )

    assert _count(session, ChangeRecord) == before_count


def test_agent_environment_switches_are_not_material_changes() -> None:
    session = _session()
    agent = _agent(session)
    authorization = authorize_agent_fixed_purpose(
        session,
        agent=agent,
        fixed_purpose="app.services.agent_snapshot_ingest.persist_agent_snapshot",
    )

    baseline = persist_agent_snapshot(
        session,
        agent=agent,
        submission=_agent_submission(
            "submission:environment-baseline",
            collected_at=NOW - timedelta(minutes=3),
            image="nginx:1.27-alpine",
            pod_uid="pod-environment-stable",
            pod_name="payment-api-environment-stable",
            replica_uid="rs-environment-stable",
            environment="development",
        ),
        authorization_context=authorization,
    )

    for index, environment in enumerate(
        ("development", "golden", "development"),
        start=1,
    ):
        receipt = persist_agent_snapshot(
            session,
            agent=agent,
            submission=_agent_submission(
                f"submission:environment-{index}",
                collected_at=(NOW - timedelta(minutes=3 - index)),
                image="nginx:1.27-alpine",
                pod_uid="pod-environment-stable",
                pod_name="payment-api-environment-stable",
                replica_uid="rs-environment-stable",
                environment=environment,
            ),
            authorization_context=authorization,
        )

        assert receipt.snapshot_id == baseline.snapshot_id
        assert receipt.checkpoint_reused is True
        assert receipt.detected_change_count == 0

    stored = load_snapshot(
        session,
        baseline.snapshot_id,
        tenant_id=TEST_TENANT,
    )
    assert stored is not None
    assert all(
        entity.environment == "development"
        for entity in stored.entities
        if entity.source_system == "kubernetes"
    )
    assert stored.metadata["agent_id"] == agent.agent_id
    assert stored.metadata["agent_name"] == agent.name
    assert _count(session, SnapshotRecord) == 1
    assert _count(session, ChangeRecord) == 0
    assert _count(session, ChangeEventRecord) == 0


def test_alternating_agents_do_not_create_reporting_metadata_changes() -> None:
    session = _session()
    first_agent = _agent(session)
    second_agent = _agent(
        session,
        agent_id="agent:lifecycle-alternate",
        name="lifecycle-alternate",
        token_hash="b" * 64,
    )
    authorizations = {
        agent.agent_id: authorize_agent_fixed_purpose(
            session,
            agent=agent,
            fixed_purpose="app.services.agent_snapshot_ingest.persist_agent_snapshot",
        )
        for agent in (first_agent, second_agent)
    }

    receipts = []
    for index, agent in enumerate(
        (first_agent, second_agent, first_agent)
    ):
        receipts.append(
            persist_agent_snapshot(
                session,
                agent=agent,
                submission=_agent_submission(
                    f"submission:alternating-agent-{index}",
                    collected_at=NOW + timedelta(seconds=index),
                    image="nginx:1.27-alpine",
                    pod_uid="pod-agent-stable",
                    pod_name="payment-api-agent-stable",
                    replica_uid="rs-agent-stable",
                ),
                authorization_context=authorizations[agent.agent_id],
            )
        )

    assert receipts[0].checkpoint_created is True
    assert all(
        receipt.snapshot_id == receipts[0].snapshot_id
        for receipt in receipts[1:]
    )
    assert all(
        receipt.checkpoint_reused is True
        and receipt.detected_change_count == 0
        for receipt in receipts[1:]
    )
    assert _count(session, SnapshotRecord) == 1
    assert _count(session, ChangeRecord) == 0
    assert _count(session, ChangeEventRecord) == 0


def test_real_kubernetes_change_survives_reporting_metadata_switch() -> None:
    session = _session()
    first_agent = _agent(session)
    second_agent = _agent(
        session,
        agent_id="agent:lifecycle-material",
        name="lifecycle-material",
        token_hash="c" * 64,
    )
    first_authorization = authorize_agent_fixed_purpose(
        session,
        agent=first_agent,
        fixed_purpose="app.services.agent_snapshot_ingest.persist_agent_snapshot",
    )
    second_authorization = authorize_agent_fixed_purpose(
        session,
        agent=second_agent,
        fixed_purpose="app.services.agent_snapshot_ingest.persist_agent_snapshot",
    )
    baseline = _agent_submission(
        "submission:material-baseline",
        collected_at=NOW - timedelta(minutes=1),
        image="nginx:1.27-alpine",
        pod_uid="pod-material-stable",
        pod_name="payment-api-material-stable",
        replica_uid="rs-material-stable",
        pod_template_fingerprint="sha256:" + "1" * 64,
        environment="development",
    )
    baseline.inventory["deployments"][0]["desired_replicas"] = 1
    persist_agent_snapshot(
        session,
        agent=first_agent,
        submission=baseline,
        authorization_context=first_authorization,
    )

    changed = _agent_submission(
        "submission:material-change",
        collected_at=NOW,
        image="nginx:1.28-alpine",
        pod_uid="pod-material-stable",
        pod_name="payment-api-material-stable",
        replica_uid="rs-material-stable",
        pod_template_fingerprint="sha256:" + "2" * 64,
        environment="golden",
    )
    changed.inventory["deployments"][0]["desired_replicas"] = 2
    receipt = persist_agent_snapshot(
        session,
        agent=second_agent,
        submission=changed,
        authorization_context=second_authorization,
    )

    deployment_record = session.scalar(
        select(ChangeRecord).where(
            ChangeRecord.entity_id
            == "k8s:production:deployment:deployment-payment"
        )
    )
    assert receipt.checkpoint_created is True
    assert receipt.detected_change_count > 0
    assert deployment_record is not None
    payload = json.loads(deployment_record.payload_json)
    assert set(payload["changed_fields"]) == {
        "properties.containers",
        "properties.desired_replicas",
        "properties.pod_template_fingerprint",
    }
    assert "environment" not in payload["changed_fields"]
    assert not any(
        field.endswith("agent_id") or field.endswith("agent_name")
        for field in payload["changed_fields"]
    )

    stored = load_snapshot(
        session,
        receipt.snapshot_id,
        tenant_id=TEST_TENANT,
    )
    assert stored is not None
    assert stored.metadata["agent_id"] == second_agent.agent_id
    assert stored.metadata["agent_name"] == second_agent.name
    assert all(
        entity.environment == "golden"
        for entity in stored.entities
        if entity.source_system == "kubernetes"
    )
    cluster = next(
        entity
        for entity in stored.entities
        if entity.kind == "KubernetesCluster"
    )
    assert cluster.properties == {
        "agent_id": second_agent.agent_id,
        "agent_name": second_agent.name,
    }
    assert stored.relationships
    assert all(
        relationship.provenance is not None
        for relationship in stored.relationships
    )
    assert load_snapshot(
        session,
        receipt.snapshot_id,
        tenant_id="tenant:eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
    ) is None


def test_no_hypothesis_has_controlled_terminal_lifecycle_state() -> None:
    session = _session()
    snapshot = _snapshot("snapshot:no-hypothesis")
    persist_topology_checkpoint(
        session,
        snapshot=snapshot,
        reason=(TopologyCheckpointReason.INCIDENT_BOUNDARY),
        tenant_id=TEST_TENANT,
    )
    result = ingest_failure_signal_batch(
        session,
        signals=[
            _signal(
                "signal:no-hypothesis",
                snapshot_id=snapshot.snapshot_id,
            )
        ],
        tenant_id=TEST_TENANT,
    )
    incident_id = result.results[0].incident_id
    assert incident_id is not None
    status = build_incident_lifecycle_status(
        session, incident_id=incident_id, tenant_id=TEST_TENANT
    )

    assert status.automatic_analysis_state == (
        AutomaticAnalysisState
        .COMPLETED_NO_HYPOTHESIS
    )
    assert status.briefing_ready is False
    assert status.retryable is False
    assert "not identified a supported root cause" in (
        status.message
    )
