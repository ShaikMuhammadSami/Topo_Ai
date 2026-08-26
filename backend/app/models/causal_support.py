from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.confidence_semantics import (
    CausalEvidenceCompleteness,
    CausalEvidenceState,
)


CAUSAL_SUPPORT_GATE_POLICY_VERSION = "causal-support-gate-v1"


class CausalSupportGateState(str, Enum):
    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"


class CausalSupportGateAudit(BaseModel):
    """Deterministic evidence-sufficiency decision for one hypothesis."""

    model_config = ConfigDict(extra="forbid")

    policy_version: str = CAUSAL_SUPPORT_GATE_POLICY_VERSION
    relevance_gate_state: CausalSupportGateState
    relevance_gate_reason: str
    candidate_linkage_gate_state: CausalSupportGateState
    candidate_linkage_gate_reason: str
    candidate_linkage_claim_ids: list[str] = Field(default_factory=list)
    candidate_linkage_claim_types: list[str] = Field(default_factory=list)
    incident_level_claim_ids: list[str] = Field(default_factory=list)
    candidate_context_claim_ids: list[str] = Field(default_factory=list)
    support_state: CausalEvidenceState
    support_reason: str
    evidence_completeness: CausalEvidenceCompleteness
