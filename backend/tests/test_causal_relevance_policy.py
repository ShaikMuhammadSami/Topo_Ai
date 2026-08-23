from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.services.causal_candidate_policy as candidate_policy
import app.services.causal_rca as causal_service
import app.services.causal_relevance_policy as relevance_policy
from app.db.database import Base
from app.db.models import CausalAnalysisRecord, IncidentRecord, SnapshotRecord
from app.models.causal_candidates import CAUSAL_CANDIDATE_POLICY_VERSION
from app.models.causal_rca import CausalAnalysisRequest
from app.models.causal_relevance import (
    CAUSAL_RELEVANCE_POLICY_VERSION,
    CausalPathSemantic,
    CausalRelevanceStatus,
    CausalTraversalDirection,
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
from app.models.changes import ChangeCategory, ChangeType
from app.models.confidence_semantics import CONFIDENCE_SEMANTICS_VERSION
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
from app.services.blast_impact_policy import BLAST_POLICY_VERSION


NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[2]
POLICY_CONTRACT = (
    ROOT
    / "docs"
    / "architecture"
    / "causal-relevance"
    / "causal-relevance-policy-v1.json"
)
TC2_CONTRACT = (
    ROOT
    / "docs"
    / "architecture"
    / "truth-contract"
    / "relationship-provenance-contract.json"
)


def _entity(entity_id: str, kind: str = "KubernetesPod") -> Entity:
    return Entity(
        id=entity_id,
        entity_type=(
            EntityType.RUNTIME_INSTANCE
            if "Pod" in kind
            else EntityType.WORKLOAD
        ),
        kind=kind,
        name=entity_id,
        source_system="kubernetes",
        observed_at=NOW,
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
        source_system="kubernetes",
        observed_at=NOW,
        provenance=RelationshipProvenance(
            origin=RelationshipOrigin.DECLARED,
            source_component="test",
            linker_version="tc2.v1",
            completeness=RelationshipProvenanceCompleteness.COMPLETE,
        ),
    )


def _snapshot(
    relationships: list[Relationship],
    *,
    snapshot_id: str = "snapshot:pinned",
    extra_entities: tuple[str, ...] = (),
) -> GraphSnapshot:
    ids = set(extra_entities)
    for relationship in relationships:
        ids.add(relationship.source_entity_id)
        ids.add(relationship.target_entity_id)
    kinds = {
        "deployment": "KubernetesDeployment",
        "distractor": "KubernetesDeployment",
        "replicaset": "KubernetesReplicaSet",
        "pod": "KubernetesPod",
        "namespace": "KubernetesNamespace",
        "artifact": "ContainerImage",
        "consumer": "KubernetesDeployment",
        "commit": "GitCommit",
        "run": "GitHubWorkflowRun",
        "dependency": "KubernetesService",
        "dependent": "KubernetesPod",
        "destination": "NetworkEndpoint",
        "caller": "KubernetesPod",
        "resource": "KubernetesService",
        "endpoint": "KubernetesEndpointSlice",
        "host": "KubernetesNode",
    }
    return GraphSnapshot(
        snapshot_id=snapshot_id,
        collected_at=NOW,
        collector_name="test",
        collector_version="1",
        scope={"cluster_name": "production", "namespace": "payments"},
        entities=[_entity(entity_id, kinds.get(entity_id, "KubernetesPod")) for entity_id in sorted(ids)],
        relationships=relationships,
    )


def _evaluate(
    snapshot: GraphSnapshot | None,
    start: str,
    target: str,
    *,
    max_hops: int = 4,
):
    return relevance_policy.evaluate_causal_relevance(
        snapshot,
        candidate_event_id="event:test",
        candidate_entity_ids=[start],
        affected_entity_ids=[target],
        max_hops=max_hops,
    )


@pytest.mark.parametrize(
    "predicate,support,direction,semantic",
    [
        ("attached_to", "unsupported", "none", "runtime_hosting"),
        ("calls", "supported", "reverse", "dependency_impact"),
        ("contains", "structural_only", "none", "structural_context"),
        ("depends_on", "supported", "reverse", "dependency_impact"),
        ("exposes", "supported", "forward", "runtime_hosting"),
        ("owns", "supported", "forward", "control_ownership"),
        ("produces", "supported", "forward", "artifact_lineage"),
        ("protects", "unsupported", "none", "unsupported_unknown"),
        ("resolves_to", "unsupported", "none", "unsupported_unknown"),
        ("routes_to", "conditional", "none", "unsupported_unknown"),
        ("runs", "supported", "forward", "runtime_hosting"),
        ("selects", "conditional", "none", "unsupported_unknown"),
        ("triggers", "supported", "forward", "artifact_lineage"),
        ("uses", "supported", "reverse", "artifact_lineage"),
    ],
)
def test_every_active_tc2_predicate_has_explicit_policy(
    predicate, support, direction, semantic
) -> None:
    policy = relevance_policy.policy_for_predicate(predicate)
    assert policy is not None
    assert policy.support.value == support
    assert policy.traversal_direction.value == direction
    assert policy.semantic_class.value == semantic
    assert policy.policy_version == CAUSAL_RELEVANCE_POLICY_VERSION


def test_machine_contract_matches_executable_registry() -> None:
    contract = json.loads(POLICY_CONTRACT.read_text(encoding="utf-8"))
    tc2 = json.loads(TC2_CONTRACT.read_text(encoding="utf-8"))
    assert contract["policy_version"] == CAUSAL_RELEVANCE_POLICY_VERSION
    entries = {item["predicate"]: item for item in contract["predicates"]}
    assert set(entries) == relevance_policy.ACTIVE_TC2_PREDICATES
    assert set(entries) == {item["predicate"] for item in tc2["active_predicates"]}
    for predicate, policy in relevance_policy.CAUSAL_RELATIONSHIP_POLICIES.items():
        assert entries[predicate]["causal_traversal_direction"] == policy.traversal_direction.value
        assert entries[predicate]["semantic_class"] == policy.semantic_class.value
        assert entries[predicate]["support"] == policy.support.value


def test_unknown_predicate_has_no_fallback() -> None:
    assert relevance_policy.policy_for_predicate("future_magic_edge") is None


@pytest.mark.parametrize(
    "hops,expected",
    [(None, 0.0), (0, 1.0), (1, 0.85), (2, 0.65), (3, 0.45), (4, 0.25)],
)
def test_existing_topology_component_mapping_is_preserved(hops, expected) -> None:
    assert relevance_policy.topology_component_for_hops(hops) == expected


@pytest.mark.parametrize(
    "predicate,start,target,direction,semantic",
    [
        (RelationshipType.OWNS, "deployment", "replicaset", "forward", "control_ownership"),
        (RelationshipType.USES, "artifact", "consumer", "reverse", "artifact_lineage"),
        (RelationshipType.PRODUCES, "commit", "artifact", "forward", "artifact_lineage"),
        (RelationshipType.TRIGGERS, "commit", "run", "forward", "artifact_lineage"),
        (RelationshipType.DEPENDS_ON, "dependency", "dependent", "reverse", "dependency_impact"),
        (RelationshipType.CALLS, "destination", "caller", "reverse", "dependency_impact"),
        (RelationshipType.EXPOSES, "resource", "endpoint", "forward", "runtime_hosting"),
        (RelationshipType.RUNS, "host", "pod", "forward", "runtime_hosting"),
    ],
)
def test_supported_predicate_traversal(predicate, start, target, direction, semantic) -> None:
    relationship = _relationship("relationship:1", relationship_source(predicate, start, target), relationship_target(predicate, start, target), predicate)
    result = _evaluate(_snapshot([relationship]), start, target)
    assert result.relevance_status == CausalRelevanceStatus.SEMANTIC_PATH
    assert result.path_traversal_directions == [CausalTraversalDirection(direction)]
    assert result.path_semantic == CausalPathSemantic(semantic)


def relationship_source(predicate: RelationshipType, start: str, target: str) -> str:
    if predicate in {RelationshipType.USES, RelationshipType.DEPENDS_ON, RelationshipType.CALLS}:
        return target
    return start


def relationship_target(predicate: RelationshipType, start: str, target: str) -> str:
    if predicate in {RelationshipType.USES, RelationshipType.DEPENDS_ON, RelationshipType.CALLS}:
        return start
    return target


@pytest.mark.parametrize(
    "predicate",
    [
        RelationshipType.CONTAINS,
        RelationshipType.SELECTS,
        RelationshipType.ROUTES_TO,
        RelationshipType.PROTECTS,
        RelationshipType.RESOLVES_TO,
        RelationshipType.ATTACHED_TO,
    ],
)
def test_structural_conditional_and_unsupported_predicates_do_not_traverse(predicate) -> None:
    result = _evaluate(
        _snapshot([_relationship("relationship:blocked", "deployment", "pod", predicate)]),
        "deployment",
        "pod",
    )
    assert result.relevance_status == CausalRelevanceStatus.NO_SUPPORTED_PATH
    assert result.topology_component == 0.0
    assert result.hops == []


def _ownership_and_contains(order: str = "normal") -> GraphSnapshot:
    relationships = [
        _relationship("relationship:contains-deployment", "namespace", "deployment", RelationshipType.CONTAINS),
        _relationship("relationship:contains-pod", "namespace", "pod", RelationshipType.CONTAINS),
        _relationship("relationship:owns-deployment", "deployment", "replicaset", RelationshipType.OWNS),
        _relationship("relationship:owns-replicaset", "replicaset", "pod", RelationshipType.OWNS),
    ]
    if order == "reverse":
        relationships.reverse()
    return _snapshot(relationships)


def test_same_namespace_alone_creates_no_causal_path() -> None:
    snapshot = _snapshot(
        [
            _relationship("relationship:1", "namespace", "deployment", RelationshipType.CONTAINS),
            _relationship("relationship:2", "namespace", "pod", RelationshipType.CONTAINS),
        ]
    )
    result = _evaluate(snapshot, "deployment", "pod")
    assert result.relevance_status == CausalRelevanceStatus.NO_SUPPORTED_PATH


def test_owner_path_beats_short_structural_alternative() -> None:
    result = _evaluate(_ownership_and_contains(), "deployment", "pod")
    assert result.path_entity_ids == ["deployment", "replicaset", "pod"]
    assert result.path_predicates == ["owns", "owns"]
    assert result.path_traversal_directions == [
        CausalTraversalDirection.FORWARD,
        CausalTraversalDirection.FORWARD,
    ]


def test_relationship_serialization_order_cannot_change_path() -> None:
    first = _evaluate(_ownership_and_contains("normal"), "deployment", "pod")
    second = _evaluate(_ownership_and_contains("reverse"), "deployment", "pod")
    assert second.model_dump() == first.model_dump()


def test_stable_relationship_id_breaks_equal_path_tie() -> None:
    snapshot = _snapshot(
        [
            _relationship("relationship:z", "deployment", "pod", RelationshipType.OWNS),
            _relationship("relationship:a", "deployment", "pod", RelationshipType.OWNS),
        ]
    )
    result = _evaluate(snapshot, "deployment", "pod")
    assert result.path_relationship_ids == ["relationship:a"]


def test_cycles_terminate_without_revisiting_entities() -> None:
    snapshot = _snapshot(
        [
            _relationship("relationship:1", "deployment", "replicaset", RelationshipType.OWNS),
            _relationship("relationship:2", "replicaset", "deployment", RelationshipType.OWNS),
            _relationship("relationship:3", "replicaset", "pod", RelationshipType.OWNS),
        ]
    )
    result = _evaluate(snapshot, "deployment", "pod")
    assert result.path_entity_ids == ["deployment", "replicaset", "pod"]


def test_existing_maximum_path_depth_is_enforced() -> None:
    snapshot = _snapshot(
        [
            _relationship("relationship:1", "deployment", "one", RelationshipType.OWNS),
            _relationship("relationship:2", "one", "two", RelationshipType.OWNS),
            _relationship("relationship:3", "two", "pod", RelationshipType.OWNS),
        ]
    )
    assert _evaluate(snapshot, "deployment", "pod", max_hops=2).relevance_status == CausalRelevanceStatus.NO_SUPPORTED_PATH
    assert _evaluate(snapshot, "deployment", "pod", max_hops=3).path_hops == 3


def test_direct_entity_match_is_valid_without_relationship() -> None:
    snapshot = _snapshot([], extra_entities=("pod",))
    result = _evaluate(snapshot, "pod", "pod")
    assert result.relevance_status == CausalRelevanceStatus.DIRECT
    assert result.topology_component == 1.0
    assert result.path_hops == 0


def test_incident_pin_is_mandatory_and_no_snapshot_is_not_contradiction() -> None:
    result = _evaluate(None, "deployment", "pod")
    assert result.relevance_status == CausalRelevanceStatus.IDENTITY_UNRESOLVED
    assert result.topology_component == 0.0
    assert "fallback" not in result.reason.casefold()


def test_missing_snapshot_identity_does_not_fuzzy_match() -> None:
    result = _evaluate(_snapshot([], extra_entities=("pod",)), "deployment", "pod")
    assert result.relevance_status == CausalRelevanceStatus.IDENTITY_UNRESOLVED
    assert result.path_entity_ids == []


def _candidate(event_id: str, entity_id: str) -> IncidentChangeCandidate:
    occurred_at = "2026-08-24T11:58:00+00:00"
    link = ChangeEntityLinkView(
        link_id=f"link:{event_id}",
        event_id=event_id,
        entity_id=entity_id,
        link_type=ChangeEntityLinkType.AUTOMATIC,
        confidence=1.0,
        reason="Exact snapshot entity ID.",
        snapshot_id="snapshot:pinned",
        created_at=occurred_at,
        updated_at=occurred_at,
    )
    event = ChangeEventView(
        event_id=event_id,
        event_fingerprint=f"fingerprint:{event_id}",
        source=ChangeEventSource.TOPOLOGY_DIFF,
        kind=ChangeEventKind.DEPLOYMENT,
        external_id=event_id,
        origin_change_id=f"change:{event_id}",
        title="Deployment configuration changed",
        summary=None,
        actor=None,
        occurred_at=occurred_at,
        received_at=occurred_at,
        environment="production",
        provider="kubernetes",
        account_id=None,
        region=None,
        cluster_name="production",
        namespace="payments",
        repository=None,
        commit_sha=None,
        pipeline_name=None,
        release_version=None,
        terraform_workspace=None,
        risk_score=80,
        risk_level=ChangeEventRiskLevel.HIGH,
        status="observed",
        observation_count=1,
        metadata={
            "change_type": ChangeType.ENTITY_UPDATED.value,
            "category": ChangeCategory.DEPLOYMENT.value,
            "after": {"kind": "KubernetesDeployment"},
            "entity_refs": [{"entity_id": entity_id, "kind": "KubernetesDeployment"}],
        },
        raw_payload={},
        agent_id=None,
        links=[link],
        created_at=occurred_at,
        updated_at=occurred_at,
    )
    return IncidentChangeCandidate(
        event=event,
        score=55.2,
        minutes_before_incident=2.0,
    )


def _session_with_pinned_snapshot(snapshot: GraphSnapshot) -> Session:
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
            namespace="payments",
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
            incident_id="incident:cr1",
            fingerprint="fingerprint:cr1",
            status="investigating",
            severity="error",
            title="Victim Pod image pull failure",
            summary="CR-1 integrated fixture",
            cluster_name="production",
            namespace="payments",
            primary_signal_id="",
            latest_signal_id="",
            topology_snapshot_id=snapshot.snapshot_id,
            affected_entity_id="pod",
            first_observed_at=NOW.isoformat(),
            last_observed_at=NOW.isoformat(),
            created_at=NOW.isoformat(),
            updated_at=NOW.isoformat(),
        )
    )
    session.commit()
    return session


