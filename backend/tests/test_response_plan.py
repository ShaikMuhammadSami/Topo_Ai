from datetime import (
    datetime,
    timezone,
)
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.api.causal_rca as causal_api
import app.api.incident_context as context_api
import app.api.ownership as ownership_api
import app.api.response_plan as response_api
import app.services.response_plan as response_service
from app.models.causal_rca import (
    CausalAnalysisResponse,
    CausalChainStep,
    CausalConfidenceLevel,
    CausalEdgeType,
    CausalHypothesis,
    CausalNode,
    CausalNodeType,
)
from app.models.change_events import (
    ChangeEventKind,
    ChangeEventRiskLevel,
    ChangeEventSource,
    ChangeEventView,
)
from app.models.incident_context import (
    IncidentOperationalContext,
)
from app.models.ownership import (
    BusinessImpactLevel,
    EntityOwnershipResolution,
    IncidentOwnershipImpact,
    OwnershipSource,
    ServiceCriticality,
)
from app.models.response_plan import (
    ResponseActionCategory,
    ResponsePriority,
)
from app.models.topology import (
    Entity,
    EntityType,
    GraphSnapshot,
)


NOW = datetime(
    2026,
    8,
    16,
    10,
    0,
    tzinfo=timezone.utc,
)


def _entity(
    *,
    runbook_url: str | None = None,
) -> Entity:
    labels = {}

    if runbook_url:
        labels["topo.ai/runbook"] = (
            runbook_url
        )

    return Entity(
        id="entity:payments",
        entity_type=EntityType.APPLICATION,
        kind="KubernetesDeployment",
        name="payments-api",
        source_system="kubernetes",
        environment="production",
        observed_at=NOW,
        labels=labels,
        properties={
            "namespace": "payments"
        },
    )


def _snapshot(
    snapshot_id: str = "snapshot-historical",
    *,
    runbook_url: str | None = None,
) -> GraphSnapshot:
    return GraphSnapshot(
        snapshot_id=snapshot_id,
        collected_at=NOW,
        collector_name="test",
        collector_version="1.0",
        scope={"cluster": "production"},
        entities=[
            _entity(
                runbook_url=runbook_url
            )
        ],
    )


def _analysis(
    *,
    confidence: float = 0.84,
    minutes_before_incident: (
        float | None
    ) = 5.0,
    snapshot_id: str = "snapshot-historical",
    evidence_ids: list[str] | None = None,
) -> CausalAnalysisResponse:
    evidence = (
        evidence_ids
        if evidence_ids is not None
        else ["evidence:temporal"]
    )

    level = (
        CausalConfidenceLevel.HIGH
        if confidence >= 0.75
        else (
            CausalConfidenceLevel.MEDIUM
            if confidence >= 0.5
            else CausalConfidenceLevel.LOW
        )
    )

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
        score=confidence * 100,
        confidence=confidence,
        confidence_level=level,
        minutes_before_incident=(
            minutes_before_incident
        ),
        summary="Test causal chain.",
        supporting_evidence_ids=evidence,
        chain=[
            CausalChainStep(
                order=1,
                node_id="event|event:commit",
                node_type=(
                    CausalNodeType.CHANGE_EVENT
                ),
                label="Payment retry change",
            ),
            CausalChainStep(
                order=2,
                node_id="event|event:deploy",
                node_type=(
                    CausalNodeType.CHANGE_EVENT
                ),
                label="Deploy payments",
                relation_from_previous=(
                    CausalEdgeType.PRECEDES
                ),
                confidence_from_previous=0.9,
            ),
            CausalChainStep(
                order=3,
                node_id=(
                    "entity|entity:payments"
                ),
                node_type=CausalNodeType.ENTITY,
                label="payments-api",
                relation_from_previous=(
                    CausalEdgeType
                    .TOUCHES_ENTITY
                ),
                confidence_from_previous=0.95,
            ),
        ],
    )

    return CausalAnalysisResponse(
        analysis_id="causal-analysis:1",
        incident_id="incident:1",
        incident_title="Payments incident",
        incident_time=NOW.isoformat(),
        topology_snapshot_id=snapshot_id,
        algorithm_version="13c-causal-v1",
        generated_at=NOW.isoformat(),
        parameters={},
        candidate_count=2,
        node_count=3,
        edge_count=2,
        evidence_count=len(evidence),
        hypothesis_count=1,
        top_hypothesis=hypothesis,
        hypotheses=[hypothesis],
        nodes=[
            CausalNode(
                node_id="event|event:commit",
                node_type=(
                    CausalNodeType.CHANGE_EVENT
                ),
                label="Payment retry change",
                event_id="event:commit",
                occurred_at=(
                    "2026-08-16T09:50:00+00:00"
                ),
                attributes={
                    "source": "github",
                    "kind": "code",
                },
            ),
            CausalNode(
                node_id="event|event:deploy",
                node_type=(
                    CausalNodeType.CHANGE_EVENT
                ),
                label="Deploy payments",
                event_id="event:deploy",
                occurred_at=(
                    "2026-08-16T09:55:00+00:00"
                ),
                attributes={
                    "source": "github_actions",
                    "kind": "deployment",
                },
            ),
            CausalNode(
                node_id=(
                    "entity|entity:payments"
                ),
                node_type=CausalNodeType.ENTITY,
                label="payments-api",
                entity_id="entity:payments",
            ),
        ],
    )


