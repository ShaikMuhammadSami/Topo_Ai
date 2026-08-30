from __future__ import annotations
from domain_tenant_fixtures import TEST_TENANT, seed_domain_tenant

import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.services.causal_evidence_ledger as ledger_service
import app.services.causal_rca as causal_service
from app.db.database import Base
from app.db.models import (
    CausalAnalysisRecord,
    ChangeEntityLinkRecord,
    IncidentRecord,
)
from app.models.causal_rca import (
    CAUSAL_EVIDENCE_LEDGER_VERSION,
    CausalAnalysisRequest,
    CausalAnalysisResponse,
    CausalEvidenceClaimType,
    CausalEvidenceLedger,
    CausalEvidenceQuality,
    CausalEvidenceSourceCategory,
    CausalEvidenceStance,
)
from app.models.causal_support import CAUSAL_SUPPORT_GATE_POLICY_VERSION
from app.models.confidence_semantics import CausalEvidenceState
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
    RelationshipOrigin,
    RelationshipProvenanceCompleteness,
    RelationshipType,
)
from app.repositories.causal_analysis_repository import (
    latest_causal_analysis,
    load_causal_analysis,
)
from app.repositories.change_event_repository import ingest_change_event
from app.repositories.signal_repository import save_signals
from app.repositories.snapshot_repository import save_snapshot
from app.services.causal_rca import analyze_causal_rca
from app.services.incident_briefing import build_incident_briefing
from app.services.relationship_provenance import (
    relationship_provenance,
    source_reference,
)
from app.services.topology_checkpoint import topology_state_digest

UTC = timezone.utc
CHANGE_AT = datetime(2026, 8, 21, 10, 1, tzinfo=UTC)
SNAPSHOT_AT = datetime(2026, 8, 21, 10, 2, tzinfo=UTC)
INCIDENT_AT = datetime(2026, 8, 21, 10, 4, tzinfo=UTC)
RECEIVED_AT = datetime(2026, 8, 21, 10, 8, tzinfo=UTC)
SNAPSHOT_ID = "snapshot:tc4:incident"
INCIDENT_ID = "incident:tc4"
DEPLOYMENT_ID = "entity:deployment:payments"
REPLICASET_ID = "entity:replicaset:payments"
POD_ID = "entity:pod:payments"


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine)
    return Session(engine)


def _provenance(
    predicate: RelationshipType,
    reference: str,
    *,
    origin: RelationshipOrigin = RelationshipOrigin.DECLARED,
    reverse_source_reference_order: bool = False,
):
    references = [
        source_reference(
            reference_type="kubernetes_uid",
            reference=reference,
            source_system="kubernetes",
            attributes={"b": 2, "a": 1},
        ),
        source_reference(
            reference_type="object_kind",
            reference="OwnerReference",
            source_system="kubernetes",
        ),
    ]
    if reverse_source_reference_order:
        references.reverse()
    return relationship_provenance(
        predicate=predicate,
        origin=origin,
        source_component="tc4.fixture",
        source_references=references,
        linker_version="tc4-fixture:v1",
        completeness=RelationshipProvenanceCompleteness.COMPLETE,
    )


def _snapshot(
    *,
    snapshot_id: str = SNAPSHOT_ID,
    immutable_image: bool = False,
    legacy_relationship: bool = False,
    ambiguous_identity: bool = False,
    reverse_source_reference_order: bool = False,
) -> GraphSnapshot:
    image_id = (
        "artifact:container-image:sha256:" + "a" * 64
        if immutable_image
        else "artifact:container-image:reference:payments-v42"
    )
    entities = [
        Entity(
            id=DEPLOYMENT_ID,
            entity_type=EntityType.WORKLOAD,
            kind="KubernetesDeployment",
            name="payments",
            source_system="kubernetes",
            external_id="deployment-uid",
            identity_version="v1",
            environment="production",
            observed_at=SNAPSHOT_AT,
            properties={
                "namespace": "payments",
                "containers": [{"name": "app", "image": "pay:v42"}],
            },
        ),
        Entity(
            id=REPLICASET_ID,
            entity_type=EntityType.WORKLOAD,
            kind="KubernetesReplicaSet",
            name="payments-abc",
            source_system="kubernetes",
            external_id="replicaset-uid",
            identity_version="v1",
            environment="production",
            observed_at=SNAPSHOT_AT,
            properties={"namespace": "payments"},
        ),
        Entity(
            id=POD_ID,
            entity_type=EntityType.RUNTIME_INSTANCE,
            kind="KubernetesPod",
            name="payments-abc-123",
            source_system="kubernetes",
            external_id="pod-uid",
            identity_version="v1",
            environment="production",
            observed_at=SNAPSHOT_AT,
            properties={"namespace": "payments"},
        ),
        Entity(
            id=image_id,
            entity_type=EntityType.ARTIFACT,
            kind="ContainerImage",
            name="pay:v42",
            source_system="kubernetes",
            external_id=("sha256:" + "a" * 64 if immutable_image else "pay:v42"),
            identity_version="v1",
            environment="production",
            observed_at=SNAPSHOT_AT,
            properties={
                "digest": ("sha256:" + "a" * 64 if immutable_image else None),
                "immutable": immutable_image,
                "requested_references": ["pay:v42"],
            },
        ),
    ]
    if ambiguous_identity:
        entities.append(
            Entity(
                id="entity:deployment:payments:duplicate",
                entity_type=EntityType.WORKLOAD,
                kind="KubernetesDeployment",
                name="payments",
                source_system="kubernetes",
                external_id="deployment-uid-duplicate",
                identity_version="v1",
                environment="production",
                observed_at=SNAPSHOT_AT,
                properties={"namespace": "payments"},
            )
        )
    relationships = [
        Relationship(
            id="relationship:deployment-owns-rs",
            source_entity_id=DEPLOYMENT_ID,
            target_entity_id=REPLICASET_ID,
            relationship_type=RelationshipType.OWNS,
            source_system="kubernetes",
            observed_at=SNAPSHOT_AT,
            provenance=(
                None
                if legacy_relationship
                else _provenance(
                    RelationshipType.OWNS,
                    "replicaset-uid",
                    reverse_source_reference_order=reverse_source_reference_order,
                )
            ),
        ),
        Relationship(
            id="relationship:rs-owns-pod",
            source_entity_id=REPLICASET_ID,
            target_entity_id=POD_ID,
            relationship_type=RelationshipType.OWNS,
            source_system="kubernetes",
            observed_at=SNAPSHOT_AT,
            provenance=_provenance(RelationshipType.OWNS, "pod-uid"),
        ),
        Relationship(
            id="relationship:deployment-uses-image",
            source_entity_id=DEPLOYMENT_ID,
            target_entity_id=image_id,
            relationship_type=RelationshipType.USES,
            source_system="kubernetes",
            observed_at=SNAPSHOT_AT,
            provenance=_provenance(
                RelationshipType.USES,
                image_id,
                origin=(
                    RelationshipOrigin.DERIVED
                    if immutable_image
                    else RelationshipOrigin.DECLARED
                ),
            ),
        ),
    ]
    return GraphSnapshot(
        snapshot_id=snapshot_id,
        collected_at=SNAPSHOT_AT,
        collector_name="tc4-fixture",
        collector_version="1",
        scope={
            "cluster": "prod",
            "namespace": "payments",
            "environment": "production",
        },
        entities=entities,
        relationships=relationships,
        evidence=[],
    )


