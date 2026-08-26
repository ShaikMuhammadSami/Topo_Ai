from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.services.causal_rca as causal_service
import app.services.causal_relevance_policy as relevance_policy
from app.db.database import Base
from app.db.models import CausalAnalysisRecord, IncidentRecord, SnapshotRecord
from app.models.causal_candidates import (
    CAUSAL_CANDIDATE_ADMISSION_POLICY_VERSION,
    CandidateAdmissionBasis,
    CandidateAdmissionEvidenceReference,
    LineageAdmissionReason,
    LineageAdmissionState,
    LineagePathAudit,
)
from app.models.causal_rca import CausalAnalysisRequest
from app.models.causal_relevance import (
    CAUSAL_RELEVANCE_POLICY_VERSION,
    CAUSAL_RELEVANCE_TOPOLOGY_POLICY_VERSION,
    CandidateCausalRelevanceAudit,
    CausalPathSemantic,
    CausalRelevanceResolutionBasis,
    CausalRelevanceStatus,
    CausalTopologyPathState,
    CausalTraversalDirection,
    LineageRelevanceBridgeState,
)
from app.models.causal_support import CAUSAL_SUPPORT_GATE_POLICY_VERSION
from app.models.confidence_semantics import CausalEvidenceState
from app.models.temporal import (
    TemporalMetadata,
    TemporalStatus,
    TimeOrigin,
    TimeQuality,
)
from app.models.change_events import (
    ChangeEntityLinkType,
    ChangeEntityLinkView,
    ChangeEventKind,
    ChangeEventRiskLevel,
    ChangeEventSource,
    ChangeEventView,
    IncidentChangeAnalysisResponse,
    IncidentChangeCandidate,
)
from app.models.topology import (
    Entity,
    EntityType,
    GraphSnapshot,
    Relationship,
    RelationshipOrigin,
    RelationshipProvenance,
    RelationshipProvenanceCompleteness,
    RelationshipType,
)
from app.repositories.causal_analysis_repository import latest_causal_analysis


NOW = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
EVENT = "change-event:source-a"
REVISION = "1" * 40
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
IMAGE_A = f"artifact:container-image:{DIGEST_A}"
IMAGE_B = f"artifact:container-image:{DIGEST_B}"
DEPLOYMENT = "k8s:deployment:checkout"
REPLICA_SET = "k8s:replicaset:checkout-rs"
POD = "k8s:pod:checkout-abc"


def _entity(
    entity_id: str,
    kind: str,
    entity_type: EntityType,
    *,
    digest: str | None = None,
) -> Entity:
    properties = {}
    external_id = entity_id
    if digest is not None:
        properties = {"digest": digest, "immutable": True}
        external_id = digest
    return Entity(
        id=entity_id,
        entity_type=entity_type,
        kind=kind,
        name=entity_id,
        source_system="test",
        external_id=external_id,
        identity_version="test-v1",
        observed_at=NOW,
        properties=properties,
    )


def _relationship(
    relationship_id: str,
    source: str,
    target: str,
    predicate: RelationshipType,
) -> Relationship:
    return Relationship(
        id=relationship_id,
        source_entity_id=source,
        target_entity_id=target,
        relationship_type=predicate,
        source_system="test-topology",
        observed_at=NOW,
        provenance=RelationshipProvenance(
            origin=RelationshipOrigin.DECLARED,
            source_component="test-topology",
            linker_version="tc2.v1",
            completeness=RelationshipProvenanceCompleteness.COMPLETE,
        ),
    )


def _runtime_relationships(
    image_id: str = IMAGE_A,
    *,
    prefix: str = "a",
) -> list[Relationship]:
    return [
        _relationship(
            f"relationship:{prefix}:uses",
            DEPLOYMENT,
            image_id,
            RelationshipType.USES,
        ),
        _relationship(
            f"relationship:{prefix}:owns",
            DEPLOYMENT,
            REPLICA_SET,
            RelationshipType.OWNS,
        ),
        _relationship(
            f"relationship:{prefix}:runs",
            REPLICA_SET,
            POD,
            RelationshipType.RUNS,
        ),
    ]


def _snapshot(
    *,
    image_a: bool = True,
    image_b: bool = False,
    relationships: list[Relationship] | None = None,
    snapshot_id: str = "snapshot:pinned",
) -> GraphSnapshot:
    entities = [
        _entity(DEPLOYMENT, "KubernetesDeployment", EntityType.WORKLOAD),
        _entity(REPLICA_SET, "KubernetesReplicaSet", EntityType.WORKLOAD),
        _entity(POD, "KubernetesPod", EntityType.RUNTIME_INSTANCE),
    ]
    if image_a:
        entities.append(
            _entity(IMAGE_A, "ContainerImage", EntityType.ARTIFACT, digest=DIGEST_A)
        )
    if image_b:
        entities.append(
            _entity(IMAGE_B, "ContainerImage", EntityType.ARTIFACT, digest=DIGEST_B)
        )
    return GraphSnapshot(
        snapshot_id=snapshot_id,
        collected_at=NOW,
        collector_name="test",
        collector_version="1",
        scope={"cluster_name": "production", "namespace": "checkout"},
        entities=entities,
        relationships=(
            list(relationships)
            if relationships is not None
            else _runtime_relationships()
        ),
    )


