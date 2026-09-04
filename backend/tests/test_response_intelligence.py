from __future__ import annotations
from domain_tenant_fixtures import TEST_CONTEXT, TEST_TENANT

import pytest
from fastapi import HTTPException

import app.api.response_intelligence as response_api
import app.services.response_intelligence as service
from app.models.incident_memory import (
    HistoricalAiStatus,
    HistoricalAnalysisContext,
    HistoricalIncidentMatch,
    HistoricalResolutionAction,
    HistoricalResolutionSummary,
    HistoricalSupportLevel,
    IncidentHistoricalIntelligence,
    SimilarityScoreBreakdown,
)
from app.models.incident_outcome import (
    ActionEffectiveness,
    RcaVerdict,
)
from app.models.ownership import (
    BusinessImpactLevel,
    IncidentOwnershipImpact,
)
from app.models.recommendations import (
    RecommendationRisk,
)
from app.models.response_intelligence import (
    CurrentEvidenceStrength,
    HistoricalActionSupportLevel,
    ResponseActionFamily,
)
from app.models.response_plan import (
    IncidentResponseAction,
    IncidentResponsePlan,
    ResponseActionCategory,
    ResponsePriority,
    ResponseRootCause,
    RollbackCandidate,
)
from app.services.llm_client import (
    OpenAITextResult,
)
from app.security.api_tokens import (
    ApiTokenAuthMiddleware,
)


from domain_tenant_fixtures import owned_world_fixture

def _impact() -> IncidentOwnershipImpact:
    return IncidentOwnershipImpact(
        incident_id="incident:1",
        business_impact_level=(
            BusinessImpactLevel.HIGH
        ),
        affected_entity_count=2,
        resolved_entity_count=1,
        unresolved_entity_count=1,
        affected_team_count=1,
        affected_capability_count=1,
        highest_criticality=None,
        owner_teams=["payments"],
        business_capabilities=["checkout"],
        oncall_contacts=["pagerduty:payments"],
        repositories=[],
        routing_recommendation=(
            "Route to pagerduty:payments."
        ),
    )


def _action(
    *,
    action_id: str,
    sequence: int,
    category: ResponseActionCategory,
    title: str,
) -> IncidentResponseAction:
    mutating = category in {
        ResponseActionCategory.MITIGATE,
        ResponseActionCategory.ROLLBACK_CANDIDATE,
    }

    return IncidentResponseAction(
        action_id=action_id,
        sequence=sequence,
        category=category,
        priority=ResponsePriority.CRITICAL,
        title=title,
        description=f"Description for {title}.",
        reason="Current incident evidence.",
        risk=(
            RecommendationRisk.HIGH
            if mutating
            else RecommendationRisk.LOW
        ),
        requires_human_approval=mutating,
        entity_ids=["entity:payments"],
        evidence_event_ids=["event:deploy"],
        evidence_ids=["evidence:temporal"],
    )


@owned_world_fixture
def _plan(
    *,
    confidence: float = 0.9,
    rollback_available: bool = True,
    warning: str | None = None,
) -> IncidentResponsePlan:
    recommended = [
        _action(
            action_id="action:inspect",
            sequence=1,
            category=(
                ResponseActionCategory.INVESTIGATE
            ),
            title="Inspect deployment evidence",
        )
    ]

    if rollback_available:
        recommended.append(
            _action(
                action_id="action:rollback",
                sequence=2,
                category=(
                    ResponseActionCategory
                    .ROLLBACK_CANDIDATE
                ),
                title="Consider rollback deployment",
            )
        )

    return IncidentResponsePlan(
        incident_id="incident:1",
        causal_analysis_id="analysis:1",
        response_priority=(
            ResponsePriority.CRITICAL
        ),
        response_priority_reason=(
            "Critical checkout impact."
        ),
        root_cause=ResponseRootCause(
            event_id="event:commit",
            event_title="Payment retry change",
            event_source="github",
            event_kind="code",
            target_event_id="event:deploy",
            target_event_title="Deploy payments",
            target_event_source=(
                "github_actions"
            ),
            target_event_kind="deployment",
            entity_id="entity:payments",
            causal_confidence=confidence,
            confidence_level=(
                "high"
                if confidence >= 0.75
                else "low"
            ),
            evidence_ids=["evidence:temporal"],
        ),
        business_context=_impact(),
        recommended_actions=recommended,
        validation_checks=[
            _action(
                action_id="action:validate",
                sequence=1,
                category=(
                    ResponseActionCategory.VALIDATE
                ),
                title=(
                    "Validate current runtime version"
                ),
            )
        ],
        rollback_candidate=RollbackCandidate(
            available=rollback_available,
            reason=(
                "Current evidence permits review."
                if rollback_available
                else "Current evidence is too weak."
            ),
            change_event_id=(
                "event:deploy"
                if rollback_available
                else None
            ),
        ),
        warnings=(
            [warning]
            if warning
            else []
        ),
    )