def _signal() -> NormalizedSignal:
    return NormalizedSignal(
        signal_id="signal:tc4",
        fingerprint="signal-fingerprint:tc4",
        signal_type=SignalType.KUBERNETES_EVENT,
        severity=SignalSeverity.ERROR,
        category=SignalCategory.IMAGE,
        source_system="kubernetes",
        title="ImagePullBackOff on payments",
        summary="payments image pull failed",
        reason="ImagePullBackOff",
        first_observed_at=INCIDENT_AT,
        last_observed_at=INCIDENT_AT,
        cluster_name="prod",
        namespace="payments",
        topology_snapshot_id=SNAPSHOT_ID,
        involved_entity_id=POD_ID,
        involved_object_uid="pod-uid",
        involved_object_kind="Pod",
        involved_object_name="payments-abc-123",
        temporal=TemporalMetadata(
            effective_at=INCIDENT_AT,
            source_event_at=INCIDENT_AT,
            observed_at=INCIDENT_AT + timedelta(seconds=10),
            time_origin=TimeOrigin.SOURCE_REPORTED,
            time_quality=TimeQuality.EXACT,
            source_field="KubernetesEvent.first_timestamp",
            source_time_authoritative=True,
            status=TemporalStatus.PARTIAL,
        ),
    )


def _incident(
    *,
    primary_signal_id: str = "signal:tc4",
) -> IncidentRecord:
    return IncidentRecord(
        incident_id=INCIDENT_ID,
        fingerprint="incident-fingerprint:tc4",
        status="investigating",
        severity="error",
        title="payments unavailable",
        summary="payments failed after deployment",
        cluster_name="prod",
        namespace="payments",
        primary_signal_id=primary_signal_id,
        latest_signal_id=primary_signal_id or None,
        topology_snapshot_id=SNAPSHOT_ID,
        affected_entity_id=POD_ID,
        affected_object_kind="Pod",
        affected_object_name="payments-abc-123",
        first_observed_at=INCIDENT_AT.isoformat(),
        last_observed_at=INCIDENT_AT.isoformat(),
        created_at=(INCIDENT_AT + timedelta(minutes=1)).isoformat(),
        updated_at=(INCIDENT_AT + timedelta(minutes=1)).isoformat(),
        tenant_id=TEST_TENANT,
    )


def _event(
    *,
    external_id: str = "deployment:42",
    occurred_at: datetime = CHANGE_AT,
    event_cluster: str = "prod",
    entity_reference: bool = True,
    ambiguous_reference: bool = False,
    kind: ChangeEventKind = ChangeEventKind.DEPLOYMENT,
    source: ChangeEventSource = ChangeEventSource.GITHUB,
    title: str = "Deploy payments v42",
    commit_sha: str | None = "abc123",
) -> ChangeEventCreate:
    refs = []
    if entity_reference:
        refs = [
            ChangeEventEntityReference(
                entity_id=(None if ambiguous_reference else DEPLOYMENT_ID),
                kind="KubernetesDeployment",
                name="payments",
                namespace="payments",
                cluster_name="prod",
            )
        ]
    return ChangeEventCreate(
        source=source,
        kind=kind,
        external_id=external_id,
        title=title,
        occurred_at=occurred_at.isoformat(),
        cluster_name=event_cluster,
        namespace="payments",
        environment="production",
        repository="company/payments",
        commit_sha=commit_sha,
        entity_refs=refs,
    )


def _persist_event(
    session: Session,
    request: ChangeEventCreate,
    *,
    observed_at: datetime = RECEIVED_AT,
    source_time_trusted: bool = True,
) -> str:
    receipt = ingest_change_event(
        session,
        request=request,
        correlation_snapshot_id=SNAPSHOT_ID,
        source_time_trusted=source_time_trusted,
        observed_at=observed_at.isoformat(),
        tenant_id=TEST_TENANT,
    )
    return receipt.event_id


def _analysis_fixture(
    *,
    immutable_image: bool = False,
    legacy_relationship: bool = False,
    ambiguous_identity: bool = False,
    event: ChangeEventCreate | None = None,
    persist: bool = True,
    include_signal: bool = True,
    primary_signal_id: str = "signal:tc4",
    reverse_source_reference_order: bool = False,
    source_time_trusted: bool = True,
) -> tuple[Session, GraphSnapshot, CausalAnalysisResponse]:
    session = _session()
    snapshot = _snapshot(
        immutable_image=immutable_image,
        legacy_relationship=legacy_relationship,
        ambiguous_identity=ambiguous_identity,
        reverse_source_reference_order=reverse_source_reference_order,
    )
    save_snapshot(session, snapshot, tenant_id=TEST_TENANT)
    if include_signal:
        save_signals(session, [_signal()], tenant_id=TEST_TENANT)
    incident = _incident(primary_signal_id=primary_signal_id)
    session.add(incident)
    session.commit()
    _persist_event(
        session,
        event
        or _event(ambiguous_reference=ambiguous_identity),
        source_time_trusted=source_time_trusted,
    )
    analysis = analyze_causal_rca(
        session,
        incident_id=INCIDENT_ID,
        request=CausalAnalysisRequest(),
        persist=persist,
        tenant_id=TEST_TENANT,
    )
    assert analysis.top_hypothesis is not None
    assert analysis.top_hypothesis.evidence_ledger is not None
    return session, snapshot, analysis