def _analysis_response(candidates) -> IncidentChangeAnalysisResponse:
    return IncidentChangeAnalysisResponse(
        incident_id="incident:cr1",
        incident_time=NOW.isoformat(),
        lookback_minutes=180,
        after_minutes=10,
        affected_entity_ids=["pod"],
        candidate_count=len(candidates),
        candidates=list(candidates),
    )


def test_integrated_sentinel_b_shape_ranks_victim_without_score_change(monkeypatch) -> None:
    snapshot = _ownership_and_contains()
    snapshot.relationships.extend(
        [
            _relationship("relationship:contains-distractor", "namespace", "distractor", RelationshipType.CONTAINS)
        ]
    )
    snapshot.entities.append(_entity("distractor", "KubernetesDeployment"))
    session = _session_with_pinned_snapshot(snapshot)
    distractor = _candidate("event:a-distractor", "distractor")
    victim = _candidate("event:z-victim", "deployment")
    monkeypatch.setattr(
        causal_service,
        "analyze_incident_change_events",
        lambda *args, **kwargs: _analysis_response([distractor, victim]),
    )

    analysis = causal_service.analyze_causal_rca(
        session,
        incident_id="incident:cr1",
        request=CausalAnalysisRequest(),
    )

    assert analysis.top_hypothesis.target_event_id == "event:z-victim"
    by_event = {item.candidate_event_id: item for item in analysis.candidate_relevance_audit}
    assert by_event["event:z-victim"].path_predicates == ["owns", "owns"]
    assert by_event["event:z-victim"].topology_component == 0.65
    assert by_event["event:a-distractor"].relevance_status == CausalRelevanceStatus.NO_SUPPORTED_PATH
    assert by_event["event:a-distractor"].topology_component == 0.0
    selection = {item.event_id: item for item in analysis.candidate_selection_audit}
    assert selection["event:z-victim"].raw_score == 55.2
    assert selection["event:a-distractor"].raw_score == 55.2
    victim_hypothesis = next(item for item in analysis.hypotheses if item.target_event_id == "event:z-victim")
    distractor_hypothesis = next(item for item in analysis.hypotheses if item.target_event_id == "event:a-distractor")
    assert victim_hypothesis.score - distractor_hypothesis.score == 16.25
    assert [item.claim_type.value for item in distractor_hypothesis.evidence_ledger.contradicting] == []
    assert "topology_path" in [item.claim_type.value for item in distractor_hypothesis.evidence_ledger.missing]
    assert "topology_path" not in [item.claim_type.value for item in distractor_hypothesis.evidence_ledger.supporting]


