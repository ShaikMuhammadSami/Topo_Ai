from __future__ import annotations
from domain_tenant_fixtures import TEST_TENANT, seed_domain_tenant

import inspect
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.services.causal_candidate_policy as policy_service
import app.services.causal_rca as causal_service
from app.db.database import Base
from app.db.models import CausalAnalysisRecord, IncidentRecord
from app.models.causal_candidates import (
    CAUSAL_CANDIDATE_POLICY_VERSION,
    CausalCandidateEligibility,
    CausalCandidateRole,
)
from app.models.causal_rca import CausalAnalysisRequest, CausalAnalysisResponse
from app.models.change_events import (
    ChangeEventKind,
    ChangeEventRiskLevel,
    ChangeEventSource,
    ChangeEventView,
    IncidentChangeAnalysisResponse,
    IncidentChangeCandidate,
)
from app.models.changes import ChangeCategory, ChangeType
from app.repositories.causal_analysis_repository import latest_causal_analysis
from app.services.blast_impact_policy import BLAST_POLICY_VERSION
from app.models.confidence_semantics import CONFIDENCE_SEMANTICS_VERSION

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[2]
POLICY_CONTRACT = (
    ROOT
    / "docs"
    / "architecture"
    / "causal-candidates"
    / "causal-candidate-policy-v1.json"
)


def _candidate(
    event_id: str,
    *,
    score: float = 50.0,
    source: ChangeEventSource = ChangeEventSource.TOPOLOGY_DIFF,
    event_kind: ChangeEventKind = ChangeEventKind.TOPOLOGY,
    change_type: ChangeType | None = None,
    category: ChangeCategory | None = None,
    entity_kind: str | None = None,
    relationship_type: str | None = None,
    reason: str | None = None,
    status: str = "observed",
    occurred_at: str = "2026-08-23T11:58:00+00:00",
    risk_score: int = 50,
) -> IncidentChangeCandidate:
    metadata: dict = {}
    if change_type is not None:
        metadata["change_type"] = change_type.value
    if category is not None:
        metadata["category"] = category.value
    if entity_kind is not None:
        metadata["after"] = {"kind": entity_kind}
        metadata["entity_refs"] = [{"kind": entity_kind}]
    if relationship_type is not None:
        metadata.update(
            {
                "relationship_id": f"relationship:{event_id}",
                "relationship_type": relationship_type,
            }
        )
    if reason is not None:
        metadata["reason"] = reason

    event = ChangeEventView(
        event_id=event_id,
        event_fingerprint=f"fingerprint:{event_id}",
        source=source,
        kind=event_kind,
        external_id=event_id,
        origin_change_id=(
            f"change:{event_id}"
            if source == ChangeEventSource.TOPOLOGY_DIFF
            else None
        ),
        title="Structured candidate fixture",
        summary=None,
        actor=None,
        occurred_at=occurred_at,
        received_at=occurred_at,
        environment="production",
        provider=None,
        account_id=None,
        region=None,
        cluster_name="production",
        namespace="payments",
        repository=None,
        commit_sha=None,
        pipeline_name=None,
        release_version=None,
        terraform_workspace=None,
        risk_score=risk_score,
        risk_level=ChangeEventRiskLevel.MEDIUM,
        status=status,
        observation_count=1,
        metadata=metadata,
        raw_payload={},
        agent_id=None,
        links=[],
        created_at=occurred_at,
        updated_at=occurred_at,
    )
    return IncidentChangeCandidate(
        event=event,
        score=score,
        minutes_before_incident=2.0,
    )


def _relationship_candidate(
    event_id: str,
    predicate: str,
    change_type: ChangeType = ChangeType.RELATIONSHIP_ADDED,
    *,
    score: float = 90.0,
) -> IncidentChangeCandidate:
    return _candidate(
        event_id,
        score=score,
        change_type=change_type,
        category=ChangeCategory.TOPOLOGY,
        relationship_type=predicate,
    )


def _deployment_candidate(
    event_id: str = "event:deployment",
    *,
    score: float = 55.2,
) -> IncidentChangeCandidate:
    return _candidate(
        event_id,
        score=score,
        event_kind=ChangeEventKind.DEPLOYMENT,
        change_type=ChangeType.ENTITY_UPDATED,
        category=ChangeCategory.DEPLOYMENT,
        entity_kind="KubernetesDeployment",
        risk_score=80,
    )