def _ledger_items(analysis: CausalAnalysisResponse):
    ledger = analysis.top_hypothesis.evidence_ledger
    assert ledger is not None
    return ledger, [*ledger.supporting, *ledger.contradicting, *ledger.missing]


def test_ranked_hypothesis_has_structured_durable_supporting_evidence() -> None:
    _, _, analysis = _analysis_fixture()
    ledger, items = _ledger_items(analysis)
    assert ledger.ledger_version == CAUSAL_EVIDENCE_LEDGER_VERSION
    assert ledger.supporting
    source_change = next(
        item
        for item in ledger.supporting
        if item.claim_type == CausalEvidenceClaimType.SOURCE_CHANGE
    )
    assert source_change.change_event_ids
    assert source_change.source_references[0].reference_type == "change_event"
    assert all(item.hypothesis_id == analysis.top_hypothesis.hypothesis_id for item in items)


def test_tc1_tc2_tc3_and_signal_evidence_are_preserved() -> None:
    _, _, analysis = _analysis_fixture()
    ledger, _ = _ledger_items(analysis)
    identity = next(
        item
        for item in ledger.supporting
        if item.claim_type == CausalEvidenceClaimType.IDENTITY_RESOLUTION
    )
    assert identity.identity_resolution is not None
    assert identity.identity_resolution.strategy.value == "scoped_alias"
    temporal = next(
        item
        for item in ledger.supporting
        if item.claim_type == CausalEvidenceClaimType.TEMPORAL_PRECEDENCE
    )
    assert temporal.temporal is not None
    assert temporal.temporal.effective_at == CHANGE_AT
    assert temporal.temporal.observed_at == RECEIVED_AT
    assert temporal.incident_boundary_at == INCIDENT_AT.isoformat()
    topology = next(
        item
        for item in ledger.supporting
        if item.claim_type == CausalEvidenceClaimType.TOPOLOGY_PATH
    )
    assert topology.snapshot_id == SNAPSHOT_ID
    assert topology.relationship is not None
    assert topology.relationship.relationship_id in topology.relationship_ids
    assert topology.relationship.origin == RelationshipOrigin.DECLARED
    assert topology.relationship.linker_version == "tc4-fixture:v1"
    runtime = next(
        item
        for item in ledger.supporting
        if item.claim_type == CausalEvidenceClaimType.RUNTIME_FAILURE
    )
    assert runtime.signal_ids == ["signal:tc4"]


def test_late_preincident_change_is_supporting_without_collapsing_record_time() -> None:
    _, _, analysis = _analysis_fixture()
    ledger, _ = _ledger_items(analysis)
    item = next(
        item
        for item in ledger.supporting
        if item.claim_type == CausalEvidenceClaimType.TEMPORAL_PRECEDENCE
    )
    assert item.temporal is not None
    assert item.temporal.effective_at == CHANGE_AT
    assert item.temporal.observed_at == RECEIVED_AT
    assert item.temporal.observed_at > INCIDENT_AT
    assert item.stance == CausalEvidenceStance.SUPPORTING


def test_postincident_change_is_a_real_temporal_contradiction() -> None:
    _, _, analysis = _analysis_fixture(
        event=_event(occurred_at=INCIDENT_AT + timedelta(minutes=2))
    )
    ledger, _ = _ledger_items(analysis)
    contradictions = [
        item
        for item in ledger.contradicting
        if item.claim_type == CausalEvidenceClaimType.TEMPORAL_PRECEDENCE
    ]
    assert len(contradictions) == 1
    assert not any(
        item.claim_type == CausalEvidenceClaimType.TEMPORAL_PRECEDENCE
        for item in ledger.supporting
    )


def test_scope_incompatibility_is_contradicting_entity_evidence() -> None:
    _, _, analysis = _analysis_fixture(
        event=_event(event_cluster="staging")
    )
    ledger, _ = _ledger_items(analysis)
    conflict = next(
        item
        for item in ledger.contradicting
        if item.claim_type == CausalEvidenceClaimType.ENTITY_LINKAGE
    )
    assert "Candidate cluster 'staging'" in conflict.reason
    assert conflict.change_event_ids
    assert conflict.snapshot_id == SNAPSHOT_ID


def test_ambiguous_identity_is_missing_and_never_positive_support() -> None:
    _, _, analysis = _analysis_fixture(ambiguous_identity=True)
    ledger, _ = _ledger_items(analysis)
    missing = next(
        item
        for item in ledger.missing
        if item.claim_type == CausalEvidenceClaimType.IDENTITY_RESOLUTION
    )
    assert missing.identity_resolution is not None
    assert missing.identity_resolution.status.value == "ambiguous"
    assert len(missing.identity_resolution.candidate_entity_ids) == 2
    assert not any(
        item.claim_type == CausalEvidenceClaimType.IDENTITY_RESOLUTION
        for item in ledger.supporting
    )


def test_legacy_relationship_provenance_is_honest_missing_evidence() -> None:
    _, _, analysis = _analysis_fixture(legacy_relationship=True)
    ledger, _ = _ledger_items(analysis)
    item = next(
        item
        for item in ledger.missing
        if item.claim_type == CausalEvidenceClaimType.RELATIONSHIP_PROVENANCE
        and "deployment-owns-rs" in item.relationship_ids[0]
    )
    assert item.quality == CausalEvidenceQuality.LEGACY
    assert item.relationship is not None
    assert item.relationship.completeness.value == "legacy_unspecified"
    assert item.stance == CausalEvidenceStance.MISSING


def test_mutable_tag_has_limited_support_and_missing_immutable_proof() -> None:
    _, _, analysis = _analysis_fixture(immutable_image=False)
    ledger, _ = _ledger_items(analysis)
    support = next(
        item
        for item in ledger.supporting
        if item.claim_type == CausalEvidenceClaimType.ARTIFACT_PROVENANCE
    )
    missing = next(
        item
        for item in ledger.missing
        if item.claim_type == CausalEvidenceClaimType.ARTIFACT_PROVENANCE
    )
    assert support.quality == CausalEvidenceQuality.LIMITED
    assert missing.stance == CausalEvidenceStance.MISSING
    assert "immutable image digest" in missing.reason