def _event(
    *,
    event_id: str,
    title: str,
    source: ChangeEventSource,
    kind: ChangeEventKind,
    metadata: dict | None = None,
    repository: str | None = None,
    commit_sha: str | None = None,
    release_version: str | None = None,
) -> ChangeEventView:
    return ChangeEventView(
        event_id=event_id,
        event_fingerprint=(
            f"fingerprint:{event_id}"
        ),
        source=source,
        kind=kind,
        external_id=event_id,
        origin_change_id=None,
        title=title,
        summary=None,
        actor="deployer",
        occurred_at=(
            "2026-08-16T09:55:00+00:00"
        ),
        received_at=(
            "2026-08-16T09:56:00+00:00"
        ),
        environment="production",
        provider="github",
        account_id=None,
        region=None,
        cluster_name="production",
        namespace="payments",
        repository=repository,
        commit_sha=commit_sha,
        pipeline_name="deploy-payments",
        release_version=release_version,
        terraform_workspace=None,
        risk_score=80,
        risk_level=ChangeEventRiskLevel.HIGH,
        status="observed",
        observation_count=1,
        metadata=metadata or {},
        raw_payload={},
        agent_id=None,
        links=[],
        created_at=NOW.isoformat(),
        updated_at=NOW.isoformat(),
    )


def _events(
    *,
    target_kind: ChangeEventKind = (
        ChangeEventKind.DEPLOYMENT
    ),
    target_metadata: dict | None = None,
) -> dict[str, ChangeEventView]:
    return {
        "event:commit": _event(
            event_id="event:commit",
            title="Payment retry change",
            source=ChangeEventSource.GITHUB,
            kind=ChangeEventKind.CODE,
            repository="company/payments",
            commit_sha="abc123",
        ),
        "event:deploy": _event(
            event_id="event:deploy",
            title="Deploy payments",
            source=(
                ChangeEventSource
                .GITHUB_ACTIONS
            ),
            kind=target_kind,
            metadata=target_metadata,
            repository="company/payments",
            commit_sha="abc123",
            release_version="2026.08.16.1",
        ),
    }


