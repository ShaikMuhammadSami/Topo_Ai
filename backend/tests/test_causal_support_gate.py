from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

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
from app.models.causal_relevance import (
    CAUSAL_RELEVANCE_POLICY_VERSION,
    CandidateCausalRelevanceAudit,
    CausalPathSemantic,
    CausalRelevanceResolutionBasis,
    CausalRelevanceStatus,
    CausalTopologyPathState,
    LineageRelevanceBridgeState,
)
from app.models.causal_support import (
    CAUSAL_SUPPORT_GATE_POLICY_VERSION,
    CausalSupportGateState,
)
from app.models.confidence_semantics import (
    CausalEvidenceCompleteness,
    CausalEvidenceState,
)
from app.services.causal_rca import (
    _stable_id,
)
from app.services.causal_support_gate import (
    CANDIDATE_CONTEXT_CLAIM_TYPES,
    CANDIDATE_LINKAGE_CLAIM_TYPES,
    INCIDENT_LEVEL_CLAIM_TYPES,
    classify_causal_support,
    is_causal_relevance_supported,
)
from app.services.confidence_semantics import (
    ensure_analysis_confidence_semantics,
)


ROOT = Path(__file__).resolve().parents[2]
HYPOTHESIS_ID = "hypothesis:ar2"
CANDIDATE_ID = "change-event:ar2-candidate"
OTHER_CANDIDATE_ID = "change-event:other-candidate"
SNAPSHOT_ID = "snapshot:ar2"
SOURCE_ENTITY_ID = "entity:deployment:payments"
AFFECTED_ENTITY_ID = "entity:pod:payments"
RELATIONSHIP_ID = "relationship:deployment-pod"


def _reference(reference_type: str, reference_id: str):
    return CausalEvidenceSourceReference(
        reference_type=reference_type,
        reference_id=reference_id,
        source_system="test",
    )


def _claim(
    claim_type: CausalEvidenceClaimType,
    *,
    stance: CausalEvidenceStance = CausalEvidenceStance.SUPPORTING,
    candidate_event_id: str = CANDIDATE_ID,
    suffix: str = "0",
) -> CausalEvidenceLedgerItem:
    common = {
        "evidence_id": f"evidence:{claim_type.value}:{stance.value}:{suffix}",
        "hypothesis_id": HYPOTHESIS_ID,
        "stance": stance,
        "claim_type": claim_type,
        "summary": "AR-2 deterministic fixture claim.",
        "reason": "Exercises categorical support only.",
        "source_category": CausalEvidenceSourceCategory.CHANGE,
        "source_references": [_reference("change_event", candidate_event_id)],
        "quality": CausalEvidenceQuality.DIRECT,
        "why_it_matters": "Separates context from causal linkage.",
        "change_event_ids": [candidate_event_id],
    }
    if stance == CausalEvidenceStance.MISSING:
        common["expectation_basis"] = "Fixture establishes a material expectation."

    if claim_type == CausalEvidenceClaimType.RUNTIME_FAILURE:
        common.update(
            source_category=CausalEvidenceSourceCategory.SIGNAL,
            source_references=[_reference("signal", "signal:ar2")],
            signal_ids=["signal:ar2"],
            change_event_ids=[],
        )
    elif claim_type == CausalEvidenceClaimType.TEMPORAL_PRECEDENCE:
        common.update(
            source_category=CausalEvidenceSourceCategory.TEMPORAL,
            incident_boundary_at="2026-08-26T12:00:00+00:00",
        )
    elif claim_type == CausalEvidenceClaimType.ENTITY_LINKAGE:
        common.update(
            source_category=CausalEvidenceSourceCategory.IDENTITY,
            entity_ids=[SOURCE_ENTITY_ID],
            snapshot_id=SNAPSHOT_ID,
        )
    elif claim_type == CausalEvidenceClaimType.TOPOLOGY_PATH:
        common.update(
            source_category=CausalEvidenceSourceCategory.TOPOLOGY,
            entity_ids=[SOURCE_ENTITY_ID, AFFECTED_ENTITY_ID],
            relationship_ids=[RELATIONSHIP_ID],
            snapshot_id=SNAPSHOT_ID,
        )
    elif claim_type == CausalEvidenceClaimType.RELATIONSHIP_PROVENANCE:
        common.update(
            source_category=CausalEvidenceSourceCategory.TOPOLOGY,
            relationship_ids=[RELATIONSHIP_ID],
            snapshot_id=SNAPSHOT_ID,
        )
    elif claim_type == CausalEvidenceClaimType.ARTIFACT_PROVENANCE:
        common.update(
            source_category=CausalEvidenceSourceCategory.ARTIFACT,
            entity_ids=[SOURCE_ENTITY_ID, "artifact:image:ar2"],
            relationship_ids=[RELATIONSHIP_ID],
            snapshot_id=SNAPSHOT_ID,
        )
    elif claim_type == CausalEvidenceClaimType.EVENT_LINEAGE:
        common.update(
            source_category=CausalEvidenceSourceCategory.LINEAGE,
            change_event_ids=["change-event:predecessor", candidate_event_id],
        )

    return CausalEvidenceLedgerItem(**common)