def test_immutable_digest_is_directer_than_mutable_tag_without_score_change() -> None:
    _, _, mutable = _analysis_fixture(immutable_image=False)
    _, _, immutable = _analysis_fixture(immutable_image=True)
    mutable_item = next(
        item
        for item in mutable.top_hypothesis.evidence_ledger.supporting
        if item.claim_type == CausalEvidenceClaimType.ARTIFACT_PROVENANCE
    )
    immutable_item = next(
        item
        for item in immutable.top_hypothesis.evidence_ledger.supporting
        if item.claim_type == CausalEvidenceClaimType.ARTIFACT_PROVENANCE
    )
    assert mutable_item.quality == CausalEvidenceQuality.LIMITED
    assert immutable_item.quality == CausalEvidenceQuality.DIRECT
    assert immutable.top_hypothesis.score == mutable.top_hypothesis.score


def test_absent_optional_telemetry_creates_neither_contradiction_nor_spam() -> None:
    _, _, analysis = _analysis_fixture(
        event=_event(entity_reference=False),
        include_signal=False,
        primary_signal_id="",
    )
    ledger, _ = _ledger_items(analysis)
    assert ledger.contradicting == []
    assert ledger.missing == []
    assert {
        item.claim_type for item in ledger.supporting
    } == {
        CausalEvidenceClaimType.SOURCE_CHANGE,
        CausalEvidenceClaimType.TEMPORAL_PRECEDENCE,
    }


def test_explicit_expected_but_unavailable_signal_is_bounded_missing() -> None:
    _, _, analysis = _analysis_fixture(
        include_signal=False,
        primary_signal_id="signal:expected-but-missing",
    )
    ledger, _ = _ledger_items(analysis)
    missing = next(
        item
        for item in ledger.missing
        if item.claim_type == CausalEvidenceClaimType.RUNTIME_FAILURE
    )
    assert missing.signal_ids == ["signal:expected-but-missing"]
    assert missing.expectation_basis


def test_alternative_hypotheses_keep_separate_ledgers() -> None:
    session, _, _ = _analysis_fixture(persist=False)
    unrelated_id = _persist_event(
        session,
        _event(
            external_id="config:unrelated",
            occurred_at=CHANGE_AT + timedelta(minutes=1),
            entity_reference=False,
            kind=ChangeEventKind.CONFIGURATION,
            source=ChangeEventSource.MANUAL,
            title="Unrelated ConfigMap update",
            commit_sha=None,
        ).model_copy(update={"repository": "company/unrelated"}),
    )
    analysis = analyze_causal_rca(
        session,
        incident_id=INCIDENT_ID,
        request=CausalAnalysisRequest(),
        persist=False,
        tenant_id=TEST_TENANT,
    )
    assert len(analysis.hypotheses) >= 2
    for hypothesis in analysis.hypotheses:
        assert hypothesis.evidence_ledger is not None
        assert hypothesis.evidence_ledger.hypothesis_id == hypothesis.hypothesis_id
        event_ids = {
            event_id
            for item in hypothesis.evidence_ledger.supporting
            for event_id in item.change_event_ids
        }
        if hypothesis.target_event_id == unrelated_id:
            assert unrelated_id in event_ids
        else:
            assert unrelated_id not in event_ids


def test_evidence_ids_and_order_are_deterministic_across_record_times() -> None:
    _, _, first = _analysis_fixture()
    first_ledger = first.top_hypothesis.evidence_ledger
    session = _session()
    save_snapshot(session, _snapshot(), tenant_id=TEST_TENANT)
    save_signals(session, [_signal()], tenant_id=TEST_TENANT)
    session.add(_incident())
    session.commit()
    _persist_event(
        session,
        _event(),
        observed_at=RECEIVED_AT + timedelta(minutes=20),
    )
    second = analyze_causal_rca(
        session,
        incident_id=INCIDENT_ID,
        request=CausalAnalysisRequest(),
        persist=False,
        tenant_id=TEST_TENANT,
    )
    second_ledger = second.top_hypothesis.evidence_ledger
    first_ids = [
        item.evidence_id
        for item in [
            *first_ledger.supporting,
            *first_ledger.contradicting,
            *first_ledger.missing,
        ]
    ]
    second_ids = [
        item.evidence_id
        for item in [
            *second_ledger.supporting,
            *second_ledger.contradicting,
            *second_ledger.missing,
        ]
    ]
    assert first_ids == second_ids
    assert first_ledger.model_dump_json() == first_ledger.model_dump_json()


def test_provenance_serialization_order_does_not_change_evidence_identity() -> None:
    _, _, first = _analysis_fixture(reverse_source_reference_order=False)
    _, _, second = _analysis_fixture(reverse_source_reference_order=True)
    first_ids = {
        item.evidence_id
        for item in first.top_hypothesis.evidence_ledger.supporting
        if item.claim_type in {
            CausalEvidenceClaimType.TOPOLOGY_PATH,
            CausalEvidenceClaimType.RELATIONSHIP_PROVENANCE,
        }
    }
    second_ids = {
        item.evidence_id
        for item in second.top_hypothesis.evidence_ledger.supporting
        if item.claim_type in {
            CausalEvidenceClaimType.TOPOLOGY_PATH,
            CausalEvidenceClaimType.RELATIONSHIP_PROVENANCE,
        }
    }
    assert first_ids == second_ids


def test_legacy_analysis_without_ledger_loads_without_fabricated_evidence() -> None:
    _, _, analysis = _analysis_fixture(persist=False)
    payload = analysis.model_dump(mode="json")
    for hypothesis in payload["hypotheses"]:
        hypothesis.pop("evidence_ledger", None)
    payload["top_hypothesis"].pop("evidence_ledger", None)
    legacy = CausalAnalysisResponse.model_validate(payload)
    assert legacy.top_hypothesis.evidence_ledger is None
    assert all(item.evidence_ledger is None for item in legacy.hypotheses)


def test_new_ledger_persists_and_reloads_exactly() -> None:
    session, _, analysis = _analysis_fixture(persist=True)
    reloaded = load_causal_analysis(
        session, analysis_id=analysis.analysis_id, tenant_id=TEST_TENANT
    )
    latest = latest_causal_analysis(
        session, incident_id=INCIDENT_ID, tenant_id=TEST_TENANT
    )
    assert reloaded is not None
    assert latest is not None
    assert reloaded.model_dump_json() == analysis.model_dump_json()
    assert latest.top_hypothesis.evidence_ledger.model_dump_json() == (
        analysis.top_hypothesis.evidence_ledger.model_dump_json()
    )