def _lineage_path(
    *,
    image_id: str = IMAGE_A,
    digest: str = DIGEST_A,
    path_id: str = "lineage-path:a",
    canonical_change_id: str = EVENT,
    image_kind: str = "ContainerImage",
    provider_evidence_ids: tuple[str, ...] = ("build-evidence:a",),
    run_id: str = "1001",
) -> LineagePathAudit:
    return LineagePathAudit(
        path_id=path_id,
        affected_entity_id=POD,
        entity_ids=[POD, REPLICA_SET, DEPLOYMENT, image_id],
        relationship_ids=[
            "relationship:a:uses",
            "relationship:a:owns",
            "relationship:a:runs",
        ],
        provider_evidence_ids=list(provider_evidence_ids),
        container_name="application",
        image_entity_id=image_id,
        image_entity_kind=image_kind,
        image_digest=digest,
        repository_id="repository:1",
        repository="example/topology-service",
        run_id=run_id,
        run_attempt=1,
        revision=REVISION,
        canonical_change_id=canonical_change_id,
        provider_effective_at=NOW.isoformat(),
    )


def _evidence_refs(*, reverse: bool = False):
    values = [
        CandidateAdmissionEvidenceReference(
            reference_type="build_artifact_evidence",
            reference="build-evidence:a",
            source_system="topo",
        ),
        CandidateAdmissionEvidenceReference(
            reference_type="container_image_digest",
            reference=DIGEST_A,
            source_system="provider",
        ),
        CandidateAdmissionEvidenceReference(
            reference_type="graph_entity_id",
            reference=IMAGE_A,
            source_system="topo",
        ),
    ]
    return list(reversed(values)) if reverse else values


def _lineage_relevance(
    snapshot: GraphSnapshot | None,
    *,
    paths: list[LineagePathAudit] | None = None,
    evidence_refs=None,
    event_id: str = EVENT,
    candidate_entity_ids: tuple[str, ...] = (),
    admission_policy: str = CAUSAL_CANDIDATE_ADMISSION_POLICY_VERSION,
    basis=(CandidateAdmissionBasis.EXACT_IMMUTABLE_LINEAGE,),
    state: LineageAdmissionState | str = LineageAdmissionState.ADMITTED,
    reason: LineageAdmissionReason | str = (
        LineageAdmissionReason.EXACT_IMMUTABLE_LINEAGE
    ),
    policy_version: str = CAUSAL_RELEVANCE_POLICY_VERSION,
):
    return relevance_policy.evaluate_causal_relevance(
        snapshot,
        candidate_event_id=event_id,
        candidate_entity_ids=candidate_entity_ids,
        affected_entity_ids=[POD],
        max_hops=4,
        relevance_policy_version=policy_version,
        candidate_admission_policy_version=admission_policy,
        admission_basis=basis,
        lineage_admission_state=state,
        lineage_admission_reason=reason,
        lineage_paths=paths if paths is not None else [_lineage_path()],
        admission_evidence_refs=(
            evidence_refs if evidence_refs is not None else _evidence_refs()
        ),
    )


def test_lineage_shaped_contract_uses_separate_exact_anchor() -> None:
    result = _lineage_relevance(_snapshot())

    assert result.relevance_policy_version == "causal-relevance-v2"
    assert result.relevance_status == CausalRelevanceStatus.SEMANTIC_PATH
    assert result.resolution_basis == (
        CausalRelevanceResolutionBasis.EXACT_IMMUTABLE_LINEAGE_ANCHOR
    )
    assert result.candidate_entity_id is None
    assert result.relevance_anchor_entity_id == IMAGE_A
    assert result.relevance_anchor_kind == "ContainerImage"
    assert result.bridge_source_change_id == EVENT
    assert result.bridge_revision == REVISION
    assert result.bridge_image_digest == DIGEST_A
    assert result.bridge_score == 0.0
    assert result.path_entity_ids == [IMAGE_A, DEPLOYMENT, REPLICA_SET, POD]
    assert result.path_predicates == ["uses", "owns", "runs"]
    assert result.path_traversal_directions == [
        CausalTraversalDirection.REVERSE,
        CausalTraversalDirection.FORWARD,
        CausalTraversalDirection.FORWARD,
    ]
    assert result.path_semantic == CausalPathSemantic.OTHER_SUPPORTED
    assert result.path_hops == 3
    assert result.topology_component == 0.45
    assert result.topology_path_state == CausalTopologyPathState.SUPPORTED


