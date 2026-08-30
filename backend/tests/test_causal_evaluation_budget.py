from __future__ import annotations
from domain_tenant_fixtures import TEST_TENANT, seed_domain_tenant

import inspect
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.services.causal_evaluation_budget as budget_service
import app.services.causal_rca as causal_service
from app.db.database import Base
from app.db.models import CausalAnalysisRecord, IncidentRecord
from app.models.causal_candidates import (
    CAUSAL_CANDIDATE_ADMISSION_POLICY_VERSION,
    CAUSAL_EVALUATION_BUDGET_POLICY_VERSION,
    CandidateAdmissionBasis,
    CandidateAdmissionEvidenceReference,
    CausalEvaluationSelectionBasis,
    LineageAdmissionReason,
    LineageAdmissionState,
    LineageContainerScope,
    LineagePathAudit,
)
from app.models.causal_rca import CausalAnalysisRequest
from app.models.change_events import (
    ChangeEventKind,
    ChangeEventRiskLevel,
    ChangeEventSource,
    ChangeEventView,
    IncidentChangeAnalysisResponse,
    IncidentChangeCandidate,
)
from app.repositories.causal_analysis_repository import latest_causal_analysis
from app.services.causal_candidate_policy import select_causal_candidates
from app.services.lineage_candidate_admission import (
    evaluate_lineage_candidate_admission,
)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
GOLDEN_ID = "change:golden-source-mutation"
EXACT_BASIS = (
    CausalEvaluationSelectionBasis
    .EVIDENCE_PRESERVED_EXACT_IMMUTABLE_LINEAGE
)


def _candidate(
    event_id: str,
    *,
    score: float,
    exact_lineage: bool = False,
    admission_state: LineageAdmissionState | None = None,
    admission_reason: LineageAdmissionReason | None = None,
    admission_policy: str = CAUSAL_CANDIDATE_ADMISSION_POLICY_VERSION,
    admission_basis: list[CandidateAdmissionBasis] | None = None,
    status: str = "observed",
) -> IncidentChangeCandidate:
    occurred_at = "2026-08-23T11:58:00+00:00"
    event = ChangeEventView(
        event_id=event_id,
        event_fingerprint=f"fingerprint:{event_id}",
        source=ChangeEventSource.GITHUB,
        kind=ChangeEventKind.CODE,
        external_id=event_id,
        origin_change_id=event_id,
        title=f"Source mutation {event_id}",
        summary=None,
        actor="fixture",
        occurred_at=occurred_at,
        received_at=occurred_at,
        environment="production",
        provider="github",
        account_id=None,
        region=None,
        cluster_name="production",
        namespace="payments",
        repository="example/payments",
        commit_sha="a" * 40,
        pipeline_name=None,
        release_version=None,
        terraform_workspace=None,
        risk_score=50,
        risk_level=ChangeEventRiskLevel.MEDIUM,
        status=status,
        observation_count=1,
        metadata={},
        raw_payload={},
        agent_id=None,
        links=[],
        created_at=occurred_at,
        updated_at=occurred_at,
    )

    bases = admission_basis
    evidence_refs: list[CandidateAdmissionEvidenceReference] = []
    paths: list[LineagePathAudit] = []
    container_scope = None
    state = admission_state
    reason = admission_reason
    if exact_lineage:
        bases = [
            CandidateAdmissionBasis.TEMPORAL,
            CandidateAdmissionBasis.EXACT_IMMUTABLE_LINEAGE,
        ]
        state = LineageAdmissionState.ADMITTED
        reason = LineageAdmissionReason.EXACT_IMMUTABLE_LINEAGE
        evidence_refs = [
            CandidateAdmissionEvidenceReference(
                reference_type="provider_build_evidence",
                reference="build:evidence:1",
                source_system="github-actions",
            )
        ]
        container_scope = LineageContainerScope(
            affected_entity_id="entity:pod",
            pod_entity_id="entity:pod",
            workload_entity_id="entity:deployment",
            container_name="payments",
            image_entity_id="entity:image",
            image_digest="sha256:" + "b" * 64,
        )
        paths = [
            LineagePathAudit(
                path_id="lineage-path:golden",
                affected_entity_id="entity:pod",
                entity_ids=[
                    "entity:pod",
                    "entity:deployment",
                    "entity:image",
                ],
                relationship_ids=["relationship:pod-owner"],
                provider_evidence_ids=["build:evidence:1"],
                container_name="payments",
                image_entity_id="entity:image",
                image_entity_kind="ContainerImage",
                image_digest="sha256:" + "b" * 64,
                repository_id="repository:example/payments",
                repository="example/payments",
                run_id="1234",
                run_attempt=1,
                revision="a" * 40,
                canonical_change_id=event_id,
                provider_effective_at="2026-08-23T11:30:00+00:00",
            )
        ]

    return IncidentChangeCandidate(
        event=event,
        score=score,
        minutes_before_incident=2.0,
        candidate_admission_policy_version=admission_policy,
        admission_basis=(
            bases if bases is not None else [CandidateAdmissionBasis.TEMPORAL]
        ),
        admission_evidence_refs=evidence_refs,
        lineage_paths=paths,
        container_scope=container_scope,
        lineage_admission_state=state,
        lineage_admission_reason=reason,
    )