@pytest.mark.parametrize(
    "source",
    [
        ChangeEventSource.GIT,
        ChangeEventSource.GITHUB,
        ChangeEventSource.GITLAB,
        ChangeEventSource.CI,
        ChangeEventSource.CD,
        ChangeEventSource.GITHUB_ACTIONS,
        ChangeEventSource.JENKINS,
        ChangeEventSource.AZURE_DEVOPS,
        ChangeEventSource.TERRAFORM,
        ChangeEventSource.AWS_CLOUDTRAIL,
        ChangeEventSource.AZURE_ACTIVITY_LOG,
        ChangeEventSource.GCP_AUDIT_LOG,
        ChangeEventSource.MANUAL,
    ],
)
def test_source_native_mutations_are_primary_eligible(source) -> None:
    decision = policy_service.classify_causal_candidate(
        _candidate(
            f"event:{source.value}",
            source=source,
            event_kind=ChangeEventKind.INFRASTRUCTURE,
        )
    )
    assert decision.role == CausalCandidateRole.SOURCE_MUTATION
    assert decision.eligibility == CausalCandidateEligibility.PRIMARY_ELIGIBLE


@pytest.mark.parametrize(
    "kind,category",
    [
        ("KubernetesDeployment", ChangeCategory.DEPLOYMENT),
        ("KubernetesStatefulSet", ChangeCategory.CONFIGURATION),
        ("KubernetesDaemonSet", ChangeCategory.CONFIGURATION),
        ("KubernetesService", ChangeCategory.SERVICE),
        ("KubernetesConfigMap", ChangeCategory.CONFIGURATION),
        ("KubernetesSecret", ChangeCategory.CONFIGURATION),
        ("KubernetesIngress", ChangeCategory.NETWORKING),
        ("KubernetesNetworkPolicy", ChangeCategory.NETWORKING),
        ("KubernetesJob", ChangeCategory.CONFIGURATION),
        ("KubernetesCronJob", ChangeCategory.CONFIGURATION),
        ("AWSLambdaFunction", ChangeCategory.OTHER),
        ("AzureVirtualMachine", ChangeCategory.OTHER),
        ("GCPComputeInstance", ChangeCategory.OTHER),
    ],
)
def test_observed_mutable_resource_changes_are_primary(kind, category) -> None:
    decision = policy_service.classify_causal_candidate(
        _candidate(
            f"event:{kind}",
            event_kind=ChangeEventKind.CONFIGURATION,
            change_type=ChangeType.ENTITY_UPDATED,
            category=category,
            entity_kind=kind,
        )
    )
    assert decision.role == CausalCandidateRole.OBSERVED_RESOURCE_MUTATION
    assert decision.eligibility == CausalCandidateEligibility.PRIMARY_ELIGIBLE


@pytest.mark.parametrize(
    "change_type,predicate",
    [
        (ChangeType.RELATIONSHIP_ADDED, "selects"),
        (ChangeType.RELATIONSHIP_ADDED, "routes_to"),
        (ChangeType.RELATIONSHIP_ADDED, "owns"),
        (ChangeType.RELATIONSHIP_REMOVED, "selects"),
        (ChangeType.RELATIONSHIP_REMOVED, "uses"),
        (ChangeType.RELATIONSHIP_UPDATED, "routes_to"),
        (ChangeType.RELATIONSHIP_UPDATED, "depends_on"),
    ],
)
def test_topology_relationship_changes_are_supporting_only(
    change_type, predicate
) -> None:
    decision = policy_service.classify_causal_candidate(
        _relationship_candidate("event:relationship", predicate, change_type)
    )
    assert decision.role == CausalCandidateRole.DERIVED_TOPOLOGY_CONSEQUENCE
    assert decision.eligibility == CausalCandidateEligibility.SUPPORTING_ONLY
    assert decision.reason == "derived_relationship_change"