def test_topology_native_v2_preserves_v1_path_and_score() -> None:
    snapshot = _snapshot()
    common = dict(
        snapshot=snapshot,
        candidate_event_id="event:topology",
        candidate_entity_ids=[DEPLOYMENT],
        affected_entity_ids=[POD],
        max_hops=4,
    )
    v1 = relevance_policy.evaluate_causal_relevance(
        **common,
        relevance_policy_version=CAUSAL_RELEVANCE_TOPOLOGY_POLICY_VERSION,
    )
    v2 = relevance_policy.evaluate_causal_relevance(
        **common,
        relevance_policy_version=CAUSAL_RELEVANCE_POLICY_VERSION,
    )

    assert v1.path_entity_ids == v2.path_entity_ids
    assert v1.path_relationship_ids == v2.path_relationship_ids
    assert v1.path_predicates == v2.path_predicates
    assert v1.path_traversal_directions == v2.path_traversal_directions
    assert v1.path_semantic == v2.path_semantic
    assert v1.topology_component == v2.topology_component
    assert v2.resolution_basis == CausalRelevanceResolutionBasis.TOPOLOGY_ENTITY
    assert v2.bridge_state == LineageRelevanceBridgeState.NOT_APPLICABLE
    assert v2.relevance_anchor_entity_id is None


def test_topology_native_mode_calls_the_shared_path_engine(monkeypatch) -> None:
    original = relevance_policy.evaluate_topology_path
    calls = []

    def spy(*args, **kwargs):
        calls.append(tuple(kwargs["source_entity_ids"]))
        return original(*args, **kwargs)

    monkeypatch.setattr(relevance_policy, "evaluate_topology_path", spy)
    relevance_policy.evaluate_causal_relevance(
        _snapshot(),
        candidate_event_id="event:topology",
        candidate_entity_ids=[DEPLOYMENT],
        affected_entity_ids=[POD],
        max_hops=4,
    )
    _lineage_relevance(_snapshot())

    assert calls == [(DEPLOYMENT,), (IMAGE_A,)]


def test_unknown_policy_version_fails_safely() -> None:
    result = _lineage_relevance(
        _snapshot(), policy_version="causal-relevance-future"
    )
    assert result.relevance_status == CausalRelevanceStatus.IDENTITY_UNRESOLVED
    assert result.resolution_basis == CausalRelevanceResolutionBasis.UNRESOLVED
    assert result.bridge_reason == "unsupported_policy_version"
    assert result.topology_component == 0.0


@pytest.mark.parametrize(
    "updates,expected_reason",
    [
        ({"basis": (CandidateAdmissionBasis.TEMPORAL,)}, "lineage_admission_not_eligible"),
        ({"state": LineageAdmissionState.INCOMPLETE}, "lineage_admission_not_eligible"),
        ({"state": "ambiguous"}, "lineage_admission_not_eligible"),
        ({"reason": LineageAdmissionReason.IMAGE_TO_RUN_MISSING}, "lineage_admission_not_eligible"),
        ({"admission_policy": "causal-candidate-admission-v1"}, "lineage_admission_policy_not_eligible"),
    ],
)
def test_non_exact_lineage_admission_is_not_eligible(updates, expected_reason) -> None:
    result = _lineage_relevance(_snapshot(), **updates)
    assert result.relevance_status == CausalRelevanceStatus.IDENTITY_UNRESOLVED
    assert result.candidate_entity_id is None
    assert result.relevance_anchor_entity_id is None
    assert result.bridge_state == LineageRelevanceBridgeState.INELIGIBLE
    assert result.bridge_reason == expected_reason


def test_temporal_null_entity_candidate_remains_unresolved() -> None:
    result = relevance_policy.evaluate_causal_relevance(
        _snapshot(),
        candidate_event_id=EVENT,
        candidate_entity_ids=[],
        affected_entity_ids=[POD],
        max_hops=4,
        candidate_admission_policy_version=(
            CAUSAL_CANDIDATE_ADMISSION_POLICY_VERSION
        ),
        admission_basis=[CandidateAdmissionBasis.TEMPORAL],
    )
    assert result.relevance_status == CausalRelevanceStatus.IDENTITY_UNRESOLVED
    assert result.bridge_reason == "lineage_admission_not_eligible"
    assert result.topology_component == 0.0


@pytest.mark.parametrize(
    "paths,evidence_refs,expected_reason",
    [
        ([], _evidence_refs(), "lineage_bridge_missing"),
        ([_lineage_path()], [], "lineage_bridge_evidence_missing"),
        (
            [_lineage_path(provider_evidence_ids=())],
            _evidence_refs(),
            "lineage_bridge_incomplete",
        ),
        (
            [_lineage_path().model_copy(update={"image_entity_id": None})],
            _evidence_refs(),
            "lineage_bridge_incomplete",
        ),
    ],
)
def test_incomplete_bridge_fails_closed(paths, evidence_refs, expected_reason) -> None:
    result = _lineage_relevance(
        _snapshot(), paths=paths, evidence_refs=evidence_refs
    )
    assert result.relevance_status == CausalRelevanceStatus.IDENTITY_UNRESOLVED
    assert result.bridge_reason == expected_reason
    assert result.topology_component == 0.0


