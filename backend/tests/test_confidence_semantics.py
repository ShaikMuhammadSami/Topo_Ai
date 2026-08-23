from __future__ import annotations

import json
from pathlib import Path

from app.models.causal_rca import (
    CausalAnalysisResponse,
    CausalConfidenceLevel,
    CausalEvidenceClaimType,
    CausalEvidenceLedger,
    CausalEvidenceLedgerItem,
    CausalEvidenceQuality,
    CausalEvidenceSourceCategory,
    CausalEvidenceSourceReference,
    CausalEvidenceStance,
    CausalHypothesis,
)
from app.models.confidence_semantics import (
    CONFIDENCE_SEMANTICS_VERSION,
    CausalCalibrationStatus,
    CausalEvidenceCompleteness,
    CausalEvidenceState,
    CausalScoreType,
    LegacyConfidenceSemantics,
)
from app.models.incident_briefing import BriefingRootCause
from app.services.causal_rca import _confidence_level
from app.services.confidence_semantics import (
    ensure_analysis_confidence_semantics,
)


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
CONTRACT_PATH = (
    ROOT
    / "docs"
    / "architecture"
    / "truth-contract"
    / "confidence-semantics-contract.json"
)


def _item(
    stance: CausalEvidenceStance,
    index: int,
) -> CausalEvidenceLedgerItem:
    common = {
        "evidence_id": f"evidence:{stance.value}:{index}",
        "hypothesis_id": "hypothesis:test",
        "stance": stance,
        "summary": f"{stance.value} item",
        "reason": "Deterministic fixture evidence.",
        "source_references": [
            CausalEvidenceSourceReference(
                reference_type="change_event",
                reference_id=f"event:{index}",
                source_system="test",
            )
        ],
        "quality": CausalEvidenceQuality.STRONG,
        "why_it_matters": "Exercises TC-5 interpretation only.",
    }
    if stance == CausalEvidenceStance.SUPPORTING:
        return CausalEvidenceLedgerItem(
            **common,
            claim_type=CausalEvidenceClaimType.SOURCE_CHANGE,
            source_category=CausalEvidenceSourceCategory.CHANGE,
            change_event_ids=[f"event:{index}"],
        )
    if stance == CausalEvidenceStance.CONTRADICTING:
        return CausalEvidenceLedgerItem(
            **common,
            claim_type=CausalEvidenceClaimType.TEMPORAL_PRECEDENCE,
            source_category=CausalEvidenceSourceCategory.TEMPORAL,
            change_event_ids=[f"event:{index}"],
            incident_boundary_at="2026-08-23T10:00:00+00:00",
        )
    return CausalEvidenceLedgerItem(
        **common,
        claim_type=CausalEvidenceClaimType.RELATIONSHIP_PROVENANCE,
        source_category=CausalEvidenceSourceCategory.TOPOLOGY,
        relationship_ids=[f"relationship:{index}"],
        snapshot_id="snapshot:test",
        expectation_basis="A selected topology hop requires provenance.",
    )


def _ledger(
    *,
    supporting: int = 1,
    contradicting: int = 0,
    missing: int = 0,
) -> CausalEvidenceLedger:
    return CausalEvidenceLedger(
        hypothesis_id="hypothesis:test",
        snapshot_id="snapshot:test",
        supporting=[
            _item(CausalEvidenceStance.SUPPORTING, index)
            for index in range(supporting)
        ],
        contradicting=[
            _item(CausalEvidenceStance.CONTRADICTING, index)
            for index in range(contradicting)
        ],
        missing=[
            _item(CausalEvidenceStance.MISSING, index)
            for index in range(missing)
        ],
    )


def _hypothesis(
    *,
    score: float = 83.5,
    confidence: float = 0.835,
    rank: int = 1,
    ledger: CausalEvidenceLedger | None = None,
) -> CausalHypothesis:
    return CausalHypothesis(
        hypothesis_id="hypothesis:test",
        rank=rank,
        root_event_id="event:root",
        root_source="kubernetes",
        root_title="Deployment changed",
        target_event_id="event:target",
        target_title="Pod failed",
        affected_entity_id="entity:pod",
        score=score,
        confidence=confidence,
        confidence_level=_confidence_level(confidence),
        summary="A deterministic causal hypothesis.",
        evidence_ledger=ledger,
    )


