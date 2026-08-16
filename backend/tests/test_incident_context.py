from datetime import (
    datetime,
    timezone,
)

import pytest
from fastapi import HTTPException

import app.api.incident_context as context_api
import app.api.ownership as ownership_api
import app.services.incident_context as context_service
from app.models.causal_rca import (
    CausalAnalysisResponse,
    CausalChainStep,
    CausalConfidenceLevel,
    CausalEdgeType,
    CausalHypothesis,
    CausalNode,
    CausalNodeType,
)
from app.models.ownership import (
    BusinessImpactLevel,
    EntityOwnershipResolution,
    IncidentOwnershipImpact,
    OwnershipSource,
    ServiceCriticality,
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
    entity_id: str,
    name: str,
) -> Entity:
    return Entity(
        id=entity_id,
        entity_type=EntityType.APPLICATION,
        kind="KubernetesDeployment",
        name=name,
        source_system="kubernetes",
        environment="production",
        observed_at=NOW,
        labels={},
        properties={
            "namespace": "payments"
        },
    )


def _snapshot(
    snapshot_id: str = (
        "snapshot-historical"
    ),
) -> GraphSnapshot:
    return GraphSnapshot(
        snapshot_id=snapshot_id,
        collected_at=NOW,
        collector_name="test",
        collector_version="1.0",
        scope={
            "cluster": "production"
        },
        entities=[
            _entity(
                "entity:root-service",
                "root-service",
            ),
            _entity(
                "entity:affected-service",
                "affected-service",
            ),
        ],
    )