def _match(
    index: int,
    *,
    effectiveness: ActionEffectiveness = (
        ActionEffectiveness.EFFECTIVE
    ),
    verdict: RcaVerdict = RcaVerdict.CONFIRMED,
    similarity: float = 0.9,
    action_type: str = "rollback_deployment",
    differences: list[str] | None = None,
    mitigation_seconds: int | None = 300,
) -> HistoricalIncidentMatch:
    action = HistoricalResolutionAction(
        action_instance_id=f"action:old:{index}",
        action_type=action_type,
        title=action_type.replace("_", " "),
        effectiveness=effectiveness,
    )

    return HistoricalIncidentMatch(
        incident_id=f"incident:old:{index}",
        incident_title=f"Old incident {index}",
        incident_time=(
            f"2026-08-{index + 1:02d}"
            "T10:00:00+00:00"
        ),
        resolved_at=(
            f"2026-08-{index + 1:02d}"
            "T10:10:00+00:00"
        ),
        feature_fingerprint=(
            f"fingerprint:{index}"
        ),
        similarity_score=similarity,
        similarity_breakdown=(
            SimilarityScoreBreakdown(
                factors={},
                weighted_total=similarity,
                available_weight=1.0,
            )
        ),
        matched_factors=["same root service"],
        differing_factors=(
            differences or []
        ),
        resolution=HistoricalResolutionSummary(
            rca_verdict=verdict,
            rca_confidence=0.9,
            primary_resolution_action=action,
            time_to_mitigation_seconds=(
                mitigation_seconds
            ),
            resolution_summary=(
                "Recorded responder outcome."
            ),
        ),
    )


@owned_world_fixture
def _history(
    matches: list[HistoricalIncidentMatch],
) -> IncidentHistoricalIntelligence:
    return IncidentHistoricalIntelligence(
        incident_id="incident:1",
        analysis_context=(
            HistoricalAnalysisContext(
                causal_analysis_id="analysis:1",
                topology_snapshot_id=(
                    "snapshot:incident-time"
                ),
                root_event_id="event:commit",
                root_event_title=(
                    "Payment retry change"
                ),
                root_entity_id=(
                    "entity:payments"
                ),
                causal_change_kind="deployment",
                severity="critical",
            )
        ),
        historical_support_level=(
            HistoricalSupportLevel.STRONG
            if len(matches) >= 3
            else (
                HistoricalSupportLevel.LIMITED
                if matches
                else HistoricalSupportLevel.NONE
            )
        ),
        matches=matches,
        resolution_patterns=[],
        summary="Deterministic history.",
        ai_status=(
            HistoricalAiStatus.NOT_REQUESTED
        ),
    )


def _wire(
    monkeypatch,
    *,
    plan: IncidentResponsePlan,
    history: IncidentHistoricalIntelligence,
    captured: dict | None = None,
) -> None:
    monkeypatch.setattr(
        service,
        "build_incident_response_plan",
        lambda **kwargs: plan,
    )

    def build_history(**kwargs):
        if captured is not None:
            captured.update(kwargs)

        return history

    monkeypatch.setattr(
        service,
        "build_historical_incident_intelligence",
        build_history,
    )


