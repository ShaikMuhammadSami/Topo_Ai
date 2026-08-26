from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.models.causal_candidates import (
    CAUSAL_CANDIDATE_ADMISSION_POLICY_VERSION,
    CAUSAL_EVALUATION_BUDGET_POLICY_VERSION,
    CandidateAdmissionBasis,
    CausalCandidateEvaluationAudit,
    CausalCandidateEligibility,
    CausalCandidateSelectionAudit,
    CausalEvaluationBudgetAudit,
    CausalEvaluationBudgetReason,
    CausalEvaluationBudgetState,
    CausalEvaluationSelectionBasis,
    LineageAdmissionReason,
    LineageAdmissionState,
)
from app.models.change_events import IncidentChangeCandidate


# SC-2 admits at most one canonical source change for an incident: its
# bounded provider lookup must resolve to one repository/revision and its
# bounded source lookup must resolve to one source event. This value records
# that upstream proof; it is not used to truncate the protected set here.
SC2_EXACT_LINEAGE_CANDIDATE_MAX = 1


@dataclass(frozen=True)
class CausalCandidateEvaluationFrontier:
    candidates: tuple[IncidentChangeCandidate, ...]
    audit: tuple[CausalCandidateEvaluationAudit, ...]
    budget: CausalEvaluationBudgetAudit


def _require_supported_policy(policy_version: str) -> None:
    if policy_version != CAUSAL_EVALUATION_BUDGET_POLICY_VERSION:
        raise ValueError(
            "Unsupported causal evaluation budget policy version: "
            f"{policy_version}."
        )


def _is_exact_lineage_admitted(
    candidate: IncidentChangeCandidate,
    selection_audit: CausalCandidateSelectionAudit,
) -> bool:
    """Consume the already-established SC-2 result without re-admission."""

    return (
        candidate.candidate_admission_policy_version
        == CAUSAL_CANDIDATE_ADMISSION_POLICY_VERSION
        and candidate.lineage_admission_state == LineageAdmissionState.ADMITTED
        and candidate.lineage_admission_reason
        == LineageAdmissionReason.EXACT_IMMUTABLE_LINEAGE
        and CandidateAdmissionBasis.EXACT_IMMUTABLE_LINEAGE
        in candidate.admission_basis
        and selection_audit.eligibility
        in {
            CausalCandidateEligibility.PRIMARY_ELIGIBLE,
            CausalCandidateEligibility.FALLBACK_ELIGIBLE,
        }
    )


def build_causal_candidate_evaluation_frontier(
    candidates: Sequence[IncidentChangeCandidate],
    *,
    ordinary_candidates: Sequence[IncidentChangeCandidate],
    ordinary_selection_audit: Sequence[CausalCandidateSelectionAudit],
    ordinary_shortlist_limit: int,
    policy_version: str = CAUSAL_EVALUATION_BUDGET_POLICY_VERSION,
) -> CausalCandidateEvaluationFrontier:
    """Union the ordinary shortlist with candidates already admitted by SC-2.

    The function neither discovers lineage nor scores, ranks, or truncates the
    protected set. Ordinary candidates retain the existing selection order;
    outside-shortlist protected candidates use stable event-ID ordering.
    """

    _require_supported_policy(policy_version)
    if ordinary_shortlist_limit < 1:
        raise ValueError("ordinary_shortlist_limit must be at least one.")

    considered = list(candidates)
    by_event_id: dict[str, IncidentChangeCandidate] = {}
    raw_rank_by_event_id: dict[str, int] = {}
    for raw_rank, candidate in enumerate(considered, start=1):
        event_id = candidate.event.event_id
        if event_id in by_event_id:
            raise ValueError(f"Duplicate causal candidate event ID: {event_id}.")
        by_event_id[event_id] = candidate
        raw_rank_by_event_id[event_id] = raw_rank

    selection_audit_by_event_id = {
        item.event_id: item for item in ordinary_selection_audit
    }
    if set(selection_audit_by_event_id) != set(by_event_id):
        raise ValueError(
            "Candidate-selection audit must cover the complete raw candidate set."
        )

    ordinary_ids: list[str] = []
    for candidate in ordinary_candidates:
        event_id = candidate.event.event_id
        if event_id not in by_event_id:
            raise ValueError(
                "Ordinary causal candidate is absent from the raw candidate "
                f"set: {event_id}."
            )
        if event_id not in ordinary_ids:
            ordinary_ids.append(event_id)

    ordinary_id_set = set(ordinary_ids)
    protected_ids = {
        candidate.event.event_id
        for candidate in considered
        if _is_exact_lineage_admitted(
            candidate,
            selection_audit_by_event_id[candidate.event.event_id],
        )
    }
    protected_outside_ordinary = sorted(protected_ids - ordinary_id_set)
    frontier_ids = [*ordinary_ids, *protected_outside_ordinary]
    frontier_position = {
        event_id: position
        for position, event_id in enumerate(frontier_ids, start=1)
    }

    audit: list[CausalCandidateEvaluationAudit] = []
    for candidate in considered:
        event_id = candidate.event.event_id
        ordinary_member = event_id in ordinary_id_set
        protected_member = event_id in protected_ids
        bases: list[CausalEvaluationSelectionBasis] = []
        if ordinary_member:
            bases.append(CausalEvaluationSelectionBasis.ORDINARY_RAW_TOP_K)
        if protected_member:
            bases.append(
                CausalEvaluationSelectionBasis
                .EVIDENCE_PRESERVED_EXACT_IMMUTABLE_LINEAGE
            )
        selected = bool(bases)
        audit.append(
            CausalCandidateEvaluationAudit(
                event_id=event_id,
                raw_rank=raw_rank_by_event_id[event_id],
                raw_score=candidate.score,
                selected_for_evaluation=selected,
                evaluation_selection_bases=bases,
                ordinary_shortlist_member=ordinary_member,
                evidence_preserved_member=protected_member,
                evaluation_frontier_position=frontier_position.get(event_id),
                exclusion_reason=(None if selected else "outside_evaluation_frontier"),
                policy_version=policy_version,
            )
        )

    budget = CausalEvaluationBudgetAudit(
        policy_version=policy_version,
        ordinary_shortlist_limit=ordinary_shortlist_limit,
        ordinary_shortlist_count=len(ordinary_ids),
        evidence_preserved_candidate_count=len(protected_ids),
        evaluation_frontier_size=len(frontier_ids),
        evaluation_budget_state=CausalEvaluationBudgetState.BOUNDED,
        evaluation_budget_reason=(
            CausalEvaluationBudgetReason.ORDINARY_UNION_EXACT_SC2_LINEAGE
        ),
    )
    return CausalCandidateEvaluationFrontier(
        candidates=tuple(by_event_id[event_id] for event_id in frontier_ids),
        audit=tuple(audit),
        budget=budget,
    )
