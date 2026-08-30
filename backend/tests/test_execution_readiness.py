from __future__ import annotations
from domain_tenant_fixtures import TEST_CONTEXT, TEST_TENANT

from copy import deepcopy
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

import app.api.execution_readiness as readiness_api
import app.services.execution_readiness as service
from app.models.execution_readiness import (
    ExecutionReadinessStatus,
    IncidentExecutionPosture,
)
from app.models.incident_memory import (
    HistoricalAiStatus,
)
from app.models.incident_outcome import (
    ActionEffectiveness,
    IncidentOutcome,
    IncidentResponseActionObservation,
    RcaVerdict,
    RecommendationFollowThrough,
    ResponseActionResult,
    ResponsePlanActionOutcome,
)
from app.models.incident_records import (
    IncidentStatus,
)
from app.models.ownership import (
    BusinessImpactLevel,
    EntityOwnershipResolution,
    IncidentOwnershipImpact,
    OwnershipSource,
    ServiceCriticality,
)
from app.models.recommendations import (
    RecommendationRisk,
)
from app.models.response_intelligence import (
    CombinedDecisionSupport,
    CurrentEvidenceStrength,
    HistoricalActionSupport,
    HistoricalActionSupportLevel,
    IncidentResponseIntelligence,
    ResponseActionFamily,
    ResponseActionGroup,
    ResponseActionIntelligence,
    ResponseActionSemantics,
    RollbackResponseIntelligence,
)
from app.models.response_plan import (
    IncidentResponseAction,
    IncidentResponsePlan,
    ResponseActionCategory,
    ResponsePriority,
    ResponseRootCause,
    RollbackCandidate,
)
from app.security.api_tokens import (
    ApiTokenAuthMiddleware,
)
from app.services.llm_client import (
    OpenAITextResult,
)


def _owner(
    *,
    resolved: bool = True,
    criticality: ServiceCriticality = (
        ServiceCriticality.TIER_3
    ),
) -> EntityOwnershipResolution:
    return EntityOwnershipResolution(
        resolved=resolved,
        entity_id="entity:payments",
        entity_kind="service",
        entity_name="payments",
        service_name=(
            "payment-api" if resolved else None
        ),
        owner_team=(
            "payments" if resolved else None
        ),
        owner_email=(
            "payments@example.com"
            if resolved
            else None
        ),
        oncall_contact=(
            "pagerduty:payments"
            if resolved
            else None
        ),
        criticality=(
            criticality if resolved else None
        ),
        source=(
            OwnershipSource.MANUAL
            if resolved
            else OwnershipSource.UNRESOLVED
        ),
        confidence=0.95 if resolved else 0.0,
        matched_ownership_id=(
            "ownership:payments"
            if resolved
            else None
        ),
        resolution_reason=(
            "Exact entity mapping."
            if resolved
            else "No ownership mapping matched."
        ),
    )


def _impact(
    *,
    criticality: ServiceCriticality = (
        ServiceCriticality.TIER_3
    ),
    affected: int = 2,
    level: BusinessImpactLevel = (
        BusinessImpactLevel.HIGH
    ),
    resolved: bool = True,
) -> IncidentOwnershipImpact:
    return IncidentOwnershipImpact(
        incident_id="incident:1",
        business_impact_level=level,
        affected_entity_count=affected,
        resolved_entity_count=(
            affected if resolved else 0
        ),
        unresolved_entity_count=(
            0 if resolved else affected
        ),
        affected_team_count=(
            1 if resolved else 0
        ),
        affected_capability_count=(
            1 if resolved else 0
        ),
        highest_criticality=(
            criticality if resolved else None
        ),
        owner_teams=(
            ["payments"] if resolved else []
        ),
        business_capabilities=(
            ["checkout"] if resolved else []
        ),
        oncall_contacts=(
            ["pagerduty:payments"]
            if resolved
            else []
        ),
        repositories=[],
        routing_recommendation=(
            "Route to pagerduty:payments."
            if resolved
            else "Ownership resolution is required."
        ),
    )