def test_ar2_support_gate_persists_and_reloads_exactly() -> None:
    session, _, analysis = _analysis_fixture(
        event=_event(kind=ChangeEventKind.CONFIGURATION),
        persist=True,
    )
    reloaded = load_causal_analysis(
        session, analysis_id=analysis.analysis_id, tenant_id=TEST_TENANT
    )
    assert reloaded is not None
    assert analysis.support_policy_version == CAUSAL_SUPPORT_GATE_POLICY_VERSION
    assert analysis.top_hypothesis.support_gate is not None
    assert analysis.top_hypothesis.support_gate.support_state == (
        CausalEvidenceState.SUPPORTED_UNDER_CURRENT_MODEL
    )
    assert reloaded.top_hypothesis.support_gate.model_dump_json() == (
        analysis.top_hypothesis.support_gate.model_dump_json()
    )


def test_legacy_persisted_support_result_is_not_reclassified_on_readback() -> None:
    session, _, analysis = _analysis_fixture(
        event=_event(kind=ChangeEventKind.CONFIGURATION),
        persist=False,
    )
    payload = analysis.model_dump(mode="json")
    payload["analysis_id"] = "causal-analysis:legacy-pre-ar2"
    payload.pop("support_policy_version", None)
    payload["top_hypothesis"].pop("support_gate", None)
    for hypothesis in payload["hypotheses"]:
        hypothesis.pop("support_gate", None)
    persisted_state = payload["top_hypothesis"]["confidence_semantics"][
        "evidence_state"
    ]
    session.add(
        CausalAnalysisRecord(
            analysis_id=payload["analysis_id"],
            incident_id=payload["incident_id"],
            generated_at=payload["generated_at"],
            algorithm_version=payload["algorithm_version"],
            candidate_count=payload["candidate_count"],
            hypothesis_count=payload["hypothesis_count"],
            top_hypothesis_score=payload["top_hypothesis"]["score"],
            top_root_event_id=payload["top_hypothesis"]["root_event_id"],
            payload_json=json.dumps(payload),
            created_at=RECEIVED_AT.isoformat(),
            updated_at=RECEIVED_AT.isoformat(),
            tenant_id=TEST_TENANT,
        )
    )
    session.commit()

    loaded = load_causal_analysis(
        session, analysis_id="causal-analysis:legacy-pre-ar2", tenant_id=TEST_TENANT
    )
    assert loaded is not None
    assert loaded.support_policy_version is None
    assert loaded.top_hypothesis.support_gate is None
    assert loaded.top_hypothesis.confidence_semantics.evidence_state.value == (
        persisted_state
    )


def test_same_generation_is_immutable_and_newer_topology_is_not_consulted() -> None:
    session, _, analysis = _analysis_fixture(persist=True)
    original = analysis.model_dump_json()
    newer = _snapshot(snapshot_id="snapshot:tc4:newer", legacy_relationship=True)
    newer = newer.model_copy(
        update={"collected_at": INCIDENT_AT + timedelta(hours=1)}
    )
    save_snapshot(session, newer, tenant_id=TEST_TENANT)
    rerun = analyze_causal_rca(
        session,
        incident_id=INCIDENT_ID,
        request=CausalAnalysisRequest(),
        persist=True,
        tenant_id=TEST_TENANT,
    )
    assert rerun.analysis_id == analysis.analysis_id
    assert rerun.model_dump_json() == original
    relationship_ids = {
        relationship_id
        for item in rerun.top_hypothesis.evidence_ledger.supporting
        for relationship_id in item.relationship_ids
    }
    assert "relationship:deployment-owns-rs" in relationship_ids
    assert rerun.topology_snapshot_id == SNAPSHOT_ID
    assert session.query(CausalAnalysisRecord).count() == 1


def test_late_evidence_creates_new_generation_without_mutating_generation_one() -> None:
    session, _, generation_one = _analysis_fixture(persist=True)
    generation_one_json = generation_one.model_dump_json()
    late_id = _persist_event(
        session,
        _event(
            external_id="pipeline:41",
            occurred_at=CHANGE_AT - timedelta(minutes=2),
            kind=ChangeEventKind.PIPELINE,
            title="Build payments v42",
        ),
        observed_at=RECEIVED_AT + timedelta(minutes=30),
    )
    generation_two = analyze_causal_rca(
        session,
        incident_id=INCIDENT_ID,
        request=CausalAnalysisRequest(),
        persist=True,
        tenant_id=TEST_TENANT,
    )
    assert generation_two.analysis_id != generation_one.analysis_id
    assert session.query(CausalAnalysisRecord).count() == 2
    reloaded_one = load_causal_analysis(
        session, analysis_id=generation_one.analysis_id, tenant_id=TEST_TENANT
    )
    assert reloaded_one.model_dump_json() == generation_one_json
    generation_two_event_ids = {
        event_id
        for hypothesis in generation_two.hypotheses
        for item in hypothesis.evidence_ledger.supporting
        for event_id in item.change_event_ids
    }
    assert late_id in generation_two_event_ids


def test_briefing_reuses_the_canonical_hypothesis_ledger() -> None:
    session, _, analysis = _analysis_fixture(persist=True)
    briefing = build_incident_briefing(
        session, incident_id=INCIDENT_ID, include_ai=False, tenant_id=TEST_TENANT
    )
    assert briefing.causal_evidence_ledger is not None
    assert briefing.causal_evidence_ledger.model_dump_json() == (
        analysis.top_hypothesis.evidence_ledger.model_dump_json()
    )


def test_evidence_counts_do_not_change_existing_score_or_ranking_constants() -> None:
    _, _, analysis = _analysis_fixture()
    hypothesis = analysis.top_hypothesis
    original_score = hypothesis.score
    ledger = hypothesis.evidence_ledger
    hypothesis.evidence_ledger = ledger.model_copy(
        update={"supporting": [*ledger.supporting, *ledger.supporting]}
    )
    assert hypothesis.score == original_score
    source = inspect.getsource(causal_service.analyze_causal_rca)
    assert "candidate.score * 0.40" in source
    assert "+ topology_component * 25" in source
    assert "+ temporal_component * 15" in source
    assert "+ _kind_prior" in source and ") * 10" in source
    assert "+ lineage_component * 10" in source


