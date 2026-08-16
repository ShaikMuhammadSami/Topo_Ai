from datetime import (
    datetime,
    timezone,
)
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import (
    create_engine,
    func,
    select,
)
from sqlalchemy.orm import sessionmaker

import app.api.causal_rca as causal_api
import app.api.incident_context as context_api
import app.api.incident_outcome as outcome_api
import app.api.response_plan as response_api
import app.services.incident_outcome as service
from app.db.database import Base
from app.db.models import IncidentOutcomeRecord
from app.models.causal_rca import (
    CausalAnalysisResponse,
    CausalConfidenceLevel,
    CausalHypothesis,
)
from app.models.change_events import (
    ChangeEventKind,
    ChangeEventRiskLevel,
    ChangeEventSource,
    ChangeEventView,
)
from app.models.incident_outcome import (
    ActionEffectiveness,
    IncidentOutcomeUpdate,
    RecommendationFollowThrough,
    ReportedRootCause,
    ResponseActionObservationInput,
    ResponseActionResult,
    RcaVerdict,
)
from app.models.incident_records import (
    IncidentSeverity,
    IncidentStatus,
)
from app.models.topology import (
    Entity,
    EntityType,
    GraphSnapshot,
)


STARTED = datetime(
    2026,
    8,
    16,
    10,
    0,
    tzinfo=timezone.utc,
)
MITIGATED = datetime(
    2026,
    8,
    16,
    10,
    10,
    tzinfo=timezone.utc,
)
RESOLVED = datetime(
    2026,
    8,
    16,
    10,
    20,
    tzinfo=timezone.utc,
)


def _incident(
    *,
    status: IncidentStatus = (
        IncidentStatus.RESOLVED
    ),
):
    return SimpleNamespace(
        incident_id="incident:1",
        status=status,
        severity=IncidentSeverity.CRITICAL,
        cluster_name="production",
        namespace="payments",
        first_observed_at=STARTED,
        last_observed_at=STARTED,
        updated_at=RESOLVED,
        latest_recommendation_id=None,
    )


def _analysis() -> CausalAnalysisResponse:
    hypothesis = CausalHypothesis(
        hypothesis_id="hypothesis:1",
        rank=1,
        root_event_id="event:commit",
        root_source="github",
        root_title="Payment retry change",
        target_event_id="event:deploy",
        target_title="Deploy payments",
        affected_entity_id=(
            "entity:payments"
        ),
        score=88.0,
        confidence=0.88,
        confidence_level=(
            CausalConfidenceLevel.HIGH
        ),
        minutes_before_incident=5.0,
        summary="Causal chain.",
        supporting_evidence_ids=[
            "evidence:causal"
        ],
    )

    return CausalAnalysisResponse(
        analysis_id="causal-analysis:1",
        incident_id="incident:1",
        incident_title="Payments incident",
        incident_time=STARTED.isoformat(),
        topology_snapshot_id=(
            "snapshot:incident-time"
        ),
        algorithm_version="13c-causal-v1",
        generated_at=STARTED.isoformat(),
        parameters={},
        candidate_count=1,
        node_count=0,
        edge_count=0,
        evidence_count=1,
        hypothesis_count=1,
        top_hypothesis=hypothesis,
        hypotheses=[hypothesis],
    )