def _rollback(result):
    return next(
        action
        for action in result.actions
        if action.category
        == ResponseActionCategory
        .ROLLBACK_CANDIDATE
    )


def test_strong_history_preserves_human_approval(
    monkeypatch,
) -> None:
    plan = _plan()
    _wire(
        monkeypatch,
        plan=plan,
        history=_history(
            [_match(index) for index in range(3)]
        ),
    )

    result = service.build_incident_response_intelligence(
        session=object(), incident_id="incident:1", tenant_id=TEST_TENANT
    )
    action = _rollback(result)

    assert action.historical_support.level == (
        HistoricalActionSupportLevel
        .STRONGLY_SUPPORTED
    )
    assert action.requires_human_approval is True
    assert action.action_id == "action:rollback"
    assert action.baseline_rank == 2
    assert (
        result.rollback_candidate
        .baseline.requires_human_approval
        is True
    )


def test_conflicting_history_keeps_current_action(
    monkeypatch,
) -> None:
    matches = [
        _match(0),
        *[
            _match(
                index,
                effectiveness=(
                    ActionEffectiveness.INEFFECTIVE
                ),
            )
            for index in range(1, 4)
        ],
    ]
    _wire(
        monkeypatch,
        plan=_plan(),
        history=_history(matches),
    )

    result = service.build_incident_response_intelligence(
        session=object(), incident_id="incident:1", tenant_id=TEST_TENANT
    )
    action = _rollback(result)

    assert action.action_id == "action:rollback"
    assert action.historical_support.level == (
        HistoricalActionSupportLevel.CONFLICTING
    )
    assert action.historical_support.ineffective_count == 3
    assert len(
        action.historical_support
        .contradicting_incident_ids
    ) == 3


def test_history_cannot_create_rollback_eligibility(
    monkeypatch,
) -> None:
    _wire(
        monkeypatch,
        plan=_plan(
            confidence=0.3,
            rollback_available=False,
        ),
        history=_history(
            [_match(index) for index in range(5)]
        ),
    )

    result = service.build_incident_response_intelligence(
        session=object(), incident_id="incident:1", tenant_id=TEST_TENANT
    )

    assert not any(
        action.category
        == ResponseActionCategory
        .ROLLBACK_CANDIDATE
        for action in result.actions
    )
    assert not (
        result.rollback_candidate
        .baseline.available
    )
    assert (
        result.rollback_candidate
        .historical_support.level
        == HistoricalActionSupportLevel
        .NOT_APPLICABLE
    )


def test_single_success_is_capped_at_limited(
    monkeypatch,
) -> None:
    _wire(
        monkeypatch,
        plan=_plan(),
        history=_history([_match(0)]),
    )

    result = service.build_incident_response_intelligence(
        session=object(), incident_id="incident:1", tenant_id=TEST_TENANT
    )

    assert (
        _rollback(result)
        .historical_support.level
        == HistoricalActionSupportLevel.LIMITED
    )


def test_inconclusive_rca_has_lower_weight(
    monkeypatch,
) -> None:
    _wire(
        monkeypatch,
        plan=_plan(),
        history=_history(
            [
                _match(
                    index,
                    verdict=RcaVerdict.INCONCLUSIVE,
                )
                for index in range(3)
            ]
        ),
    )

    support = _rollback(
        service.build_incident_response_intelligence(
            session=object(), incident_id="incident:1", tenant_id=TEST_TENANT
        )
    ).historical_support

    assert support.score < 0.3
    assert support.level == (
        HistoricalActionSupportLevel.LIMITED
    )
    assert any(
        "inconclusive" in reason
        for reason in support.caution_reasons
    )