def _baseline_action(
    *,
    action_id: str,
    sequence: int,
    category: ResponseActionCategory,
    title: str,
    entity_ids: list[str] | None = None,
    risk: RecommendationRisk | None = None,
) -> IncidentResponseAction:
    mutation = category in {
        ResponseActionCategory.MITIGATE,
        ResponseActionCategory
        .ROLLBACK_CANDIDATE,
    }

    return IncidentResponseAction(
        action_id=action_id,
        sequence=sequence,
        category=category,
        priority=ResponsePriority.HIGH,
        title=title,
        description=f"Description for {title}.",
        reason="Current incident evidence.",
        risk=(
            risk
            or (
                RecommendationRisk.HIGH
                if mutation
                else RecommendationRisk.LOW
            )
        ),
        requires_human_approval=mutation,
        owner_team="payments",
        oncall_contact="pagerduty:payments",
        entity_ids=(
            entity_ids
            if entity_ids is not None
            else ["entity:payments"]
        ),
        evidence_event_ids=["event:deploy"],
        evidence_ids=["evidence:causal"],
    )


def _support(
    level: HistoricalActionSupportLevel,
) -> HistoricalActionSupport:
    conflicting = (
        level
        == HistoricalActionSupportLevel
        .CONFLICTING
    )
    strong = (
        level
        == HistoricalActionSupportLevel
        .STRONGLY_SUPPORTED
    )

    return HistoricalActionSupport(
        level=level,
        score=0.9 if strong else 0.2,
        similar_incident_count=(
            3
            if level
            not in {
                HistoricalActionSupportLevel
                .INSUFFICIENT_HISTORY,
                HistoricalActionSupportLevel
                .NOT_APPLICABLE,
            }
            else 0
        ),
        action_observed_count=(
            3 if strong or conflicting else 0
        ),
        effective_count=3 if strong else 0,
        ineffective_count=2 if conflicting else 0,
        unknown_effect_count=0,
        high_similarity_support_count=(
            3 if strong else 0
        ),
        supporting_incident_ids=(
            ["incident:old:1"] if strong else []
        ),
        contradicting_incident_ids=(
            ["incident:old:2"]
            if conflicting
            else []
        ),
        support_reasons=(
            ["Three prior effective outcomes."]
            if strong
            else []
        ),
        caution_reasons=(
            ["Prior matching actions conflicted."]
            if conflicting
            else []
        ),
    )


def _intelligent_action(
    action: IncidentResponseAction,
    *,
    family: ResponseActionFamily,
    semantics: ResponseActionSemantics,
    evidence: CurrentEvidenceStrength,
    support: HistoricalActionSupportLevel,
    group: ResponseActionGroup = (
        ResponseActionGroup.RECOMMENDED
    ),
) -> ResponseActionIntelligence:
    combined = {
        HistoricalActionSupportLevel
        .STRONGLY_SUPPORTED: (
            CombinedDecisionSupport
            .HISTORICALLY_STRONGLY_SUPPORTED
        ),
        HistoricalActionSupportLevel
        .CONFLICTING: (
            CombinedDecisionSupport
            .HISTORICALLY_CONFLICTING
        ),
        HistoricalActionSupportLevel
        .INSUFFICIENT_HISTORY: (
            CombinedDecisionSupport
            .INSUFFICIENT_HISTORY
        ),
        HistoricalActionSupportLevel
        .NOT_APPLICABLE: (
            CombinedDecisionSupport
            .NOT_APPLICABLE
        ),
    }.get(
        support,
        CombinedDecisionSupport.CURRENT_ONLY,
    )

    return ResponseActionIntelligence(
        **action.model_dump(),
        baseline_group=group,
        baseline_rank=action.sequence,
        action_family=family,
        action_semantics=semantics,
        current_evidence_strength=evidence,
        historical_support=_support(support),
        combined_decision_support=combined,
    )