def test_history_response_llm_fuzzy_and_new_traversal_cannot_feed_ledger() -> None:
    source = inspect.getsource(ledger_service)
    causal_source = inspect.getsource(causal_service)
    forbidden = (
        "incident_similarity",
        "incident_memory",
        "incident_outcome",
        "response_plan",
        "response_intelligence",
        "llm_client",
        "generate_openai",
        "Groq",
        "fuzzywuzzy",
        "embedding",
    )
    assert all(token not in source for token in forbidden)
    assert all(token not in causal_source for token in forbidden)
    assert "deque" not in source
    assert source.count("def _relationship_between") == 1


def test_tc4_does_not_change_snapshot_digest_or_change_fingerprint() -> None:
    session, snapshot, analysis = _analysis_fixture()
    digest_before = topology_state_digest(snapshot)
    ledger_json = analysis.top_hypothesis.evidence_ledger.model_dump_json()
    assert ledger_json
    assert topology_state_digest(snapshot) == digest_before
    event_record = session.query(
        __import__("app.db.models", fromlist=["ChangeEventRecord"])
        .ChangeEventRecord
    ).one()
    fingerprint = event_record.event_fingerprint
    analyze_causal_rca(
        session,
        incident_id=INCIDENT_ID,
        request=CausalAnalysisRequest(),
        persist=False,
        tenant_id=TEST_TENANT,
    )
    assert event_record.event_fingerprint == fingerprint


def test_recent_but_unlinked_change_gets_no_invented_linkage_support() -> None:
    session, _, _ = _analysis_fixture(persist=False)
    unrelated_id = _persist_event(
        session,
        _event(
            external_id="deployment:unrelated",
            occurred_at=CHANGE_AT + timedelta(minutes=2),
            entity_reference=False,
            title="Recent but unlinked Deployment A",
            commit_sha=None,
            source=ChangeEventSource.MANUAL,
        ).model_copy(update={"repository": "company/unrelated"}),
    )
    analysis = analyze_causal_rca(
        session,
        incident_id=INCIDENT_ID,
        request=CausalAnalysisRequest(),
        persist=False,
        tenant_id=TEST_TENANT,
    )
    hypothesis = next(
        item for item in analysis.hypotheses
        if item.target_event_id == unrelated_id
    )
    support_types = {
        item.claim_type for item in hypothesis.evidence_ledger.supporting
    }
    assert CausalEvidenceClaimType.ENTITY_LINKAGE not in support_types
    assert CausalEvidenceClaimType.TOPOLOGY_PATH not in support_types


def test_every_item_has_valid_stance_and_required_references() -> None:
    _, _, analysis = _analysis_fixture(legacy_relationship=True)
    for hypothesis in analysis.hypotheses:
        ledger = hypothesis.evidence_ledger
        for expected, items in (
            (CausalEvidenceStance.SUPPORTING, ledger.supporting),
            (CausalEvidenceStance.CONTRADICTING, ledger.contradicting),
            (CausalEvidenceStance.MISSING, ledger.missing),
        ):
            for item in items:
                assert item.stance == expected
                assert (
                    item.source_references
                    or item.entity_ids
                    or item.relationship_ids
                    or item.change_event_ids
                    or item.signal_ids
                    or item.snapshot_id
                )
                if expected == CausalEvidenceStance.MISSING:
                    assert item.expectation_basis


