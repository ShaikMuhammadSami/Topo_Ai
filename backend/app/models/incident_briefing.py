from __future__ import annotations

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.models.incident_memory import (
    HistoricalAiStatus,
    HistoricalSupportLevel,
)
from app.models.causal_rca import CausalEvidenceLedger
from app.models.incident_outcome import (
    ActionEffectiveness,
    RcaVerdict,
)
from app.models.incident_records import (
    IncidentSeverity,
    IncidentStatus,
)
from app.models.ownership import (
    BusinessImpactLevel,
    ServiceCriticality,
)
from app.models.recommendations import (
    RecommendationRisk,
)
from app.models.response_intelligence import (
    CombinedDecisionSupport,
    CurrentEvidenceStrength,
    HistoricalActionSupportLevel,
    ResponseActionFamily,
    ResponseActionSemantics,
)
from app.models.response_plan import (
    ResponseActionCategory,
    ResponsePriority,
    RunbookReference,
)


class BriefingModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )


class BriefingIncident(BriefingModel):
    incident_id: str
    title: str
    summary: str
    status: IncidentStatus
    severity: IncidentSeverity
    cluster_name: str
    namespace: str | None = None
    environment: str | None = None
    affected_entity_id: str | None = None
    affected_object_kind: str | None = None
    affected_object_name: str | None = None
    first_observed_at: datetime
    last_observed_at: datetime
    current_state: str
    recovery_status: str | None = None


class BriefingSummary(BriefingModel):
    text: str
    evidence_references: list[str] = Field(
        default_factory=list
    )


class BriefingEvidenceReference(
    BriefingModel
):
    evidence_id: str
    evidence_type: str
    source: str
    title: str
    detail: str
    observed_at: str | None = None
    event_id: str | None = None
    entity_id: str | None = None
    weight: float = Field(
        ge=0.0,
        le=1.0,
    )


class BriefingCausalPathStep(
    BriefingModel
):
    order: int = Field(ge=1)
    node_id: str
    node_type: str
    label: str
    event_id: str | None = None
    entity_id: str | None = None
    relation_from_previous: str | None = None
    relation_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    topology_relationship_id: str | None = None
    topology_relationship_type: str | None = None
    topology_relationship_direction: str | None = None
    evidence_references: list[str] = Field(
        default_factory=list
    )


class BriefingRootCause(BriefingModel):
    causal_analysis_id: str
    topology_snapshot_id: str | None = None
    root_event_id: str
    root_event_title: str
    root_event_source: str
    root_event_kind: str | None = None
    root_entity_id: str | None = None
    causal_confidence: float = Field(
        ge=0.0,
        le=1.0,
    )
    confidence_level: str
    causal_change_event_id: str
    causal_change_title: str
    causal_change_source: str | None = None
    causal_change_type: str | None = None
    causal_change_occurred_at: str | None = None
    summary: str
    reasons: list[str] = Field(
        default_factory=list
    )
    evidence_references: list[str] = Field(
        default_factory=list
    )


class BriefingRelevantChange(BriefingModel):
    event_id: str
    title: str
    role: str
    source: str | None = None
    change_type: str | None = None
    occurred_at: str | None = None
    repository: str | None = None
    commit_sha: str | None = None
    pipeline_name: str | None = None
    release_version: str | None = None
    minutes_before_incident: float | None = None
    evidence_references: list[str] = Field(
        default_factory=list
    )


class BriefingAffectedEntity(BriefingModel):
    entity_id: str
    entity_kind: str
    entity_name: str
    impact: str
    distance: int = Field(ge=0)
    impact_score: float = Field(
        ge=0.0,
        le=1.0,
    )
    service_name: str | None = None
    owner_team: str | None = None
    business_capability: str | None = None
    criticality: ServiceCriticality | None = None