@pytest.mark.parametrize(
    "kind,change_type",
    [
        ("KubernetesReplicaSet", ChangeType.ENTITY_ADDED),
        ("KubernetesReplicaSet", ChangeType.ENTITY_REMOVED),
        ("KubernetesPod", ChangeType.ENTITY_ADDED),
        ("KubernetesPod", ChangeType.ENTITY_REMOVED),
        ("KubernetesEndpointSlice", ChangeType.ENTITY_UPDATED),
        ("KubernetesControllerRevision", ChangeType.ENTITY_ADDED),
        ("ContainerImage", ChangeType.ENTITY_ADDED),
    ],
)
def test_generated_runtime_changes_are_supporting_only(kind, change_type) -> None:
    decision = policy_service.classify_causal_candidate(
        _candidate(
            f"event:{kind}:{change_type.value}",
            change_type=change_type,
            category=ChangeCategory.RUNTIME,
            entity_kind=kind,
        )
    )
    assert decision.role == CausalCandidateRole.DERIVED_RUNTIME_CONSEQUENCE
    assert decision.eligibility == CausalCandidateEligibility.SUPPORTING_ONLY


@pytest.mark.parametrize(
    "reason",
    [
        "ImagePullBackOff",
        "ErrImagePull",
        "CrashLoopBackOff",
        "OOMKilled",
        "Unhealthy",
        "ResourcePressure",
    ],
)
def test_runtime_failure_symptoms_are_supporting_only(reason) -> None:
    decision = policy_service.classify_causal_candidate(
        _candidate(
            f"event:{reason}",
            source=ChangeEventSource.KUBERNETES,
            event_kind=ChangeEventKind.TOPOLOGY,
            entity_kind="KubernetesPod",
            reason=reason,
        )
    )
    assert decision.role == CausalCandidateRole.RUNTIME_SYMPTOM
    assert decision.eligibility == CausalCandidateEligibility.SUPPORTING_ONLY


@pytest.mark.parametrize(
    "reason",
    ["ScalingReplicaSet", "SuccessfulCreate", "SuccessfulDelete", "Killing"],
)
def test_kubernetes_controller_lifecycle_events_are_supporting_only(reason) -> None:
    decision = policy_service.classify_causal_candidate(
        _candidate(
            f"event:{reason}",
            source=ChangeEventSource.KUBERNETES,
            event_kind=ChangeEventKind.SCALING,
            entity_kind="KubernetesDeployment",
            reason=reason,
        )
    )
    assert decision.role == CausalCandidateRole.DERIVED_RUNTIME_CONSEQUENCE
    assert decision.eligibility == CausalCandidateEligibility.SUPPORTING_ONLY
    assert decision.reason == "kubernetes_controller_lifecycle_event"


@pytest.mark.parametrize("status", ["cancelled", "canceled", "noop", "skipped"])
def test_explicit_non_mutation_status_is_ineligible(status) -> None:
    decision = policy_service.classify_causal_candidate(
        _candidate(
            f"event:{status}",
            source=ChangeEventSource.GITHUB_ACTIONS,
            event_kind=ChangeEventKind.PIPELINE,
            status=status,
        )
    )
    assert decision.eligibility == CausalCandidateEligibility.INELIGIBLE


def test_legacy_unclassified_candidate_is_fallback_eligible() -> None:
    decision = policy_service.classify_causal_candidate(
        _candidate("event:legacy", source=ChangeEventSource.UNKNOWN)
    )
    assert decision.role == CausalCandidateRole.LEGACY_OR_UNKNOWN
    assert decision.eligibility == CausalCandidateEligibility.FALLBACK_ELIGIBLE


def test_unknown_event_kind_is_not_silently_a_source_mutation() -> None:
    decision = policy_service.classify_causal_candidate(
        _candidate(
            "event:unknown-kind",
            source=ChangeEventSource.GITHUB,
            event_kind=ChangeEventKind.UNKNOWN,
        )
    )
    assert decision.role == CausalCandidateRole.LEGACY_OR_UNKNOWN
    assert decision.eligibility == CausalCandidateEligibility.FALLBACK_ELIGIBLE


def test_clearly_derived_candidate_never_uses_legacy_fallback() -> None:
    candidate = _relationship_candidate("event:derived", "selects")
    selection = policy_service.select_causal_candidates([candidate], limit=5)
    assert not selection.selected_candidates
    assert selection.audit[0].eligibility == CausalCandidateEligibility.SUPPORTING_ONLY
    assert selection.audit[0].eligible_rank is None