def _distractors(count: int) -> list[IncidentChangeCandidate]:
    return [
        _candidate(f"change:distractor:{index:03d}", score=99.0 - index)
        for index in range(count)
    ]


def _frontier(candidates, *, limit: int = 5):
    ordinary = select_causal_candidates(candidates, limit=limit)
    evaluation = budget_service.build_causal_candidate_evaluation_frontier(
        candidates,
        ordinary_candidates=ordinary.selected_candidates,
        ordinary_selection_audit=ordinary.audit,
        ordinary_shortlist_limit=limit,
    )
    return ordinary, evaluation


@pytest.mark.parametrize(
    "distractor_count,expected_raw_rank",
    [(5, 6), (10, 11), (20, 21), (50, 51)],
)
def test_exact_lineage_candidate_outside_top_five_is_evaluated_without_reranking(
    distractor_count: int,
    expected_raw_rank: int,
) -> None:
    candidates = [
        *_distractors(distractor_count),
        _candidate(GOLDEN_ID, score=1.0, exact_lineage=True),
    ]
    ordinary, evaluation = _frontier(candidates)

    assert [item.event.event_id for item in ordinary.selected_candidates] == [
        f"change:distractor:{index:03d}" for index in range(5)
    ]
    assert [item.event.event_id for item in evaluation.candidates] == [
        *[f"change:distractor:{index:03d}" for index in range(5)],
        GOLDEN_ID,
    ]
    audit = {item.event_id: item for item in evaluation.audit}[GOLDEN_ID]
    assert audit.raw_rank == expected_raw_rank
    assert audit.raw_score == 1.0
    assert audit.selected_for_evaluation is True
    assert audit.ordinary_shortlist_member is False
    assert audit.evidence_preserved_member is True
    assert audit.evaluation_selection_bases == [EXACT_BASIS]
    assert evaluation.budget.ordinary_shortlist_limit == 5
    assert evaluation.budget.ordinary_shortlist_count == 5
    assert evaluation.budget.evidence_preserved_candidate_count == 1
    assert evaluation.budget.evaluation_frontier_size == 6


@pytest.mark.parametrize("candidate_count", [6, 50])
def test_temporal_only_candidates_do_not_expand_the_ordinary_budget(
    candidate_count: int,
) -> None:
    candidates = _distractors(candidate_count)
    ordinary, evaluation = _frontier(candidates)

    assert len(ordinary.selected_candidates) == 5
    assert len(evaluation.candidates) == 5
    sixth = evaluation.audit[5]
    assert sixth.raw_rank == 6
    assert sixth.selected_for_evaluation is False
    assert sixth.evaluation_selection_bases == []
    assert sixth.exclusion_reason == "outside_evaluation_frontier"