class BriefingBlastRadius(BriefingModel):
    topology_snapshot_id: str | None = None
    root_entity_id: str | None = None
    affected_entity_count: int = Field(ge=0)
    returned_entity_count: int = Field(ge=0)
    omitted_entity_count: int = Field(ge=0)
    direct_impact_count: int = Field(ge=0)
    indirect_impact_count: int = Field(ge=0)
    potential_impact_count: int = Field(ge=0)
    affected_services: list[str] = Field(
        default_factory=list
    )
    affected_dependency_types: list[str] = Field(
        default_factory=list
    )
    affected_teams: list[str] = Field(
        default_factory=list
    )
    business_capabilities: list[str] = Field(
        default_factory=list
    )
    important_affected_entities: list[
        BriefingAffectedEntity
    ] = Field(default_factory=list)
    evidence_references: list[str] = Field(
        default_factory=list
    )


class BriefingOwnership(BriefingModel):
    resolved: bool
    entity_id: str | None = None
    owner_team: str | None = None
    owner_email: str | None = None
    oncall_contact: str | None = None
    service_name: str | None = None
    repository_url: str | None = None
    business_capability: str | None = None
    criticality: ServiceCriticality | None = None
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    evidence_references: list[str] = Field(
        default_factory=list
    )


class BriefingBusinessImpact(BriefingModel):
    business_impact_level: BusinessImpactLevel
    affected_entity_count: int = Field(ge=0)
    resolved_entity_count: int = Field(ge=0)
    unresolved_entity_count: int = Field(ge=0)
    affected_team_count: int = Field(ge=0)
    affected_capability_count: int = Field(ge=0)
    highest_criticality: ServiceCriticality | None = None
    owner_teams: list[str] = Field(
        default_factory=list
    )
    business_capabilities: list[str] = Field(
        default_factory=list
    )
    oncall_contacts: list[str] = Field(
        default_factory=list
    )
    repositories: list[str] = Field(
        default_factory=list
    )
    routing_recommendation: str
    evidence_references: list[str] = Field(
        default_factory=list
    )


class BriefingOperationalContext(
    BriefingModel
):
    ownership: BriefingOwnership
    business_impact: BriefingBusinessImpact
    escalation_targets: list[str] = Field(
        default_factory=list
    )


class BriefingHistoricalActionSupport(
    BriefingModel
):
    level: HistoricalActionSupportLevel
    score: float = Field(
        ge=0.0,
        le=1.0,
    )
    similar_incident_count: int = Field(ge=0)
    action_observed_count: int = Field(ge=0)
    effective_count: int = Field(ge=0)
    ineffective_count: int = Field(ge=0)
    unknown_effect_count: int = Field(ge=0)
    supporting_incident_ids: list[str] = Field(
        default_factory=list
    )
    contradicting_incident_ids: list[str] = Field(
        default_factory=list
    )
    support_reasons: list[str] = Field(
        default_factory=list
    )
    caution_reasons: list[str] = Field(
        default_factory=list
    )


class BriefingRemediationAction(
    BriefingModel
):
    action_id: str
    rank: int = Field(ge=1)
    category: ResponseActionCategory
    semantics: ResponseActionSemantics
    family: ResponseActionFamily
    priority: ResponsePriority
    title: str
    description: str
    reason: str
    risk: RecommendationRisk
    requires_human_approval: bool
    entity_ids: list[str] = Field(
        default_factory=list
    )
    evidence_event_ids: list[str] = Field(
        default_factory=list
    )
    evidence_references: list[str] = Field(
        default_factory=list
    )
    runbook_url: str | None = None
    current_evidence_strength: (
        CurrentEvidenceStrength
    )
    historical_support: (
        BriefingHistoricalActionSupport
    )
    combined_decision_support: (
        CombinedDecisionSupport
    )


class BriefingVerificationStep(
    BriefingModel
):
    step_id: str
    source_action_id: str
    title: str
    description: str
    expected_observation: str
    entity_ids: list[str] = Field(
        default_factory=list
    )
    evidence_references: list[str] = Field(
        default_factory=list
    )


class BriefingRemediationTarget(
    BriefingModel
):
    entity_ids: list[str] = Field(
        default_factory=list
    )
    change_event_ids: list[str] = Field(
        default_factory=list
    )