def test_top_n_regression_classifies_all_candidates_before_limit() -> None:
    derived = [
        _relationship_candidate(f"event:derived:{index}", "selects", score=99 - index)
        for index in range(1, 11)
    ]
    actual = _deployment_candidate(score=55.2)
    raw = [*derived, actual]

    selection = policy_service.select_causal_candidates(raw, limit=5)
    audit = {item.event_id: item for item in selection.audit}

    assert actual.score == 55.2
    assert audit[actual.event.event_id].raw_rank == 11
    assert audit[actual.event.event_id].eligible_rank == 1
    assert audit[actual.event.event_id].selected_for_hypothesis is True
    assert selection.selected_candidates == (actual,)
    assert audit[derived[0].event.event_id].raw_rank == 1
    assert audit[derived[0].event.event_id].role == (
        CausalCandidateRole.DERIVED_TOPOLOGY_CONSEQUENCE
    )
    assert audit[derived[0].event.event_id].selected_for_hypothesis is False


def test_identical_scores_use_eligibility_not_a_numeric_bonus() -> None:
    derived = _relationship_candidate("event:derived", "owns", score=60)
    primary = _deployment_candidate("event:primary", score=60)
    selection = policy_service.select_causal_candidates([derived, primary], limit=1)
    assert selection.selected_candidates == (primary,)
    assert derived.score == primary.score == 60


def test_existing_score_order_is_preserved_within_primary_population() -> None:
    low = _deployment_candidate("event:low", score=40)
    high = _deployment_candidate("event:high", score=80)
    selection = policy_service.select_causal_candidates([low, high], limit=5)
    assert selection.selected_candidates == (high, low)
    ranks = {item.event_id: item.eligible_rank for item in selection.audit}
    assert ranks == {"event:low": 2, "event:high": 1}


def test_exact_ties_use_stable_event_identifiers_under_reordering() -> None:
    alpha = _deployment_candidate("event:alpha", score=70)
    beta = _deployment_candidate("event:beta", score=70)
    first = policy_service.select_causal_candidates([beta, alpha], limit=2)
    second = policy_service.select_causal_candidates([alpha, beta], limit=2)
    assert [item.event.event_id for item in first.selected_candidates] == [
        "event:alpha",
        "event:beta",
    ]
    assert [item.event.event_id for item in second.selected_candidates] == [
        "event:alpha",
        "event:beta",
    ]


def test_fallback_is_used_only_when_primary_population_is_empty() -> None:
    legacy = _candidate("event:legacy", source=ChangeEventSource.UNKNOWN)
    fallback_only = policy_service.select_causal_candidates([legacy], limit=5)
    assert fallback_only.selected_candidates == (legacy,)

    primary = _deployment_candidate()
    with_primary = policy_service.select_causal_candidates([legacy, primary], limit=5)
    assert with_primary.selected_candidates == (primary,)
    legacy_audit = next(item for item in with_primary.audit if item.event_id == "event:legacy")
    assert legacy_audit.eligible_rank is None
    assert legacy_audit.exclusion_reason == "primary_candidates_available"


def test_supporting_only_population_does_not_fabricate_primary_candidate() -> None:
    candidates = [
        _relationship_candidate("event:selects", "selects"),
        _candidate(
            "event:pod",
            change_type=ChangeType.ENTITY_ADDED,
            category=ChangeCategory.RUNTIME,
            entity_kind="KubernetesPod",
        ),
    ]
    selection = policy_service.select_causal_candidates(candidates, limit=5)
    assert selection.selected_candidates == ()


def test_policy_registry_explicitly_handles_every_change_enum() -> None:
    assert policy_service.HANDLED_CHANGE_TYPES == {
        item.value for item in ChangeType
    }
    assert policy_service.HANDLED_CHANGE_CATEGORIES == {
        item.value for item in ChangeCategory
    }


def test_machine_contract_matches_executable_policy_registry() -> None:
    contract = json.loads(POLICY_CONTRACT.read_text(encoding="utf-8"))
    assert contract["policy_version"] == CAUSAL_CANDIDATE_POLICY_VERSION
    assert set(contract["handled_change_types"]) == policy_service.HANDLED_CHANGE_TYPES
    assert set(contract["handled_change_categories"]) == (
        policy_service.HANDLED_CHANGE_CATEGORIES
    )
    assert set(contract["kubernetes_mutable_resource_kinds"]) == (
        policy_service.KUBERNETES_MUTABLE_RESOURCE_KINDS
    )
    assert set(contract["kubernetes_generated_resource_kinds"]) == (
        policy_service.KUBERNETES_GENERATED_RESOURCE_KINDS
    )
    assert set(contract["kubernetes_derived_event_reasons"]) == (
        policy_service.KUBERNETES_DERIVED_EVENT_REASONS
    )


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine)
    return Session(engine)