def _analysis(
    hypotheses: list[CausalHypothesis],
) -> CausalAnalysisResponse:
    return CausalAnalysisResponse(
        analysis_id="analysis:test",
        incident_id="incident:test",
        incident_title="Test incident",
        incident_time="2026-08-23T10:00:00+00:00",
        topology_snapshot_id="snapshot:test",
        algorithm_version="13c-causal-v1",
        generated_at="2026-08-23T10:01:00+00:00",
        parameters={},
        candidate_count=len(hypotheses),
        node_count=0,
        edge_count=0,
        evidence_count=0,
        hypothesis_count=len(hypotheses),
        top_hypothesis=hypotheses[0] if hypotheses else None,
        hypotheses=hypotheses,
    )


def _enriched(
    *,
    supporting: int = 1,
    contradicting: int = 0,
    missing: int = 0,
    score: float = 83.5,
) -> tuple[CausalAnalysisResponse, CausalHypothesis]:
    hypothesis = _hypothesis(
        score=score,
        confidence=round(score / 100, 4),
        ledger=_ledger(
            supporting=supporting,
            contradicting=contradicting,
            missing=missing,
        ),
    )
    analysis = ensure_analysis_confidence_semantics(_analysis([hypothesis]))
    assert analysis.top_hypothesis is not None
    assert analysis.confidence_semantics is not None
    return analysis, analysis.top_hypothesis


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_current_ranking_score_value_is_unchanged() -> None:
    _, hypothesis = _enriched(score=83.5)
    assert hypothesis.score == 83.5


def test_existing_top_hypothesis_order_is_unchanged() -> None:
    first = _hypothesis(score=83.5, confidence=0.835, rank=1, ledger=_ledger())
    second = first.model_copy(
        update={
            "hypothesis_id": "hypothesis:second",
            "score": 81.0,
            "confidence": 0.81,
            "rank": 2,
            "evidence_ledger": None,
        }
    )
    analysis = ensure_analysis_confidence_semantics(_analysis([first, second]))
    assert [item.score for item in analysis.hypotheses] == [83.5, 81.0]
    assert analysis.top_hypothesis.score == 83.5


def test_legacy_confidence_value_remains_compatible() -> None:
    _, hypothesis = _enriched(score=83.5)
    assert hypothesis.confidence == 0.835
    assert hypothesis.confidence_semantics.legacy_confidence == 0.835


def test_legacy_confidence_is_explicitly_heuristic() -> None:
    analysis, _ = _enriched()
    semantics = analysis.confidence_semantics
    assert semantics.score_type == CausalScoreType.HEURISTIC_RANKING
    assert semantics.legacy_confidence_semantics == (
        LegacyConfidenceSemantics.NORMALIZED_HEURISTIC_RANKING_SCORE
    )


def test_calibrated_probability_is_null() -> None:
    analysis, _ = _enriched()
    assert analysis.confidence_semantics.calibrated_probability is None
    assert analysis.confidence_semantics.calibration_status == (
        CausalCalibrationStatus.NOT_CALIBRATED
    )


def test_score_divided_by_100_is_not_labeled_probability() -> None:
    semantics = _enriched()[0].confidence_semantics
    assert semantics.legacy_confidence == semantics.ranking_score / 100
    assert "probability" not in semantics.legacy_confidence_semantics.value


def test_alternative_scores_are_not_a_probability_distribution() -> None:
    values = [0.835, 0.81]
    assert sum(values) != 1.0
    assert _contract()["causal_ranking"]["alternative_scores_form_distribution"] is False


def test_supporting_count_does_not_change_ranking() -> None:
    _, one = _enriched(supporting=1)
    _, five = _enriched(supporting=5)
    assert (one.score, one.confidence) == (five.score, five.confidence)