def _ledger(
    supporting: list[CausalEvidenceClaimType],
    *,
    contradicting: list[CausalEvidenceClaimType] | None = None,
    missing: list[CausalEvidenceClaimType] | None = None,
    linkage_candidate_id: str = CANDIDATE_ID,
) -> CausalEvidenceLedger:
    return CausalEvidenceLedger(
        hypothesis_id=HYPOTHESIS_ID,
        snapshot_id=SNAPSHOT_ID,
        supporting=[
            _claim(
                claim_type,
                candidate_event_id=(
                    linkage_candidate_id
                    if claim_type in CANDIDATE_LINKAGE_CLAIM_TYPES
                    else CANDIDATE_ID
                ),
                suffix=claim_type.value,
            )
            for index, claim_type in enumerate(supporting)
        ],
        contradicting=[
            _claim(
                claim_type,
                stance=CausalEvidenceStance.CONTRADICTING,
                suffix=claim_type.value,
            )
            for index, claim_type in enumerate(contradicting or [])
        ],
        missing=[
            _claim(
                claim_type,
                stance=CausalEvidenceStance.MISSING,
                suffix=claim_type.value,
            )
            for index, claim_type in enumerate(missing or [])
        ],
    )


def _relevance(
    *,
    status: CausalRelevanceStatus = CausalRelevanceStatus.SEMANTIC_PATH,
    semantic: CausalPathSemantic = CausalPathSemantic.CONTROL_OWNERSHIP,
    basis: CausalRelevanceResolutionBasis = (
        CausalRelevanceResolutionBasis.TOPOLOGY_ENTITY
    ),
    candidate_entity_id: str | None = SOURCE_ENTITY_ID,
    topology_path_state: CausalTopologyPathState | None = None,
) -> CandidateCausalRelevanceAudit:
    supported = status in {
        CausalRelevanceStatus.DIRECT,
        CausalRelevanceStatus.SEMANTIC_PATH,
    }
    if topology_path_state is None:
        topology_path_state = (
            CausalTopologyPathState.SUPPORTED
            if supported
            else (
                CausalTopologyPathState.NOT_EVALUATED
                if status
                in {
                    CausalRelevanceStatus.IDENTITY_UNRESOLVED,
                    CausalRelevanceStatus.AMBIGUOUS,
                }
                else CausalTopologyPathState.UNSUPPORTED
            )
        )
    lineage = basis == CausalRelevanceResolutionBasis.EXACT_IMMUTABLE_LINEAGE_ANCHOR
    direct = status == CausalRelevanceStatus.DIRECT
    return CandidateCausalRelevanceAudit(
        candidate_event_id=CANDIDATE_ID,
        candidate_entity_id=None if lineage else candidate_entity_id,
        affected_entity_id=AFFECTED_ENTITY_ID,
        relevance_policy_version=CAUSAL_RELEVANCE_POLICY_VERSION,
        resolution_basis=basis,
        relevance_anchor_entity_id=("artifact:image:ar2" if lineage else None),
        relevance_anchor_kind=("ContainerImage" if lineage else None),
        bridge_state=(
            LineageRelevanceBridgeState.VALID
            if lineage
            else LineageRelevanceBridgeState.NOT_APPLICABLE
        ),
        bridge_reason=("exact_immutable_lineage_anchor" if lineage else None),
        bridge_source_change_id=(CANDIDATE_ID if lineage else None),
        bridge_image_digest=("sha256:" + "a" * 64 if lineage else None),
        bridge_score=(0.0 if lineage else None),
        topology_path_state=topology_path_state,
        relevance_status=status,
        path_semantic=(CausalPathSemantic.DIRECT_ENTITY if direct else semantic),
        path_entity_ids=(
            [AFFECTED_ENTITY_ID]
            if direct
            else ["artifact:image:ar2" if lineage else SOURCE_ENTITY_ID, AFFECTED_ENTITY_ID]
        ),
        path_relationship_ids=([] if direct else [RELATIONSHIP_ID]),
        path_predicates=([] if direct else ["owns"]),
        path_hops=(0 if direct else 1),
        topology_component=(1.0 if direct else (0.85 if supported else 0.0)),
        reason="AR-2 deterministic relevance fixture.",
    )