@pytest.mark.parametrize(
    "candidate",
    [
        _candidate(
            "change:incomplete",
            score=1,
            admission_state=LineageAdmissionState.INCOMPLETE,
            admission_reason=LineageAdmissionReason.SOURCE_CHANGE_MISSING,
            admission_basis=[CandidateAdmissionBasis.EXACT_IMMUTABLE_LINEAGE],
        ),
        _candidate(
            "change:ambiguous",
            score=1,
            admission_state=LineageAdmissionState.INCOMPLETE,
            admission_reason=LineageAdmissionReason.AMBIGUOUS_SOURCE_PROVENANCE,
            admission_basis=[CandidateAdmissionBasis.EXACT_IMMUTABLE_LINEAGE],
        ),
        _candidate(
            "change:wrong-policy",
            score=1,
            admission_state=LineageAdmissionState.ADMITTED,
            admission_reason=LineageAdmissionReason.EXACT_IMMUTABLE_LINEAGE,
            admission_policy="causal-candidate-admission-unknown",
            admission_basis=[CandidateAdmissionBasis.EXACT_IMMUTABLE_LINEAGE],
        ),
        _candidate(
            "change:no-exact-basis",
            score=1,
            admission_state=LineageAdmissionState.ADMITTED,
            admission_reason=LineageAdmissionReason.EXACT_IMMUTABLE_LINEAGE,
            admission_basis=[CandidateAdmissionBasis.TEMPORAL],
        ),
        _candidate("change:repository-similarity", score=1),
        _candidate("change:tag-similarity", score=1),
        _candidate("change:high-risk", score=1),
        _candidate("change:old-age", score=1),
        _candidate(
            "change:no-change",
            score=1,
            exact_lineage=True,
            status="no_change",
        ),
    ],
    ids=lambda item: item.event.event_id,
)
def test_only_complete_exact_sc2_admission_is_evidence_preserved(
    candidate: IncidentChangeCandidate,
) -> None:
    _, evaluation = _frontier([*_distractors(5), candidate])
    audit = {item.event_id: item for item in evaluation.audit}[
        candidate.event.event_id
    ]
    assert audit.selected_for_evaluation is False
    assert audit.evidence_preserved_member is False


def test_dual_basis_candidate_is_evaluated_once_with_deterministic_metadata() -> None:
    golden = _candidate(GOLDEN_ID, score=100.0, exact_lineage=True)
    candidates = [golden, *_distractors(5)]
    _ordinary, evaluation = _frontier(candidates)

    assert [item.event.event_id for item in evaluation.candidates].count(GOLDEN_ID) == 1
    audit = {item.event_id: item for item in evaluation.audit}[GOLDEN_ID]
    assert audit.evaluation_selection_bases == [
        CausalEvaluationSelectionBasis.ORDINARY_RAW_TOP_K,
        EXACT_BASIS,
    ]
    assert audit.evaluation_frontier_position == 1
    assert audit.raw_score == 100.0


def test_evaluation_membership_and_order_do_not_depend_on_input_permutation() -> None:
    golden = _candidate(GOLDEN_ID, score=1.0, exact_lineage=True)
    candidates = [*_distractors(8), golden]
    _ordinary_a, evaluation_a = _frontier(candidates)
    _ordinary_b, evaluation_b = _frontier(list(reversed(candidates)))

    assert [item.event.event_id for item in evaluation_a.candidates] == [
        item.event.event_id for item in evaluation_b.candidates
    ]