def test_candidate_mismatch_fails_closed() -> None:
    result = _lineage_relevance(
        _snapshot(),
        paths=[_lineage_path(canonical_change_id="change-event:other")],
    )
    assert result.bridge_state == LineageRelevanceBridgeState.CONFLICT
    assert result.bridge_reason == "lineage_candidate_mismatch"
    assert result.relevance_anchor_entity_id is None


def test_anchor_absent_from_pinned_topology_does_not_fallback() -> None:
    pinned = _snapshot(image_a=False, relationships=[])
    result = _lineage_relevance(pinned)

    assert result.relevance_status == CausalRelevanceStatus.IDENTITY_UNRESOLVED
    assert result.relevance_anchor_entity_id == IMAGE_A
    assert result.bridge_reason == "lineage_anchor_not_in_pinned_topology"
    assert "pinned" in result.reason
    assert result.path_relationship_ids == []


@pytest.mark.parametrize(
    "path",
    [
        _lineage_path(digest=DIGEST_B),
        _lineage_path(image_kind="ImageByTag"),
        _lineage_path(image_id=IMAGE_B, digest=DIGEST_B),
    ],
)
def test_anchor_requires_exact_entity_kind_and_digest(path) -> None:
    result = _lineage_relevance(_snapshot(), paths=[path])
    assert result.relevance_status == CausalRelevanceStatus.IDENTITY_UNRESOLVED
    assert result.bridge_reason in {
        "lineage_anchor_identity_conflict",
        "lineage_anchor_not_in_pinned_topology",
    }
    assert result.topology_component == 0.0


def test_no_digest_prefix_repository_tag_or_image_name_fallback() -> None:
    source = inspect.getsource(relevance_policy.evaluate_causal_relevance)
    assert "startswith" not in source
    assert "repository" not in source
    assert "tag" not in source
    assert "image name" not in source.casefold()


def test_wrong_artifact_has_no_relevance_path() -> None:
    relationships = _runtime_relationships(IMAGE_B, prefix="b")
    snapshot = _snapshot(
        image_a=True,
        image_b=True,
        relationships=relationships,
    )
    result = _lineage_relevance(snapshot)

    assert result.relevance_status == CausalRelevanceStatus.NO_SUPPORTED_PATH
    assert result.relevance_anchor_entity_id == IMAGE_A
    assert result.bridge_state == LineageRelevanceBridgeState.VALID
    assert result.topology_path_state == CausalTopologyPathState.UNSUPPORTED
    assert result.topology_component == 0.0
    assert "lineage_topology_path_missing" in result.reason


def test_contains_remains_non_propagating_from_lineage_anchor() -> None:
    snapshot = _snapshot(
        relationships=[
            _relationship(
                "relationship:contains",
                IMAGE_A,
                POD,
                RelationshipType.CONTAINS,
            )
        ]
    )
    result = _lineage_relevance(snapshot)
    assert result.relevance_status == CausalRelevanceStatus.NO_SUPPORTED_PATH
    assert result.path_relationship_ids == []


def test_duplicate_paths_same_anchor_are_deduplicated_without_score_change() -> None:
    paths = [
        _lineage_path(path_id="lineage-path:z", run_id="1002"),
        _lineage_path(path_id="lineage-path:a", run_id="1001"),
    ]
    result = _lineage_relevance(
        _snapshot(),
        paths=paths,
        evidence_refs=[*_evidence_refs(reverse=True), *_evidence_refs()],
    )

    assert len(result.anchor_audits) == 1
    assert result.bridge_path_ids == ["lineage-path:a", "lineage-path:z"]
    assert result.bridge_run_ids == ["1001", "1002"]
    assert len(result.bridge_evidence_refs) == 2
    assert all(
        item.reference_type != "graph_entity_id"
        for item in result.bridge_evidence_refs
    )
    assert all(
        item.reference_type != "topology_relationship"
        for item in result.bridge_evidence_refs
    )
    assert result.topology_component == 0.45
    assert result.bridge_score == 0.0


def test_duplicate_path_input_order_is_deterministic() -> None:
    paths = [
        _lineage_path(path_id="lineage-path:z", run_id="1002"),
        _lineage_path(path_id="lineage-path:a", run_id="1001"),
    ]
    first = _lineage_relevance(_snapshot(), paths=paths)
    second = _lineage_relevance(
        _snapshot(), paths=list(reversed(paths)), evidence_refs=_evidence_refs(reverse=True)
    )
    assert first.model_dump() == second.model_dump()