def test_integrated_sentinel_a_path_contains_only_ownership(monkeypatch) -> None:
    snapshot = _ownership_and_contains()
    session = _session_with_pinned_snapshot(snapshot)
    victim = _candidate("event:victim", "deployment")
    monkeypatch.setattr(
        causal_service,
        "analyze_incident_change_events",
        lambda *args, **kwargs: _analysis_response([victim]),
    )
    analysis = causal_service.analyze_causal_rca(
        session,
        incident_id="incident:cr1",
        request=CausalAnalysisRequest(),
    )
    audit = analysis.candidate_relevance_audit[0]
    assert audit.path_entity_ids == ["deployment", "replicaset", "pod"]
    assert audit.path_predicates == ["owns", "owns"]
    ledger_relationships = {
        item.relationship.predicate
        for item in analysis.top_hypothesis.evidence_ledger.supporting
        if item.relationship is not None
        and item.claim_type.value in {"topology_path", "relationship_provenance"}
    }
    assert ledger_relationships == {"owns"}
    assert all("namespace" not in step.node_id for step in analysis.top_hypothesis.chain)


def test_new_analysis_persists_version_audit_and_is_idempotent(monkeypatch) -> None:
    session = _session_with_pinned_snapshot(_ownership_and_contains())
    victim = _candidate("event:victim", "deployment")
    monkeypatch.setattr(
        causal_service,
        "analyze_incident_change_events",
        lambda *args, **kwargs: _analysis_response([victim]),
    )
    first = causal_service.analyze_causal_rca(
        session, incident_id="incident:cr1", request=CausalAnalysisRequest()
    )
    second = causal_service.analyze_causal_rca(
        session, incident_id="incident:cr1", request=CausalAnalysisRequest()
    )
    loaded = latest_causal_analysis(session, incident_id="incident:cr1")
    assert second.model_dump_json() == first.model_dump_json()
    assert loaded.causal_relevance_policy_version == CAUSAL_RELEVANCE_POLICY_VERSION
    assert loaded.candidate_relevance_audit[0].path_predicates == ["owns", "owns"]
    assert session.query(CausalAnalysisRecord).count() == 1