def test_contradicting_count_does_not_automatically_rescore() -> None:
    _, clear = _enriched(contradicting=0)
    _, contested = _enriched(contradicting=1)
    assert (clear.score, clear.confidence) == (contested.score, contested.confidence)


def test_missing_count_does_not_automatically_rescore() -> None:
    _, complete = _enriched(missing=0)
    _, partial = _enriched(missing=1)
    assert (complete.score, complete.confidence) == (partial.score, partial.confidence)


def test_high_ranking_with_contradiction_is_contested() -> None:
    analysis, _ = _enriched(contradicting=1, score=85.0)
    assert analysis.confidence_semantics.evidence_state == CausalEvidenceState.CONTESTED
    assert analysis.confidence_semantics.calibrated_probability is None


def test_high_ranking_with_missing_evidence_is_partial() -> None:
    analysis, _ = _enriched(missing=1, score=85.0)
    assert analysis.confidence_semantics.evidence_state == CausalEvidenceState.INCOMPLETE
    assert analysis.confidence_semantics.evidence_completeness == CausalEvidenceCompleteness.PARTIAL


def test_no_hypothesis_is_explicit_insufficient_evidence() -> None:
    analysis = ensure_analysis_confidence_semantics(_analysis([]))
    assert analysis.confidence_semantics.evidence_state == CausalEvidenceState.INSUFFICIENT_EVIDENCE


def test_completed_no_hypothesis_fabricates_no_score_or_confidence() -> None:
    analysis = ensure_analysis_confidence_semantics(_analysis([]))
    semantics = analysis.confidence_semantics
    assert semantics.ranking_score is None
    assert semantics.legacy_confidence is None
    assert semantics.calibrated_probability is None


def test_tc4_evidence_ledger_is_not_mutated() -> None:
    ledger = _ledger(supporting=2, contradicting=1, missing=1)
    before = ledger.model_dump_json()
    ensure_analysis_confidence_semantics(_analysis([_hypothesis(ledger=ledger)]))
    assert ledger.model_dump_json() == before


def test_tc3_temporal_metadata_remains_outside_confidence_contract() -> None:
    fields = set(_contract()["evidence_interpretation"])
    assert "temporal_score" not in fields
    assert "TC-3" in _source(
        "docs/architecture/truth-contract/confidence-semantics.md"
    )


def test_tc2_relationship_confidence_semantics_remain_unchanged() -> None:
    tc2 = json.loads(
        _source("docs/architecture/truth-contract/relationship-provenance-contract.json")
    )
    assert tc2["confidence"]["semantics"] == "heuristic_score"
    assert tc2["confidence"]["probabilistic"] is False


def test_tc1_identity_resolution_contract_is_unchanged() -> None:
    tc1 = json.loads(
        _source("docs/architecture/truth-contract/entity-identity-contract.json")
    )
    assert tc1["identity_version"] == "v1"
    assert tc1["fuzzy_matching"] is False


def test_14d_similarity_is_separate_from_causal_score() -> None:
    concepts = {item["field"]: item for item in _contract()["score_concepts"]}
    similarity = concepts["HistoricalIncidentMatch.similarity_score"]
    assert similarity["semantic_type"] == "deterministic_weighted_similarity_score"
    assert similarity["probabilistic"] is False


def test_ownership_confidence_is_not_causal_probability() -> None:
    concepts = {item["field"]: item for item in _contract()["score_concepts"]}
    ownership = concepts["EntityOwnershipResolution.confidence"]
    assert ownership["semantic_type"] == "ownership_mapping_specificity_score"
    assert ownership["probabilistic"] is False


def test_response_plan_threshold_behavior_is_unchanged() -> None:
    source = _source("backend/app/services/response_plan.py")
    assert "STRONG_CAUSAL_CONFIDENCE = 0.75" in source
    assert "hypothesis.confidence < 0.50" in source


def test_dormant_14f_readiness_strength_policy_is_unchanged() -> None:
    source = _source("backend/app/services/execution_readiness.py")
    assert "CurrentEvidenceStrength.HIGH" in source
    assert "CurrentEvidenceStrength.MODERATE" in source