def _classify(
    ledger: CausalEvidenceLedger,
    *,
    relevance: CandidateCausalRelevanceAudit | None = None,
):
    return classify_causal_support(
        candidate_event_id=CANDIDATE_ID,
        relevance=relevance or _relevance(),
        ledger=ledger,
    )


def _hypothesis(*, score: float, gate) -> CausalHypothesis:
    return CausalHypothesis(
        hypothesis_id=HYPOTHESIS_ID,
        rank=1,
        root_event_id=CANDIDATE_ID,
        root_source="github",
        root_title="Candidate source change",
        target_event_id=CANDIDATE_ID,
        target_title="Candidate source change",
        affected_entity_id=AFFECTED_ENTITY_ID,
        score=score,
        confidence=score / 100,
        confidence_level=CausalConfidenceLevel.HIGH,
        summary="AR-2 score-independence fixture.",
        evidence_ledger=_ledger(
            [
                CausalEvidenceClaimType.SOURCE_CHANGE,
                CausalEvidenceClaimType.TEMPORAL_PRECEDENCE,
                CausalEvidenceClaimType.RUNTIME_FAILURE,
            ]
        ),
        support_gate=gate,
    )


def _analysis(hypothesis: CausalHypothesis) -> CausalAnalysisResponse:
    return CausalAnalysisResponse(
        analysis_id="causal-analysis:ar2",
        incident_id="incident:ar2",
        incident_title="AR-2 incident",
        incident_time="2026-08-26T12:00:00+00:00",
        topology_snapshot_id=SNAPSHOT_ID,
        algorithm_version="13c-causal-v1",
        support_policy_version=CAUSAL_SUPPORT_GATE_POLICY_VERSION,
        generated_at="2026-08-26T12:01:00+00:00",
        parameters={},
        candidate_count=1,
        node_count=0,
        edge_count=0,
        evidence_count=0,
        hypothesis_count=1,
        top_hypothesis=hypothesis,
        hypotheses=[hypothesis],
    )


def test_temporal_only_distractor_is_rejected_without_mutating_tc4() -> None:
    ledger = _ledger(
        [
            CausalEvidenceClaimType.RUNTIME_FAILURE,
            CausalEvidenceClaimType.SOURCE_CHANGE,
            CausalEvidenceClaimType.TEMPORAL_PRECEDENCE,
        ]
    )
    before = ledger.model_dump_json()
    audit = _classify(
        ledger,
        relevance=_relevance(
            status=CausalRelevanceStatus.IDENTITY_UNRESOLVED,
            semantic=CausalPathSemantic.UNSUPPORTED_UNKNOWN,
            basis=CausalRelevanceResolutionBasis.UNRESOLVED,
            candidate_entity_id=None,
        ),
    )

    assert audit.support_state == (
        CausalEvidenceState.INSUFFICIENT_CANDIDATE_SPECIFIC_EVIDENCE
    )
    assert audit.support_reason == "insufficient_candidate_specific_evidence"
    assert audit.relevance_gate_state == CausalSupportGateState.UNSATISFIED
    assert audit.candidate_linkage_gate_state == CausalSupportGateState.UNSATISFIED
    assert audit.evidence_completeness == CausalEvidenceCompleteness.PARTIAL
    assert audit.candidate_linkage_claim_ids == []
    assert len(audit.incident_level_claim_ids) == 1
    assert len(audit.candidate_context_claim_ids) == 2
    assert (len(ledger.supporting), len(ledger.contradicting), len(ledger.missing)) == (
        3,
        0,
        0,
    )
    assert ledger.model_dump_json() == before