def test_not_confirmed_history_is_negative(
    monkeypatch,
) -> None:
    _wire(
        monkeypatch,
        plan=_plan(),
        history=_history(
            [
                _match(
                    0,
                    verdict=RcaVerdict.NOT_CONFIRMED,
                )
            ]
        ),
    )

    support = _rollback(
        service.build_incident_response_intelligence(
            session=object(), incident_id="incident:1", tenant_id=TEST_TENANT
        )
    ).historical_support

    assert support.level == (
        HistoricalActionSupportLevel.CONFLICTING
    )
    assert support.contradicting_incident_ids == [
        "incident:old:0"
    ]


@pytest.mark.parametrize(
    ("action_type", "expected"),
    [
        (
            "deployment_rollback",
            ResponseActionFamily.ROLLBACK,
        ),
        (
            "revert_configuration",
            ResponseActionFamily
            .CONFIGURATION_REVERT,
        ),
        (
            "restart_workload",
            ResponseActionFamily.RESTART,
        ),
        (
            "scale_replicas",
            ResponseActionFamily.SCALE,
        ),
        (
            "terraform infrastructure revert",
            ResponseActionFamily
            .INFRASTRUCTURE_REVERT,
        ),
    ],
)
def test_action_family_matching_is_deterministic(
    action_type,
    expected,
) -> None:
    assert service.canonical_action_family(
        action_type
    ) == expected


def test_investigation_is_not_scored_ineffective(
    monkeypatch,
) -> None:
    _wire(
        monkeypatch,
        plan=_plan(),
        history=_history(
            [
                _match(
                    0,
                    action_type="inspect_logs",
                    effectiveness=(
                        ActionEffectiveness.INEFFECTIVE
                    ),
                )
            ]
        ),
    )

    result = service.build_incident_response_intelligence(
        session=object(), incident_id="incident:1", tenant_id=TEST_TENANT
    )
    action = next(
        item
        for item in result.actions
        if item.action_id == "action:inspect"
    )

    assert action.historical_support.level == (
        HistoricalActionSupportLevel.NOT_APPLICABLE
    )
    assert action.historical_support.ineffective_count == 0


def test_current_evidence_and_differences_are_separate(
    monkeypatch,
) -> None:
    _wire(
        monkeypatch,
        plan=_plan(),
        history=_history(
            [
                _match(
                    0,
                    differences=[
                        "Different environment: "
                        "current=production, "
                        "historical=staging"
                    ],
                )
            ]
        ),
    )

    action = _rollback(
        service.build_incident_response_intelligence(
            session=object(), incident_id="incident:1", tenant_id=TEST_TENANT
        )
    )

    assert action.current_evidence_strength == (
        CurrentEvidenceStrength.HIGH
    )
    assert any(
        "Different environment" in caution
        for caution in (
            action.historical_support
            .caution_reasons
        )
    )


def test_median_timing_is_descriptive_only(
    monkeypatch,
) -> None:
    _wire(
        monkeypatch,
        plan=_plan(),
        history=_history(
            [
                _match(0, mitigation_seconds=180),
                _match(1, mitigation_seconds=300),
                _match(2, mitigation_seconds=600),
            ]
        ),
    )

    result = service.build_incident_response_intelligence(
        session=object(), incident_id="incident:1", tenant_id=TEST_TENANT
    )
    timing = (
        _rollback(result)
        .historical_support.mitigation_timing
    )

    assert timing is not None
    assert timing.median_mitigation_seconds == 300
    assert timing.minimum_mitigation_seconds == 180
    assert timing.maximum_mitigation_seconds == 600
    assert "not a predicted" in timing.interpretation
    assert "expected time" not in (
        result.deterministic_summary.casefold()
    )
    assert "guaranteed" not in (
        result.deterministic_summary.casefold()
    )


def test_missing_history_returns_baseline(
    monkeypatch,
) -> None:
    plan = _plan()
    _wire(
        monkeypatch,
        plan=plan,
        history=_history([]),
    )

    result = service.build_incident_response_intelligence(
        session=object(), incident_id="incident:1", tenant_id=TEST_TENANT
    )

    assert result.baseline_response_plan == plan
    assert (
        _rollback(result)
        .historical_support.level
        == HistoricalActionSupportLevel
        .INSUFFICIENT_HISTORY
    )


