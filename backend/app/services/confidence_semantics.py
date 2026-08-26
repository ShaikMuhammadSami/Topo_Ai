from __future__ import annotations

from app.models.causal_rca import (
    CausalAnalysisResponse,
    CausalHypothesis,
)
from app.models.confidence_semantics import (
    CausalConfidenceSemantics,
    CausalEvidenceCompleteness,
    CausalEvidenceState,
    CausalEvidenceSummary,
    CausalRankingStrength,
)
from app.models.causal_support import CAUSAL_SUPPORT_GATE_POLICY_VERSION


def _evidence_counts(
    hypothesis: CausalHypothesis,
) -> tuple[int, int, int]:
    ledger = hypothesis.evidence_ledger
    if ledger is None:
        return 0, 0, 0
    return (
        len(ledger.supporting),
        len(ledger.contradicting),
        len(ledger.missing),
    )


def causal_confidence_semantics(
    hypothesis: CausalHypothesis,
    *,
    ranking_algorithm_version: str,
) -> CausalConfidenceSemantics:
    supporting, contradicting, missing = _evidence_counts(hypothesis)
    ledger_available = hypothesis.evidence_ledger is not None
    support_gate = hypothesis.support_gate

    if support_gate is not None:
        if support_gate.policy_version != CAUSAL_SUPPORT_GATE_POLICY_VERSION:
            raise ValueError(
                "unsupported_causal_support_gate_policy: "
                f"'{support_gate.policy_version}' is not recognized"
            )
        completeness = support_gate.evidence_completeness
        evidence_state = support_gate.support_state
    elif not ledger_available:
        completeness = CausalEvidenceCompleteness.UNKNOWN
        evidence_state = CausalEvidenceState.LEGACY_UNKNOWN
    elif contradicting and missing:
        completeness = CausalEvidenceCompleteness.PARTIAL
        evidence_state = CausalEvidenceState.CONTESTED_WITH_GAPS
    elif contradicting:
        completeness = CausalEvidenceCompleteness.COMPLETE_FOR_CURRENT_MODEL
        evidence_state = CausalEvidenceState.CONTESTED
    elif missing:
        completeness = CausalEvidenceCompleteness.PARTIAL
        evidence_state = CausalEvidenceState.INCOMPLETE
    else:
        completeness = CausalEvidenceCompleteness.COMPLETE_FOR_CURRENT_MODEL
        evidence_state = CausalEvidenceState.SUPPORTED_UNDER_CURRENT_MODEL

    return CausalConfidenceSemantics(
        ranking_algorithm_version=ranking_algorithm_version,
        ranking_score=hypothesis.score,
        ranking_strength=CausalRankingStrength(
            hypothesis.confidence_level.value
        ),
        legacy_confidence=hypothesis.confidence,
        evidence_summary=CausalEvidenceSummary(
            supporting_count=supporting,
            contradicting_count=contradicting,
            missing_count=missing,
        ),
        evidence_completeness=completeness,
        evidence_state=evidence_state,
        interpretation=(
            "Relative deterministic strength under the current 13C "
            "heuristic. It ranks independent causal hypotheses; it is "
            "not a probability of correctness."
        ),
    )


def insufficient_evidence_semantics(
    *,
    ranking_algorithm_version: str,
) -> CausalConfidenceSemantics:
    return CausalConfidenceSemantics(
        ranking_algorithm_version=ranking_algorithm_version,
        evidence_summary=CausalEvidenceSummary(
            supporting_count=0,
            contradicting_count=0,
            missing_count=0,
        ),
        evidence_completeness=CausalEvidenceCompleteness.UNKNOWN,
        evidence_state=CausalEvidenceState.INSUFFICIENT_EVIDENCE,
        interpretation=(
            "Insufficient evidence: no supported causal hypothesis was "
            "ranked. No calibrated probability is available."
        ),
    )


def ensure_analysis_confidence_semantics(
    analysis: CausalAnalysisResponse,
) -> CausalAnalysisResponse:
    """Add TC-5 interpretation in memory without rewriting old records."""

    for hypothesis in analysis.hypotheses:
        if hypothesis.confidence_semantics is None:
            hypothesis.confidence_semantics = causal_confidence_semantics(
                hypothesis,
                ranking_algorithm_version=analysis.algorithm_version,
            )

    top = analysis.top_hypothesis
    if top is not None and top.confidence_semantics is None:
        top.confidence_semantics = causal_confidence_semantics(
            top,
            ranking_algorithm_version=analysis.algorithm_version,
        )

    if analysis.confidence_semantics is None:
        analysis.confidence_semantics = (
            top.confidence_semantics
            if top is not None
            else insufficient_evidence_semantics(
                ranking_algorithm_version=analysis.algorithm_version,
            )
        )
    return analysis