class BriefingRemediationPreview(
    BriefingModel
):
    action_id: str
    action_title: str
    intended_effect: str
    affected_target: BriefingRemediationTarget
    potentially_impacted_entities: list[
        BriefingAffectedEntity
    ] = Field(default_factory=list)
    potential_impact_scope_note: str
    risk: RecommendationRisk
    expected_observation_if_successful: str
    possible_failure_modes: list[str] = Field(
        default_factory=list
    )
    verification_steps: list[
        BriefingVerificationStep
    ] = Field(default_factory=list)
    rollback_or_recovery_considerations: list[
        str
    ] = Field(default_factory=list)
    historical_observations: list[str] = Field(
        default_factory=list
    )
    evidence_references: list[str] = Field(
        default_factory=list
    )


class BriefingRemediation(BriefingModel):
    response_priority: ResponsePriority
    response_priority_reason: str
    actions: list[
        BriefingRemediationAction
    ] = Field(default_factory=list)
    previews: list[
        BriefingRemediationPreview
    ] = Field(default_factory=list)
    runbooks: list[RunbookReference] = Field(
        default_factory=list
    )
    overall_historical_support: (
        HistoricalActionSupportLevel
    )
    read_only: bool = True


class BriefingHistoricalIncident(
    BriefingModel
):
    incident_id: str
    incident_title: str
    similarity: float = Field(
        ge=0.0,
        le=1.0,
    )
    why_it_matches: list[str] = Field(
        default_factory=list
    )
    important_differences: list[str] = Field(
        default_factory=list
    )
    rca_verdict: RcaVerdict
    resolution_summary: str
    primary_resolution_action: str | None = None
    primary_action_effectiveness: (
        ActionEffectiveness | None
    ) = None
    time_to_mitigation_seconds: int | None = Field(
        default=None,
        ge=0,
    )
    time_to_resolution_seconds: int | None = Field(
        default=None,
        ge=0,
    )
    evidence_references: list[str] = Field(
        default_factory=list
    )


class BriefingHistoricalContext(
    BriefingModel
):
    support_level: HistoricalSupportLevel
    similar_incident_count: int = Field(ge=0)
    similar_incidents: list[
        BriefingHistoricalIncident
    ] = Field(default_factory=list)
    resolution_patterns: list[dict] = Field(
        default_factory=list
    )
    summary: str


class BriefingOutcome(BriefingModel):
    outcome_id: str
    status: IncidentStatus
    mitigated_at: datetime | None = None
    resolved_at: datetime | None = None
    time_to_mitigation_seconds: int | None = Field(
        default=None,
        ge=0,
    )
    time_to_resolution_seconds: int | None = Field(
        default=None,
        ge=0,
    )
    final_rca_verdict: RcaVerdict
    rca_confidence: float = Field(
        ge=0.0,
        le=1.0,
    )
    final_root_cause: str | None = None
    primary_resolution_action: str | None = None
    resolution_summary: str
    evidence_references: list[str] = Field(
        default_factory=list
    )


class IncidentBriefing(BriefingModel):
    incident: BriefingIncident
    summary: BriefingSummary
    root_cause: BriefingRootCause
    causal_evidence: list[
        BriefingEvidenceReference
    ] = Field(default_factory=list)
    causal_evidence_ledger: CausalEvidenceLedger | None = None
    recent_relevant_changes: list[
        BriefingRelevantChange
    ] = Field(default_factory=list)
    dependency_path: list[
        BriefingCausalPathStep
    ] = Field(default_factory=list)
    blast_radius: BriefingBlastRadius | None = None
    operational_context: (
        BriefingOperationalContext | None
    ) = None
    remediation: BriefingRemediation | None = None
    historical_context: BriefingHistoricalContext
    verification_plan: list[
        BriefingVerificationStep
    ] = Field(default_factory=list)
    outcome: BriefingOutcome | None = None
    warnings: list[str] = Field(
        default_factory=list
    )
    ai_summary: str | None = None
    ai_status: HistoricalAiStatus
    ai_provider: str | None = None
    ai_model: str | None = None