def test_unknown_evaluation_budget_policy_fails_safely() -> None:
    candidates = _distractors(1)
    ordinary = select_causal_candidates(candidates, limit=5)
    with pytest.raises(ValueError, match="Unsupported causal evaluation budget"):
        budget_service.build_causal_candidate_evaluation_frontier(
            candidates,
            ordinary_candidates=ordinary.selected_candidates,
            ordinary_selection_audit=ordinary.audit,
            ordinary_shortlist_limit=5,
            policy_version="causal-evaluation-budget-unknown",
        )


def test_sc2_proves_one_preserved_candidate_without_ar1_truncation() -> None:
    assert budget_service.SC2_EXACT_LINEAGE_CANDIDATE_MAX == 1
    admission_source = inspect.getsource(evaluate_lineage_candidate_admission)
    budget_source = inspect.getsource(
        budget_service.build_causal_candidate_evaluation_frontier
    )
    assert "admitted=(admitted,)" in admission_source
    assert "protected_ids" in budget_source
    assert "protected_ids[:" not in budget_source
    assert "protected_outside_ordinary[:" not in budget_source


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine)
    return Session(engine)


def _incident(session: Session) -> None:
    session.add(
        IncidentRecord(
            incident_id="incident:ar1",
            fingerprint="fingerprint:incident:ar1",
            status="investigating",
            severity="error",
            title="AR-1 incident",
            summary="Evidence-preserving evaluation fixture",
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
        incident_id="incident:ar1",
        incident_time=NOW.isoformat(),
        lookback_minutes=180,
        after_minutes=10,
        affected_entity_ids=["entity:pod"],
        candidate_count=len(candidates),
        candidates=list(candidates),
    )


@pytest.mark.parametrize(
    "distractor_count,expected_raw_rank",
    [(5, 6), (50, 51)],
)
def test_ar1_frontier_reaches_relevance_once_and_persists_round_trip(
    monkeypatch,
    distractor_count: int,
    expected_raw_rank: int,
) -> None:
    session = _session()
    _incident(session)
    golden = _candidate(GOLDEN_ID, score=1.0, exact_lineage=True)
    candidates = [*_distractors(distractor_count), golden]
    monkeypatch.setattr(
        causal_service,
        "analyze_incident_change_events",
        lambda *args, **kwargs: _analysis_response(candidates),
    )
    relevance_calls: list[str] = []
    real_relevance = causal_service.evaluate_causal_relevance

    def recording_relevance(*args, **kwargs):
        relevance_calls.append(kwargs["candidate_event_id"])
        return real_relevance(*args, **kwargs)

    monkeypatch.setattr(causal_service, "evaluate_causal_relevance", recording_relevance)
    analysis = causal_service.analyze_causal_rca(
        session,
        incident_id="incident:ar1",
        request=CausalAnalysisRequest(),
        tenant_id=TEST_TENANT,
    )
    loaded = latest_causal_analysis(
        session, incident_id="incident:ar1", tenant_id=TEST_TENANT
    )

    assert loaded is not None
    assert loaded.analysis_id == analysis.analysis_id
    assert loaded.evaluation_policy_version == CAUSAL_EVALUATION_BUDGET_POLICY_VERSION
    assert loaded.evaluation_budget_audit is not None
    assert loaded.evaluation_budget_audit.evaluation_frontier_size == 6
    assert relevance_calls.count(GOLDEN_ID) == 1
    relevance_ids = [item.candidate_event_id for item in loaded.candidate_relevance_audit]
    assert relevance_ids.count(GOLDEN_ID) == 1
    evaluation = {item.event_id: item for item in loaded.candidate_evaluation_audit}
    assert evaluation[GOLDEN_ID].raw_rank == expected_raw_rank
    assert evaluation[GOLDEN_ID].raw_score == 1.0
    assert evaluation[GOLDEN_ID].evaluation_selection_bases == [EXACT_BASIS]
    golden_relevance = next(
        item
        for item in loaded.candidate_relevance_audit
        if item.candidate_event_id == GOLDEN_ID
    )
    assert golden_relevance.relevance_status.value == "identity_unresolved"
    assert any(item.target_event_id == GOLDEN_ID for item in loaded.hypotheses)
    assert len(loaded.hypotheses) == 6
    assert len(loaded.diagnostic_hypothesis_ids) == 5
    golden_hypothesis_id = next(
        item.hypothesis_id
        for item in loaded.hypotheses
        if item.target_event_id == GOLDEN_ID
    )
    assert golden_hypothesis_id not in loaded.diagnostic_hypothesis_ids
    assert loaded.supported_hypothesis_ids == []


def test_dual_basis_produces_one_relevance_row_and_one_hypothesis_ledger(
    monkeypatch,
) -> None:
    session = _session()
    _incident(session)
    golden = _candidate(GOLDEN_ID, score=100.0, exact_lineage=True)
    candidates = [golden, *_distractors(5)]
    monkeypatch.setattr(
        causal_service,
        "analyze_incident_change_events",
        lambda *args, **kwargs: _analysis_response(candidates),
    )
    analysis = causal_service.analyze_causal_rca(
        session,
        incident_id="incident:ar1",
        request=CausalAnalysisRequest(),
        persist=False,
        tenant_id=TEST_TENANT,
    )

    assert sum(
        item.candidate_event_id == GOLDEN_ID
        for item in analysis.candidate_relevance_audit
    ) == 1
    matching = [item for item in analysis.hypotheses if item.target_event_id == GOLDEN_ID]
    assert len(matching) == 1
    assert matching[0].evidence_ledger is not None
    assert analysis.top_hypothesis is not None
    assert analysis.top_hypothesis.target_event_id == GOLDEN_ID


def test_historical_analysis_loads_without_fabricated_ar1_metadata(monkeypatch) -> None:
    session = _session()
    _incident(session)
    candidates = [_candidate("change:ordinary", score=50.0)]
    monkeypatch.setattr(
        causal_service,
        "analyze_incident_change_events",
        lambda *args, **kwargs: _analysis_response(candidates),
    )
    current = causal_service.analyze_causal_rca(
        session,
        incident_id="incident:ar1",
        request=CausalAnalysisRequest(),
        persist=False,
        tenant_id=TEST_TENANT,
    )
    payload = current.model_dump(mode="json")
    payload.pop("evaluation_policy_version")
    payload.pop("candidate_evaluation_audit")
    payload.pop("evaluation_budget_audit")
    payload["analysis_id"] = "causal-analysis:pre-ar1"
    legacy_json = json.dumps(payload)
    session.add(
        CausalAnalysisRecord(
            analysis_id="causal-analysis:pre-ar1",
            incident_id="incident:ar1",
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
        session, incident_id="incident:ar1", tenant_id=TEST_TENANT
    )
    assert loaded is not None
    assert loaded.evaluation_policy_version is None
    assert loaded.candidate_evaluation_audit == []
    assert loaded.evaluation_budget_audit is None
    assert session.get(
        CausalAnalysisRecord, "causal-analysis:pre-ar1"
    ).payload_json == legacy_json


def test_ar1_changes_only_evaluation_membership_not_frozen_semantics() -> None:
    rca_source = inspect.getsource(causal_service.analyze_causal_rca)
    budget_source = inspect.getsource(budget_service).lower()

    assert "candidate.score * 0.40" in rca_source
    assert "topology_component * 25" in rca_source
    assert "temporal_component * 15" in rca_source
    assert "lineage_component * 10" in rca_source
    assert '"causal_evaluation_budget_policy"' in rca_source
    assert "project_causal_hypotheses(" in rca_source
    assert "diagnostic_limit=request.max_hypotheses" in rca_source
    assert "supported_limit=request.max_hypotheses" in rca_source
    assert "list_build_artifact_evidence" not in budget_source
    assert "http" not in budget_source
    assert "embedding" not in budget_source
    assert "llm" not in budget_source
    assert "sentinel" not in budget_source
    assert "topo-eval" not in budget_source
    assert "sha256:" not in budget_source