def _intelligence(
    *,
    evidence: CurrentEvidenceStrength = (
        CurrentEvidenceStrength.HIGH
    ),
    support: HistoricalActionSupportLevel = (
        HistoricalActionSupportLevel
        .STRONGLY_SUPPORTED
    ),
    rollback_available: bool = True,
    root_entity_id: str | None = (
        "entity:payments"
    ),
    target_event_id: str | None = (
        "event:deploy"
    ),
    rollback_entity_ids: list[str] | None = None,
    owner_resolved: bool = True,
    criticality: ServiceCriticality = (
        ServiceCriticality.TIER_3
    ),
    affected: int = 2,
    impact_level: BusinessImpactLevel = (
        BusinessImpactLevel.HIGH
    ),
) -> IncidentResponseIntelligence:
    inspect = _baseline_action(
        action_id="action:inspect",
        sequence=1,
        category=ResponseActionCategory.INVESTIGATE,
        title="Inspect deployment evidence",
    )
    validate = _baseline_action(
        action_id="action:validate",
        sequence=1,
        category=ResponseActionCategory.VALIDATE,
        title="Validate current runtime revision",
    )
    recommended = [inspect]

    if rollback_available:
        recommended.append(
            _baseline_action(
                action_id="action:rollback",
                sequence=2,
                category=(
                    ResponseActionCategory
                    .ROLLBACK_CANDIDATE
                ),
                title="Consider rollback deployment",
                entity_ids=rollback_entity_ids,
            )
        )

    owner = _owner(
        resolved=owner_resolved,
        criticality=criticality,
    )
    plan = IncidentResponsePlan(
        incident_id="incident:1",
        causal_analysis_id="analysis:1",
        response_priority=ResponsePriority.CRITICAL,
        response_priority_reason=(
            "Critical checkout impact."
        ),
        root_cause=ResponseRootCause(
            event_id="event:commit",
            event_title="Payment retry change",
            event_source="github",
            event_kind="code",
            target_event_id=target_event_id,
            target_event_title="Deploy payments",
            target_event_source="github_actions",
            target_event_kind="deployment",
            entity_id=root_entity_id,
            causal_confidence=(
                0.9
                if evidence
                == CurrentEvidenceStrength.HIGH
                else 0.4
            ),
            confidence_level=(
                evidence.value
            ),
            evidence_ids=["evidence:causal"],
        ),
        primary_owner=owner,
        business_context=_impact(
            criticality=criticality,
            affected=affected,
            level=impact_level,
            resolved=owner_resolved,
        ),
        recommended_actions=recommended,
        validation_checks=[validate],
        rollback_candidate=RollbackCandidate(
            available=rollback_available,
            reason=(
                "Current evidence permits review."
                if rollback_available
                else "Current evidence does not permit rollback."
            ),
            change_event_id=(
                "event:deploy"
                if rollback_available
                else None
            ),
        ),
        escalation_targets=(
            ["payments", "pagerduty:payments"]
            if owner_resolved
            else []
        ),
    )
    actions = [
        _intelligent_action(
            inspect,
            family=ResponseActionFamily.INVESTIGATE,
            semantics=(
                ResponseActionSemantics
                .INVESTIGATION
            ),
            evidence=evidence,
            support=(
                HistoricalActionSupportLevel
                .NOT_APPLICABLE
            ),
        ),
        _intelligent_action(
            validate,
            family=ResponseActionFamily.VALIDATE,
            semantics=(
                ResponseActionSemantics.VALIDATION
            ),
            evidence=evidence,
            support=(
                HistoricalActionSupportLevel
                .NOT_APPLICABLE
            ),
            group=ResponseActionGroup.VALIDATION,
        ),
    ]

    if rollback_available:
        actions.insert(
            1,
            _intelligent_action(
                recommended[-1],
                family=ResponseActionFamily.ROLLBACK,
                semantics=(
                    ResponseActionSemantics
                    .MITIGATION
                ),
                evidence=evidence,
                support=support,
            ),
        )

    return IncidentResponseIntelligence(
        incident_id="incident:1",
        response_plan_reference=(
            "response-plan:analysis:1"
        ),
        causal_analysis_id="analysis:1",
        response_priority=ResponsePriority.CRITICAL,
        response_priority_reason=(
            "Critical checkout impact."
        ),
        baseline_response_plan=plan,
        actions=actions,
        rollback_candidate=(
            RollbackResponseIntelligence(
                baseline=plan.rollback_candidate,
                historical_support=(
                    _support(
                        support
                        if rollback_available
                        else (
                            HistoricalActionSupportLevel
                            .NOT_APPLICABLE
                        )
                    )
                ),
            )
        ),
        overall_historical_support=support,
        deterministic_summary=(
            "Deterministic response intelligence."
        ),
        ai_status=HistoricalAiStatus.NOT_REQUESTED,
    )


