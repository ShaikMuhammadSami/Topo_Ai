from __future__ import annotations

from collections.abc import Iterable

from app.models.causal_rca import (
    CausalEvidenceClaimType,
    CausalEvidenceLedger,
    CausalEvidenceLedgerItem,
)
from app.models.causal_relevance import (
    CandidateCausalRelevanceAudit,
    CausalPathSemantic,
    CausalRelevanceResolutionBasis,
    CausalRelevanceStatus,
    CausalTopologyPathState,
    LineageRelevanceBridgeState,
)
from app.models.causal_support import (
    CAUSAL_SUPPORT_GATE_POLICY_VERSION,
    CausalSupportGateAudit,
    CausalSupportGateState,
)
from app.models.confidence_semantics import (
    CausalEvidenceCompleteness,
    CausalEvidenceState,
)


INCIDENT_LEVEL_CLAIM_TYPES = frozenset(
    {CausalEvidenceClaimType.RUNTIME_FAILURE}
)

CANDIDATE_CONTEXT_CLAIM_TYPES = frozenset(
    {
        CausalEvidenceClaimType.SOURCE_CHANGE,
        CausalEvidenceClaimType.TEMPORAL_PRECEDENCE,
    }
)

CANDIDATE_LINKAGE_CLAIM_TYPES = frozenset(
    {
        CausalEvidenceClaimType.IDENTITY_RESOLUTION,
        CausalEvidenceClaimType.ENTITY_LINKAGE,
        CausalEvidenceClaimType.TOPOLOGY_PATH,
        CausalEvidenceClaimType.RELATIONSHIP_PROVENANCE,
        CausalEvidenceClaimType.ARTIFACT_PROVENANCE,
        CausalEvidenceClaimType.EVENT_LINEAGE,
    }
)


def _ordered_items(
    ledger: CausalEvidenceLedger | None,
) -> list[CausalEvidenceLedgerItem]:
    if ledger is None:
        return []
    return sorted(
        [
            *ledger.supporting,
            *ledger.contradicting,
            *ledger.missing,
        ],
        key=lambda item: (item.claim_type.value, item.evidence_id),
    )


def _claim_ids(
    items: Iterable[CausalEvidenceLedgerItem],
    claim_types: frozenset[CausalEvidenceClaimType],
) -> list[str]:
    return sorted(
        {
            item.evidence_id
            for item in items
            if item.claim_type in claim_types
        }
    )


def is_causal_relevance_supported(
    relevance: CandidateCausalRelevanceAudit,
) -> tuple[bool, str]:
    """Recognize only current relevance-policy success states.

    A direct same-entity result is valid without a positive hop count. Source
    candidates may keep a null candidate entity when an exact immutable-lineage
    anchor supplies the accepted incident-time topology path.
    """

    if relevance.relevance_status not in {
        CausalRelevanceStatus.DIRECT,
        CausalRelevanceStatus.SEMANTIC_PATH,
    }:
        return False, relevance.relevance_status.value
    if relevance.path_semantic in {
        CausalPathSemantic.STRUCTURAL_CONTEXT,
        CausalPathSemantic.UNSUPPORTED_UNKNOWN,
    }:
        return False, "unsupported_path_semantic"
    if relevance.topology_path_state != CausalTopologyPathState.SUPPORTED:
        return False, "topology_path_not_supported"
    if not relevance.affected_entity_id or not relevance.path_entity_ids:
        return False, "affected_topology_identity_missing"

    if relevance.resolution_basis == CausalRelevanceResolutionBasis.TOPOLOGY_ENTITY:
        if not relevance.candidate_entity_id:
            return False, "candidate_topology_identity_missing"
        return (
            True,
            "supported_direct_topology_identity"
            if relevance.relevance_status == CausalRelevanceStatus.DIRECT
            else "supported_semantic_incident_time_path",
        )

    if (
        relevance.resolution_basis
        == CausalRelevanceResolutionBasis.EXACT_IMMUTABLE_LINEAGE_ANCHOR
    ):
        if (
            relevance.bridge_state != LineageRelevanceBridgeState.VALID
            or not relevance.relevance_anchor_entity_id
            or relevance.bridge_source_change_id != relevance.candidate_event_id
        ):
            return False, "lineage_anchor_missing_or_invalid"
        return True, "supported_exact_immutable_lineage_anchor"

    return False, "relevance_resolution_basis_unresolved"