def _incident(session: Session, incident_id: str = "incident:cc1") -> None:
    session.add(
        IncidentRecord(
            incident_id=incident_id,
            fingerprint=f"fingerprint:{incident_id}",
            status="investigating",
            severity="error",
            title="Candidate selection incident",
            summary="Candidate semantics fixture",
            cluster_name="production",
            namespace="payments",
            primary_signal_id="",
            latest_signal_id="",
            affected_entity_id="entity:pod",
            first_observed_at=NOW.isoformat(),
            last_observed_at=NOW.isoformat(),
            created_at=NOW.isoformat(),
            updated_at=NOW.isoformat(),
            tenant_id=TEST_TENANT,
        )
    )
    session.commit()


def _analysis_response(candidates) -> IncidentChangeAnalysisResponse:
    return IncidentChangeAnalysisResponse(
        incident_id="incident:cc1",
        incident_time=NOW.isoformat(),
        lookback_minutes=180,
        after_minutes=10,
        affected_entity_ids=["entity:pod"],
        candidate_count=len(candidates),
        candidates=list(candidates),
    )


def test_causal_analysis_persists_candidate_audit_and_policy(monkeypatch) -> None:
    session = _session()
    _incident(session)
    derived = [
        _relationship_candidate(
            f"event:derived:{index}",
            "selects",
            score=99 - index,
        )
        for index in range(1, 11)
    ]
    primary = _deployment_candidate(score=55.2)
    monkeypatch.setattr(
        causal_service,
        "analyze_incident_change_events",
        lambda *args, **kwargs: _analysis_response([*derived, primary]),
    )

    analysis = causal_service.analyze_causal_rca(
        session,
        incident_id="incident:cc1",
        request=CausalAnalysisRequest(max_hypotheses=1),
        tenant_id=TEST_TENANT,
    )
    loaded = latest_causal_analysis(
        session, incident_id="incident:cc1", tenant_id=TEST_TENANT
    )

    assert loaded is not None
    assert loaded.analysis_id == analysis.analysis_id
    assert loaded.candidate_policy_version == CAUSAL_CANDIDATE_POLICY_VERSION
    assert loaded.top_hypothesis is not None
    assert loaded.top_hypothesis.target_event_id == primary.event.event_id
    audit = {item.event_id: item for item in loaded.candidate_selection_audit}
    assert audit[derived[0].event.event_id].raw_rank == 1
    assert (
        audit[derived[0].event.event_id].exclusion_reason
        == "derived_relationship_change"
    )
    assert audit[primary.event.event_id].raw_rank == 11
    assert audit[primary.event.event_id].raw_score == 55.2
    assert audit[primary.event.event_id].eligible_rank == 1
    assert audit[primary.event.event_id].policy_version == "causal-candidate-v1"


def test_only_derived_candidates_produce_no_hypothesis(monkeypatch) -> None:
    session = _session()
    _incident(session)
    derived = _relationship_candidate("event:derived", "selects")
    monkeypatch.setattr(
        causal_service,
        "analyze_incident_change_events",
        lambda *args, **kwargs: _analysis_response([derived]),
    )
    analysis = causal_service.analyze_causal_rca(
        session,
        incident_id="incident:cc1",
        request=CausalAnalysisRequest(),
        tenant_id=TEST_TENANT,
    )
    assert analysis.hypothesis_count == 0
    assert analysis.top_hypothesis is None
    assert analysis.confidence_semantics is not None
    assert analysis.confidence_semantics.evidence_state.value == "insufficient_evidence"


def test_only_runtime_symptoms_produce_no_hypothesis(monkeypatch) -> None:
    session = _session()
    _incident(session)
    symptom = _candidate(
        "event:symptom",
        source=ChangeEventSource.KUBERNETES,
        event_kind=ChangeEventKind.TOPOLOGY,
        entity_kind="KubernetesPod",
        reason="ImagePullBackOff",
    )
    monkeypatch.setattr(
        causal_service,
        "analyze_incident_change_events",
        lambda *args, **kwargs: _analysis_response([symptom]),
    )
    analysis = causal_service.analyze_causal_rca(
        session,
        incident_id="incident:cc1",
        request=CausalAnalysisRequest(),
        tenant_id=TEST_TENANT,
    )
    assert analysis.top_hypothesis is None