def test_multiple_distinct_admitted_anchors_select_supported_path() -> None:
    paths = [
        _lineage_path(image_id=IMAGE_A, digest=DIGEST_A, path_id="lineage-path:a"),
        _lineage_path(image_id=IMAGE_B, digest=DIGEST_B, path_id="lineage-path:b"),
    ]
    snapshot = _snapshot(
        image_a=True,
        image_b=True,
        relationships=_runtime_relationships(IMAGE_B, prefix="b"),
    )
    result = _lineage_relevance(snapshot, paths=paths)

    assert result.relevance_status == CausalRelevanceStatus.SEMANTIC_PATH
    assert result.relevance_anchor_entity_id == IMAGE_B
    assert len(result.anchor_audits) == 2
    by_anchor = {item.anchor_entity_id: item for item in result.anchor_audits}
    assert by_anchor[IMAGE_A].topology_path_state == CausalTopologyPathState.UNSUPPORTED
    assert by_anchor[IMAGE_B].topology_path_state == CausalTopologyPathState.SUPPORTED
    assert result.topology_component == 0.45


def test_multiple_supported_anchors_choose_deterministically_without_addition() -> None:
    paths = [
        _lineage_path(image_id=IMAGE_B, digest=DIGEST_B, path_id="lineage-path:b"),
        _lineage_path(image_id=IMAGE_A, digest=DIGEST_A, path_id="lineage-path:a"),
    ]
    relationships = [
        *_runtime_relationships(IMAGE_A, prefix="a"),
        *_runtime_relationships(IMAGE_B, prefix="b"),
    ]
    result = _lineage_relevance(
        _snapshot(image_a=True, image_b=True, relationships=relationships),
        paths=paths,
    )
    assert result.relevance_anchor_entity_id == IMAGE_A
    assert result.topology_component == 0.45
    assert result.bridge_score == 0.0


@pytest.mark.parametrize(
    "second",
    [
        _lineage_path(digest=DIGEST_B, path_id="lineage-path:conflict"),
        _lineage_path(image_kind="OtherImage", path_id="lineage-path:conflict"),
    ],
)
def test_conflicting_same_anchor_identity_fails_closed(second) -> None:
    result = _lineage_relevance(
        _snapshot(), paths=[_lineage_path(), second]
    )
    assert result.relevance_status == CausalRelevanceStatus.IDENTITY_UNRESOLVED
    assert result.bridge_state == LineageRelevanceBridgeState.CONFLICT
    assert result.bridge_reason == "lineage_anchor_identity_conflict"
    assert result.topology_component == 0.0


def test_legacy_v1_audit_payload_loads_without_v2_backfill() -> None:
    payload = {
        "candidate_event_id": "event:legacy",
        "candidate_entity_id": DEPLOYMENT,
        "affected_entity_id": POD,
        "relevance_policy_version": "causal-relevance-v1",
        "relevance_status": "no_supported_path",
        "path_semantic": "unsupported_unknown",
        "path_entity_ids": [],
        "path_relationship_ids": [],
        "path_predicates": [],
        "path_traversal_directions": [],
        "path_relationship_origins": [],
        "path_relationship_source_systems": [],
        "path_hops": 0,
        "topology_component": 0.0,
        "hops": [],
        "reason": "Historical v1 result.",
    }
    loaded = CandidateCausalRelevanceAudit.model_validate(payload)
    assert loaded.relevance_policy_version == "causal-relevance-v1"
    assert loaded.resolution_basis is None
    assert loaded.relevance_anchor_entity_id is None
    assert loaded.anchor_audits == []


def _source_candidate(*, score: float = 10.0) -> IncidentChangeCandidate:
    occurred = "2026-08-25T06:00:00+00:00"
    effective_at = datetime.fromisoformat(occurred)
    event = ChangeEventView(
        event_id=EVENT,
        event_fingerprint="fingerprint:source-a",
        source=ChangeEventSource.GITHUB,
        kind=ChangeEventKind.CODE,
        external_id="provider:source-a",
        origin_change_id=None,
        title="Source mutation",
        summary=None,
        actor="developer",
        occurred_at=occurred,
        received_at=NOW.isoformat(),
        environment="production",
        provider=None,
        account_id=None,
        region=None,
        cluster_name="production",
        namespace="checkout",
        repository="example/topology-service",
        commit_sha=REVISION,
        pipeline_name=None,
        release_version=None,
        terraform_workspace=None,
        risk_score=20,
        risk_level=ChangeEventRiskLevel.LOW,
        status="observed",
        observation_count=1,
        metadata={"source_file_mutations": [{"path": "src/mode.txt"}]},
        raw_payload={},
        agent_id=None,
        links=[],
        created_at=NOW.isoformat(),
        updated_at=NOW.isoformat(),
        temporal=TemporalMetadata(
            effective_at=effective_at,
            source_event_at=effective_at,
            observed_at=NOW,
            time_origin=TimeOrigin.SOURCE_REPORTED,
            time_quality=TimeQuality.EXACT,
            source_field="fixture.occurred_at",
            source_time_authoritative=True,
            status=TemporalStatus.COMPLETE,
        ),
    )
    return IncidentChangeCandidate(
        event=event,
        score=score,
        minutes_before_incident=1800.0,
        admission_basis=[CandidateAdmissionBasis.EXACT_IMMUTABLE_LINEAGE],
        admission_evidence_refs=_evidence_refs(),
        lineage_paths=[_lineage_path()],
        lineage_admission_state=LineageAdmissionState.ADMITTED,
        lineage_admission_reason=LineageAdmissionReason.EXACT_IMMUTABLE_LINEAGE,
        mutation_set=[{"path": "src/mode.txt"}],
        mutation_completeness="complete",
    )