def test_llm_cannot_produce_authoritative_semantics_fields() -> None:
    source = _source("backend/app/services/confidence_semantics.py")
    assert "llm" not in source.casefold()
    assert "openai" not in source.casefold()


def test_ai_narrative_update_cannot_overwrite_calibration_status() -> None:
    source = _source("backend/app/services/incident_briefing.py")
    final_update = source[source.rfind('"ai_summary": generated.text') :]
    assert "confidence_semantics" not in final_update
    assert "calibration_status" not in final_update


def test_api_serialization_exposes_explicit_semantics() -> None:
    payload = _enriched()[0].model_dump(mode="json")
    assert payload["confidence_semantics"]["score_type"] == "heuristic_ranking"
    assert payload["confidence_semantics"]["calibrated_probability"] is None
    assert payload["top_hypothesis"]["confidence_semantics"] == payload["confidence_semantics"]


def test_old_persisted_analysis_payload_deserializes_and_enriches_in_memory() -> None:
    current = _enriched()[0].model_dump(mode="json")
    current.pop("confidence_semantics", None)
    current["top_hypothesis"].pop("confidence_semantics", None)
    for item in current["hypotheses"]:
        item.pop("confidence_semantics", None)
    legacy = CausalAnalysisResponse.model_validate(current)
    assert legacy.confidence_semantics is None
    enriched = ensure_analysis_confidence_semantics(legacy)
    assert enriched.confidence_semantics.evidence_state == (
        CausalEvidenceState.SUPPORTED_UNDER_CURRENT_MODEL
    )


def test_old_briefing_root_payload_remains_backward_compatible() -> None:
    root = BriefingRootCause(
        causal_analysis_id="analysis:test",
        root_event_id="event:root",
        root_event_title="Deployment changed",
        root_event_source="kubernetes",
        causal_confidence=0.835,
        confidence_level="high",
        causal_change_event_id="event:target",
        causal_change_title="Pod failed",
        summary="Legacy briefing root.",
    )
    assert root.confidence_semantics is None


def test_new_briefing_root_exposes_honest_semantics() -> None:
    semantics = _enriched()[0].confidence_semantics
    root = BriefingRootCause(
        causal_analysis_id="analysis:test",
        root_event_id="event:root",
        root_event_title="Deployment changed",
        root_event_source="kubernetes",
        causal_confidence=0.835,
        confidence_level="high",
        confidence_semantics=semantics,
        causal_change_event_id="event:target",
        causal_change_title="Pod failed",
        summary="Current briefing root.",
    )
    assert root.confidence_semantics.calibrated_probability is None


def test_frontend_technical_view_has_no_percent_causal_confidence() -> None:
    source = _source("frontend/components/app/incident-briefing-technical.tsx")
    assert "formatConfidence" not in source
    assert "% confidence" not in source.casefold()
    assert "probability not calibrated" in source


def test_frontend_business_view_has_no_causal_probability_claim() -> None:
    source = _source("frontend/components/app/incident-briefing-business.tsx")
    assert "formatConfidence" not in source
    assert "Causal confidence is" not in source
    assert "Calibrated causal probability is unavailable" in source


def test_advanced_analysis_does_not_render_hypothesis_score_as_percent() -> None:
    source = _source("frontend/components/app/live-incident-workspace.tsx")
    assert "hypothesis.score * 100" not in source
    assert "heuristic rank" in source


def test_cli_does_not_mislabel_heuristic_rank_as_confidence() -> None:
    causal = _source("cli/src/topo_cli/commands/causal_rca.py")
    incidents = _source("cli/src/topo_cli/commands/incidents.py")
    assert '"CONF"' not in causal
    assert '"Causal Confidence"' not in incidents
    assert "Heuristic Ranking Score" in incidents


def test_machine_contract_covers_required_active_score_fields() -> None:
    fields = {item["field"] for item in _contract()["score_concepts"]}
    required = {
        "CausalHypothesis.score",
        "CausalHypothesis.confidence",
        "CausalHypothesis.confidence_level",
        "CausalHypothesis.confidence_semantics",
        "CausalAnalysisResponse.confidence_semantics",
        "Relationship.confidence",
        "EntityOwnershipResolution.confidence",
        "HistoricalIncidentMatch.similarity_score",
        "HistoricalActionSupport.score",
        "CurrentEvidenceStrength",
    }
    assert required <= fields