@pytest.mark.parametrize(
    "status",
    [
        CausalRelevanceStatus.IDENTITY_UNRESOLVED,
        CausalRelevanceStatus.NO_SUPPORTED_PATH,
        CausalRelevanceStatus.AMBIGUOUS,
    ],
)
def test_unresolved_relevance_states_cannot_be_supported(status) -> None:
    audit = _classify(
        _ledger([CausalEvidenceClaimType.TOPOLOGY_PATH]),
        relevance=_relevance(
            status=status,
            semantic=CausalPathSemantic.UNSUPPORTED_UNKNOWN,
            basis=CausalRelevanceResolutionBasis.UNRESOLVED,
            candidate_entity_id=None,
        ),
    )
    assert audit.relevance_gate_state == CausalSupportGateState.UNSATISFIED
    assert audit.support_state != CausalEvidenceState.SUPPORTED_UNDER_CURRENT_MODEL
    assert audit.support_state != CausalEvidenceState.CONTESTED


def test_unsupported_path_semantic_fails_even_with_success_status() -> None:
    supported, reason = is_causal_relevance_supported(
        _relevance(semantic=CausalPathSemantic.UNSUPPORTED_UNKNOWN)
    )
    assert supported is False
    assert reason == "unsupported_path_semantic"


@pytest.mark.parametrize(
    "claims",
    [
        [CausalEvidenceClaimType.RUNTIME_FAILURE],
        [CausalEvidenceClaimType.SOURCE_CHANGE],
        [CausalEvidenceClaimType.TEMPORAL_PRECEDENCE],
        [
            CausalEvidenceClaimType.RUNTIME_FAILURE,
            CausalEvidenceClaimType.SOURCE_CHANGE,
            CausalEvidenceClaimType.TEMPORAL_PRECEDENCE,
        ],
    ],
)
def test_incident_and_candidate_context_claims_do_not_satisfy_linkage(claims) -> None:
    audit = _classify(_ledger(claims))
    assert audit.relevance_gate_state == CausalSupportGateState.SATISFIED
    assert audit.candidate_linkage_gate_state == CausalSupportGateState.UNSATISFIED
    assert audit.support_state == (
        CausalEvidenceState.INSUFFICIENT_CANDIDATE_SPECIFIC_EVIDENCE
    )


@pytest.mark.parametrize(
    "claim_type",
    [
        CausalEvidenceClaimType.ENTITY_LINKAGE,
        CausalEvidenceClaimType.TOPOLOGY_PATH,
        CausalEvidenceClaimType.RELATIONSHIP_PROVENANCE,
        CausalEvidenceClaimType.ARTIFACT_PROVENANCE,
        CausalEvidenceClaimType.EVENT_LINEAGE,
    ],
)
def test_candidate_bound_linkage_claims_can_satisfy_gate(claim_type) -> None:
    audit = _classify(_ledger([claim_type]))
    assert audit.candidate_linkage_gate_state == CausalSupportGateState.SATISFIED
    assert audit.candidate_linkage_claim_types == [claim_type.value]
    assert audit.support_state == CausalEvidenceState.SUPPORTED_UNDER_CURRENT_MODEL


def test_linkage_claim_for_another_candidate_is_ignored() -> None:
    audit = _classify(
        _ledger(
            [CausalEvidenceClaimType.TOPOLOGY_PATH],
            linkage_candidate_id=OTHER_CANDIDATE_ID,
        )
    )
    assert audit.candidate_linkage_claim_ids == []
    assert audit.support_state == (
        CausalEvidenceState.INSUFFICIENT_CANDIDATE_SPECIFIC_EVIDENCE
    )


def test_same_entity_zero_hop_relevance_remains_supportable() -> None:
    relevance = _relevance(
        status=CausalRelevanceStatus.DIRECT,
        semantic=CausalPathSemantic.DIRECT_ENTITY,
        candidate_entity_id=AFFECTED_ENTITY_ID,
    )
    audit = _classify(
        _ledger([CausalEvidenceClaimType.ENTITY_LINKAGE]),
        relevance=relevance,
    )
    assert relevance.path_hops == 0
    assert audit.relevance_gate_reason == "supported_direct_topology_identity"
    assert audit.support_state == CausalEvidenceState.SUPPORTED_UNDER_CURRENT_MODEL