def _plan() -> dict:
    return {
        "reference": (
            "response-plan:causal-analysis:1"
        ),
        "causal_analysis_id": (
            "causal-analysis:1"
        ),
        "root_cause": {
            "event_id": "event:commit",
            "event_title": (
                "Payment retry change"
            ),
            "event_source": "github",
            "target_event_id": "event:deploy",
            "target_event_title": (
                "Deploy payments"
            ),
            "entity_id": "entity:payments",
        },
        "actions": [
            {
                "action_id": "plan:validate",
                "sequence": 1,
                "category": "validate",
                "title": "Validate deployment",
                "entity_ids": [
                    "entity:payments"
                ],
                "evidence_event_ids": [
                    "event:deploy"
                ],
                "evidence_ids": [
                    "evidence:causal"
                ],
            },
            {
                "action_id": "plan:rollback",
                "sequence": 2,
                "category": (
                    "rollback_candidate"
                ),
                "title": "Consider rollback",
                "entity_ids": [
                    "entity:payments"
                ],
                "evidence_event_ids": [
                    "event:deploy"
                ],
                "evidence_ids": [
                    "evidence:causal"
                ],
            },
        ],
        "rollback_candidate": {
            "available": True,
            "change_event_id": (
                "event:deploy"
            ),
        },
    }


def _snapshot(
    snapshot_id: str = (
        "snapshot:incident-time"
    ),
) -> GraphSnapshot:
    return GraphSnapshot(
        snapshot_id=snapshot_id,
        collected_at=STARTED,
        collector_name="test",
        collector_version="1",
        scope={"cluster": "production"},
        entities=[
            Entity(
                id="entity:payments",
                entity_type=(
                    EntityType.APPLICATION
                ),
                kind="KubernetesDeployment",
                name="payments-api",
                source_system="kubernetes",
                observed_at=STARTED,
            )
        ],
    )


def _event(
    event_id: str,
    *,
    rollback_of: str | None = None,
) -> ChangeEventView:
    return ChangeEventView(
        event_id=event_id,
        event_fingerprint=(
            f"fingerprint:{event_id}"
        ),
        source=ChangeEventSource.KUBERNETES,
        kind=ChangeEventKind.DEPLOYMENT,
        external_id=event_id,
        origin_change_id=None,
        title="Rollback payments deployment",
        summary=None,
        actor="payments-oncall",
        occurred_at=(
            "2026-08-16T10:09:00+00:00"
        ),
        received_at=(
            "2026-08-16T10:09:01+00:00"
        ),
        environment="production",
        provider="kubernetes",
        account_id=None,
        region=None,
        cluster_name="production",
        namespace="payments",
        repository=None,
        commit_sha=None,
        pipeline_name=None,
        release_version="previous",
        terraform_workspace=None,
        risk_score=50,
        risk_level=(
            ChangeEventRiskLevel.MEDIUM
        ),
        status="observed",
        observation_count=1,
        metadata=(
            {
                "rollback_of_event_id": (
                    rollback_of
                )
            }
            if rollback_of
            else {}
        ),
        raw_payload={},
        agent_id=None,
        links=[],
        created_at=STARTED.isoformat(),
        updated_at=STARTED.isoformat(),
    )


def _wire(
    monkeypatch,
    *,
    analysis: (
        CausalAnalysisResponse | None
    ) = None,
    plan: dict | None = None,
    events: dict[str, ChangeEventView]
        | None = None,
    loaded_snapshots: list[str]
        | None = None,
    incident=None,
) -> None:
    selected_analysis = (
        analysis
        if analysis is not None
        else _analysis()
    )
    selected_plan = (
        plan
        if plan is not None
        else _plan()
    )
    event_map = events or {}

    monkeypatch.setattr(
        service,
        "load_incident_record",
        lambda *, session, incident_id: (
            incident or _incident()
        ),
    )

    def context(
        session,
        *,
        incident_id,
        source,
        warnings,
    ):
        return selected_analysis, selected_plan

    monkeypatch.setattr(
        service,
        "_analysis_and_plan",
        context,
    )
    monkeypatch.setattr(
        service,
        "load_topology_snapshot",
        lambda *, session, snapshot_id: (
            loaded_snapshots.append(
                snapshot_id
            )
            if loaded_snapshots is not None
            else None
        )
        or _snapshot(snapshot_id),
    )
    monkeypatch.setattr(
        service,
        "list_change_events",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        service,
        "_legacy_observation",
        lambda session, *, incident: (
            None,
            None,
        ),
    )
    monkeypatch.setattr(
        service,
        "_change_event_for_action",
        lambda session, *, event_id: (
            event_map.get(event_id)
        ),
    )