def _analysis(
    snapshot_id: str | None = (
        "snapshot-historical"
    ),
) -> CausalAnalysisResponse:
    hypothesis = CausalHypothesis(
        hypothesis_id="hypothesis:1",
        rank=1,
        root_event_id="event:commit",
        root_source="github",
        root_title="Payment retry change",
        target_event_id="event:deploy",
        target_title="Deploy payments",
        affected_entity_id=(
            "entity:affected-service"
        ),
        score=84.0,
        confidence=0.84,
        confidence_level=(
            CausalConfidenceLevel.HIGH
        ),
        summary="Test causal chain.",
        chain=[
            CausalChainStep(
                order=1,
                node_id="event|event:commit",
                node_type=(
                    CausalNodeType
                    .CHANGE_EVENT
                ),
                label="Payment retry change",
            ),
            CausalChainStep(
                order=2,
                node_id="event|event:deploy",
                node_type=(
                    CausalNodeType
                    .CHANGE_EVENT
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
                    "entity|"
                    "entity:root-service"
                ),
                node_type=(
                    CausalNodeType.ENTITY
                ),
                label="root-service",
                relation_from_previous=(
                    CausalEdgeType
                    .TOUCHES_ENTITY
                ),
                confidence_from_previous=0.95,
            ),
            CausalChainStep(
                order=4,
                node_id=(
                    "entity|"
                    "entity:affected-service"
                ),
                node_type=(
                    CausalNodeType.ENTITY
                ),
                label="affected-service",
                relation_from_previous=(
                    CausalEdgeType
                    .TOPOLOGY_PATH
                ),
                confidence_from_previous=0.75,
            ),
            CausalChainStep(
                order=5,
                node_id=(
                    "incident|incident:1"
                ),
                node_type=(
                    CausalNodeType.INCIDENT
                ),
                label="Payments incident",
                relation_from_previous=(
                    CausalEdgeType
                    .CULMINATES_IN
                ),
                confidence_from_previous=1.0,
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
        node_count=5,
        edge_count=4,
        evidence_count=4,
        hypothesis_count=1,
        top_hypothesis=hypothesis,
        hypotheses=[hypothesis],
        nodes=[
            CausalNode(
                node_id=(
                    "entity|"
                    "entity:root-service"
                ),
                node_type=(
                    CausalNodeType.ENTITY
                ),
                label="root-service",
                entity_id=(
                    "entity:root-service"
                ),
            ),
            CausalNode(
                node_id=(
                    "entity|"
                    "entity:affected-service"
                ),
                node_type=(
                    CausalNodeType.ENTITY
                ),
                label="affected-service",
                entity_id=(
                    "entity:affected-service"
                ),
            ),
        ],
    )


def _impact(
    *,
    oncall_contacts: list[str] | None = None,
    owner_teams: list[str] | None = None,
) -> IncidentOwnershipImpact:
    teams = owner_teams or [
        "payments",
        "platform",
    ]

    return IncidentOwnershipImpact(
        incident_id="incident:1",
        business_impact_level=(
            BusinessImpactLevel.HIGH
        ),
        affected_entity_count=2,
        resolved_entity_count=1,
        unresolved_entity_count=1,
        affected_team_count=len(teams),
        affected_capability_count=1,
        highest_criticality=(
            ServiceCriticality.TIER_1
        ),
        owner_teams=teams,
        business_capabilities=[
            "checkout"
        ],
        oncall_contacts=(
            oncall_contacts
            or ["pagerduty:payments"]
        ),
        repositories=[
            "https://github.example/payments"
        ],
        routing_recommendation=(
            "Route the incident to "
            "pagerduty:payments."
        ),
        warnings=[
            "1 affected entities have "
            "unresolved ownership."
        ],
    )


def _ownership(
    *,
    resolved: bool,
) -> EntityOwnershipResolution:
    return EntityOwnershipResolution(
        resolved=resolved,
        entity_id="entity:root-service",
        entity_kind="KubernetesDeployment",
        entity_name="root-service",
        service_name="root-service",
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
        confidence=(
            1.0
            if resolved
            else 0.0
        ),
        matched_ownership_id=(
            "ownership:payments"
            if resolved
            else None
        ),
        resolution_reason=(
            "Resolved from a stored "
            "ownership mapping."
            if resolved
            else "No ownership found."
        ),
    )


def _wire_context(
    monkeypatch,
    *,
    analysis: CausalAnalysisResponse,
    impact: IncidentOwnershipImpact,
    snapshot: GraphSnapshot,
    ownership: EntityOwnershipResolution,
):
    monkeypatch.setattr(
        context_service,
        "latest_causal_analysis",
        lambda session, *, incident_id:
            analysis,
    )
    monkeypatch.setattr(
        context_service,
        "calculate_incident_ownership_impact",
        lambda *, session, incident_id:
            impact,
    )
    monkeypatch.setattr(
        context_service,
        "load_topology_snapshot",
        lambda *, session, snapshot_id:
            snapshot,
    )
    monkeypatch.setattr(
        context_service,
        "resolve_entity_ownership",
        lambda *, session, snapshot, entity:
            ownership,
    )


def test_causal_root_entity_resolves_ownership(
    monkeypatch,
) -> None:
    analysis = _analysis()
    impact = _impact()
    snapshot = _snapshot()
    ownership = _ownership(
        resolved=True
    )
    selected = {}

    _wire_context(
        monkeypatch,
        analysis=analysis,
        impact=impact,
        snapshot=snapshot,
        ownership=ownership,
    )

    def resolve(
        *,
        session,
        snapshot,
        entity,
    ):
        selected["entity_id"] = entity.id
        return ownership

    monkeypatch.setattr(
        context_service,
        "resolve_entity_ownership",
        resolve,
    )

    result = (
        context_service
        .build_incident_operational_context(
            session=object(),
            incident_id="incident:1",
        )
    )

    assert result.root_entity_id == (
        "entity:root-service"
    )
    assert selected["entity_id"] == (
        "entity:root-service"
    )
    assert (
        result.root_entity_id
        != analysis.top_hypothesis
        .affected_entity_id
    )
    assert result.root_cause_ownership == (
        ownership
    )
    assert result.root_event_id == (
        "event:commit"
    )


def test_unresolved_root_ownership_is_explicit(
    monkeypatch,
) -> None:
    _wire_context(
        monkeypatch,
        analysis=_analysis(),
        impact=_impact(),
        snapshot=_snapshot(),
        ownership=_ownership(
            resolved=False
        ),
    )

    result = (
        context_service
        .build_incident_operational_context(
            session=object(),
            incident_id="incident:1",
        )
    )

    assert (
        result.root_cause_ownership
        is not None
    )
    assert (
        result.root_cause_ownership
        .resolved
        is False
    )
    assert any(
        "Root-cause ownership is unresolved"
        in warning
        for warning in result.warnings
    )


def test_business_impact_survives_unresolved_root(
    monkeypatch,
) -> None:
    impact = _impact()

    _wire_context(
        monkeypatch,
        analysis=_analysis(),
        impact=impact,
        snapshot=_snapshot(),
        ownership=_ownership(
            resolved=False
        ),
    )

    result = (
        context_service
        .build_incident_operational_context(
            session=object(),
            incident_id="incident:1",
        )
    )

    assert (
        result.overall_business_impact
        == impact
    )
    assert (
        result.overall_business_impact
        .affected_entity_count
        == 2
    )


def test_historical_causal_snapshot_is_used(
    monkeypatch,
) -> None:
    analysis = _analysis(
        "snapshot-incident-time"
    )
    historical = _snapshot(
        "snapshot-incident-time"
    )
    loaded_snapshot_ids = []
    resolved_snapshots = []

    _wire_context(
        monkeypatch,
        analysis=analysis,
        impact=_impact(),
        snapshot=historical,
        ownership=_ownership(
            resolved=True
        ),
    )

    def load(
        *,
        session,
        snapshot_id,
    ):
        loaded_snapshot_ids.append(
            snapshot_id
        )
        return historical

    def resolve(
        *,
        session,
        snapshot,
        entity,
    ):
        resolved_snapshots.append(
            snapshot.snapshot_id
        )
        return _ownership(
            resolved=True
        )

    monkeypatch.setattr(
        context_service,
        "load_topology_snapshot",
        load,
    )
    monkeypatch.setattr(
        context_service,
        "resolve_entity_ownership",
        resolve,
    )

    context_service.build_incident_operational_context(
        session=object(),
        incident_id="incident:1",
    )

    assert loaded_snapshot_ids == [
        "snapshot-incident-time"
    ]
    assert resolved_snapshots == [
        "snapshot-incident-time"
    ]


def test_escalation_targets_are_deduplicated(
    monkeypatch,
) -> None:
    impact = _impact(
        oncall_contacts=[
            "PAGERDUTY:PAYMENTS",
            "payments@example.com",
        ],
        owner_teams=[
            "Payments",
            "platform",
        ],
    )

    _wire_context(
        monkeypatch,
        analysis=_analysis(),
        impact=impact,
        snapshot=_snapshot(),
        ownership=_ownership(
            resolved=True
        ),
    )

    result = (
        context_service
        .build_incident_operational_context(
            session=object(),
            incident_id="incident:1",
        )
    )

    assert result.escalation_targets == [
        "pagerduty:payments",
        "payments@example.com",
        "payments",
        "platform",
    ]


def test_missing_causal_analysis_returns_404(
    monkeypatch,
) -> None:
    def missing(
        *,
        session,
        incident_id,
    ):
        raise ValueError(
            "No causal analysis exists for "
            "this incident."
        )

    monkeypatch.setattr(
        context_api,
        "build_incident_operational_context",
        missing,
    )

    with pytest.raises(
        HTTPException
    ) as raised:
        context_api.get_incident_operational_context(
            incident_id="incident:missing",
            session=object(),
        )

    assert raised.value.status_code == 404
    assert raised.value.detail == (
        "No causal analysis exists for "
        "this incident."
    )


def test_existing_ownership_impact_endpoint_unchanged(
    monkeypatch,
) -> None:
    impact = _impact()
    calls = []

    def calculate(
        *,
        session,
        incident_id,
    ):
        calls.append(incident_id)
        return impact

    monkeypatch.setattr(
        ownership_api,
        "calculate_incident_ownership_impact",
        calculate,
    )

    result = (
        ownership_api
        .get_incident_ownership_impact(
            incident_id="incident:1",
            session=object(),
        )
    )

    assert result == impact
    assert calls == ["incident:1"]
    assert any(
        route.path
        == (
            "/api/v1/incidents/"
            "{incident_id}/ownership-impact"
        )
        for route in ownership_api.router.routes
    )