def test_exact_lineage_anchor_with_null_candidate_entity_remains_supportable() -> None:
    relevance = _relevance(
        basis=CausalRelevanceResolutionBasis.EXACT_IMMUTABLE_LINEAGE_ANCHOR,
        candidate_entity_id=None,
    )
    audit = _classify(
        _ledger(
            [
                CausalEvidenceClaimType.TOPOLOGY_PATH,
                CausalEvidenceClaimType.RELATIONSHIP_PROVENANCE,
            ]
        ),
        relevance=relevance,
    )
    assert relevance.candidate_entity_id is None
    assert relevance.topology_component == 0.85
    assert audit.relevance_gate_reason == "supported_exact_immutable_lineage_anchor"
    assert audit.support_state == CausalEvidenceState.SUPPORTED_UNDER_CURRENT_MODEL


def test_golden_lineage_five_claim_ledger_remains_unchanged_and_supported() -> None:
    ledger = _ledger(
        [
            CausalEvidenceClaimType.RELATIONSHIP_PROVENANCE,
            CausalEvidenceClaimType.RUNTIME_FAILURE,
            CausalEvidenceClaimType.SOURCE_CHANGE,
            CausalEvidenceClaimType.TEMPORAL_PRECEDENCE,
            CausalEvidenceClaimType.TOPOLOGY_PATH,
        ]
    )
    before = ledger.model_dump_json()
    audit = _classify(
        ledger,
        relevance=_relevance(
            basis=CausalRelevanceResolutionBasis.EXACT_IMMUTABLE_LINEAGE_ANCHOR,
            candidate_entity_id=None,
        ),
    )
    assert (len(ledger.supporting), len(ledger.contradicting), len(ledger.missing)) == (
        5,
        0,
        0,
    )
    assert audit.support_state == CausalEvidenceState.SUPPORTED_UNDER_CURRENT_MODEL
    assert audit.evidence_completeness == (
        CausalEvidenceCompleteness.COMPLETE_FOR_CURRENT_MODEL
    )
    assert ledger.model_dump_json() == before


def test_topology_native_candidate_needs_no_immutable_lineage() -> None:
    relevance = _relevance()
    audit = _classify(
        _ledger([CausalEvidenceClaimType.TOPOLOGY_PATH]),
        relevance=relevance,
    )
    assert relevance.resolution_basis == CausalRelevanceResolutionBasis.TOPOLOGY_ENTITY
    assert relevance.relevance_anchor_entity_id is None
    assert audit.support_state == CausalEvidenceState.SUPPORTED_UNDER_CURRENT_MODEL


def test_actual_contradiction_remains_contested() -> None:
    audit = _classify(
        _ledger(
            [CausalEvidenceClaimType.TOPOLOGY_PATH],
            contradicting=[CausalEvidenceClaimType.TEMPORAL_PRECEDENCE],
        )
    )
    assert audit.support_state == CausalEvidenceState.CONTESTED
    assert audit.support_reason == "contradictory_evidence_present"
    assert audit.evidence_completeness == (
        CausalEvidenceCompleteness.COMPLETE_FOR_CURRENT_MODEL
    )


def test_missing_evidence_remains_incomplete_and_is_not_fabricated() -> None:
    ledger = _ledger(
        [CausalEvidenceClaimType.ENTITY_LINKAGE],
        missing=[CausalEvidenceClaimType.TOPOLOGY_PATH],
    )
    before = ledger.model_dump_json()
    audit = _classify(ledger)
    assert audit.support_state == CausalEvidenceState.INCOMPLETE
    assert audit.evidence_completeness == CausalEvidenceCompleteness.PARTIAL
    assert ledger.model_dump_json() == before


def test_unknown_support_policy_fails_safely() -> None:
    with pytest.raises(ValueError, match="unsupported_causal_support_gate_policy"):
        classify_causal_support(
            candidate_event_id=CANDIDATE_ID,
            relevance=_relevance(),
            ledger=_ledger([CausalEvidenceClaimType.TOPOLOGY_PATH]),
            policy_version="causal-support-gate-unknown",
        )


def test_claim_input_order_does_not_change_gate_audit() -> None:
    claims = [
        CausalEvidenceClaimType.RUNTIME_FAILURE,
        CausalEvidenceClaimType.TOPOLOGY_PATH,
        CausalEvidenceClaimType.SOURCE_CHANGE,
        CausalEvidenceClaimType.RELATIONSHIP_PROVENANCE,
    ]
    first = _classify(_ledger(claims))
    second = _classify(_ledger(list(reversed(claims))))
    assert first.model_dump_json() == second.model_dump_json()


