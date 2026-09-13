"""Typed, tenant-bound customer-data envelopes for external LLM providers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, ClassVar, Literal, Sequence, TypeAlias

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.models.incident_copilot import CopilotMessageView
from app.models.incident_explanation import EvidenceType, GroundingEvidence
from app.repositories.tenant_scope import DomainTenant, tenant_value
from app.security.customer_data_policy import (
    CONTROL,
    STRUCTURED,
    TENANT_META,
    USER_TEXT,
    CustomerDataPolicyError,
    ExternalDataSink,
    require_content_classes,
    scrub_outbound_text,
)
from app.security.egress_inventory import CustomerDataClass


IDENTIFIER_CHARS = 256
TITLE_CHARS = 512
NORMALIZED_TEXT_CHARS = 1024
USER_TEXT_CHARS = 4096
MAX_CONVERSATION_MESSAGES = 10
MAX_ENTITY_REFS = 50
MAX_RELATIONSHIP_FACTS = 100
MAX_CHANGE_FACTS = 50
MAX_EVIDENCE_REFS = 100
MAX_WARNINGS = 50
MAX_ENVELOPE_BYTES = 65_536
MAX_RESPONDER_NOTES = 50


class LLMDataBoundaryError(CustomerDataPolicyError):
    """Bounded failure raised before any provider request is attempted."""


class LLMEgressPurpose(StrEnum):
    INCIDENT_EXPLANATION = "INCIDENT_EXPLANATION"
    INCIDENT_COPILOT = "INCIDENT_COPILOT"
    INVESTIGATION_PLANNER = "INVESTIGATION_PLANNER"
    POST_INCIDENT_REPORT = "POST_INCIDENT_REPORT"
    EXECUTION_READINESS_SUMMARY = "EXECUTION_READINESS_SUMMARY"
    UNIFIED_BRIEFING_SUMMARY = "UNIFIED_BRIEFING_SUMMARY"
    SIMILARITY_SUMMARY = "SIMILARITY_SUMMARY"
    RESPONSE_INTELLIGENCE_SUMMARY = "RESPONSE_INTELLIGENCE_SUMMARY"


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > IDENTIFIER_CHARS:
        raise LLMDataBoundaryError("llm_identifier_invalid")
    if any(character in value for character in ("\r", "\n", "\x00")):
        raise LLMDataBoundaryError("llm_identifier_invalid")
    if scrub_outbound_text(value, maximum=len(value)) != value:
        raise LLMDataBoundaryError("llm_identifier_not_allowed")
    return value


def _title(value: object) -> str:
    if not isinstance(value, str):
        raise LLMDataBoundaryError("llm_text_invalid")
    return scrub_outbound_text(value, maximum=TITLE_CHARS)


def _normalized_text(value: object) -> str:
    if not isinstance(value, str):
        raise LLMDataBoundaryError("llm_text_invalid")
    return scrub_outbound_text(value, maximum=NORMALIZED_TEXT_CHARS)


def _user_text(value: object) -> str:
    if not isinstance(value, str):
        raise LLMDataBoundaryError("llm_text_invalid")
    return scrub_outbound_text(value, maximum=USER_TEXT_CHARS)


Identifier: TypeAlias = Annotated[
    str,
    BeforeValidator(_identifier),
    StringConstraints(min_length=1, max_length=IDENTIFIER_CHARS),
]
TitleText: TypeAlias = Annotated[
    str,
    BeforeValidator(_title),
    StringConstraints(max_length=TITLE_CHARS),
]
NormalizedText: TypeAlias = Annotated[
    str,
    BeforeValidator(_normalized_text),
    StringConstraints(max_length=NORMALIZED_TEXT_CHARS),
]
UserText: TypeAlias = Annotated[
    str,
    BeforeValidator(_user_text),
    StringConstraints(max_length=USER_TEXT_CHARS),
]
ScalarValue: TypeAlias = str | int | float | bool | None


class _EnvelopeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LLMScalarFact(_EnvelopeModel):
    code: Identifier
    value: ScalarValue


class LLMEvidenceReference(_EnvelopeModel):
    evidence_id: Identifier
    evidence_type: EvidenceType
    summary: NormalizedText
    observed_at: Identifier | None = None
    facts: tuple[LLMScalarFact, ...] = Field(default=(), max_length=25)


class LLMConversationMessage(_EnvelopeModel):
    role: Literal["user", "assistant"]
    content: UserText


class LLMEvidenceEnvelope(_EnvelopeModel):
    tenant_id: Identifier = Field(exclude=True, repr=False)
    incident_id: Identifier
    prompt_version: Identifier
    allowed_evidence_ids: tuple[Identifier, ...] = Field(
        default=(), max_length=MAX_EVIDENCE_REFS
    )
    evidence_catalog: tuple[LLMEvidenceReference, ...] = Field(
        default=(), max_length=MAX_EVIDENCE_REFS
    )

    @model_validator(mode="after")
    def validate_allowed_evidence(self) -> "LLMEvidenceEnvelope":
        catalog_ids = {item.evidence_id for item in self.evidence_catalog}
        if any(
            evidence_id not in catalog_ids
            for evidence_id in self.allowed_evidence_ids
        ):
            raise ValueError("llm_evidence_reference_invalid")
        return self


class LLMIncidentExplanationEnvelope(LLMEvidenceEnvelope):
    purpose: ClassVar[LLMEgressPurpose] = LLMEgressPurpose.INCIDENT_EXPLANATION


class LLMCopilotEnvelope(LLMEvidenceEnvelope):
    purpose: ClassVar[LLMEgressPurpose] = LLMEgressPurpose.INCIDENT_COPILOT
    question: UserText
    conversation_history: tuple[LLMConversationMessage, ...] = Field(
        default=(), max_length=MAX_CONVERSATION_MESSAGES
    )


class LLMInvestigationPlannerEnvelope(LLMEvidenceEnvelope):
    purpose: ClassVar[LLMEgressPurpose] = LLMEgressPurpose.INVESTIGATION_PLANNER


class LLMPostIncidentReportEnvelope(LLMEvidenceEnvelope):
    purpose: ClassVar[LLMEgressPurpose] = LLMEgressPurpose.POST_INCIDENT_REPORT
    responder_notes: tuple[UserText, ...] = Field(
        default=(), max_length=MAX_RESPONDER_NOTES
    )


class LLMActionFact(_EnvelopeModel):
    action_id: Identifier
    title: TitleText
    category: Identifier | None = None
    family: Identifier | None = None
    risk: Identifier | None = None
    status: Identifier | None = None
    current_evidence_strength: Identifier | None = None
    historical_support: Identifier | None = None
    rank: int | None = None
    mutation: bool | None = None
    requires_human_approval: bool | None = None
    missing_preconditions: tuple[NormalizedText, ...] = Field(
        default=(), max_length=MAX_WARNINGS
    )
    blockers: tuple[NormalizedText, ...] = Field(
        default=(), max_length=MAX_WARNINGS
    )
    cautions: tuple[NormalizedText, ...] = Field(
        default=(), max_length=MAX_WARNINGS
    )


class LLMRootCauseFact(_EnvelopeModel):
    causal_analysis_id: Identifier
    root_event_id: Identifier
    root_event_title: TitleText
    root_event_source: Identifier
    root_entity_id: Identifier | None = None
    causal_confidence: float
    causal_change_event_id: Identifier
    causal_change_title: TitleText
    causal_change_source: Identifier | None = None
    causal_change_type: Identifier | None = None
    summary: NormalizedText
    evidence_references: tuple[Identifier, ...] = Field(
        default=(), max_length=MAX_EVIDENCE_REFS
    )


class LLMChangeFact(_EnvelopeModel):
    event_id: Identifier
    title: TitleText
    role: Identifier
    source: Identifier | None = None
    change_type: Identifier | None = None
    occurred_at: Identifier | None = None
    repository: NormalizedText | None = None
    commit_sha: Identifier | None = None


class LLMRelationshipFact(_EnvelopeModel):
    node_id: Identifier
    node_type: Identifier
    label: TitleText
    relation: Identifier | None = None
    entity_id: Identifier | None = None


class LLMBlastRadiusFact(_EnvelopeModel):
    root_entity_id: Identifier | None = None
    affected_entity_count: int
    direct_impact_count: int
    indirect_impact_count: int
    potential_impact_count: int
    affected_services: tuple[NormalizedText, ...] = Field(
        default=(), max_length=MAX_ENTITY_REFS
    )
    affected_teams: tuple[NormalizedText, ...] = Field(
        default=(), max_length=MAX_ENTITY_REFS
    )
    business_capabilities: tuple[NormalizedText, ...] = Field(
        default=(), max_length=MAX_ENTITY_REFS
    )


class LLMOwnershipImpactFact(_EnvelopeModel):
    resolved: bool
    owner_team: NormalizedText | None = None
    oncall_contact: NormalizedText | None = None
    service_name: NormalizedText | None = None
    repository_url: NormalizedText | None = None
    business_capability: NormalizedText | None = None
    criticality: Identifier | None = None
    business_impact_level: Identifier | None = None
    routing_recommendation: NormalizedText | None = None


class LLMHistoricalIncidentFact(_EnvelopeModel):
    incident_id: Identifier
    title: TitleText
    similarity: float
    rca_verdict: Identifier
    resolution_summary: NormalizedText
    primary_resolution_action: TitleText | None = None
    time_to_mitigation_seconds: int | None = None
    time_to_resolution_seconds: int | None = None
    matched_factors: tuple[NormalizedText, ...] = Field(default=(), max_length=10)
    differing_factors: tuple[NormalizedText, ...] = Field(default=(), max_length=10)


class LLMResolutionPatternFact(_EnvelopeModel):
    action_type: Identifier
    action_title: TitleText
    observed_cases: int
    effective_cases: int
    ineffective_cases: int
    unknown_effectiveness_cases: int
    supporting_incident_ids: tuple[Identifier, ...] = Field(default=(), max_length=20)


class LLMOutcomeFact(_EnvelopeModel):
    status: Identifier
    final_rca_verdict: Identifier
    rca_confidence: float
    final_root_cause: TitleText | None = None
    primary_resolution_action: TitleText | None = None
    resolution_summary: NormalizedText
    time_to_mitigation_seconds: int | None = None
    time_to_resolution_seconds: int | None = None


class LLMExecutionReadinessSummaryEnvelope(_EnvelopeModel):
    purpose: ClassVar[LLMEgressPurpose] = LLMEgressPurpose.EXECUTION_READINESS_SUMMARY
    tenant_id: Identifier = Field(exclude=True, repr=False)
    incident_id: Identifier
    policy_version: Identifier
    overall_execution_posture: Identifier
    deterministic_summary: NormalizedText
    actions: tuple[LLMActionFact, ...] = Field(default=(), max_length=50)
    warnings: tuple[NormalizedText, ...] = Field(default=(), max_length=MAX_WARNINGS)


class LLMUnifiedBriefingSummaryEnvelope(_EnvelopeModel):
    purpose: ClassVar[LLMEgressPurpose] = LLMEgressPurpose.UNIFIED_BRIEFING_SUMMARY
    tenant_id: Identifier = Field(exclude=True, repr=False)
    incident_id: Identifier
    incident_title: TitleText
    incident_status: Identifier
    incident_severity: Identifier
    summary: NormalizedText
    root_cause: LLMRootCauseFact
    recent_changes: tuple[LLMChangeFact, ...] = Field(
        default=(), max_length=MAX_CHANGE_FACTS
    )
    dependency_path: tuple[LLMRelationshipFact, ...] = Field(
        default=(), max_length=MAX_RELATIONSHIP_FACTS
    )
    blast_radius: LLMBlastRadiusFact | None = None
    ownership_impact: LLMOwnershipImpactFact | None = None
    remediation_actions: tuple[LLMActionFact, ...] = Field(default=(), max_length=50)
    historical_incidents: tuple[LLMHistoricalIncidentFact, ...] = Field(
        default=(), max_length=20
    )
    outcome: LLMOutcomeFact | None = None
    warnings: tuple[NormalizedText, ...] = Field(default=(), max_length=MAX_WARNINGS)


class LLMSimilaritySummaryEnvelope(_EnvelopeModel):
    purpose: ClassVar[LLMEgressPurpose] = LLMEgressPurpose.SIMILARITY_SUMMARY
    tenant_id: Identifier = Field(exclude=True, repr=False)
    incident_id: Identifier
    historical_support_level: Identifier
    deterministic_summary: NormalizedText
    current_analysis: tuple[LLMScalarFact, ...] = Field(default=(), max_length=25)
    top_matches: tuple[LLMHistoricalIncidentFact, ...] = Field(default=(), max_length=20)
    resolution_patterns: tuple[LLMResolutionPatternFact, ...] = Field(
        default=(), max_length=50
    )
    warnings: tuple[NormalizedText, ...] = Field(default=(), max_length=MAX_WARNINGS)


class LLMResponseIntelligenceSummaryEnvelope(_EnvelopeModel):
    purpose: ClassVar[LLMEgressPurpose] = LLMEgressPurpose.RESPONSE_INTELLIGENCE_SUMMARY
    tenant_id: Identifier = Field(exclude=True, repr=False)
    incident_id: Identifier
    response_priority: Identifier
    root_cause: LLMRootCauseFact
    overall_historical_support: Identifier
    deterministic_summary: NormalizedText
    actions: tuple[LLMActionFact, ...] = Field(default=(), max_length=50)
    warnings: tuple[NormalizedText, ...] = Field(default=(), max_length=MAX_WARNINGS)


LLMEnvelope: TypeAlias = (
    LLMIncidentExplanationEnvelope
    | LLMCopilotEnvelope
    | LLMInvestigationPlannerEnvelope
    | LLMPostIncidentReportEnvelope
    | LLMExecutionReadinessSummaryEnvelope
    | LLMUnifiedBriefingSummaryEnvelope
    | LLMSimilaritySummaryEnvelope
    | LLMResponseIntelligenceSummaryEnvelope
)


_REQUEST_TOKEN = object()


@dataclass(frozen=True, slots=True, init=False)
class SafeLLMRequest:
    purpose: LLMEgressPurpose
    customer_context_json: str = field(repr=False)
    customer_context_bytes: int
    customer_data_classes: frozenset[CustomerDataClass]
    _token: object = field(repr=False, compare=False)

    def __init__(
        self,
        *,
        purpose: LLMEgressPurpose,
        customer_context_json: str,
        customer_context_bytes: int,
        customer_data_classes: frozenset[CustomerDataClass],
        _token: object,
    ) -> None:
        if _token is not _REQUEST_TOKEN:
            raise TypeError("SafeLLMRequest must be produced by the LLM data boundary.")
        object.__setattr__(self, "purpose", purpose)
        object.__setattr__(self, "customer_context_json", customer_context_json)
        object.__setattr__(self, "customer_context_bytes", customer_context_bytes)
        object.__setattr__(self, "customer_data_classes", customer_data_classes)
        object.__setattr__(self, "_token", _token)


_PURPOSE_CLASSES = {
    LLMEgressPurpose.INCIDENT_COPILOT: frozenset(
        {CONTROL, TENANT_META, STRUCTURED, USER_TEXT}
    ),
    LLMEgressPurpose.POST_INCIDENT_REPORT: frozenset(
        {CONTROL, TENANT_META, STRUCTURED, USER_TEXT}
    ),
}
_DEFAULT_CLASSES = frozenset({CONTROL, TENANT_META, STRUCTURED})


def build_safe_llm_request(
    *, tenant_id: DomainTenant, envelope: LLMEnvelope
) -> SafeLLMRequest:
    expected_tenant = tenant_value(tenant_id)
    if envelope.tenant_id != expected_tenant:
        raise LLMDataBoundaryError("llm_tenant_mismatch")
    purpose = envelope.purpose
    body = {
        "purpose": purpose.value,
        "customer_context": envelope.model_dump(mode="json"),
    }
    serialized = json.dumps(body, sort_keys=True, separators=(",", ":"))
    size = len(serialized.encode("utf-8"))
    if size > MAX_ENVELOPE_BYTES:
        raise LLMDataBoundaryError("llm_envelope_too_large")
    return SafeLLMRequest(
        purpose=purpose,
        customer_context_json=serialized,
        customer_context_bytes=size,
        customer_data_classes=_PURPOSE_CLASSES.get(purpose, _DEFAULT_CLASSES),
        _token=_REQUEST_TOKEN,
    )


def require_provider_safe_request(
    request: SafeLLMRequest, *, sink: ExternalDataSink
) -> None:
    if not isinstance(request, SafeLLMRequest) or request._token is not _REQUEST_TOKEN:
        raise LLMDataBoundaryError("safe_llm_request_required")
    if sink not in {ExternalDataSink.OPENAI, ExternalDataSink.GROQ}:
        raise LLMDataBoundaryError("llm_provider_not_allowed")
    require_content_classes(sink, request.customer_data_classes)
    if request.customer_context_bytes > MAX_ENVELOPE_BYTES:
        raise LLMDataBoundaryError("llm_envelope_too_large")


_EVIDENCE_FACT_KEYS: dict[EvidenceType, tuple[str, ...]] = {
    EvidenceType.INCIDENT: (
        "incident_id", "status", "severity", "cluster_name", "namespace",
        "affected_entity_id", "affected_object_kind", "affected_object_name",
        "first_observed_at", "last_observed_at", "recovery_status",
    ),
    EvidenceType.SIGNAL: (
        "signal_id", "signal_type", "severity", "category", "source_system",
        "reason", "first_observed_at", "last_observed_at", "occurrence_count",
        "cluster_name", "namespace", "involved_entity_id", "involved_object_uid",
        "involved_object_kind", "involved_object_name",
    ),
    EvidenceType.ANALYSIS: (
        "analysis_id", "signal_id", "topology_snapshot_id", "algorithm_version",
        "generated_at", "candidate_count", "hypothesis_count",
        "top_hypothesis_title", "top_hypothesis_score",
    ),
    EvidenceType.RECOMMENDATION: (
        "recommendation_id", "analysis_id", "hypothesis_id", "signal_id",
        "change_id", "algorithm_version", "generated_at", "title", "action_type",
        "status", "confidence", "risk", "cluster_name", "namespace",
        "target_entity_id", "target_entity_kind", "target_entity_name", "applied_at",
    ),
    EvidenceType.RECOVERY: (
        "verification_id", "recommendation_id", "analysis_id", "signal_id",
        "pre_snapshot_id", "post_snapshot_id", "algorithm_version", "generated_at",
        "status", "confidence", "passed_count", "failed_count", "unknown_count",
    ),
    EvidenceType.TOPOLOGY: (
        "root_entity_id", "root_entity_name", "root_entity_kind",
        "affected_entity_count", "direct_impact_count", "indirect_impact_count",
        "potential_impact_count", "entity_id", "entity_kind", "entity_name",
        "impact", "distance", "impact_score", "service_name", "owner_team",
        "business_capability", "criticality",
    ),
    EvidenceType.OWNERSHIP: (
        "business_impact_level", "affected_entity_count", "resolved_entity_count",
        "unresolved_entity_count", "affected_team_count", "affected_capability_count",
        "highest_criticality", "routing_recommendation",
    ),
    EvidenceType.NETWORK: (
        "entity_count", "relationship_count", "path_count", "issue_count",
    ),
    EvidenceType.INVESTIGATION: (
        "plan_id", "title", "status", "objective", "step_count",
        "completed_step_count", "blocked_step_count",
    ),
}


def _fact_value(value: object) -> ScalarValue:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, StrEnum):
        value = value.value
    if isinstance(value, str):
        return scrub_outbound_text(value, maximum=NORMALIZED_TEXT_CHARS)
    return None


def safe_evidence_references(
    evidence: Sequence[GroundingEvidence], *, tenant_id: DomainTenant
) -> tuple[LLMEvidenceReference, ...]:
    expected_tenant = tenant_value(tenant_id)
    result: list[LLMEvidenceReference] = []
    for item in list(evidence)[:MAX_EVIDENCE_REFS]:
        if not isinstance(item, GroundingEvidence):
            raise LLMDataBoundaryError("llm_evidence_type_invalid")
        carried_tenant = item.data.get("tenant_id")
        if carried_tenant is not None and carried_tenant != expected_tenant:
            raise LLMDataBoundaryError("llm_tenant_mismatch")
        facts = []
        for key in _EVIDENCE_FACT_KEYS[item.evidence_type]:
            if key not in item.data:
                continue
            value = _fact_value(item.data[key])
            if value is not None:
                facts.append(LLMScalarFact(code=key, value=value))
        summary = (
            "A normalized failure signal is available; use its code-owned facts."
            if item.evidence_type is EvidenceType.SIGNAL
            else item.summary
        )
        result.append(
            LLMEvidenceReference(
                evidence_id=item.evidence_id,
                evidence_type=item.evidence_type,
                summary=summary,
                observed_at=item.observed_at,
                facts=tuple(facts),
            )
        )
    return tuple(result)


def evidence_ids(evidence: Sequence[LLMEvidenceReference]) -> tuple[str, ...]:
    return tuple(item.evidence_id for item in evidence)


def safe_conversation_history(
    history: Sequence[CopilotMessageView], *, tenant_id: DomainTenant
) -> tuple[LLMConversationMessage, ...]:
    expected_tenant = tenant_value(tenant_id)
    selected = list(history)[-MAX_CONVERSATION_MESSAGES:]
    result: list[LLMConversationMessage] = []
    for item in selected:
        carried_tenant = getattr(item, "tenant_id", expected_tenant)
        if carried_tenant != expected_tenant:
            raise LLMDataBoundaryError("llm_tenant_mismatch")
        result.append(
            LLMConversationMessage(role=item.role.value, content=item.content)
        )
    return tuple(result)


def responder_notes_from_evidence(
    evidence: Sequence[GroundingEvidence], *, tenant_id: DomainTenant
) -> tuple[str, ...]:
    expected_tenant = tenant_value(tenant_id)
    notes: list[str] = []
    for item in evidence:
        carried_tenant = item.data.get("tenant_id")
        if carried_tenant is not None and carried_tenant != expected_tenant:
            raise LLMDataBoundaryError("llm_tenant_mismatch")
        if item.evidence_type is not EvidenceType.INVESTIGATION:
            continue
        findings = item.data.get("findings")
        if not isinstance(findings, list):
            continue
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            note = finding.get("responder_notes")
            if isinstance(note, str) and note:
                notes.append(scrub_outbound_text(note, maximum=USER_TEXT_CHARS))
                if len(notes) == MAX_RESPONDER_NOTES:
                    return tuple(notes)
    return tuple(notes)