def test_no_ranking_weights_changed() -> None:
    source = _source("backend/app/services/causal_rca.py")
    for expression in (
        "candidate.score * 0.40",
        "topology_component * 25",
        "temporal_component * 15",
        ") * 10",
        "lineage_component * 10",
    ):
        assert expression in source


def test_no_causal_thresholds_changed() -> None:
    assert _confidence_level(0.75) == CausalConfidenceLevel.HIGH
    assert _confidence_level(0.50) == CausalConfidenceLevel.MEDIUM
    assert _confidence_level(0.4999) == CausalConfidenceLevel.LOW


def test_no_new_probability_calculation_exists() -> None:
    source = _source("backend/app/services/confidence_semantics.py")
    assert " / 100" not in source
    assert "calibrated_probability=" not in source


def test_no_logistic_sigmoid_or_softmax_transform_exists() -> None:
    source = _source("backend/app/services/confidence_semantics.py").casefold()
    assert all(word not in source for word in ("logistic", "sigmoid", "softmax"))


def test_no_evidence_count_score_is_added() -> None:
    source = _source("backend/app/services/confidence_semantics.py")
    assert "supporting - contradicting" not in source
    assert "supporting_count=" in source


def test_no_llm_scoring_is_added() -> None:
    source = _source("backend/app/services/confidence_semantics.py").casefold()
    assert all(word not in source for word in ("prompt", "model_name", "generated"))


def test_confidence_semantics_serialization_is_deterministic() -> None:
    first = _enriched(supporting=2, missing=1)[0].confidence_semantics
    second = _enriched(supporting=2, missing=1)[0].confidence_semantics
    assert first.model_dump_json() == second.model_dump_json()


def test_scenario_a_high_score_missing_evidence() -> None:
    analysis, hypothesis = _enriched(supporting=3, missing=1, score=88.0)
    assert hypothesis.score == 88.0
    assert analysis.confidence_semantics.evidence_completeness == CausalEvidenceCompleteness.PARTIAL
    assert analysis.confidence_semantics.calibrated_probability is None


def test_scenario_b_high_score_contradiction() -> None:
    analysis, hypothesis = _enriched(contradicting=1, score=88.0)
    assert hypothesis.score == 88.0
    assert analysis.confidence_semantics.evidence_state == CausalEvidenceState.CONTESTED


def test_scenario_c_two_close_hypotheses_are_only_ranked() -> None:
    first = _hypothesis(score=83.5, confidence=0.835, ledger=_ledger())
    second = first.model_copy(
        update={
            "hypothesis_id": "hypothesis:close",
            "rank": 2,
            "score": 81.0,
            "confidence": 0.81,
            "evidence_ledger": None,
        }
    )
    analysis = ensure_analysis_confidence_semantics(_analysis([first, second]))
    assert analysis.hypotheses[0].score > analysis.hypotheses[1].score
    assert all(item.confidence_semantics.calibrated_probability is None for item in analysis.hypotheses)


def test_scenario_d_no_supported_hypothesis_has_no_placeholder_number() -> None:
    semantics = ensure_analysis_confidence_semantics(_analysis([])).confidence_semantics
    assert semantics.evidence_state == CausalEvidenceState.INSUFFICIENT_EVIDENCE
    assert semantics.ranking_score is None
    assert semantics.legacy_confidence is None


def test_semantics_version_is_separate_from_algorithm_version() -> None:
    analysis, _ = _enriched()
    assert analysis.algorithm_version == "13c-causal-v1"
    assert analysis.confidence_semantics.semantics_version == CONFIDENCE_SEMANTICS_VERSION


def test_only_not_calibrated_status_is_advertised() -> None:
    assert list(CausalCalibrationStatus) == [CausalCalibrationStatus.NOT_CALIBRATED]