def _outcome(
    *,
    validation_recorded: bool = True,
    causal_analysis_id: str = "analysis:1",
    follow_through_only: bool = False,
) -> IncidentOutcome:
    observations = []

    if validation_recorded:
        observations.append(
            IncidentResponseActionObservation(
                action_instance_id=(
                    "action-instance:validate"
                ),
                response_plan_action_id=(
                    "action:validate"
                ),
                action_type="validate",
                title="Validate current runtime revision",
                actor="responder@example.com",
                source="responder",
                completed_at=datetime(
                    2026,
                    8,
                    16,
                    10,
                    5,
                    tzinfo=timezone.utc,
                ),
                target_entity_ids=[
                    "entity:payments"
                ],
                result=(
                    ResponseActionResult.SUCCESSFUL
                ),
                effectiveness=(
                    ActionEffectiveness.UNKNOWN
                ),
                effectiveness_reason=(
                    "Validation completion is distinct from recovery."
                ),
                evidence_ids=["evidence:runtime-version"],
            )
        )

    follow_through = []

    if follow_through_only:
        follow_through.append(
            ResponsePlanActionOutcome(
                response_plan_action_id=(
                    "action:validate"
                ),
                title="Validate current runtime revision",
                category="validate",
                follow_through=(
                    RecommendationFollowThrough.FOLLOWED
                ),
                effectiveness=(
                    ActionEffectiveness.UNKNOWN
                ),
                reason="Responder marked it followed.",
            )
        )

    return IncidentOutcome(
        outcome_id="outcome:1",
        incident_id="incident:1",
        status=IncidentStatus.RESOLVED,
        causal_analysis_id=causal_analysis_id,
        response_plan_reference=(
            "response-plan:analysis:1"
        ),
        started_at=datetime(
            2026,
            8,
            16,
            10,
            0,
            tzinfo=timezone.utc,
        ),
        rca_verdict=RcaVerdict.CONFIRMED,
        rca_confidence=0.9,
        resolution_summary="Resolved by responders.",
        actions_taken=observations,
        response_plan_actions=follow_through,
    )


def _build(
    monkeypatch,
    intelligence: IncidentResponseIntelligence,
    *,
    outcome: IncidentOutcome | None = None,
    include_ai: bool = False,
):
    monkeypatch.setattr(
        service,
        "build_incident_response_intelligence",
        lambda **kwargs: intelligence,
    )
    monkeypatch.setattr(
        service,
        "load_incident_outcome",
        lambda *args, **kwargs: outcome,
    )

    return service.build_incident_execution_readiness(
        session=object(),
        incident_id="incident:1",
        include_ai=include_ai,
        tenant_id=TEST_TENANT,
    )


def _rollback(result):
    return next(
        action
        for action in result.actions
        if action.action_family
        == ResponseActionFamily.ROLLBACK
    )


def test_read_only_action_is_safe_without_approval(
    monkeypatch,
) -> None:
    result = _build(
        monkeypatch,
        _intelligence(),
    )
    action = next(
        item
        for item in result.actions
        if item.action_id == "action:inspect"
    )

    assert action.readiness_status == (
        ExecutionReadinessStatus.READ_ONLY_SAFE
    )
    assert action.mutation is False
    assert action.requires_human_approval is False
    assert action.approval_context.required is False
    assert not (
        action.execution_contract
        .eligible_for_future_execution
    )


def test_completed_validation_allows_human_approval_readiness(
    monkeypatch,
) -> None:
    result = _build(
        monkeypatch,
        _intelligence(),
        outcome=_outcome(),
    )
    action = _rollback(result)

    assert action.readiness_status == (
        ExecutionReadinessStatus
        .READY_FOR_HUMAN_APPROVAL
    )
    assert action.requires_human_approval is True
    assert action.approval_context.required is True
    assert (
        action.execution_contract
        .eligible_for_future_execution
    )
    assert not (
        action.execution_contract
        .execution_authorized
    )
    assert not (
        action.execution_contract
        .execution_performed
    )


def test_missing_validation_prevents_approval_readiness(
    monkeypatch,
) -> None:
    action = _rollback(
        _build(
            monkeypatch,
            _intelligence(),
        )
    )

    assert action.readiness_status == (
        ExecutionReadinessStatus
        .NEEDS_VALIDATION
    )
    assert "validation:action:validate" in (
        action.missing_preconditions
    )