def test_machine_contract_matches_every_active_emitted_claim_type() -> None:
    session, _, _ = _analysis_fixture(persist=False)
    _persist_event(
        session,
        _event(
            external_id="pipeline:40",
            occurred_at=CHANGE_AT - timedelta(minutes=2),
            kind=ChangeEventKind.PIPELINE,
            title="Build payments v42",
        ),
    )
    analysis = analyze_causal_rca(
        session,
        incident_id=INCIDENT_ID,
        request=CausalAnalysisRequest(),
        persist=False,
        tenant_id=TEST_TENANT,
    )
    emitted = {
        item.claim_type.value
        for hypothesis in analysis.hypotheses
        for item in [
            *hypothesis.evidence_ledger.supporting,
            *hypothesis.evidence_ledger.contradicting,
            *hypothesis.evidence_ledger.missing,
        ]
    }
    contract_path = (
        Path(__file__).parents[2]
        / "docs"
        / "architecture"
        / "truth-contract"
        / "causal-evidence-ledger-contract.json"
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    declared = {
        item["claim_type"] for item in contract["active_claim_types"]
    }
    enum_values = {item.value for item in CausalEvidenceClaimType}
    assert declared == enum_values
    assert emitted == enum_values


def test_exact_identity_resolution_is_backed_by_durable_entity_link() -> None:
    _, _, analysis = _analysis_fixture()
    ledger, _ = _ledger_items(analysis)
    identity = next(
        item
        for item in ledger.supporting
        if item.claim_type == CausalEvidenceClaimType.IDENTITY_RESOLUTION
    )
    linkage = next(
        item
        for item in ledger.supporting
        if item.claim_type == CausalEvidenceClaimType.ENTITY_LINKAGE
    )
    assert identity.entity_ids == [DEPLOYMENT_ID]
    assert linkage.entity_ids == [DEPLOYMENT_ID]
    assert any(
        ref.reference_type == "change_entity_link"
        for ref in identity.source_references
    )


def test_required_unresolved_identity_is_explicit_missing_evidence() -> None:
    unresolved_ref = ChangeEventEntityReference(
        entity_id="entity:workload:not-in-snapshot",
        kind="KubernetesDeployment",
        name="not-in-snapshot",
        namespace="payments",
        cluster_name="prod",
    )
    event = _event().model_copy(update={"entity_refs": [unresolved_ref]})
    _, _, analysis = _analysis_fixture(event=event)
    ledger, _ = _ledger_items(analysis)
    missing = next(
        item
        for item in ledger.missing
        if item.claim_type == CausalEvidenceClaimType.IDENTITY_RESOLUTION
    )
    assert missing.identity_resolution is not None
    assert missing.identity_resolution.status.value == "unresolved"
    assert missing.expectation_basis
    assert not any(
        item.claim_type == CausalEvidenceClaimType.IDENTITY_RESOLUTION
        for item in ledger.supporting
    )


def test_untrusted_postincident_time_is_missing_not_contradicting() -> None:
    _, _, analysis = _analysis_fixture(
        event=_event(occurred_at=INCIDENT_AT + timedelta(minutes=2)),
        source_time_trusted=False,
    )
    ledger, _ = _ledger_items(analysis)
    assert any(
        item.claim_type == CausalEvidenceClaimType.TEMPORAL_PRECEDENCE
        for item in ledger.missing
    )
    assert not any(
        item.claim_type == CausalEvidenceClaimType.TEMPORAL_PRECEDENCE
        for item in ledger.contradicting
    )


def test_supporting_change_reference_points_to_persisted_event() -> None:
    session, _, analysis = _analysis_fixture()
    source_item = next(
        item
        for item in analysis.top_hypothesis.evidence_ledger.supporting
        if item.claim_type == CausalEvidenceClaimType.SOURCE_CHANGE
    )
    event_id = source_item.change_event_ids[0]
    event_record = session.query(
        __import__("app.db.models", fromlist=["ChangeEventRecord"])
        .ChangeEventRecord
    ).filter_by(event_id=event_id).one_or_none()
    assert event_record is not None
    assert source_item.source_references[0].reference_id == event_id


def test_topology_evidence_relationship_exists_in_pinned_snapshot() -> None:
    _, snapshot, analysis = _analysis_fixture()
    relationship_ids = {item.id for item in snapshot.relationships}
    path_items = [
        item
        for item in analysis.top_hypothesis.evidence_ledger.supporting
        if item.claim_type == CausalEvidenceClaimType.TOPOLOGY_PATH
    ]
    assert path_items
    assert all(
        set(item.relationship_ids) <= relationship_ids
        and item.snapshot_id == snapshot.snapshot_id
        for item in path_items
    )


def test_relationship_evidence_keeps_tc2_source_references() -> None:
    _, _, analysis = _analysis_fixture()
    provenance = next(
        item
        for item in analysis.top_hypothesis.evidence_ledger.supporting
        if item.claim_type == CausalEvidenceClaimType.RELATIONSHIP_PROVENANCE
    )
    assert provenance.relationship is not None
    assert {
        ref.reference_type for ref in provenance.relationship.source_references
    } == {"kubernetes_uid", "object_kind"}


def test_missing_artifact_proof_never_becomes_contradiction() -> None:
    _, _, analysis = _analysis_fixture(immutable_image=False)
    ledger, _ = _ledger_items(analysis)
    assert any(
        item.claim_type == CausalEvidenceClaimType.ARTIFACT_PROVENANCE
        for item in ledger.missing
    )
    assert not any(
        item.claim_type == CausalEvidenceClaimType.ARTIFACT_PROVENANCE
        for item in ledger.contradicting
    )


def test_runtime_signal_evidence_retains_tc3_effective_time() -> None:
    _, _, analysis = _analysis_fixture()
    runtime = next(
        item
        for item in analysis.top_hypothesis.evidence_ledger.supporting
        if item.claim_type == CausalEvidenceClaimType.RUNTIME_FAILURE
    )
    assert runtime.temporal is not None
    assert runtime.temporal.effective_at == INCIDENT_AT
    assert runtime.temporal.observed_at == INCIDENT_AT + timedelta(seconds=10)


def test_duplicate_supporting_items_do_not_rescore_hypothesis() -> None:
    _, _, analysis = _analysis_fixture()
    hypothesis = analysis.top_hypothesis
    before = (hypothesis.rank, hypothesis.score, hypothesis.confidence)
    ledger = hypothesis.evidence_ledger
    hypothesis.evidence_ledger = ledger.model_copy(
        update={"supporting": [*ledger.supporting, *ledger.supporting]}
    )
    assert (hypothesis.rank, hypothesis.score, hypothesis.confidence) == before


def test_repeated_generation_serializes_the_same_ledger() -> None:
    session, _, analysis = _analysis_fixture(persist=False)
    repeated = analyze_causal_rca(
        session,
        incident_id=INCIDENT_ID,
        request=CausalAnalysisRequest(),
        persist=False,
        tenant_id=TEST_TENANT,
    )
    assert repeated.top_hypothesis.evidence_ledger.model_dump_json() == (
        analysis.top_hypothesis.evidence_ledger.model_dump_json()
    )


def test_evidence_prose_does_not_change_evidence_identity() -> None:
    common = {
        "hypothesis_id": "hypothesis:test",
        "stance": CausalEvidenceStance.SUPPORTING,
        "claim_type": CausalEvidenceClaimType.SOURCE_CHANGE,
        "source_category": CausalEvidenceSourceCategory.CHANGE,
        "quality": CausalEvidenceQuality.DIRECT,
        "source_references": [
            ledger_service._reference("change_event", "change-event:test")
        ],
        "change_event_ids": ["change-event:test"],
    }
    first = ledger_service._item(
        summary="First wording",
        reason="First reason",
        why_it_matters="First explanation",
        **common,
    )
    second = ledger_service._item(
        summary="Reworded summary",
        reason="Reworded reason",
        why_it_matters="Reworded explanation",
        **common,
    )
    assert first.evidence_id == second.evidence_id


def test_reference_attributes_do_not_change_evidence_identity() -> None:
    common = {
        "hypothesis_id": "hypothesis:test",
        "stance": CausalEvidenceStance.SUPPORTING,
        "claim_type": CausalEvidenceClaimType.SOURCE_CHANGE,
        "source_category": CausalEvidenceSourceCategory.CHANGE,
        "quality": CausalEvidenceQuality.DIRECT,
        "summary": "Change exists",
        "reason": "Durable change",
        "why_it_matters": "Auditable source",
        "change_event_ids": ["change-event:test"],
    }
    first = ledger_service._item(
        source_references=[
            ledger_service._reference(
                "change_event",
                "change-event:test",
                attributes={"recorded_at": "2026-08-21T10:08:00Z"},
            )
        ],
        **common,
    )
    second = ledger_service._item(
        source_references=[
            ledger_service._reference(
                "change_event",
                "change-event:test",
                attributes={"recorded_at": "2026-08-21T11:08:00Z"},
            )
        ],
        **common,
    )
    assert first.evidence_id == second.evidence_id


def test_evidence_quality_label_does_not_change_evidence_identity() -> None:
    common = {
        "hypothesis_id": "hypothesis:test",
        "stance": CausalEvidenceStance.SUPPORTING,
        "claim_type": CausalEvidenceClaimType.ARTIFACT_PROVENANCE,
        "source_category": CausalEvidenceSourceCategory.ARTIFACT,
        "summary": "Artifact observed",
        "reason": "Artifact relationship exists",
        "why_it_matters": "Runtime linkage",
        "source_references": [
            ledger_service._reference("relationship", "relationship:test")
        ],
        "entity_ids": [DEPLOYMENT_ID, "artifact:container-image:test"],
        "relationship_ids": ["relationship:test"],
        "snapshot_id": SNAPSHOT_ID,
    }
    direct = ledger_service._item(quality=CausalEvidenceQuality.DIRECT, **common)
    limited = ledger_service._item(quality=CausalEvidenceQuality.LIMITED, **common)
    assert direct.evidence_id == limited.evidence_id


def test_ledger_item_without_any_durable_reference_is_rejected() -> None:
    with pytest.raises(ValueError, match="defensible reference"):
        ledger_service._item(
            hypothesis_id="hypothesis:test",
            stance=CausalEvidenceStance.SUPPORTING,
            claim_type=CausalEvidenceClaimType.SOURCE_CHANGE,
            summary="No source",
            reason="No source",
            source_category=CausalEvidenceSourceCategory.CHANGE,
            quality=CausalEvidenceQuality.UNKNOWN,
            why_it_matters="Cannot be audited",
        )


def test_missing_item_without_expectation_basis_is_rejected() -> None:
    with pytest.raises(ValueError, match="expectation basis"):
        ledger_service._item(
            hypothesis_id="hypothesis:test",
            stance=CausalEvidenceStance.MISSING,
            claim_type=CausalEvidenceClaimType.RUNTIME_FAILURE,
            summary="Signal absent",
            reason="Signal absent",
            source_category=CausalEvidenceSourceCategory.SIGNAL,
            quality=CausalEvidenceQuality.UNKNOWN,
            why_it_matters="Failure evidence",
            signal_ids=["signal:test"],
        )


def test_ledger_rejects_an_item_in_the_wrong_stance_bucket() -> None:
    item = ledger_service._item(
        hypothesis_id="hypothesis:test",
        stance=CausalEvidenceStance.CONTRADICTING,
        claim_type=CausalEvidenceClaimType.TEMPORAL_PRECEDENCE,
        summary="Postincident",
        reason="Effective time follows incident",
        source_category=CausalEvidenceSourceCategory.TEMPORAL,
        quality=CausalEvidenceQuality.DIRECT,
        why_it_matters="Temporal conflict",
        change_event_ids=["change-event:test"],
        incident_boundary_at=INCIDENT_AT.isoformat(),
    )
    with pytest.raises(ValueError, match="wrong stance bucket"):
        CausalEvidenceLedger(
            hypothesis_id="hypothesis:test",
            supporting=[item],
        )


def test_contract_allowed_stances_cover_all_emitted_stances() -> None:
    _, _, analysis = _analysis_fixture(
        event=_event(event_cluster="staging")
    )
    contract_path = (
        Path(__file__).parents[2]
        / "docs"
        / "architecture"
        / "truth-contract"
        / "causal-evidence-ledger-contract.json"
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    allowed = {
        item["claim_type"]: set(item["allowed_stances"])
        for item in contract["active_claim_types"]
    }
    for hypothesis in analysis.hypotheses:
        ledger = hypothesis.evidence_ledger
        for item in [*ledger.supporting, *ledger.contradicting, *ledger.missing]:
            assert item.stance.value in allowed[item.claim_type.value]


def test_history_services_are_not_imported_by_ledger_builder() -> None:
    imports = inspect.getsource(ledger_service).split("def _enum_value", 1)[0]
    assert "incident_memory" not in imports
    assert "incident_similarity" not in imports
    assert "incident_outcome" not in imports


def test_response_services_are_not_imported_by_ledger_builder() -> None:
    imports = inspect.getsource(ledger_service).split("def _enum_value", 1)[0]
    assert "response_plan" not in imports
    assert "response_intelligence" not in imports


def test_llm_is_not_imported_or_called_by_ledger_builder() -> None:
    source = inspect.getsource(ledger_service)
    assert "llm_client" not in source
    assert "generate_openai" not in source
    assert "chat_completion" not in source


def test_ledger_builder_has_no_fuzzy_or_embedding_identity_path() -> None:
    source = inspect.getsource(ledger_service)
    assert "fuzzywuzzy" not in source
    assert "rapidfuzz" not in source
    assert "embedding" not in source


def test_ledger_builder_reuses_path_without_graph_queue_or_search() -> None:
    source = inspect.getsource(ledger_service)
    assert "deque" not in source
    assert "shortest_path" not in source
    assert "breadth_first" not in source
    assert source.count("def _relationship_between") == 1


def test_resolved_identity_link_conflict_is_exact_contradiction() -> None:
    session = _session()
    save_snapshot(session, _snapshot(), tenant_id=TEST_TENANT)
    save_signals(session, [_signal()], tenant_id=TEST_TENANT)
    session.add(_incident())
    session.commit()
    event_id = _persist_event(session, _event())
    session.query(ChangeEntityLinkRecord).filter_by(event_id=event_id).delete()
    session.add(
        ChangeEntityLinkRecord(
            link_id="change-link:conflicting-pod",
            event_id=event_id,
            entity_id=POD_ID,
            link_type="automatic",
            confidence=1.0,
            reason="Fixture durable link points to the affected Pod.",
            snapshot_id=SNAPSHOT_ID,
            tenant_id=TEST_TENANT,
        )
    )
    session.commit()
    analysis = analyze_causal_rca(
        session,
        incident_id=INCIDENT_ID,
        request=CausalAnalysisRequest(),
        persist=False,
        tenant_id=TEST_TENANT,
    )
    ledger, _ = _ledger_items(analysis)
    identity = next(
        item
        for item in ledger.supporting
        if item.claim_type == CausalEvidenceClaimType.IDENTITY_RESOLUTION
    )
    conflict = next(
        item
        for item in ledger.contradicting
        if item.claim_type == CausalEvidenceClaimType.ENTITY_LINKAGE
    )
    assert identity.identity_resolution.status.value == "resolved"
    assert identity.entity_ids == [DEPLOYMENT_ID]
    assert conflict.entity_ids == sorted([DEPLOYMENT_ID, POD_ID])
    assert "change-link:conflicting-pod" in {
        ref.reference_id for ref in conflict.source_references
    }
    assert not any(
        item.claim_type == CausalEvidenceClaimType.IDENTITY_RESOLUTION
        and item.identity_resolution.status.value == "resolved"
        for item in ledger.missing
    )