def _ownership(
    *,
    resolved: bool = True,
) -> EntityOwnershipResolution:
    return EntityOwnershipResolution(
        resolved=resolved,
        entity_id="entity:payments",
        entity_kind="KubernetesDeployment",
        entity_name="payments-api",
        service_name="payments-api",
        cluster_name="production",
        namespace="payments",
        owner_team=(
            "payments"
            if resolved
            else None
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
        repository_url=(
            "https://github.example/payments"
            if resolved
            else None
        ),
        business_capability=(
            "checkout"
            if resolved
            else None
        ),
        criticality=(
            ServiceCriticality.TIER_1
            if resolved
            else None
        ),
        source=(
            OwnershipSource.MANUAL
            if resolved
            else OwnershipSource.UNRESOLVED
        ),
        confidence=(1.0 if resolved else 0.0),
        matched_ownership_id=(
            "ownership:payments"
            if resolved
            else None
        ),
        resolution_reason=(
            "Resolved from stored mapping."
            if resolved
            else "No ownership found."
        ),
    )


def _impact() -> IncidentOwnershipImpact:
    return IncidentOwnershipImpact(
        incident_id="incident:1",
        business_impact_level=(
            BusinessImpactLevel.CRITICAL
        ),
        affected_entity_count=3,
        resolved_entity_count=2,
        unresolved_entity_count=1,
        affected_team_count=2,
        affected_capability_count=1,
        highest_criticality=(
            ServiceCriticality.TIER_1
        ),
        owner_teams=["payments", "platform"],
        business_capabilities=["checkout"],
        oncall_contacts=[
            "pagerduty:payments"
        ],
        repositories=[
            "https://github.example/payments"
        ],
        routing_recommendation=(
            "Route to pagerduty:payments."
        ),
        warnings=[
            "1 affected entities have "
            "unresolved ownership."
        ],
    )


def _context(
    *,
    resolved: bool = True,
    escalation_targets: (
        list[str] | None
    ) = None,
) -> IncidentOperationalContext:
    ownership = _ownership(
        resolved=resolved
    )

    return IncidentOperationalContext(
        incident_id="incident:1",
        causal_analysis_id=(
            "causal-analysis:1"
        ),
        root_event_id="event:commit",
        root_event_title=(
            "Payment retry change"
        ),
        root_event_source="github",
        root_entity_id="entity:payments",
        causal_confidence=0.84,
        root_cause_ownership=ownership,
        overall_business_impact=_impact(),
        escalation_targets=(
            escalation_targets
            if escalation_targets is not None
            else [
                "pagerduty:payments",
                "payments@example.com",
                "payments",
            ]
        ),
        warnings=(
            []
            if resolved
            else [
                "Root-cause ownership is "
                "unresolved."
            ]
        ),
    )


def _wire(
    monkeypatch,
    *,
    analysis: CausalAnalysisResponse,
    context: IncidentOperationalContext,
    snapshot: GraphSnapshot,
    events: dict[str, ChangeEventView],
    loaded_snapshots: list[str] | None = None,
) -> None:
    monkeypatch.setattr(
        response_service,
        "load_incident_record",
        lambda *, session, incident_id:
            SimpleNamespace(
                severity="critical"
            ),
    )
    monkeypatch.setattr(
        response_service,
        "latest_causal_analysis",
        lambda session, *, incident_id:
            analysis,
    )
    monkeypatch.setattr(
        response_service,
        "build_incident_operational_context",
        lambda *, session, incident_id:
            context,
    )

    def load_snapshot(
        *,
        session,
        snapshot_id,
    ):
        if loaded_snapshots is not None:
            loaded_snapshots.append(
                snapshot_id
            )

        return snapshot

    monkeypatch.setattr(
        response_service,
        "load_topology_snapshot",
        load_snapshot,
    )
    monkeypatch.setattr(
        response_service,
        "load_change_event",
        lambda session, *, event_id:
            (
                SimpleNamespace(
                    event_id=event_id
                )
                if event_id in events
                else None
            ),
    )
    monkeypatch.setattr(
        response_service,
        "change_event_view",
        lambda session, *, record:
            events[record.event_id],
    )


def test_strong_causal_plan_with_resolved_owner(
    monkeypatch,
) -> None:
    analysis = _analysis()
    context = _context()

    _wire(
        monkeypatch,
        analysis=analysis,
        context=context,
        snapshot=_snapshot(),
        events=_events(),
    )

    result = (
        response_service
        .build_incident_response_plan(
            session=object(),
            incident_id="incident:1",
        )
    )

    assert result.root_cause.event_id == (
        "event:commit"
    )
    assert result.root_cause.target_event_id == (
        "event:deploy"
    )
    assert result.root_cause.entity_id == (
        "entity:payments"
    )
    assert result.root_cause.causal_confidence == (
        0.84
    )
    assert result.primary_owner is not None
    assert result.primary_owner.owner_team == (
        "payments"
    )
    assert result.recommended_actions
    assert all(
        action.evidence_event_ids
        for action in result.recommended_actions
    )


def test_deployment_rollback_candidate_requires_approval(
    monkeypatch,
) -> None:
    _wire(
        monkeypatch,
        analysis=_analysis(),
        context=_context(),
        snapshot=_snapshot(),
        events=_events(),
    )

    result = (
        response_service
        .build_incident_response_plan(
            session=object(),
            incident_id="incident:1",
        )
    )

    assert result.rollback_candidate.available
    assert (
        result.rollback_candidate
        .change_event_id
        == "event:deploy"
    )
    assert (
        result.rollback_candidate
        .requires_human_approval
        is True
    )

    rollback_actions = [
        action
        for action in result.recommended_actions
        if action.category
        == ResponseActionCategory
        .ROLLBACK_CANDIDATE
    ]

    assert len(rollback_actions) == 1
    assert (
        rollback_actions[0]
        .requires_human_approval
        is True
    )


def test_weak_confidence_is_conservative(
    monkeypatch,
) -> None:
    analysis = _analysis(
        confidence=0.30
    )

    _wire(
        monkeypatch,
        analysis=analysis,
        context=_context(),
        snapshot=_snapshot(),
        events=_events(),
    )

    result = (
        response_service
        .build_incident_response_plan(
            session=object(),
            incident_id="incident:1",
        )
    )

    assert not result.rollback_candidate.available
    assert result.validation_checks
    assert all(
        action.category
        not in {
            ResponseActionCategory.MITIGATE,
            ResponseActionCategory
            .ROLLBACK_CANDIDATE,
        }
        for action in result.recommended_actions
    )
    assert any(
        "Causal confidence is low"
        in warning
        for warning in result.warnings
    )


def test_unresolved_owner_keeps_business_context(
    monkeypatch,
) -> None:
    context = _context(
        resolved=False,
        escalation_targets=["platform"],
    )

    _wire(
        monkeypatch,
        analysis=_analysis(),
        context=context,
        snapshot=_snapshot(),
        events=_events(),
    )

    result = (
        response_service
        .build_incident_response_plan(
            session=object(),
            incident_id="incident:1",
        )
    )

    assert result.primary_owner is not None
    assert result.primary_owner.resolved is False
    assert (
        result.primary_owner.owner_team
        is None
    )
    assert (
        result.business_context
        .business_impact_level
        == BusinessImpactLevel.CRITICAL
    )
    assert result.recommended_actions
    assert result.escalation_targets == [
        "platform"
    ]
    assert any(
        "no owner was invented"
        in warning
        for warning in result.warnings
    )


def test_missing_runbook_returns_empty_list(
    monkeypatch,
) -> None:
    _wire(
        monkeypatch,
        analysis=_analysis(),
        context=_context(),
        snapshot=_snapshot(),
        events=_events(),
    )

    result = (
        response_service
        .build_incident_response_plan(
            session=object(),
            incident_id="incident:1",
        )
    )

    assert result.runbooks == []
    assert all(
        action.runbook_url is None
        for action in result.recommended_actions
    )


def test_existing_runbook_metadata_is_surfaced(
    monkeypatch,
) -> None:
    runbook_url = (
        "https://docs.example/payments/runbook"
    )

    events = _events(
        target_metadata={
            "runbook_url": runbook_url
        }
    )

    _wire(
        monkeypatch,
        analysis=_analysis(),
        context=_context(),
        snapshot=_snapshot(
            runbook_url=runbook_url
        ),
        events=events,
    )

    result = (
        response_service
        .build_incident_response_plan(
            session=object(),
            incident_id="incident:1",
        )
    )

    assert len(result.runbooks) == 1
    assert result.runbooks[0].url == (
        runbook_url
    )
    assert any(
        action.runbook_url == runbook_url
        for action in result.recommended_actions
    )


def test_historical_topology_snapshot_is_used(
    monkeypatch,
) -> None:
    loaded: list[str] = []
    snapshot_id = "snapshot-incident-time"

    _wire(
        monkeypatch,
        analysis=_analysis(
            snapshot_id=snapshot_id
        ),
        context=_context(),
        snapshot=_snapshot(snapshot_id),
        events=_events(),
        loaded_snapshots=loaded,
    )

    response_service.build_incident_response_plan(
        session=object(),
        incident_id="incident:1",
    )

    assert loaded == [snapshot_id]


def test_response_plan_is_deterministic(
    monkeypatch,
) -> None:
    _wire(
        monkeypatch,
        analysis=_analysis(),
        context=_context(),
        snapshot=_snapshot(),
        events=_events(),
    )

    first = (
        response_service
        .build_incident_response_plan(
            session=object(),
            incident_id="incident:1",
        )
    )
    second = (
        response_service
        .build_incident_response_plan(
            session=object(),
            incident_id="incident:1",
        )
    )

    assert first.model_dump(mode="json") == (
        second.model_dump(mode="json")
    )


def test_action_deduplication_merges_evidence(
) -> None:
    first = response_service._action(
        analysis_id="analysis:1",
        category=(
            ResponseActionCategory.INVESTIGATE
        ),
        priority=ResponsePriority.HIGH,
        title="Inspect exact deployment",
        description="First description.",
        reason="First reason.",
        entity_ids=["entity:1"],
        event_ids=["event:1"],
        evidence_ids=["evidence:1"],
    )
    duplicate = response_service._action(
        analysis_id="analysis:1",
        category=(
            ResponseActionCategory.INVESTIGATE
        ),
        priority=ResponsePriority.HIGH,
        title="  INSPECT exact deployment ",
        description="Second description.",
        reason="Second reason.",
        entity_ids=["entity:1"],
        event_ids=["event:1"],
        evidence_ids=["evidence:2"],
    )

    values = (
        response_service
        ._deduplicate_actions(
            [first, duplicate]
        )
    )

    assert len(values) == 1
    assert values[0].evidence_ids == [
        "evidence:1",
        "evidence:2",
    ]


def test_escalation_targets_are_deduplicated(
    monkeypatch,
) -> None:
    context = _context(
        escalation_targets=[
            "PagerDuty:Payments",
            "pagerduty:payments",
            "payments@example.com",
            "PAYMENTS@example.com",
            "Payments",
            "payments",
        ]
    )

    _wire(
        monkeypatch,
        analysis=_analysis(),
        context=context,
        snapshot=_snapshot(),
        events=_events(),
    )

    result = (
        response_service
        .build_incident_response_plan(
            session=object(),
            incident_id="incident:1",
        )
    )

    assert result.escalation_targets == [
        "PagerDuty:Payments",
        "payments@example.com",
        "Payments",
    ]


def test_missing_causal_analysis_returns_404(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        response_api,
        "build_incident_response_plan",
        lambda *, session, incident_id:
            (_ for _ in ()).throw(
                ValueError(
                    "No causal analysis exists "
                    "for this incident."
                )
            ),
    )

    with pytest.raises(HTTPException) as raised:
        response_api.get_incident_response_plan(
            incident_id="incident:missing",
            session=object(),
        )

    assert raised.value.status_code == 404
    assert raised.value.detail == (
        "No causal analysis exists for this "
        "incident."
    )


def test_existing_13c_and_14a_routes_unchanged(
) -> None:
    causal_paths = {
        route.path
        for route in causal_api
        .incident_router.routes
    }

    assert (
        "/api/v1/incidents/"
        "{incident_id}/causal-rca"
        in causal_paths
    )
    assert (
        "/api/v1/incidents/"
        "{incident_id}/causal-rca/latest"
        in causal_paths
    )
    assert any(
        route.path
        == (
            "/api/v1/incidents/"
            "{incident_id}/operational-context"
        )
        for route in context_api.router.routes
    )
    assert any(
        route.path
        == (
            "/api/v1/incidents/"
            "{incident_id}/ownership-impact"
        )
        for route in ownership_api.router.routes
    )