def test_weak_current_evidence_dominates_strong_history(
    monkeypatch,
) -> None:
    action = _rollback(
        _build(
            monkeypatch,
            _intelligence(
                evidence=CurrentEvidenceStrength.LOW,
            ),
            outcome=_outcome(),
        )
    )

    assert action.historical_support.level == (
        HistoricalActionSupportLevel
        .STRONGLY_SUPPORTED
    )
    assert action.readiness_status == (
        ExecutionReadinessStatus
        .NEEDS_MORE_EVIDENCE
    )


def test_history_cannot_create_rollback_eligibility(
    monkeypatch,
) -> None:
    result = _build(
        monkeypatch,
        _intelligence(
            rollback_available=False,
            support=(
                HistoricalActionSupportLevel
                .STRONGLY_SUPPORTED
            ),
        ),
        outcome=_outcome(),
    )

    assert not any(
        action.action_family
        == ResponseActionFamily.ROLLBACK
        for action in result.actions
    )
    assert not any(
        action.readiness_status
        == ExecutionReadinessStatus
        .READY_FOR_HUMAN_APPROVAL
        for action in result.actions
    )


def test_ambiguous_mutation_target_is_blocked(
    monkeypatch,
) -> None:
    action = _rollback(
        _build(
            monkeypatch,
            _intelligence(
                rollback_entity_ids=[
                    "entity:payments",
                    "entity:worker",
                ]
            ),
            outcome=_outcome(),
        )
    )

    assert action.readiness_status == (
        ExecutionReadinessStatus.BLOCKED
    )
    assert action.target.uniquely_identified is False


def test_missing_causal_target_is_blocked(
    monkeypatch,
) -> None:
    action = _rollback(
        _build(
            monkeypatch,
            _intelligence(
                target_event_id=None
            ),
            outcome=_outcome(),
        )
    )

    assert action.readiness_status == (
        ExecutionReadinessStatus.BLOCKED
    )
    assert any(
        "causal change target" in blocker
        for blocker in action.blockers
    )


def test_historical_conflict_is_a_caution_for_narrow_non_tier1(
    monkeypatch,
) -> None:
    action = _rollback(
        _build(
            monkeypatch,
            _intelligence(
                support=(
                    HistoricalActionSupportLevel
                    .CONFLICTING
                )
            ),
            outcome=_outcome(),
        )
    )

    assert action.readiness_status == (
        ExecutionReadinessStatus
        .READY_FOR_HUMAN_APPROVAL
    )
    assert any(
        "conflicts" in caution
        for caution in action.cautions
    )


def test_tier1_conflict_uses_stricter_policy(
    monkeypatch,
) -> None:
    action = _rollback(
        _build(
            monkeypatch,
            _intelligence(
                support=(
                    HistoricalActionSupportLevel
                    .CONFLICTING
                ),
                criticality=(
                    ServiceCriticality.TIER_1
                ),
            ),
            outcome=_outcome(),
        )
    )

    assert action.readiness_status == (
        ExecutionReadinessStatus.BLOCKED
    )
    assert any(
        "Tier-1" in blocker
        for blocker in action.blockers
    )


def test_low_criticality_narrow_action_is_not_overblocked(
    monkeypatch,
) -> None:
    action = _rollback(
        _build(
            monkeypatch,
            _intelligence(
                criticality=(
                    ServiceCriticality.TIER_4
                ),
                affected=1,
                impact_level=(
                    BusinessImpactLevel.LOW
                ),
            ),
            outcome=_outcome(),
        )
    )

    assert action.readiness_status == (
        ExecutionReadinessStatus
        .READY_FOR_HUMAN_APPROVAL
    )


def test_unresolved_ownership_blocks_high_risk_without_inventing_owner(
    monkeypatch,
) -> None:
    action = _rollback(
        _build(
            monkeypatch,
            _intelligence(owner_resolved=False),
            outcome=_outcome(),
        )
    )

    assert action.readiness_status == (
        ExecutionReadinessStatus.BLOCKED
    )
    assert action.approval_context.owner_team is None
    assert action.approval_context.oncall_contact is None
    assert action.approval_context.suggested_roles == []


