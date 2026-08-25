from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


CAUSAL_CANDIDATE_POLICY_VERSION = "causal-candidate-v1"
CAUSAL_CANDIDATE_ADMISSION_POLICY_VERSION = (
    "causal-candidate-admission-v2"
)


class CandidateAdmissionBasis(str, Enum):
    TEMPORAL = "temporal"
    EXACT_IMMUTABLE_LINEAGE = "exact_immutable_lineage"


class LineageAdmissionState(str, Enum):
    ADMITTED = "admitted"
    INCOMPLETE = "incomplete"


class LineageAdmissionReason(str, Enum):
    EXACT_IMMUTABLE_LINEAGE = "exact_immutable_lineage"
    INCIDENT_PINNED_TOPOLOGY_MISSING = "incident_pinned_topology_missing"
    AFFECTED_ENTITY_MISSING = "affected_entity_missing"
    AFFECTED_ENTITY_IDENTITY_INCOMPLETE = (
        "affected_entity_identity_incomplete"
    )
    AFFECTED_ENTITY_UNSUPPORTED = "affected_entity_unsupported"
    WORKLOAD_OWNER_MISSING = "workload_owner_missing"
    WORKLOAD_OWNER_AMBIGUOUS = "workload_owner_ambiguous"
    RELATIONSHIP_PROVENANCE_INCOMPLETE = (
        "relationship_provenance_incomplete"
    )
    AFFECTED_CONTAINER_AMBIGUOUS = "affected_container_ambiguous"
    AFFECTED_CONTAINER_MISSING = "affected_container_missing"
    IMMUTABLE_IMAGE_MISSING = "immutable_image_missing"
    IMMUTABLE_IMAGE_IDENTITY_INCOMPLETE = (
        "immutable_image_identity_incomplete"
    )
    WORKLOAD_IMAGE_MISMATCH = "workload_image_mismatch"
    IMAGE_TO_RUN_MISSING = "image_to_run_missing"
    IMAGE_TO_RUN_AMBIGUOUS = "image_to_run_ambiguous"
    RUN_TO_REVISION_MISSING = "run_to_revision_missing"
    RUN_TO_REVISION_AMBIGUOUS = "run_to_revision_ambiguous"
    SOURCE_CHANGE_MISSING = "source_change_missing"
    SOURCE_CHANGE_AMBIGUOUS = "source_change_ambiguous"
    SOURCE_CHANGE_IDENTITY_INCOMPLETE = (
        "source_change_identity_incomplete"
    )
    PROVIDER_EFFECTIVE_TIME_INCOMPATIBLE = (
        "provider_effective_time_incompatible"
    )
    AMBIGUOUS_SOURCE_PROVENANCE = "ambiguous_source_provenance"
    LINEAGE_BUDGET_EXCEEDED = "lineage_budget_exceeded"


class CandidateAdmissionEvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_type: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    source_system: str = Field(min_length=1)


class LineageContainerScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    affected_entity_id: str
    pod_entity_id: str | None = None
    workload_entity_id: str
    container_name: str
    image_entity_id: str
    image_digest: str = Field(pattern="^sha256:[0-9a-f]{64}$")


class LineagePathAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path_id: str
    affected_entity_id: str
    entity_ids: list[str] = Field(default_factory=list)
    relationship_ids: list[str] = Field(default_factory=list)
    provider_evidence_ids: list[str] = Field(default_factory=list)
    container_name: str
    image_digest: str = Field(pattern="^sha256:[0-9a-f]{64}$")
    repository_id: str
    repository: str
    run_id: str
    run_attempt: int = Field(ge=1)
    revision: str = Field(pattern="^[0-9a-f]{40}$")
    canonical_change_id: str
    provider_effective_at: str


class LineageCandidateAdmissionAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_change_id: str | None = None
    revision: str | None = None
    admission_basis: list[CandidateAdmissionBasis] = Field(
        default_factory=list
    )
    admission_evidence_refs: list[
        CandidateAdmissionEvidenceReference
    ] = Field(default_factory=list)
    lineage_paths: list[LineagePathAudit] = Field(default_factory=list)
    container_scope: LineageContainerScope | None = None
    mutation_set: list[dict[str, Any]] = Field(default_factory=list)
    mutation_completeness: str | None = None
    admission_state: LineageAdmissionState
    admission_reason: LineageAdmissionReason
    policy_version: str = CAUSAL_CANDIDATE_ADMISSION_POLICY_VERSION


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
    candidate_admission_policy_version: str | None = None
    admission_basis: list[CandidateAdmissionBasis] = Field(
        default_factory=list
    )
    admission_evidence_refs: list[
        CandidateAdmissionEvidenceReference
    ] = Field(default_factory=list)
    lineage_paths: list[LineagePathAudit] = Field(default_factory=list)
    container_scope: LineageContainerScope | None = None
    lineage_admission_state: LineageAdmissionState | None = None
    lineage_admission_reason: LineageAdmissionReason | None = None
    mutation_set: list[dict[str, Any]] = Field(default_factory=list)
    mutation_completeness: str | None = None