def _topology_candidate(*, score: float = 90.0) -> IncidentChangeCandidate:
    occurred = "2026-08-26T11:58:00+00:00"
    link = ChangeEntityLinkView(
        link_id="link:deployment",
        event_id="event:deployment",
        entity_id=DEPLOYMENT,
        link_type=ChangeEntityLinkType.AUTOMATIC,
        confidence=1.0,
        reason="Exact topology identity.",
        snapshot_id="snapshot:pinned",
        created_at=occurred,
        updated_at=occurred,
    )
    event = ChangeEventView(
        event_id="event:deployment",
        event_fingerprint="fingerprint:deployment",
        source=ChangeEventSource.TOPOLOGY_DIFF,
        kind=ChangeEventKind.DEPLOYMENT,
        external_id="provider:deployment",
        origin_change_id="change:deployment",
        title="Deployment update",
        summary=None,
        actor=None,
        occurred_at=occurred,
        received_at=occurred,
        environment="production",
        provider="kubernetes",
        account_id=None,
        region=None,
        cluster_name="production",
        namespace="checkout",
        repository=None,
        commit_sha=None,
        pipeline_name=None,
        release_version=None,
        terraform_workspace=None,
        risk_score=80,
        risk_level=ChangeEventRiskLevel.HIGH,
        status="observed",
        observation_count=1,
        metadata={"change_type": "entity_updated", "category": "deployment"},
        raw_payload={},
        agent_id=None,
        links=[link],
        created_at=occurred,
        updated_at=occurred,
    )
    return IncidentChangeCandidate(
        event=event,
        score=score,
        minutes_before_incident=2.0,
    )


def _temporal_candidate(index: int = 0, *, score: float = 90.0):
    candidate = _topology_candidate(score=score)
    event_id = f"event:temporal-control:{index}"
    effective_at = NOW.replace(hour=11, minute=55)
    return candidate.model_copy(
        update={
            "event": candidate.event.model_copy(
                update={
                    "event_id": event_id,
                    "event_fingerprint": f"fingerprint:temporal-control:{index}",
                    "source": ChangeEventSource.GITHUB,
                    "kind": ChangeEventKind.CODE,
                    "external_id": f"provider:temporal-control:{index}",
                    "origin_change_id": None,
                    "title": f"Unlinked temporal control {index}",
                    "repository": f"example/unrelated-{index}",
                    "commit_sha": f"{index + 1:040x}",
                    "links": [],
                    "metadata": {},
                    "temporal": TemporalMetadata(
                        effective_at=effective_at,
                        source_event_at=effective_at,
                        observed_at=NOW,
                        time_origin=TimeOrigin.SOURCE_REPORTED,
                        time_quality=TimeQuality.EXACT,
                        source_field="fixture.occurred_at",
                        source_time_authoritative=True,
                        status=TemporalStatus.COMPLETE,
                    ),
                }
            ),
            "direct_entity_matches": [],
            "neighboring_entity_matches": [],
        }
    )


def _session(snapshot: GraphSnapshot) -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(
        SnapshotRecord(
            snapshot_id=snapshot.snapshot_id,
            schema_version=snapshot.schema_version,
            collected_at=snapshot.collected_at.isoformat(),
            collector_name=snapshot.collector_name,
            collector_version=snapshot.collector_version,
            cluster_name="production",
            namespace="checkout",
            entity_count=len(snapshot.entities),
            relationship_count=len(snapshot.relationships),
            evidence_count=0,
            scope_json=json.dumps(snapshot.scope),
            payload_json=snapshot.model_dump_json(),
            created_at=NOW.isoformat(),
        )
    )
    session.add(
        IncidentRecord(
            incident_id="incident:sc4",
            fingerprint="fingerprint:sc4",
            status="investigating",
            severity="error",
            title="Checkout Pod failure",
            summary="SC-4 integration fixture",
            cluster_name="production",
            namespace="checkout",
            primary_signal_id="",
            latest_signal_id="",
            topology_snapshot_id=snapshot.snapshot_id,
            affected_entity_id=POD,
            first_observed_at=NOW.isoformat(),
            last_observed_at=NOW.isoformat(),
            created_at=NOW.isoformat(),
            updated_at=NOW.isoformat(),
        )
    )
    session.commit()
    return session


def _change_analysis(candidates) -> IncidentChangeAnalysisResponse:
    return IncidentChangeAnalysisResponse(
        incident_id="incident:sc4",
        incident_time=NOW.isoformat(),
        lookback_minutes=180,
        after_minutes=10,
        affected_entity_ids=[POD],
        candidate_count=len(candidates),
        candidates=list(candidates),
    )