def test_approval_requirement_is_preserved_without_downgrade(
    monkeypatch,
) -> None:
    intelligence = _intelligence()
    baseline = next(
        action
        for action in intelligence.actions
        if action.action_id == "action:rollback"
    )
    evaluated = _rollback(
        _build(
            monkeypatch,
            intelligence,
            outcome=_outcome(),
        )
    )

    assert baseline.requires_human_approval is True
    assert evaluated.requires_human_approval is True
    assert evaluated.approval_context.required is True


def test_recommended_validation_does_not_count_as_completed(
    monkeypatch,
) -> None:
    action = _rollback(
        _build(
            monkeypatch,
            _intelligence(),
            outcome=None,
        )
    )

    assert action.readiness_status == (
        ExecutionReadinessStatus
        .NEEDS_VALIDATION
    )


def test_follow_through_marker_alone_is_not_validation_evidence(
    monkeypatch,
) -> None:
    action = _rollback(
        _build(
            monkeypatch,
            _intelligence(),
            outcome=_outcome(
                validation_recorded=False,
                follow_through_only=True,
            ),
        )
    )

    assert action.readiness_status == (
        ExecutionReadinessStatus
        .NEEDS_VALIDATION
    )


def test_recorded_validation_uses_exact_durable_evidence_ids(
    monkeypatch,
) -> None:
    action = _rollback(
        _build(
            monkeypatch,
            _intelligence(),
            outcome=_outcome(),
        )
    )
    validation = next(
        item
        for item in action.preconditions
        if item.code
        == "validation:action:validate"
    )

    assert validation.satisfied is True
    assert "incident-outcome:outcome:1" in (
        validation.evidence_ids
    )
    assert "action-observation:action-instance:validate" in (
        validation.evidence_ids
    )


def test_stale_outcome_is_ignored(
    monkeypatch,
) -> None:
    result = _build(
        monkeypatch,
        _intelligence(),
        outcome=_outcome(
            causal_analysis_id="analysis:old"
        ),
    )

    assert _rollback(result).readiness_status == (
        ExecutionReadinessStatus
        .NEEDS_VALIDATION
    )
    assert any(
        "current causal analysis" in warning
        for warning in result.warnings
    )


def test_response_has_no_executable_command_field(
    monkeypatch,
) -> None:
    payload = _build(
        monkeypatch,
        _intelligence(),
        outcome=_outcome(),
    ).model_dump(mode="json")

    def keys(value):
        if isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from keys(item)
        elif isinstance(value, list):
            for item in value:
                yield from keys(item)

    assert "command" not in set(keys(payload))


def test_identical_evidence_is_deterministic(
    monkeypatch,
) -> None:
    intelligence = _intelligence()
    outcome = _outcome()
    first = _build(
        monkeypatch,
        intelligence,
        outcome=outcome,
    )
    second = _build(
        monkeypatch,
        intelligence,
        outcome=outcome,
    )

    assert first == second


def test_missing_history_does_not_disable_current_policy(
    monkeypatch,
) -> None:
    action = _rollback(
        _build(
            monkeypatch,
            _intelligence(
                support=(
                    HistoricalActionSupportLevel
                    .INSUFFICIENT_HISTORY
                )
            ),
            outcome=_outcome(),
        )
    )

    assert action.readiness_status == (
        ExecutionReadinessStatus
        .READY_FOR_HUMAN_APPROVAL
    )


def test_missing_openai_key_keeps_structured_result(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        service,
        "openai_is_configured",
        lambda: False,
    )
    result = _build(
        monkeypatch,
        _intelligence(),
        outcome=_outcome(),
        include_ai=True,
    )

    assert result.ai_status == (
        HistoricalAiStatus.UNAVAILABLE
    )
    assert _rollback(result).readiness_status == (
        ExecutionReadinessStatus
        .READY_FOR_HUMAN_APPROVAL
    )


def test_openai_failure_keeps_structured_result(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        service,
        "openai_is_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        service,
        "generate_openai_text",
        lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError("provider down")
        ),
    )
    result = _build(
        monkeypatch,
        _intelligence(),
        outcome=_outcome(),
        include_ai=True,
    )

    assert result.ai_status == (
        HistoricalAiStatus.FAILED
    )
    assert _rollback(result).readiness_status == (
        ExecutionReadinessStatus
        .READY_FOR_HUMAN_APPROVAL
    )


