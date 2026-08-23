from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


CAUSAL_CANDIDATE_POLICY_VERSION = "causal-candidate-v1"


class CausalCandidateRole(str, Enum):
    SOURCE_MUTATION = "source_mutation"
    OBSERVED_RESOURCE_MUTATION = "observed_resource_mutation"
    DERIVED_TOPOLOGY_CONSEQUENCE = "derived_topology_consequence"
    DERIVED_RUNTIME_CONSEQUENCE = "derived_runtime_consequence"
    RUNTIME_SYMPTOM = "runtime_symptom"
    LEGACY_OR_UNKNOWN = "legacy_or_unknown"


class CausalCandidateEligibility(str, Enum):
    PRIMARY_ELIGIBLE = "primary_eligible"
    SUPPORTING_ONLY = "supporting_only"
    FALLBACK_ELIGIBLE = "fallback_eligible"
    INELIGIBLE = "ineligible"


class CausalCandidateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version: str = CAUSAL_CANDIDATE_POLICY_VERSION
    role: CausalCandidateRole
    eligibility: CausalCandidateEligibility
    reason: str
    classification_inputs: dict[str, Any] = Field(default_factory=dict)


class CausalCandidateSelectionAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    origin_change_id: str | None = None
    raw_rank: int = Field(ge=1)
    raw_score: float = Field(ge=0, le=100)
    role: CausalCandidateRole
    eligibility: CausalCandidateEligibility
    eligible_rank: int | None = Field(default=None, ge=1)
    selected_for_hypothesis: bool
    classification_reason: str
    exclusion_reason: str | None = None
    classification_inputs: dict[str, Any] = Field(default_factory=dict)
    policy_version: str = CAUSAL_CANDIDATE_POLICY_VERSION