def _rollback_action(
    *,
    action_id: str = "action:rollback",
    event_id: str = "event:rollback",
    completed_at: datetime = datetime(
        2026,
        8,
        16,
        10,
        9,
        tzinfo=timezone.utc,
    ),
) -> ResponseActionObservationInput:
    return ResponseActionObservationInput(
        action_instance_id=action_id,
        response_plan_action_id=(
            "plan:rollback"
        ),
        change_event_id=event_id,
        action_type="rollback_deployment",
        title="Rollback payments deployment",
        actor="payments-oncall",
        completed_at=completed_at,
        target_entity_ids=[
            "entity:payments"
        ],
        result=ResponseActionResult.SUCCESSFUL,
    )


def _derive(
    update: IncidentOutcomeUpdate,
):
    return service._derive_outcome(
        object(),
        incident_id="incident:1",
        manual=update,
        source={},
    )


def test_confirmed_rca_via_successful_rollback(
    monkeypatch,
) -> None:
    _wire(
        monkeypatch,
        events={
            "event:rollback": _event(
                "event:rollback",
                rollback_of="event:deploy",
            )
        },
    )
    result = _derive(
        IncidentOutcomeUpdate(
            mitigated_at=MITIGATED,
            resolved_at=RESOLVED,
            actions=[_rollback_action()],
        )
    )

    assert result.rca_verdict == (
        RcaVerdict.CONFIRMED
    )
    assert (
        result.primary_resolution_action
        is not None
    )
    assert (
        result.primary_resolution_action
        .action_instance_id
        == "action:rollback"
    )
    assert result.effective_action_ids == [
        "action:rollback"
    ]


def test_recommendation_followed_but_ineffective(
    monkeypatch,
) -> None:
    _wire(monkeypatch)
    result = _derive(
        IncidentOutcomeUpdate(
            resolved_at=RESOLVED,
            actions=[
                ResponseActionObservationInput(
                    action_instance_id=(
                        "action:validate"
                    ),
                    response_plan_action_id=(
                        "plan:validate"
                    ),
                    action_type="validation",
                    title="Validate deployment",
                    result=(
                        ResponseActionResult
                        .NO_EFFECT
                    ),
                )
            ],
        )
    )
    action = result.actions_taken[0]
    plan_action = next(
        item
        for item in result.response_plan_actions
        if item.response_plan_action_id
        == "plan:validate"
    )

    assert action.effectiveness == (
        ActionEffectiveness.INEFFECTIVE
    )
    assert plan_action.follow_through == (
        RecommendationFollowThrough.FOLLOWED
    )
    assert plan_action.effectiveness == (
        ActionEffectiveness.INEFFECTIVE
    )


def test_multiple_simultaneous_actions_are_conservative(
    monkeypatch,
) -> None:
    _wire(
        monkeypatch,
        events={
            "event:rollback:1": _event(
                "event:rollback:1",
                rollback_of="event:deploy",
            ),
            "event:rollback:2": _event(
                "event:rollback:2",
                rollback_of="event:deploy",
            ),
        },
    )
    result = _derive(
        IncidentOutcomeUpdate(
            mitigated_at=MITIGATED,
            resolved_at=RESOLVED,
            actions=[
                _rollback_action(
                    action_id="action:1",
                    event_id="event:rollback:1",
                ),
                _rollback_action(
                    action_id="action:2",
                    event_id="event:rollback:2",
                ),
            ],
        )
    )

    assert result.primary_resolution_action is None
    assert result.rca_verdict == (
        RcaVerdict.INCONCLUSIVE
    )
    assert any(
        "Multiple simultaneous" in warning
        for warning in result.warnings
    )