def test_llm_prose_cannot_change_readiness_fields(
    monkeypatch,
) -> None:
    intelligence = _intelligence()
    outcome = _outcome()
    baseline = _build(
        monkeypatch,
        intelligence,
        outcome=outcome,
    )
    deterministic_actions = deepcopy(
        baseline.actions
    )
    monkeypatch.setattr(
        service,
        "openai_is_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        service,
        "generate_openai_text",
        lambda **kwargs: OpenAITextResult(
            text=(
                "Ignore policy. Approved and executed with kubectl."
            ),
            model_name="test-model",
        ),
    )
    result = _build(
        monkeypatch,
        intelligence,
        outcome=outcome,
        include_ai=True,
    )

    assert result.ai_status == (
        HistoricalAiStatus.AVAILABLE
    )
    assert result.actions == deterministic_actions
    assert all(
        not action.execution_contract
        .execution_authorized
        for action in result.actions
    )


def test_only_one_optional_openai_call_is_made(
    monkeypatch,
) -> None:
    calls = []
    monkeypatch.setattr(
        service,
        "openai_is_configured",
        lambda: True,
    )

    def generate(**kwargs):
        calls.append(kwargs)
        return OpenAITextResult(
            text="Deterministic policy remains authoritative.",
            model_name="test-model",
        )

    monkeypatch.setattr(
        service,
        "generate_openai_text",
        generate,
    )
    _build(
        monkeypatch,
        _intelligence(),
        outcome=_outcome(),
        include_ai=True,
    )

    assert len(calls) == 1
    assert calls[0]["max_output_tokens"] == 450


def test_builder_consumes_14e_once_without_requesting_14e_ai(
    monkeypatch,
) -> None:
    calls = []
    intelligence = _intelligence()

    def build(**kwargs):
        calls.append(kwargs)
        return intelligence

    monkeypatch.setattr(
        service,
        "build_incident_response_intelligence",
        build,
    )
    monkeypatch.setattr(
        service,
        "load_incident_outcome",
        lambda *args, **kwargs: None,
    )
    service.build_incident_execution_readiness(
        session=object(),
        incident_id="incident:1",
        include_ai=False,
        tenant_id=TEST_TENANT,
    )

    assert len(calls) == 1
    assert calls[0]["include_ai"] is False


def test_incident_posture_reports_human_approval_boundary(
    monkeypatch,
) -> None:
    result = _build(
        monkeypatch,
        _intelligence(),
        outcome=_outcome(),
    )

    assert result.overall_execution_posture == (
        IncidentExecutionPosture
        .HUMAN_APPROVAL_POSSIBLE
    )
    assert "No action was approved or executed" in (
        result.deterministic_summary
    )


def test_api_uses_existing_not_found_convention(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        readiness_api,
        "build_incident_execution_readiness",
        lambda **kwargs: (_ for _ in ()).throw(
            ValueError("No causal analysis exists")
        ),
    )

    with pytest.raises(HTTPException) as exc:
        readiness_api.get_incident_execution_readiness(
            incident_id="incident:missing",
            include_ai=False,
            history_limit=5,
            min_similarity=0.5,
            session=object(),
            tenant_context=TEST_CONTEXT,
        )

    assert exc.value.status_code == 404


def test_existing_14b_through_14e_payload_is_preserved(
    monkeypatch,
) -> None:
    intelligence = _intelligence()
    original = intelligence.model_dump(
        mode="json"
    )
    result = _build(
        monkeypatch,
        intelligence,
        outcome=_outcome(),
    )

    assert (
        result.response_intelligence
        .model_dump(mode="json")
        == original
    )


def test_new_route_is_registered_and_authenticated(
) -> None:
    from app.main import app

    def route_paths(routes):
        for route in routes:
            if hasattr(route, "path"):
                yield route.path
                continue

            original = getattr(
                route,
                "original_router",
                None,
            )

            if original is not None:
                yield from route_paths(
                    original.routes
                )

    paths = set(route_paths(app.routes))

    assert (
        "/api/v1/incidents/{incident_id}/"
        "execution-readiness"
    ) in paths
    assert any(
        item.cls is ApiTokenAuthMiddleware
        for item in app.user_middleware
    )