def test_analysis_generation_is_idempotent_with_candidate_policy(monkeypatch) -> None:
    session = _session()
    _incident(session)
    primary = _deployment_candidate()
    monkeypatch.setattr(
        causal_service,
        "analyze_incident_change_events",
        lambda *args, **kwargs: _analysis_response([primary]),
    )
    first = causal_service.analyze_causal_rca(
        session,
        incident_id="incident:cc1",
        request=CausalAnalysisRequest(),
        tenant_id=TEST_TENANT,
    )
    second = causal_service.analyze_causal_rca(
        session,
        incident_id="incident:cc1",
        request=CausalAnalysisRequest(),
        tenant_id=TEST_TENANT,
    )
    assert second.model_dump_json() == first.model_dump_json()
    assert session.query(CausalAnalysisRecord).count() == 1


def test_legacy_analysis_loads_without_v1_claim_or_payload_rewrite(monkeypatch) -> None:
    session = _session()
    _incident(session)
    primary = _deployment_candidate()
    monkeypatch.setattr(
        causal_service,
        "analyze_incident_change_events",
        lambda *args, **kwargs: _analysis_response([primary]),
    )
    current = causal_service.analyze_causal_rca(
        session,
        incident_id="incident:cc1",
        request=CausalAnalysisRequest(),
        persist=False,
        tenant_id=TEST_TENANT,
    )
    payload = current.model_dump(mode="json")
    payload.pop("candidate_policy_version")
    payload.pop("candidate_selection_audit")
    payload["analysis_id"] = "causal-analysis:legacy"
    legacy_json = json.dumps(payload)
    session.add(
        CausalAnalysisRecord(
            analysis_id="causal-analysis:legacy",
            incident_id="incident:cc1",
            generated_at=current.generated_at,
            algorithm_version=current.algorithm_version,
            candidate_count=current.candidate_count,
            hypothesis_count=current.hypothesis_count,
            top_hypothesis_score=current.top_hypothesis.score,
            top_root_event_id=current.top_hypothesis.root_event_id,
            payload_json=legacy_json,
            created_at=NOW.isoformat(),
            updated_at=NOW.isoformat(),
            tenant_id=TEST_TENANT,
        )
    )
    session.commit()

    loaded = latest_causal_analysis(
        session, incident_id="incident:cc1", tenant_id=TEST_TENANT
    )
    assert loaded is not None
    assert loaded.candidate_policy_version is None
    assert loaded.candidate_selection_audit == []
    assert session.get(CausalAnalysisRecord, "causal-analysis:legacy").payload_json == legacy_json


def test_13c_formula_coefficients_and_versions_remain_unchanged(monkeypatch) -> None:
    source = inspect.getsource(causal_service.analyze_causal_rca)
    assert "candidate.score * 0.40" in source
    assert "topology_component * 25" in source
    assert "temporal_component * 15" in source
    assert "_kind_prior" in source and ") * 10" in source
    assert "lineage_component * 10" in source
    assert causal_service.ALGORITHM_VERSION == "13c-causal-v1"
    assert CONFIDENCE_SEMANTICS_VERSION == "tc5.v1"
    assert BLAST_POLICY_VERSION == "blast-impact-v1"

    session = _session()
    _incident(session)
    primary = _deployment_candidate(score=55.2)
    monkeypatch.setattr(
        causal_service,
        "analyze_incident_change_events",
        lambda *args, **kwargs: _analysis_response([primary]),
    )
    analysis = causal_service.analyze_causal_rca(
        session,
        incident_id="incident:cc1",
        request=CausalAnalysisRequest(),
        persist=False,
        tenant_id=TEST_TENANT,
    )
    expected = 55.2 * 0.40 + math.exp(-2 / 90) * 15 + 1.0 * 10
    assert analysis.top_hypothesis.score == round(expected, 2)
    semantics = analysis.top_hypothesis.confidence_semantics
    assert semantics.score_type.value == "heuristic_ranking"
    assert semantics.calibration_status.value == "not_calibrated"
    assert semantics.calibrated_probability is None


def test_policy_contains_no_sentinel_or_namespace_special_cases() -> None:
    source = inspect.getsource(policy_service).lower()
    assert "sentinel-a" not in source
    assert "sentinel-b" not in source
    assert "sentinel-c" not in source
    assert "topo-eval" not in source