def test_legacy_analysis_loads_without_relevance_claim(monkeypatch) -> None:
    session = _session_with_pinned_snapshot(_ownership_and_contains())
    victim = _candidate("event:victim", "deployment")
    monkeypatch.setattr(
        causal_service,
        "analyze_incident_change_events",
        lambda *args, **kwargs: _analysis_response([victim]),
    )
    current = causal_service.analyze_causal_rca(
        session, incident_id="incident:cr1", request=CausalAnalysisRequest(), persist=False
    )
    payload = current.model_dump(mode="json")
    payload.pop("causal_relevance_policy_version")
    payload.pop("candidate_relevance_audit")
    payload["analysis_id"] = "causal-analysis:legacy-cr1"
    legacy_json = json.dumps(payload)
    session.add(
        CausalAnalysisRecord(
            analysis_id="causal-analysis:legacy-cr1",
            incident_id="incident:legacy-cr1",
            generated_at=current.generated_at,
            algorithm_version=current.algorithm_version,
            candidate_count=current.candidate_count,
            hypothesis_count=current.hypothesis_count,
            top_hypothesis_score=current.top_hypothesis.score,
            top_root_event_id=current.top_hypothesis.root_event_id,
            payload_json=legacy_json,
            created_at=NOW.isoformat(),
            updated_at=NOW.isoformat(),
        )
    )
    session.commit()
    loaded = latest_causal_analysis(session, incident_id="incident:legacy-cr1")
    assert loaded.causal_relevance_policy_version is None
    assert loaded.candidate_relevance_audit == []
    assert session.get(CausalAnalysisRecord, "causal-analysis:legacy-cr1").payload_json == legacy_json