def test_high_numeric_score_cannot_bypass_support_gate() -> None:
    ledger = _ledger(
        [
            CausalEvidenceClaimType.RUNTIME_FAILURE,
            CausalEvidenceClaimType.SOURCE_CHANGE,
            CausalEvidenceClaimType.TEMPORAL_PRECEDENCE,
        ]
    )
    gate = _classify(
        ledger,
        relevance=_relevance(
            status=CausalRelevanceStatus.IDENTITY_UNRESOLVED,
            semantic=CausalPathSemantic.UNSUPPORTED_UNKNOWN,
            basis=CausalRelevanceResolutionBasis.UNRESOLVED,
            candidate_entity_id=None,
        ),
    )
    hypothesis = _hypothesis(score=99.0, gate=gate)
    enriched = ensure_analysis_confidence_semantics(_analysis(hypothesis))
    semantics = enriched.hypotheses[0].confidence_semantics
    assert hypothesis.score == 99.0
    assert semantics.evidence_state == (
        CausalEvidenceState.INSUFFICIENT_CANDIDATE_SPECIFIC_EVIDENCE
    )
    assert enriched.top_hypothesis is hypothesis
    assert [
        item
        for item in enriched.hypotheses
        if item.confidence_semantics.evidence_state
        == CausalEvidenceState.SUPPORTED_UNDER_CURRENT_MODEL
    ] == []


def test_five_high_score_unresolved_candidates_produce_safe_abstention() -> None:
    unresolved = _relevance(
        status=CausalRelevanceStatus.IDENTITY_UNRESOLVED,
        semantic=CausalPathSemantic.UNSUPPORTED_UNKNOWN,
        basis=CausalRelevanceResolutionBasis.UNRESOLVED,
        candidate_entity_id=None,
    )
    ledger = _ledger(
        [
            CausalEvidenceClaimType.RUNTIME_FAILURE,
            CausalEvidenceClaimType.SOURCE_CHANGE,
            CausalEvidenceClaimType.TEMPORAL_PRECEDENCE,
        ]
    )
    gates = [
        classify_causal_support(
            candidate_event_id=CANDIDATE_ID,
            relevance=unresolved,
            ledger=ledger,
        )
        for _ in range(5)
    ]
    assert all(
        gate.support_state
        == CausalEvidenceState.INSUFFICIENT_CANDIDATE_SPECIFIC_EVIDENCE
        for gate in gates
    )
    assert not any(
        gate.support_state == CausalEvidenceState.SUPPORTED_UNDER_CURRENT_MODEL
        for gate in gates
    )


def test_candidate_order_does_not_change_per_hypothesis_gate() -> None:
    supported = _classify(_ledger([CausalEvidenceClaimType.TOPOLOGY_PATH]))
    unsupported = _classify(
        _ledger(
            [
                CausalEvidenceClaimType.RUNTIME_FAILURE,
                CausalEvidenceClaimType.SOURCE_CHANGE,
                CausalEvidenceClaimType.TEMPORAL_PRECEDENCE,
            ]
        ),
        relevance=_relevance(
            status=CausalRelevanceStatus.IDENTITY_UNRESOLVED,
            semantic=CausalPathSemantic.UNSUPPORTED_UNKNOWN,
            basis=CausalRelevanceResolutionBasis.UNRESOLVED,
            candidate_entity_id=None,
        ),
    )
    first = [supported.model_dump_json(), unsupported.model_dump_json()]
    second = list(reversed([unsupported.model_dump_json(), supported.model_dump_json()]))
    assert first == second


def test_support_gate_audit_roundtrips_deterministically() -> None:
    gate = _classify(_ledger([CausalEvidenceClaimType.TOPOLOGY_PATH]))
    analysis = _analysis(_hypothesis(score=55.0, gate=gate))
    payload = analysis.model_dump_json()
    loaded = CausalAnalysisResponse.model_validate_json(payload)
    assert loaded.support_policy_version == CAUSAL_SUPPORT_GATE_POLICY_VERSION
    assert loaded.hypotheses[0].support_gate.model_dump_json() == (
        gate.model_dump_json()
    )