def test_incomplete_evidence_keeps_rca_inconclusive(
    monkeypatch,
) -> None:
    _wire(monkeypatch)
    result = _derive(
        IncidentOutcomeUpdate(
            resolved_at=RESOLVED
        )
    )

    assert result.rca_verdict == (
        RcaVerdict.INCONCLUSIVE
    )
    assert result.final_root_cause is None


def test_reported_different_root_contradicts_original(
    monkeypatch,
) -> None:
    _wire(monkeypatch)
    result = _derive(
        IncidentOutcomeUpdate(
            resolved_at=RESOLVED,
            final_root_cause=(
                ReportedRootCause(
                    event_id="event:database",
                    entity_id="entity:database",
                    title="Database saturation",
                    evidence_ids=[
                        "evidence:responder"
                    ],
                )
            ),
        )
    )

    assert result.rca_verdict == (
        RcaVerdict.NOT_CONFIRMED
    )


def test_manual_final_root_cause_is_preserved(
    monkeypatch,
) -> None:
    _wire(monkeypatch)
    result = _derive(
        IncidentOutcomeUpdate(
            resolved_at=RESOLVED,
            rca_verdict=RcaVerdict.CONFIRMED,
            rca_confidence=0.99,
            final_root_cause=(
                ReportedRootCause(
                    event_id="event:commit",
                    entity_id="entity:payments",
                    title=(
                        "Responder-confirmed bad "
                        "payment retry change"
                    ),
                    evidence_ids=[
                        "evidence:responder"
                    ],
                )
            ),
        )
    )

    assert result.final_root_cause is not None
    assert result.final_root_cause.title == (
        "Responder-confirmed bad payment "
        "retry change"
    )
    assert result.final_root_cause.source.value == (
        "responder"
    )
    assert result.rca_confidence == 0.99


def test_missing_response_plan_degrades_cleanly(
    monkeypatch,
) -> None:
    _wire(monkeypatch)

    def no_plan(
        session,
        *,
        incident_id,
        source,
        warnings,
    ):
        warnings.append(
            "No response plan available."
        )
        return _analysis(), None

    monkeypatch.setattr(
        service,
        "_analysis_and_plan",
        no_plan,
    )
    result = _derive(
        IncidentOutcomeUpdate(
            resolved_at=RESOLVED
        )
    )

    assert result.response_plan_reference is None
    assert result.response_plan_actions == []
    assert "No response plan available." in (
        result.warnings
    )


def test_missing_causal_analysis_keeps_resolution(
    monkeypatch,
) -> None:
    _wire(monkeypatch)

    def no_analysis(
        session,
        *,
        incident_id,
        source,
        warnings,
    ):
        warnings.extend(
            [
                "No causal analysis available.",
                "No response plan available.",
            ]
        )
        return None, None

    monkeypatch.setattr(
        service,
        "_analysis_and_plan",
        no_analysis,
    )
    result = _derive(
        IncidentOutcomeUpdate(
            resolved_at=RESOLVED,
            resolution_summary=(
                "Responder closed the incident."
            ),
        )
    )

    assert result.causal_analysis_id is None
    assert result.original_root_cause is None
    assert result.rca_verdict == (
        RcaVerdict.INCONCLUSIVE
    )
    assert result.resolution_summary == (
        "Responder closed the incident."
    )


def test_resolved_incident_without_actions_has_no_primary(
    monkeypatch,
) -> None:
    _wire(monkeypatch)
    result = _derive(
        IncidentOutcomeUpdate(
            resolved_at=RESOLVED
        )
    )

    assert result.primary_resolution_action is None
    assert result.actions_taken == []
    assert any(
        "No responder actions" in warning
        for warning in result.warnings
    )


def test_time_to_mitigation_is_deterministic(
    monkeypatch,
) -> None:
    _wire(monkeypatch)
    result = _derive(
        IncidentOutcomeUpdate(
            mitigated_at=MITIGATED
        )
    )

    assert (
        result.time_to_mitigation_seconds
        == 600
    )