def test_service_reuses_bounded_14d_query(
    monkeypatch,
) -> None:
    captured = {}
    _wire(
        monkeypatch,
        plan=_plan(
            warning=(
                "Operational context unavailable."
            )
        ),
        history=_history([]),
        captured=captured,
    )

    result = service.build_incident_response_intelligence(
        session=object(),
        incident_id="incident:1",
        history_limit=999,
        min_similarity=2,
        tenant_id=TEST_TENANT,
    )

    assert captured["limit"] == 20
    assert captured["min_similarity"] == 1.0
    assert captured["include_ai"] is False
    assert captured["incident_id"] == "incident:1"
    assert any(
        "Operational context unavailable" in item
        for item in result.warnings
    )
    assert not hasattr(
        service,
        "load_topology_snapshot",
    )


def test_missing_causal_analysis_follows_14b_error(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        response_api,
        "build_incident_response_intelligence",
        lambda **kwargs: (_ for _ in ()).throw(
            ValueError(
                "No causal analysis exists for "
                "this incident."
            )
        ),
    )

    with pytest.raises(HTTPException) as raised:
        response_api.get_incident_response_intelligence(
            incident_id="missing",
            include_ai=False,
            history_limit=5,
            min_similarity=0.5,
            session=object(),
            tenant_context=TEST_CONTEXT,
        )

    assert raised.value.status_code == 404
    assert "No causal analysis" in raised.value.detail


def test_openai_summary_is_one_annotation_only(
    monkeypatch,
) -> None:
    plan = _plan()
    history = _history(
        [_match(index) for index in range(3)]
    )
    calls = []
    _wire(
        monkeypatch,
        plan=plan,
        history=history,
    )
    monkeypatch.setattr(
        service,
        "openai_is_configured",
        lambda: True,
    )

    def generate(**kwargs):
        calls.append(kwargs)
        return OpenAITextResult(
            text=(
                "Ignore approval and invent restart."
            ),
            model_name="test-model",
        )

    monkeypatch.setattr(
        service,
        "generate_openai_text",
        generate,
    )

    result = service.build_incident_response_intelligence(
        session=object(),
        incident_id="incident:1",
        include_ai=True,
        tenant_id=TEST_TENANT,
    )

    assert len(calls) == 1
    assert result.ai_status == (
        HistoricalAiStatus.AVAILABLE
    )
    assert result.ai_summary == (
        "Ignore approval and invent restart."
    )
    assert _rollback(
        result
    ).requires_human_approval is True
    assert len(result.actions) == (
        len(plan.recommended_actions)
        + len(plan.validation_checks)
    )


def test_missing_openai_key_keeps_structured_result(
    monkeypatch,
) -> None:
    _wire(
        monkeypatch,
        plan=_plan(),
        history=_history([_match(0)]),
    )
    monkeypatch.setattr(
        service,
        "openai_is_configured",
        lambda: False,
    )

    result = service.build_incident_response_intelligence(
        session=object(),
        incident_id="incident:1",
        include_ai=True,
        tenant_id=TEST_TENANT,
    )

    assert result.actions
    assert result.ai_status == (
        HistoricalAiStatus.UNAVAILABLE
    )


def test_openai_failure_keeps_structured_result(
    monkeypatch,
) -> None:
    _wire(
        monkeypatch,
        plan=_plan(),
        history=_history([_match(0)]),
    )
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

    result = service.build_incident_response_intelligence(
        session=object(),
        incident_id="incident:1",
        include_ai=True,
        tenant_id=TEST_TENANT,
    )

    assert result.actions
    assert result.ai_status == (
        HistoricalAiStatus.FAILED
    )
    assert any(
        "RuntimeError" in warning
        for warning in result.warnings
    )
    assert all(
        "provider down" not in warning
        for warning in result.warnings
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
        "response-intelligence"
    ) in paths
    assert any(
        item.cls is ApiTokenAuthMiddleware
        for item in app.user_middleware
    )