def test_legacy_payload_without_support_gate_retains_old_classification() -> None:
    hypothesis = _hypothesis(score=55.0, gate=None)
    analysis = _analysis(hypothesis)
    payload = analysis.model_dump(mode="json")
    payload.pop("support_policy_version", None)
    payload["hypotheses"][0].pop("support_gate", None)
    legacy = CausalAnalysisResponse.model_validate(payload)
    enriched = ensure_analysis_confidence_semantics(legacy)
    assert enriched.support_policy_version is None
    assert enriched.hypotheses[0].support_gate is None
    assert enriched.hypotheses[0].confidence_semantics.evidence_state == (
        CausalEvidenceState.SUPPORTED_UNDER_CURRENT_MODEL
    )


def test_support_policy_is_material_to_analysis_fingerprint() -> None:
    current = {
        "incident_id": "incident:ar2",
        "causal_support_gate": CAUSAL_SUPPORT_GATE_POLICY_VERSION,
    }
    legacy = {
        "incident_id": "incident:ar2",
        "causal_support_gate": "pre-ar2-support-semantics",
    }
    assert current != legacy
    assert _stable_id("causal-analysis", json.dumps(current, sort_keys=True)) != (
        _stable_id("causal-analysis", json.dumps(legacy, sort_keys=True))
    )
    source = (ROOT / "backend/app/services/causal_rca.py").read_text(
        encoding="utf-8"
    )
    assert '"causal_support_gate":' in source
    assert "CAUSAL_SUPPORT_GATE_POLICY_VERSION" in source


def test_claim_role_partition_is_explicit_and_disjoint() -> None:
    assert INCIDENT_LEVEL_CLAIM_TYPES == {
        CausalEvidenceClaimType.RUNTIME_FAILURE
    }
    assert CANDIDATE_CONTEXT_CLAIM_TYPES == {
        CausalEvidenceClaimType.SOURCE_CHANGE,
        CausalEvidenceClaimType.TEMPORAL_PRECEDENCE,
    }
    assert not (
        INCIDENT_LEVEL_CLAIM_TYPES
        & CANDIDATE_CONTEXT_CLAIM_TYPES
        or INCIDENT_LEVEL_CLAIM_TYPES
        & CANDIDATE_LINKAGE_CLAIM_TYPES
        or CANDIDATE_CONTEXT_CLAIM_TYPES
        & CANDIDATE_LINKAGE_CLAIM_TYPES
    )


def test_tc4_claim_enum_is_unchanged() -> None:
    assert {item.value for item in CausalEvidenceClaimType} == {
        "source_change",
        "temporal_precedence",
        "identity_resolution",
        "entity_linkage",
        "topology_path",
        "relationship_provenance",
        "runtime_failure",
        "artifact_provenance",
        "event_lineage",
    }


def test_support_gate_has_no_score_provider_llm_or_evaluator_dependency() -> None:
    source = inspect.getsource(
        __import__(
            "app.services.causal_support_gate",
            fromlist=["classify_causal_support"],
        )
    ).casefold()
    forbidden = (
        ".score",
        "openai",
        "embedding",
        "fuzzy",
        "github",
        "provider",
        "noncausal_control",
        "expected root",
        "grader",
    )
    assert all(value not in source for value in forbidden)


def test_ranking_frontier_and_final_cap_sources_remain_frozen() -> None:
    causal = (ROOT / "backend/app/services/causal_rca.py").read_text(
        encoding="utf-8"
    )
    budget = (ROOT / "backend/app/services/causal_evaluation_budget.py").read_text(
        encoding="utf-8"
    )
    assert "candidate.score * 0.40" in causal
    assert "+ topology_component * 25" in causal
    assert "+ temporal_component * 15" in causal
    assert "+ lineage_component * 10" in causal
    assert "hypotheses = hypotheses[" in causal
    assert ":request.max_hypotheses" in causal
    assert "CausalEvaluationSelectionBasis.ORDINARY_RAW_TOP_K" in budget
    assert "ordinary_shortlist_limit" in budget


def test_generic_product_has_no_frozen_lineage_special_cases() -> None:
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / "backend/app/models/causal_support.py",
            ROOT / "backend/app/services/causal_support_gate.py",
        )
    )
    forbidden = (
        "05a3d2361472923f5d545eaca1981f35",
        "32695735269",
        "4149b194c4c4fdfd",
        "a7616346acbcde6b",
        "NONCAUSAL_CONTROL",
        "runtime-mode.txt",
    )
    assert all(value not in sources for value in forbidden)