def _candidate_bound_linkage_items(
    ledger: CausalEvidenceLedger | None,
    *,
    candidate_event_id: str,
) -> list[CausalEvidenceLedgerItem]:
    if ledger is None:
        return []
    return sorted(
        (
            item
            for item in ledger.supporting
            if item.claim_type in CANDIDATE_LINKAGE_CLAIM_TYPES
            and item.hypothesis_id == ledger.hypothesis_id
            and candidate_event_id in item.change_event_ids
            and (
                item.snapshot_id is None
                or item.snapshot_id == ledger.snapshot_id
            )
        ),
        key=lambda item: (item.claim_type.value, item.evidence_id),
    )


def classify_causal_support(
    *,
    candidate_event_id: str,
    relevance: CandidateCausalRelevanceAudit,
    ledger: CausalEvidenceLedger | None,
    policy_version: str = CAUSAL_SUPPORT_GATE_POLICY_VERSION,
) -> CausalSupportGateAudit:
    """Classify categorical support without consulting numerical scores."""

    if policy_version != CAUSAL_SUPPORT_GATE_POLICY_VERSION:
        raise ValueError(
            "unsupported_causal_support_gate_policy: "
            f"'{policy_version}' is not recognized"
        )

    relevance_supported, relevance_reason = is_causal_relevance_supported(
        relevance
    )
    linkage_items = _candidate_bound_linkage_items(
        ledger,
        candidate_event_id=candidate_event_id,
    )
    linkage_supported = bool(linkage_items)
    all_items = _ordered_items(ledger)

    contradicting = len(ledger.contradicting) if ledger is not None else 0
    missing = len(ledger.missing) if ledger is not None else 0

    gates_satisfied = relevance_supported and linkage_supported
    if contradicting and missing:
        support_state = CausalEvidenceState.CONTESTED_WITH_GAPS
        support_reason = "contradictory_and_missing_evidence_present"
    elif contradicting:
        support_state = CausalEvidenceState.CONTESTED
        support_reason = "contradictory_evidence_present"
    elif missing:
        support_state = CausalEvidenceState.INCOMPLETE
        support_reason = "missing_expected_evidence_present"
    elif not gates_satisfied:
        support_state = (
            CausalEvidenceState.INSUFFICIENT_CANDIDATE_SPECIFIC_EVIDENCE
        )
        support_reason = "insufficient_candidate_specific_evidence"
    else:
        support_state = CausalEvidenceState.SUPPORTED_UNDER_CURRENT_MODEL
        support_reason = "candidate_specific_causal_linkage_supported"

    complete = (
        ledger is not None
        and missing == 0
        and gates_satisfied
    )
    evidence_completeness = (
        CausalEvidenceCompleteness.COMPLETE_FOR_CURRENT_MODEL
        if complete
        else (
            CausalEvidenceCompleteness.UNKNOWN
            if ledger is None
            else CausalEvidenceCompleteness.PARTIAL
        )
    )

    return CausalSupportGateAudit(
        policy_version=policy_version,
        relevance_gate_state=(
            CausalSupportGateState.SATISFIED
            if relevance_supported
            else CausalSupportGateState.UNSATISFIED
        ),
        relevance_gate_reason=relevance_reason,
        candidate_linkage_gate_state=(
            CausalSupportGateState.SATISFIED
            if linkage_supported
            else CausalSupportGateState.UNSATISFIED
        ),
        candidate_linkage_gate_reason=(
            "candidate_specific_linkage_evidence_present"
            if linkage_supported
            else "no_candidate_specific_linkage_evidence"
        ),
        candidate_linkage_claim_ids=[
            item.evidence_id for item in linkage_items
        ],
        candidate_linkage_claim_types=sorted(
            {item.claim_type.value for item in linkage_items}
        ),
        incident_level_claim_ids=_claim_ids(
            all_items,
            INCIDENT_LEVEL_CLAIM_TYPES,
        ),
        candidate_context_claim_ids=_claim_ids(
            all_items,
            CANDIDATE_CONTEXT_CLAIM_TYPES,
        ),
        support_state=support_state,
        support_reason=support_reason,
        evidence_completeness=evidence_completeness,
    )