def test_historical_pin_ignores_a_later_unrelated_snapshot(monkeypatch) -> None:
    pinned = _ownership_and_contains()
    session = _session_with_pinned_snapshot(pinned)
    later = _snapshot(
        [_relationship("relationship:later", "distractor", "pod", RelationshipType.OWNS)],
        snapshot_id="snapshot:later",
    )
    session.add(
        SnapshotRecord(
            snapshot_id=later.snapshot_id,
            schema_version=later.schema_version,
            collected_at=(NOW.replace(hour=13)).isoformat(),
            collector_name=later.collector_name,
            collector_version=later.collector_version,
            cluster_name="production",
            namespace="payments",
            entity_count=len(later.entities),
            relationship_count=len(later.relationships),
            evidence_count=0,
            scope_json=json.dumps(later.scope),
            payload_json=later.model_dump_json(),
            created_at=NOW.isoformat(),
        )
    )
    session.commit()
    distractor = _candidate("event:distractor", "distractor")
    monkeypatch.setattr(
        causal_service,
        "analyze_incident_change_events",
        lambda *args, **kwargs: _analysis_response([distractor]),
    )
    analysis = causal_service.analyze_causal_rca(
        session, incident_id="incident:cr1", request=CausalAnalysisRequest(), persist=False
    )
    assert analysis.topology_snapshot_id == "snapshot:pinned"
    assert analysis.candidate_relevance_audit[0].relevance_status == CausalRelevanceStatus.IDENTITY_UNRESOLVED


def test_frozen_versions_formula_and_policies_remain_unchanged() -> None:
    source = inspect.getsource(causal_service.analyze_causal_rca)
    assert "evaluate_causal_relevance" in source
    assert "_adjacency(" not in source
    assert "_shortest_path(" not in source
    assert "candidate.score * 0.40" in source
    assert "topology_component * 25" in source
    assert "temporal_component * 15" in source
    assert "lineage_component * 10" in source
    assert causal_service.ALGORITHM_VERSION == "13c-causal-v1"
    assert CAUSAL_CANDIDATE_POLICY_VERSION == "causal-candidate-v1"
    assert BLAST_POLICY_VERSION == "blast-impact-v1"
    assert CONFIDENCE_SEMANTICS_VERSION == "tc5.v1"
    assert candidate_policy.CAUSAL_CANDIDATE_POLICY_VERSION == "causal-candidate-v1"


def test_product_policy_has_no_sentinel_or_namespace_special_case() -> None:
    source = inspect.getsource(relevance_policy).casefold()
    assert "sentinel-a" not in source
    assert "sentinel-b" not in source
    assert "sentinel-c" not in source
    assert "topo-eval" not in source
