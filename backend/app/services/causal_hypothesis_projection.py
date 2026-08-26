from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.models.causal_projection import (
    CAUSAL_HYPOTHESIS_PROJECTION_POLICY_VERSION,
    CausalHypothesisProjectionAudit,
    CausalHypothesisProjectionSummary,
    DiagnosticProjectionReason,
    SupportedProjectionReason,
)
from app.models.causal_rca import CausalHypothesis
from app.models.causal_support import CAUSAL_SUPPORT_GATE_POLICY_VERSION
from app.models.confidence_semantics import CausalEvidenceState


@dataclass(frozen=True)
class CausalHypothesisProjection:
    """One canonical evaluated set with lightweight projection references."""

    evaluated_hypotheses: tuple[CausalHypothesis, ...]
    diagnostic_hypothesis_ids: tuple[str, ...]
    supported_hypothesis_ids: tuple[str, ...]
    audit: tuple[CausalHypothesisProjectionAudit, ...]
    summary: CausalHypothesisProjectionSummary


def _causal_order_key(hypothesis: CausalHypothesis) -> tuple:
    """Preserve causal score ordering and make exact ties deterministic."""

    return (
        -hypothesis.score,
        hypothesis.root_event_id,
        hypothesis.target_event_id,
        hypothesis.hypothesis_id,
    )


def _is_support_qualified(hypothesis: CausalHypothesis) -> bool:
    gate = hypothesis.support_gate
    return bool(
        gate is not None
        and gate.policy_version == CAUSAL_SUPPORT_GATE_POLICY_VERSION
        and gate.support_state
        == CausalEvidenceState.SUPPORTED_UNDER_CURRENT_MODEL
    )


def project_causal_hypotheses(
    hypotheses: Sequence[CausalHypothesis],
    *,
    diagnostic_limit: int,
    supported_limit: int,
    policy_version: str = CAUSAL_HYPOTHESIS_PROJECTION_POLICY_VERSION,
) -> CausalHypothesisProjection:
    """Project only the already-bounded, fully evaluated AR-1 frontier.

    Evidence qualification happens before supported-output budgeting. The
    function performs no candidate discovery, scoring, relevance evaluation,
    or support classification.
    """

    if policy_version != CAUSAL_HYPOTHESIS_PROJECTION_POLICY_VERSION:
        raise ValueError(
            "Unsupported causal hypothesis projection policy version: "
            f"{policy_version}."
        )
    if diagnostic_limit < 1:
        raise ValueError("diagnostic_limit must be at least one.")
    if supported_limit < 1:
        raise ValueError("supported_limit must be at least one.")

    hypothesis_ids = [item.hypothesis_id for item in hypotheses]
    if len(hypothesis_ids) != len(set(hypothesis_ids)):
        raise ValueError("Evaluated hypothesis IDs must be unique.")

    ordered = sorted(hypotheses, key=_causal_order_key)
    canonical = tuple(
        hypothesis.model_copy(update={"rank": rank})
        for rank, hypothesis in enumerate(ordered, start=1)
    )
    diagnostic = canonical[:diagnostic_limit]
    support_qualified = tuple(
        hypothesis for hypothesis in canonical if _is_support_qualified(hypothesis)
    )
    supported = support_qualified[:supported_limit]

    diagnostic_rank = {
        hypothesis.hypothesis_id: rank
        for rank, hypothesis in enumerate(diagnostic, start=1)
    }
    supported_rank = {
        hypothesis.hypothesis_id: rank
        for rank, hypothesis in enumerate(supported, start=1)
    }
    support_qualified_ids = {
        hypothesis.hypothesis_id for hypothesis in support_qualified
    }

    audit: list[CausalHypothesisProjectionAudit] = []
    for hypothesis in canonical:
        hypothesis_id = hypothesis.hypothesis_id
        diagnostic_position = diagnostic_rank.get(hypothesis_id)
        supported_position = supported_rank.get(hypothesis_id)
        support_qualified_member = hypothesis_id in support_qualified_ids
        audit.append(
            CausalHypothesisProjectionAudit(
                hypothesis_id=hypothesis_id,
                diagnostic_projection_included=diagnostic_position is not None,
                diagnostic_projection_rank=diagnostic_position,
                diagnostic_projection_reason=(
                    DiagnosticProjectionReason.INCLUDED_BY_CAUSAL_ORDER
                    if diagnostic_position is not None
                    else DiagnosticProjectionReason.DIAGNOSTIC_CAP_REACHED
                ),
                supported_projection_included=supported_position is not None,
                supported_projection_rank=supported_position,
                supported_projection_reason=(
                    SupportedProjectionReason.INCLUDED_AFTER_SUPPORT_QUALIFICATION
                    if supported_position is not None
                    else (
                        SupportedProjectionReason.SUPPORTED_CAP_REACHED
                        if support_qualified_member
                        else SupportedProjectionReason.SUPPORT_GATE_NOT_SATISFIED
                    )
                ),
            )
        )

    cap_excluded_count = max(0, len(support_qualified) - supported_limit)
    summary = CausalHypothesisProjectionSummary(
        diagnostic_projection_limit=diagnostic_limit,
        supported_projection_limit=supported_limit,
        evaluated_hypothesis_count=len(canonical),
        diagnostic_projection_count=len(diagnostic),
        supported_projection_count=len(supported),
        support_qualified_hypothesis_count=len(support_qualified),
        projection_dropped_supported_count=0,
        supported_projection_cap_excluded_count=cap_excluded_count,
    )
    return CausalHypothesisProjection(
        evaluated_hypotheses=canonical,
        diagnostic_hypothesis_ids=tuple(
            hypothesis.hypothesis_id for hypothesis in diagnostic
        ),
        supported_hypothesis_ids=tuple(
            hypothesis.hypothesis_id for hypothesis in supported
        ),
        audit=tuple(audit),
        summary=summary,
    )