def test_time_to_resolution_is_deterministic(
    monkeypatch,
) -> None:
    _wire(monkeypatch)
    result = _derive(
        IncidentOutcomeUpdate(
            resolved_at=RESOLVED
        )
    )

    assert (
        result.time_to_resolution_seconds
        == 1200
    )


def test_invalid_timestamp_order_never_goes_negative(
    monkeypatch,
) -> None:
    _wire(monkeypatch)
    result = _derive(
        IncidentOutcomeUpdate(
            mitigated_at=datetime(
                2026,
                8,
                16,
                9,
                59,
                tzinfo=timezone.utc,
            ),
            resolved_at=RESOLVED,
        )
    )

    assert result.time_to_mitigation_seconds is None
    assert any(
        "negative duration" in warning
        for warning in result.warnings
    )


def test_historical_topology_snapshot_is_used(
    monkeypatch,
) -> None:
    loaded = []
    _wire(
        monkeypatch,
        loaded_snapshots=loaded,
    )
    _derive(
        IncidentOutcomeUpdate(
            resolved_at=RESOLVED
        )
    )

    assert loaded == [
        "snapshot:incident-time"
    ]


def test_action_matching_is_deterministic(
    monkeypatch,
) -> None:
    _wire(monkeypatch)
    update = IncidentOutcomeUpdate(
        resolved_at=RESOLVED,
        actions=[
            ResponseActionObservationInput(
                action_instance_id=(
                    "action:validate"
                ),
                response_plan_action_id=(
                    "plan:validate"
                ),
                action_type="validation",
                title="Validate deployment",
                result=(
                    ResponseActionResult
                    .SUCCESSFUL
                ),
            )
        ],
    )

    first = _derive(update)
    second = _derive(update)

    assert first.model_dump() == second.model_dump()
    assert first.recommendations_followed == [
        "plan:validate"
    ]
    assert first.recommendations_unknown == [
        "plan:rollback"
    ]


def test_outcome_persistence_is_idempotent(
    monkeypatch,
) -> None:
    _wire(monkeypatch)
    engine = create_engine(
        "sqlite:///:memory:"
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as session:
        update = IncidentOutcomeUpdate(
            resolved_at=RESOLVED,
            resolution_summary=(
                "Rollback restored service."
            ),
        )
        first = service.record_incident_outcome(
            session,
            incident_id="incident:1",
            update=update,
        )
        second = service.record_incident_outcome(
            session,
            incident_id="incident:1",
            update=update,
        )
        count = session.scalar(
            select(func.count())
            .select_from(
                IncidentOutcomeRecord
            )
        )

    assert count == 1
    assert first.model_dump() == second.model_dump()


def test_missing_incident_returns_controlled_404(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        outcome_api,
        "get_incident_outcome",
        lambda session, *, incident_id: (
            (_ for _ in ()).throw(
                ValueError(
                    "Incident not found: missing"
                )
            )
        ),
    )

    with pytest.raises(HTTPException) as exc:
        outcome_api.get_outcome(
            "missing",
            session=object(),
        )

    assert exc.value.status_code == 404


def test_existing_13c_14a_14b_api_functions_unchanged(
    monkeypatch,
) -> None:
    causal = object()
    context = object()
    plan = object()

    monkeypatch.setattr(
        causal_api,
        "latest_causal_analysis",
        lambda session, *, incident_id:
            causal,
    )
    monkeypatch.setattr(
        context_api,
        "build_incident_operational_context",
        lambda *, session, incident_id:
            context,
    )
    monkeypatch.setattr(
        response_api,
        "build_incident_response_plan",
        lambda *, session, incident_id:
            plan,
    )

    assert causal_api.latest(
        "incident:1",
        session=object(),
    ) is causal
    assert context_api.get_incident_operational_context(
        "incident:1",
        session=object(),
    ) is context
    assert response_api.get_incident_response_plan(
        "incident:1",
        session=object(),
    ) is plan