def test_lineage_relevance_persists_and_loads_in_fresh_session(monkeypatch) -> None:
    session = _session(_snapshot())
    candidate = _source_candidate()
    monkeypatch.setattr(
        causal_service,
        "analyze_incident_change_events",
        lambda *args, **kwargs: _change_analysis([candidate]),
    )
    analysis = causal_service.analyze_causal_rca(
        session,
        incident_id="incident:sc4",
        request=CausalAnalysisRequest(),
    )
    session.expunge_all()
    loaded = latest_causal_analysis(session, incident_id="incident:sc4")

    assert analysis.causal_relevance_policy_version == "causal-relevance-v2"
    assert loaded is not None
    audit = loaded.candidate_relevance_audit[0]
    assert audit.candidate_entity_id is None
    assert audit.relevance_anchor_entity_id == IMAGE_A
    assert audit.bridge_path_ids == ["lineage-path:a"]
    assert audit.path_entity_ids == [IMAGE_A, DEPLOYMENT, REPLICA_SET, POD]
    selection = loaded.candidate_selection_audit[0]
    assert selection.event_id == EVENT
    assert selection.mutation_set == [{"path": "src/mode.txt"}]
    assert selection.mutation_completeness == "complete"
    assert loaded.candidate_count == 1
    assert loaded.incident_time == NOW.isoformat()
    assert loaded.topology_snapshot_id == "snapshot:pinned"
    source_node = next(item for item in loaded.nodes if item.event_id == EVENT)
    assert source_node.occurred_at == candidate.event.occurred_at
    assert "activation" not in source_node.attributes
    assert session.query(CausalAnalysisRecord).count() == 1
    assert loaded.support_policy_version == CAUSAL_SUPPORT_GATE_POLICY_VERSION
    assert loaded.top_hypothesis.support_gate is not None
    assert loaded.top_hypothesis.support_gate.support_state == (
        CausalEvidenceState.SUPPORTED_UNDER_CURRENT_MODEL
    )
    assert loaded.top_hypothesis.affected_entity_id == POD
    assert loaded.top_hypothesis.support_gate.candidate_linkage_claim_types == [
        "relationship_provenance",
        "topology_path",
    ]


def test_ar2_mixed_temporal_distractor_and_lineage_cause_separates_surfaces(
    monkeypatch,
) -> None:
    session = _session(_snapshot())
    distractor = _temporal_candidate(score=99.0)
    golden = _source_candidate(score=10.0)
    monkeypatch.setattr(
        causal_service,
        "analyze_incident_change_events",
        lambda *args, **kwargs: _change_analysis([distractor, golden]),
    )
    analysis = causal_service.analyze_causal_rca(
        session,
        incident_id="incident:sc4",
        request=CausalAnalysisRequest(),
        persist=False,
    )

    by_target = {item.target_event_id: item for item in analysis.hypotheses}
    control = by_target[distractor.event.event_id]
    cause = by_target[EVENT]
    supported = [
        item
        for item in analysis.hypotheses
        if item.confidence_semantics.evidence_state
        == CausalEvidenceState.SUPPORTED_UNDER_CURRENT_MODEL
    ]

    assert control.rank == 1
    assert cause.rank == 2
    assert control.score > cause.score
    assert control.support_gate.support_state == (
        CausalEvidenceState.INSUFFICIENT_CANDIDATE_SPECIFIC_EVIDENCE
    )
    assert control.support_gate.candidate_linkage_claim_ids == []
    assert cause.support_gate.support_state == (
        CausalEvidenceState.SUPPORTED_UNDER_CURRENT_MODEL
    )
    assert cause.affected_entity_id == POD
    assert cause.support_gate.relevance_gate_reason == (
        "supported_exact_immutable_lineage_anchor"
    )
    assert [item.target_event_id for item in supported] == [EVENT]
    assert analysis.top_hypothesis.target_event_id == distractor.event.event_id


def test_ar2_count_fifty_shape_preserves_ar1_frontier_and_final_cap(
    monkeypatch,
) -> None:
    session = _session(_snapshot())
    controls = [
        _temporal_candidate(index, score=99.0 - index / 100)
        for index in range(50)
    ]
    golden = _source_candidate(score=10.0)
    monkeypatch.setattr(
        causal_service,
        "analyze_incident_change_events",
        lambda *args, **kwargs: _change_analysis([*controls, golden]),
    )
    analysis = causal_service.analyze_causal_rca(
        session,
        incident_id="incident:sc4",
        request=CausalAnalysisRequest(),
        persist=False,
    )

    assert analysis.candidate_count == 51
    assert analysis.evaluation_budget_audit.evaluation_frontier_size == 6
    assert len(analysis.candidate_relevance_audit) == 6
    assert analysis.candidate_selection_audit[-1].event_id == EVENT
    assert analysis.candidate_selection_audit[-1].raw_rank == 51
    assert len(analysis.hypotheses) == CausalAnalysisRequest().max_hypotheses == 5
    assert all(
        item.support_gate.support_state
        == CausalEvidenceState.INSUFFICIENT_CANDIDATE_SPECIFIC_EVIDENCE
        for item in analysis.hypotheses
    )
    assert EVENT in {
        item.candidate_event_id for item in analysis.candidate_relevance_audit
    }
    assert EVENT not in {item.target_event_id for item in analysis.hypotheses}


def test_lineage_anchor_and_path_present_only_in_latest_snapshot_are_ignored(
    monkeypatch,
) -> None:
    pinned = _snapshot(image_a=False, relationships=[])
    session = _session(pinned)
    later = _snapshot(snapshot_id="snapshot:later")
    session.add(
        SnapshotRecord(
            snapshot_id=later.snapshot_id,
            schema_version=later.schema_version,
            collected_at=later.collected_at.isoformat(),
            collector_name=later.collector_name,
            collector_version=later.collector_version,
            cluster_name="production",
            namespace="checkout",
            entity_count=len(later.entities),
            relationship_count=len(later.relationships),
            evidence_count=0,
            scope_json=json.dumps(later.scope),
            payload_json=later.model_dump_json(),
            created_at=NOW.isoformat(),
        )
    )
    session.commit()
    candidate = _source_candidate()
    monkeypatch.setattr(
        causal_service,
        "analyze_incident_change_events",
        lambda *args, **kwargs: _change_analysis([candidate]),
    )
    analysis = causal_service.analyze_causal_rca(
        session,
        incident_id="incident:sc4",
        request=CausalAnalysisRequest(),
        persist=False,
    )

    assert analysis.topology_snapshot_id == "snapshot:pinned"
    audit = analysis.candidate_relevance_audit[0]
    assert audit.relevance_status == CausalRelevanceStatus.IDENTITY_UNRESOLVED
    assert audit.bridge_reason == "lineage_anchor_not_in_pinned_topology"
    assert audit.path_relationship_ids == []


def test_distractor_ranking_is_not_overridden_by_lineage_bridge(monkeypatch) -> None:
    session = _session(_snapshot())
    recent = _topology_candidate(score=90.0)
    old_lineage = _source_candidate(score=10.0)
    monkeypatch.setattr(
        causal_service,
        "analyze_incident_change_events",
        lambda *args, **kwargs: _change_analysis([recent, old_lineage]),
    )
    analysis = causal_service.analyze_causal_rca(
        session,
        incident_id="incident:sc4",
        request=CausalAnalysisRequest(),
        persist=False,
    )

    assert analysis.top_hypothesis is not None
    assert analysis.top_hypothesis.target_event_id == "event:deployment"
    audits = {
        item.candidate_event_id: item
        for item in analysis.candidate_relevance_audit
    }
    assert audits[EVENT].bridge_score == 0.0
    assert audits[EVENT].topology_component == 0.45
    assert audits["event:deployment"].resolution_basis == (
        CausalRelevanceResolutionBasis.TOPOLOGY_ENTITY
    )


def test_tc4_claim_types_and_graph_entities_are_not_expanded(monkeypatch) -> None:
    session = _session(_snapshot())
    candidate = _source_candidate()
    monkeypatch.setattr(
        causal_service,
        "analyze_incident_change_events",
        lambda *args, **kwargs: _change_analysis([candidate]),
    )
    analysis = causal_service.analyze_causal_rca(
        session,
        incident_id="incident:sc4",
        request=CausalAnalysisRequest(),
        persist=False,
    )

    claims = {
        item.claim_type.value
        for bucket in (
            analysis.top_hypothesis.evidence_ledger.supporting,
            analysis.top_hypothesis.evidence_ledger.contradicting,
            analysis.top_hypothesis.evidence_ledger.missing,
        )
        for item in bucket
    }
    assert "lineage_relevance" not in claims
    assert "source_to_image_relevance" not in claims
    assert {item.value for item in causal_service.CausalNodeType} == {
        "change_event",
        "entity",
        "incident",
    }
    snapshot_kinds = {entity.kind for entity in _snapshot().entities}
    assert "ChangeEvent" not in snapshot_kinds
    assert "SourceFile" not in snapshot_kinds
    assert "RelevanceBridge" not in snapshot_kinds


def test_policy_has_no_provider_current_state_or_special_case_dependency() -> None:
    source = inspect.getsource(relevance_policy).casefold()
    forbidden = [
        "github",
        "ghcr",
        "kubectl",
        "docker",
        "subprocess",
        "requests.",
        "httpx",
        "latest_snapshot",
        "embedding",
        "openai",
        "fuzzywuzzy",
        "rapidfuzz",
    ]
    assert all(value not in source for value in forbidden)


def test_ranking_formula_and_lookback_remain_frozen() -> None:
    source = inspect.getsource(causal_service.analyze_causal_rca)
    assert "candidate.score * 0.40" in source
    assert "+ topology_component * 25" in source
    assert "+ temporal_component * 15" in source
    assert "+ lineage_component * 10" in source
    assert CausalAnalysisRequest().lookback_minutes == 180
    assert "bridge_score" not in source
