from __future__ import annotations
from domain_tenant_fixtures import TEST_CONTEXT, TEST_HEADERS, TEST_TENANT

import inspect
from datetime import (
    datetime,
    timedelta,
    timezone,
)

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.api.incident_briefing as briefing_api
import app.services.incident_briefing as service
import app.services.response_intelligence as response_service
from app.main import app
from app.models.causal_rca import (
    CausalAnalysisResponse,
    CausalChainStep,
    CausalConfidenceLevel,
    CausalEdge,
    CausalEdgeType,
    CausalEvidenceItem,
    CausalEvidenceType,
    CausalHypothesis,
    CausalNode,
    CausalNodeType,
)
from app.models.incident_context import (
    IncidentOperationalContext,
)
from app.models.incident_memory import (
    HistoricalAiStatus,
    HistoricalAnalysisContext,
    HistoricalIncidentMatch,
    HistoricalResolutionAction,
    HistoricalResolutionPattern,
    HistoricalResolutionSummary,
    HistoricalSupportLevel,
    IncidentHistoricalIntelligence,
    SimilarityScoreBreakdown,
)
from app.models.incident_outcome import (
    ActionEffectiveness,
    IncidentOutcome,
    IncidentResponseActionObservation,
    OutcomeFactSource,
    OutcomeRootCause,
    RcaVerdict,
    ResponseActionResult,
)
from app.models.incident_records import (
    IncidentRecordView,
    IncidentSeverity,
    IncidentStatus,
)
from app.models.ownership import (
    AffectedEntityOwnership,
    BusinessImpactLevel,
    EntityOwnershipResolution,
    IncidentOwnershipImpact,
    OwnershipSource,
    ServiceCriticality,
)
from app.models.recommendations import (
    RecommendationRisk,
)
from app.models.response_plan import (
    IncidentResponseAction,
    IncidentResponsePlan,
    ResponseActionCategory,
    ResponsePriority,
    ResponseRootCause,
    RollbackCandidate,
)
from app.models.response_intelligence import (
    HistoricalActionSupportLevel,
)
from app.models.topology import (
    Entity,
    EntityType,
    GraphSnapshot,
    Relationship,
    RelationshipType,
)
from app.security.api_tokens import (
    ApiTokenAuthMiddleware,
)
from app.services.llm_client import (
    OpenAITextResult,
)

NOW = datetime(
    2026,
    8,
    16,
    10,
    0,
    tzinfo=timezone.utc,
)


from domain_tenant_fixtures import owned_world_fixture

@owned_world_fixture
def _incident(
    status: IncidentStatus = IncidentStatus.OPEN,
) -> IncidentRecordView:
    return IncidentRecordView(
        incident_id="incident:1",
        fingerprint="fingerprint:1",
        status=status,
        severity=IncidentSeverity.CRITICAL,
        title="Checkout degradation",
        summary="Checkout requests are failing.",
        cluster_name="production",
        namespace="payments",
        primary_signal_id="signal:1",
        latest_signal_id="signal:1",
        topology_snapshot_id=(
            "snapshot:incident-time"
        ),
        affected_entity_id="entity:checkout",
        affected_object_kind="KubernetesService",
        affected_object_name="checkout-api",
        first_observed_at=NOW,
        last_observed_at=(
            NOW + timedelta(minutes=5)
        ),
        latest_analysis_id="legacy-analysis:1",
        top_hypothesis_title="Legacy hypothesis",
        top_hypothesis_score=0.2,
        recovery_status=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _entity(
    entity_id: str,
    name: str,
    kind: str,
) -> Entity:
    return Entity(
        id=entity_id,
        entity_type=EntityType.APPLICATION,
        kind=kind,
        name=name,
        source_system="kubernetes",
        environment="production",
        observed_at=NOW,
        properties={"namespace": "payments"},
    )


@owned_world_fixture
def _snapshot(
    snapshot_id: str = "snapshot:incident-time",
) -> GraphSnapshot:
    return GraphSnapshot(
        snapshot_id=snapshot_id,
        collected_at=NOW,
        collector_name="test",
        collector_version="1.0",
        scope={
            "cluster": "production",
            "environment": "production",
        },
        entities=[
            _entity(
                "entity:payments",
                "payment-api",
                "KubernetesDeployment",
            ),
            _entity(
                "entity:checkout",
                "checkout-api",
                "KubernetesService",
            ),
            _entity(
                "entity:web",
                "web-frontend",
                "KubernetesDeployment",
            ),
        ],
        relationships=[
            Relationship(
                id="relationship:payments-checkout",
                source_entity_id="entity:payments",
                target_entity_id="entity:checkout",
                relationship_type=(
                    RelationshipType.DEPENDS_ON
                ),
                source_system="kubernetes",
                observed_at=NOW,
            ),
            Relationship(
                id="relationship:checkout-web",
                source_entity_id="entity:checkout",
                target_entity_id="entity:web",
                relationship_type=(
                    RelationshipType.CALLS
                ),
                source_system="runtime",
                observed_at=NOW,
            ),
        ],
    )


@owned_world_fixture
def _analysis(
    *,
    confidence: float = 0.9,
    snapshot_id: str | None = (
        "snapshot:incident-time"
    ),
) -> CausalAnalysisResponse:
    level = (
        CausalConfidenceLevel.HIGH
        if confidence >= 0.75
        else CausalConfidenceLevel.LOW
    )
    chain = [
        CausalChainStep(
            order=1,
            node_id="event|event:commit",
            node_type=CausalNodeType.CHANGE_EVENT,
            label="Payment retry code change",
        ),
        CausalChainStep(
            order=2,
            node_id="event|event:deploy",
            node_type=CausalNodeType.CHANGE_EVENT,
            label="Deploy payment-api revision 42",
            relation_from_previous=(
                CausalEdgeType.PRECEDES
            ),
            confidence_from_previous=0.9,
        ),
        CausalChainStep(
            order=3,
            node_id="entity|entity:payments",
            node_type=CausalNodeType.ENTITY,
            label="payment-api",
            relation_from_previous=(
                CausalEdgeType.TOUCHES_ENTITY
            ),
            confidence_from_previous=0.95,
        ),
        CausalChainStep(
            order=4,
            node_id="entity|entity:checkout",
            node_type=CausalNodeType.ENTITY,
            label="checkout-api",
            relation_from_previous=(
                CausalEdgeType.TOPOLOGY_PATH
            ),
            confidence_from_previous=0.8,
        ),
        CausalChainStep(
            order=5,
            node_id="incident|incident:1",
            node_type=CausalNodeType.INCIDENT,
            label="Checkout degradation",
            relation_from_previous=(
                CausalEdgeType.CULMINATES_IN
            ),
            confidence_from_previous=1.0,
        ),
    ]
    hypothesis = CausalHypothesis(
        hypothesis_id="hypothesis:13c",
        rank=1,
        root_event_id="event:commit",
        root_source="github",
        root_title="Payment retry code change",
        target_event_id="event:deploy",
        target_title="Deploy payment-api revision 42",
        affected_entity_id="entity:checkout",
        score=confidence * 100,
        confidence=confidence,
        confidence_level=level,
        minutes_before_incident=4.0,
        summary="The commit preceded the deployment.",
        reasons=["Temporal and topology evidence."],
        supporting_evidence_ids=[
            "evidence:temporal",
            "evidence:lineage",
            "evidence:entity",
            "evidence:topology",
        ],
        chain=chain,
    )
    nodes = [
        CausalNode(
            node_id="event|event:commit",
            node_type=CausalNodeType.CHANGE_EVENT,
            label="Payment retry code change",
            occurred_at=(
                NOW - timedelta(minutes=8)
            ).isoformat(),
            event_id="event:commit",
            attributes={
                "source": "github",
                "kind": "code",
                "repository": "acme/payments",
                "commit_sha": "abc123",
            },
        ),
        CausalNode(
            node_id="event|event:deploy",
            node_type=CausalNodeType.CHANGE_EVENT,
            label="Deploy payment-api revision 42",
            occurred_at=(
                NOW - timedelta(minutes=4)
            ).isoformat(),
            event_id="event:deploy",
            attributes={
                "source": "github_actions",
                "kind": "deployment",
                "repository": "acme/payments",
                "commit_sha": "abc123",
                "pipeline_name": "deploy-payments",
                "release_version": "42",
            },
        ),
        CausalNode(
            node_id="entity|entity:payments",
            node_type=CausalNodeType.ENTITY,
            label="payment-api",
            entity_id="entity:payments",
        ),
        CausalNode(
            node_id="entity|entity:checkout",
            node_type=CausalNodeType.ENTITY,
            label="checkout-api",
            entity_id="entity:checkout",
        ),
        CausalNode(
            node_id="incident|incident:1",
            node_type=CausalNodeType.INCIDENT,
            label="Checkout degradation",
        ),
    ]
    edges = [
        CausalEdge(
            edge_id="edge:lineage",
            source_node_id="event|event:commit",
            target_node_id="event|event:deploy",
            relation=CausalEdgeType.PRECEDES,
            confidence=0.9,
            evidence_ids=["evidence:lineage"],
        ),
        CausalEdge(
            edge_id="edge:entity",
            source_node_id="event|event:deploy",
            target_node_id="entity|entity:payments",
            relation=CausalEdgeType.TOUCHES_ENTITY,
            confidence=0.95,
            evidence_ids=["evidence:entity"],
        ),
        CausalEdge(
            edge_id="edge:topology",
            source_node_id="entity|entity:payments",
            target_node_id="entity|entity:checkout",
            relation=CausalEdgeType.TOPOLOGY_PATH,
            confidence=0.8,
            evidence_ids=["evidence:topology"],
        ),
        CausalEdge(
            edge_id="edge:incident",
            source_node_id="entity|entity:checkout",
            target_node_id="incident|incident:1",
            relation=CausalEdgeType.CULMINATES_IN,
            confidence=1.0,
            evidence_ids=["evidence:incident"],
        ),
    ]
    evidence = [
        CausalEvidenceItem(
            evidence_id="evidence:temporal",
            evidence_type=CausalEvidenceType.TEMPORAL,
            source="change-event",
            title="Temporal proximity",
            detail="Deployment preceded the incident.",
            observed_at=NOW.isoformat(),
            event_id="event:deploy",
            weight=0.9,
        ),
        CausalEvidenceItem(
            evidence_id="evidence:lineage",
            evidence_type=(
                CausalEvidenceType.EVENT_LINEAGE
            ),
            source="change-lineage",
            title="Delivery lineage",
            detail="Commit produced the deployment.",
            event_id="event:deploy",
            weight=0.9,
        ),
        CausalEvidenceItem(
            evidence_id="evidence:entity",
            evidence_type=(
                CausalEvidenceType.ENTITY_LINK
            ),
            source="change-correlation",
            title="Deployment target",
            detail="Deployment changed payment-api.",
            event_id="event:deploy",
            entity_id="entity:payments",
            weight=0.95,
        ),
        CausalEvidenceItem(
            evidence_id="evidence:topology",
            evidence_type=CausalEvidenceType.TOPOLOGY,
            source="topology",
            title="Dependency path",
            detail="payment-api connects to checkout-api.",
            entity_id="entity:checkout",
            weight=0.8,
        ),
    ]

    return CausalAnalysisResponse(
        analysis_id="analysis:13c",
        incident_id="incident:1",
        incident_title="Checkout degradation",
        incident_time=NOW.isoformat(),
        topology_snapshot_id=snapshot_id,
        algorithm_version="13c-causal-v1",
        generated_at=NOW.isoformat(),
        parameters={},
        candidate_count=2,
        node_count=len(nodes),
        edge_count=len(edges),
        evidence_count=len(evidence),
        hypothesis_count=1,
        top_hypothesis=hypothesis,
        hypotheses=[hypothesis],
        nodes=nodes,
        edges=edges,
        evidence=evidence,
    )


def _ownership(
    entity_id: str,
    name: str,
    *,
    resolved: bool = True,
) -> EntityOwnershipResolution:
    return EntityOwnershipResolution(
        resolved=resolved,
        entity_id=entity_id,
        entity_kind="KubernetesDeployment",
        entity_name=name,
        service_name=(name if resolved else None),
        cluster_name="production",
        namespace="payments",
        owner_team=(
            "Payments Platform"
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
            "https://github.com/acme/payments"
            if resolved
            else None
        ),
        business_capability=(
            "Checkout"
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
            f"ownership:{entity_id}"
            if resolved
            else None
        ),
        resolution_reason=(
            "Matched stored ownership."
            if resolved
            else "No ownership matched."
        ),
    )


def _impact(
    *,
    root_resolved: bool = True,
) -> IncidentOwnershipImpact:
    values = [
        (
            "entity:payments",
            "payment-api",
            "direct",
            0,
            1.0,
            root_resolved,
        ),
        (
            "entity:checkout",
            "checkout-api",
            "dependent",
            1,
            0.85,
            True,
        ),
        (
            "entity:web",
            "web-frontend",
            "indirect",
            2,
            0.65,
            True,
        ),
    ]
    affected = [
        AffectedEntityOwnership(
            entity_id=entity_id,
            entity_kind="KubernetesDeployment",
            entity_name=name,
            impact=impact,
            distance=distance,
            impact_score=score,
            ownership=_ownership(
                entity_id,
                name,
                resolved=resolved,
            ),
        )
        for (
            entity_id,
            name,
            impact,
            distance,
            score,
            resolved,
        ) in values
    ]
    resolved_count = sum(
        item.ownership.resolved
        for item in affected
    )

    return IncidentOwnershipImpact(
        incident_id="incident:1",
        business_impact_level=(
            BusinessImpactLevel.CRITICAL
        ),
        affected_entity_count=3,
        resolved_entity_count=resolved_count,
        unresolved_entity_count=(
            3 - resolved_count
        ),
        affected_team_count=1,
        affected_capability_count=1,
        highest_criticality=(
            ServiceCriticality.TIER_1
        ),
        owner_teams=["Payments Platform"],
        business_capabilities=["Checkout"],
        oncall_contacts=["pagerduty:payments"],
        repositories=[
            "https://github.com/acme/payments"
        ],
        routing_recommendation=(
            "Route the incident to pagerduty:payments."
        ),
        affected_entities=affected,
        warnings=(
            ["1 affected entity is unresolved."]
            if not root_resolved
            else []
        ),
    )


@owned_world_fixture
def _context(
    *,
    root_resolved: bool = True,
    warning: str | None = None,
) -> IncidentOperationalContext:
    return IncidentOperationalContext(
        incident_id="incident:1",
        causal_analysis_id="analysis:13c",
        root_event_id="event:commit",
        root_event_title="Payment retry code change",
        root_event_source="github",
        root_entity_id="entity:payments",
        causal_confidence=0.9,
        root_cause_ownership=_ownership(
            "entity:payments",
            "payment-api",
            resolved=root_resolved,
        ),
        overall_business_impact=_impact(
            root_resolved=root_resolved
        ),
        escalation_targets=[
            "pagerduty:payments",
            "Payments Platform",
        ],
        warnings=[warning] if warning else [],
    )


def _action(
    action_id: str,
    sequence: int,
    category: ResponseActionCategory,
    title: str,
) -> IncidentResponseAction:
    mutation = category in {
        ResponseActionCategory.MITIGATE,
        ResponseActionCategory.ROLLBACK_CANDIDATE,
    }

    return IncidentResponseAction(
        action_id=action_id,
        sequence=sequence,
        category=category,
        priority=ResponsePriority.CRITICAL,
        title=title,
        description=f"Evidence-backed step: {title}.",
        reason="Current incident evidence.",
        risk=(
            RecommendationRisk.HIGH
            if mutation
            else RecommendationRisk.LOW
        ),
        requires_human_approval=mutation,
        entity_ids=["entity:payments"],
        evidence_event_ids=["event:deploy"],
        evidence_ids=["evidence:entity"],
    )


@owned_world_fixture
def _plan(
    *,
    confidence: float = 0.9,
    root_resolved: bool = True,
    warning: str | None = None,
) -> IncidentResponsePlan:
    recommended = [
        _action(
            "action:inspect",
            1,
            ResponseActionCategory.INVESTIGATE,
            "Inspect deployment evidence",
        ),
        _action(
            "action:monitor",
            2,
            ResponseActionCategory.MONITOR,
            "Monitor the incident blast radius",
        ),
    ]

    if confidence >= 0.75:
        recommended.append(
            _action(
                "action:rollback",
                3,
                (
                    ResponseActionCategory
                    .ROLLBACK_CANDIDATE
                ),
                (
                    "Consider reversion after "
                    "validation confirms regression"
                ),
            )
        )

    return IncidentResponsePlan(
        incident_id="incident:1",
        causal_analysis_id="analysis:13c",
        response_priority=ResponsePriority.CRITICAL,
        response_priority_reason=(
            "Tier-1 Checkout capability is affected."
        ),
        root_cause=ResponseRootCause(
            event_id="event:commit",
            event_title="Payment retry code change",
            event_source="github",
            event_kind="code",
            occurred_at=(
                NOW - timedelta(minutes=8)
            ).isoformat(),
            target_event_id="event:deploy",
            target_event_title=(
                "Deploy payment-api revision 42"
            ),
            target_event_source="github_actions",
            target_event_kind="deployment",
            target_occurred_at=(
                NOW - timedelta(minutes=4)
            ).isoformat(),
            entity_id="entity:payments",
            causal_confidence=confidence,
            confidence_level=(
                "high" if confidence >= 0.75 else "low"
            ),
            evidence_ids=["evidence:entity"],
        ),
        primary_owner=_ownership(
            "entity:payments",
            "payment-api",
            resolved=root_resolved,
        ),
        business_context=_impact(
            root_resolved=root_resolved
        ),
        recommended_actions=recommended,
        validation_checks=[
            _action(
                "action:validate-runtime",
                1,
                ResponseActionCategory.VALIDATE,
                "Confirm runtime uses the changed artifact",
            ),
            _action(
                "action:validate-downstream",
                2,
                ResponseActionCategory.VALIDATE,
                (
                    "Confirm downstream failures match "
                    "the blast radius"
                ),
            ),
        ],
        rollback_candidate=RollbackCandidate(
            available=(confidence >= 0.75),
            reason=(
                "Current causal evidence permits "
                "human review."
            ),
            change_event_id=(
                "event:deploy"
                if confidence >= 0.75
                else None
            ),
        ),
        escalation_targets=[
            "pagerduty:payments"
        ],
        warnings=[warning] if warning else [],
    )


@owned_world_fixture
def _history(
    *,
    warning: str | None = None,
) -> IncidentHistoricalIntelligence:
    action = HistoricalResolutionAction(
        action_instance_id="action:old:rollback",
        action_type="rollback_deployment",
        title="Rollback payment-api deployment",
        effectiveness=ActionEffectiveness.EFFECTIVE,
    )
    match = HistoricalIncidentMatch(
        incident_id="incident:old:1",
        incident_title="Earlier checkout regression",
        incident_time=(
            NOW - timedelta(days=20)
        ).isoformat(),
        resolved_at=(
            NOW - timedelta(days=20)
            + timedelta(minutes=15)
        ).isoformat(),
        feature_fingerprint="fingerprint:old:1",
        similarity_score=0.88,
        similarity_breakdown=(
            SimilarityScoreBreakdown(
                factors={},
                weighted_total=0.88,
                available_weight=1.0,
            )
        ),
        matched_factors=["same root service"],
        differing_factors=[
            "Different environment: historical=staging"
        ],
        resolution=HistoricalResolutionSummary(
            rca_verdict=RcaVerdict.CONFIRMED,
            rca_confidence=0.92,
            primary_resolution_action=action,
            time_to_mitigation_seconds=300,
            time_to_resolution_seconds=900,
            resolution_summary=(
                "The deployment was manually reverted."
            ),
        ),
    )

    return IncidentHistoricalIntelligence(
        incident_id="incident:1",
        analysis_context=(
            HistoricalAnalysisContext(
                causal_analysis_id="analysis:13c",
                topology_snapshot_id=(
                    "snapshot:incident-time"
                ),
                root_event_id="event:commit",
                root_event_title=(
                    "Payment retry code change"
                ),
                root_entity_id="entity:payments",
                root_service_name="payment-api",
                causal_change_kind="deployment",
                severity="critical",
            )
        ),
        historical_support_level=(
            HistoricalSupportLevel.LIMITED
        ),
        matches=[match],
        resolution_patterns=[
            HistoricalResolutionPattern(
                action_type="rollback_deployment",
                action_title=(
                    "Rollback payment-api deployment"
                ),
                observed_cases=1,
                effective_cases=1,
                ineffective_cases=0,
                unknown_effectiveness_cases=0,
                supporting_incident_ids=[
                    "incident:old:1"
                ],
            )
        ],
        summary=(
            "One comparable recorded incident was found; "
            "history is informative, not proof."
        ),
        ai_status=HistoricalAiStatus.NOT_REQUESTED,
        warnings=[warning] if warning else [],
    )


def _response(
    *,
    plan: IncidentResponsePlan | None = None,
    history: IncidentHistoricalIntelligence | None = None,
):
    return response_service.build_incident_response_intelligence(
        session=object(),
        incident_id="incident:1",
        response_plan=plan or _plan(),
        historical_intelligence=(history or _history()),
        tenant_id=TEST_TENANT,
    )


def _outcome() -> IncidentOutcome:
    primary = IncidentResponseActionObservation(
        action_instance_id="action:observed:rollback",
        response_plan_action_id="action:rollback",
        change_event_id="event:rollback",
        action_type="rollback_deployment",
        title="Rollback payment-api deployment",
        source="responder",
        started_at=NOW + timedelta(minutes=4),
        completed_at=NOW + timedelta(minutes=5),
        target_entity_ids=["entity:payments"],
        result=ResponseActionResult.SUCCESSFUL,
        recovery_confirmed=True,
        effectiveness=ActionEffectiveness.EFFECTIVE,
        effectiveness_reason="Recovery was confirmed.",
        evidence_ids=["evidence:recovery"],
    )
    root = OutcomeRootCause(
        event_id="event:deploy",
        entity_id="entity:payments",
        event_source="github_actions",
        title="Deploy payment-api revision 42",
        source=OutcomeFactSource.RESPONDER,
        evidence_ids=["evidence:entity"],
    )

    return IncidentOutcome(
        outcome_id="outcome:1",
        incident_id="incident:1",
        status=IncidentStatus.RESOLVED,
        causal_analysis_id="analysis:13c",
        historical_topology_snapshot_id=(
            "snapshot:incident-time"
        ),
        started_at=NOW,
        mitigated_at=NOW + timedelta(minutes=5),
        resolved_at=NOW + timedelta(minutes=15),
        time_to_mitigation_seconds=300,
        time_to_resolution_seconds=900,
        original_root_cause=root,
        final_root_cause=root,
        rca_verdict=RcaVerdict.CONFIRMED,
        rca_confidence=0.95,
        resolution_summary=(
            "Manual rollback restored checkout."
        ),
        actions_taken=[primary],
        primary_resolution_action=primary,
        evidence_event_ids=["event:deploy"],
        evidence_ids=["evidence:recovery"],
    )


def _wire(
    monkeypatch,
    *,
    incident: IncidentRecordView | None = None,
    analysis: CausalAnalysisResponse | None = None,
    snapshot: GraphSnapshot | None = None,
    context: IncidentOperationalContext | None = None,
    plan: IncidentResponsePlan | None = None,
    history: IncidentHistoricalIntelligence | None = None,
    response=None,
    outcome: IncidentOutcome | None = None,
    captured: dict | None = None,
) -> None:
    incident = incident or _incident()
    analysis = analysis or _analysis()
    snapshot = snapshot or _snapshot()
    context = context or _context()
    plan = plan or _plan()
    history = history or _history()
    response = response or _response(
        plan=plan,
        history=history,
    )

    monkeypatch.setattr(
        service,
        "load_incident_record",
        lambda **kwargs: incident,
    )
    monkeypatch.setattr(
        service,
        "latest_causal_analysis",
        lambda *args, **kwargs: analysis,
    )

    def load_snapshot(**kwargs):
        if captured is not None:
            captured["snapshot_id"] = kwargs[
                "snapshot_id"
            ]
        return snapshot

    monkeypatch.setattr(
        service,
        "load_topology_snapshot",
        load_snapshot,
    )

    def build_context(**kwargs):
        if captured is not None:
            captured["context_analysis"] = kwargs.get(
                "causal_analysis"
            )
        return context

    monkeypatch.setattr(
        service,
        "build_incident_operational_context",
        build_context,
    )

    def build_plan(**kwargs):
        if captured is not None:
            captured["plan_context"] = kwargs.get(
                "operational_context"
            )
            captured["plan_analysis"] = kwargs.get(
                "causal_analysis"
            )
        return plan

    monkeypatch.setattr(
        service,
        "build_incident_response_plan",
        build_plan,
    )
    monkeypatch.setattr(
        service,
        "build_current_incident_profile",
        lambda **kwargs: object(),
    )

    def build_history(**kwargs):
        if captured is not None:
            captured["history_profile"] = kwargs.get(
                "current_profile"
            )
        return history

    monkeypatch.setattr(
        service,
        "build_historical_incident_intelligence",
        build_history,
    )

    def build_response(**kwargs):
        if captured is not None:
            captured["response_plan"] = kwargs.get(
                "response_plan"
            )
            captured["response_history"] = kwargs.get(
                "historical_intelligence"
            )
        return response

    monkeypatch.setattr(
        service,
        "build_incident_response_intelligence",
        build_response,
    )
    monkeypatch.setattr(
        service,
        "load_incident_outcome",
        lambda *args, **kwargs: outcome,
    )
    monkeypatch.setattr(
        service,
        "get_incident_outcome",
        lambda *args, **kwargs: outcome,
    )
    monkeypatch.setattr(
        service,
        "openai_is_configured",
        lambda: False,
    )


def _build(monkeypatch, **kwargs):
    _wire(monkeypatch, **kwargs)
    return service.build_incident_briefing(
        session=object(), incident_id="incident:1", tenant_id=TEST_TENANT
    )


def test_complete_incident_returns_unified_briefing(
    monkeypatch,
) -> None:
    result = _build(
        monkeypatch,
        outcome=_outcome(),
    )

    assert result.incident.incident_id == "incident:1"
    assert result.root_cause.causal_analysis_id == (
        "analysis:13c"
    )
    assert result.blast_radius is not None
    assert result.operational_context is not None
    assert result.remediation is not None
    assert result.historical_context.similar_incidents
    assert result.outcome is not None


def test_root_cause_comes_from_13c(
    monkeypatch,
) -> None:
    result = _build(monkeypatch)

    assert result.root_cause.root_event_title == (
        "Payment retry code change"
    )
    assert result.root_cause.root_event_title != (
        _incident().top_hypothesis_title
    )


def test_briefing_exposes_authoritative_tc5_confidence_semantics(
    monkeypatch,
) -> None:
    result = _build(monkeypatch)
    semantics = result.root_cause.confidence_semantics

    assert semantics is not None
    assert semantics.score_type.value == "heuristic_ranking"
    assert semantics.ranking_score == 90.0
    assert semantics.legacy_confidence == 0.9
    assert semantics.evidence_state.value == "legacy_unknown"
    assert semantics.calibration_status.value == "not_calibrated"
    assert semantics.calibrated_probability is None


def test_relevant_change_matches_causal_target(
    monkeypatch,
) -> None:
    result = _build(monkeypatch)
    change = result.recent_relevant_changes[0]

    assert change.event_id == "event:deploy"
    assert change.role == "causal_target"
    assert change.change_type == "deployment"
    assert change.release_version == "42"


def test_dependency_path_uses_pinned_snapshot(
    monkeypatch,
) -> None:
    captured = {}
    result = _build(
        monkeypatch,
        captured=captured,
    )
    topology_step = result.dependency_path[3]

    assert captured["snapshot_id"] == (
        "snapshot:incident-time"
    )
    assert topology_step.topology_relationship_id == (
        "relationship:payments-checkout"
    )
    assert (
        topology_step.topology_relationship_type
        == "depends_on"
    )


def test_blast_radius_matches_14a_impact(
    monkeypatch,
) -> None:
    result = _build(monkeypatch)
    blast = result.blast_radius

    assert blast is not None
    assert blast.affected_entity_count == 3
    assert blast.direct_impact_count == 1
    assert blast.indirect_impact_count == 1
    assert blast.potential_impact_count == 1
    assert blast.affected_dependency_types == [
        "depends_on",
        "calls",
    ]


def test_ownership_and_business_impact_match_14a(
    monkeypatch,
) -> None:
    result = _build(monkeypatch)
    operational = result.operational_context

    assert operational is not None
    assert operational.ownership.owner_team == (
        "Payments Platform"
    )
    assert (
        operational.business_impact
        .business_impact_level
        == BusinessImpactLevel.CRITICAL
    )
    assert operational.escalation_targets == [
        "pagerduty:payments",
        "Payments Platform",
    ]


def test_response_actions_match_14b(
    monkeypatch,
) -> None:
    plan = _plan()
    result = _build(
        monkeypatch,
        plan=plan,
        response=_response(plan=plan),
    )

    assert result.remediation is not None
    assert [
        item.action_id
        for item in result.remediation.actions
    ] == [
        *[
            item.action_id
            for item in plan.recommended_actions
        ],
        *[
            item.action_id
            for item in plan.validation_checks
        ],
    ]


def test_historical_support_matches_14d_14e(
    monkeypatch,
) -> None:
    result = _build(monkeypatch)

    assert (
        result.historical_context.support_level
        == HistoricalSupportLevel.LIMITED
    )
    assert (
        result.historical_context
        .similar_incidents[0].similarity
        == 0.88
    )
    rollback = next(
        item
        for item in result.remediation.actions
        if item.action_id == "action:rollback"
    )
    assert (
        rollback.historical_support
        .action_observed_count
        == 1
    )


def test_outcome_matches_14c(
    monkeypatch,
) -> None:
    result = _build(
        monkeypatch,
        outcome=_outcome(),
    )

    assert result.outcome is not None
    assert result.outcome.outcome_id == "outcome:1"
    assert result.outcome.final_rca_verdict == (
        RcaVerdict.CONFIRMED
    )
    assert result.outcome.primary_resolution_action == (
        "Rollback payment-api deployment"
    )


def test_preview_does_not_claim_guaranteed_success(
    monkeypatch,
) -> None:
    result = _build(monkeypatch)
    preview = result.remediation.previews[0]
    text = (
        preview.intended_effect
        + " "
        + preview.expected_observation_if_successful
    ).casefold()

    assert "will fix" not in text
    assert "will resolve" not in text
    assert "if the leading causal hypothesis" in text


def test_preview_references_actual_target(
    monkeypatch,
) -> None:
    result = _build(monkeypatch)
    preview = result.remediation.previews[0]

    assert preview.affected_target.entity_ids == [
        "entity:payments"
    ]
    assert "event:deploy" in (
        preview.affected_target.change_event_ids
    )


def test_preview_potential_impact_uses_blast_evidence(
    monkeypatch,
) -> None:
    result = _build(monkeypatch)
    preview = result.remediation.previews[0]

    assert [
        item.entity_id
        for item in (
            preview.potentially_impacted_entities
        )
    ] == ["entity:checkout", "entity:web"]
    assert "not a simulation" in (
        preview.potential_impact_scope_note
    )


def test_verification_reuses_14b_validation(
    monkeypatch,
) -> None:
    result = _build(monkeypatch)

    assert [
        item.source_action_id
        for item in result.verification_plan
    ] == [
        "action:validate-runtime",
        "action:validate-downstream",
    ]
    assert result.remediation.previews[0].verification_steps == (
        result.verification_plan
    )


def test_weak_rca_uses_cautious_language(
    monkeypatch,
) -> None:
    analysis = _analysis(confidence=0.35)
    plan = _plan(confidence=0.35)
    response = _response(plan=plan)
    result = _build(
        monkeypatch,
        analysis=analysis,
        plan=plan,
        response=response,
    )

    assert result.root_cause.confidence_level == "low"
    assert result.remediation.previews == []
    assert not any(
        item.category
        == ResponseActionCategory.ROLLBACK_CANDIDATE
        for item in result.remediation.actions
    )
    assert any(
        "weak hypothesis" in warning
        for warning in result.warnings
    )


def test_missing_ownership_degrades_cleanly(
    monkeypatch,
) -> None:
    context = _context(root_resolved=False)
    plan = _plan(root_resolved=False)
    result = _build(
        monkeypatch,
        context=context,
        plan=plan,
        response=_response(plan=plan),
    )

    assert result.operational_context is not None
    assert result.operational_context.ownership.resolved is False
    assert result.operational_context.ownership.owner_team is None
    assert (
        result.operational_context.business_impact
        .affected_entity_count
        == 3
    )


def test_missing_history_degrades_cleanly(
    monkeypatch,
) -> None:
    _wire(monkeypatch)
    monkeypatch.setattr(
        service,
        "build_historical_incident_intelligence",
        lambda **kwargs: (_ for _ in ()).throw(
            ValueError("history unavailable")
        ),
    )
    result = service.build_incident_briefing(
        session=object(), incident_id="incident:1", tenant_id=TEST_TENANT
    )

    assert result.historical_context.similar_incident_count == 0
    assert result.historical_context.support_level == (
        HistoricalSupportLevel.NONE
    )
    assert any(
        "Historical intelligence is unavailable"
        in warning
        for warning in result.warnings
    )


def test_missing_outcome_is_in_progress_not_fabricated(
    monkeypatch,
) -> None:
    calls = []
    _wire(monkeypatch, outcome=None)
    monkeypatch.setattr(
        service,
        "get_incident_outcome",
        lambda *args, **kwargs: calls.append(True),
    )
    result = service.build_incident_briefing(
        session=object(), incident_id="incident:1", tenant_id=TEST_TENANT
    )

    assert result.outcome is None
    assert calls == []
    assert result.incident.status == IncidentStatus.OPEN


def test_duplicate_warnings_are_removed(
    monkeypatch,
) -> None:
    shared = "Shared warning."
    context = _context(warning=shared)
    plan = _plan(warning=shared)
    history = _history(warning=shared)
    response = _response(
        plan=plan,
        history=history,
    ).model_copy(
        update={"warnings": [shared]}
    )
    result = _build(
        monkeypatch,
        context=context,
        plan=plan,
        history=history,
        response=response,
    )

    assert result.warnings.count(shared) == 1


def test_ai_disabled_is_deterministic(
    monkeypatch,
) -> None:
    _wire(monkeypatch)
    first = service.build_incident_briefing(
        session=object(),
        incident_id="incident:1",
        include_ai=False,
        tenant_id=TEST_TENANT,
    )
    second = service.build_incident_briefing(
        session=object(),
        incident_id="incident:1",
        include_ai=False,
        tenant_id=TEST_TENANT,
    )

    assert first == second
    assert first.ai_status == (
        HistoricalAiStatus.NOT_REQUESTED
    )


def test_openai_summary_success(
    monkeypatch,
) -> None:
    _wire(monkeypatch)
    calls = []
    monkeypatch.setattr(
        service,
        "openai_is_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        service,
        "configured_openai_model",
        lambda: "gpt-test",
    )

    def generate(**kwargs):
        calls.append(kwargs)
        return OpenAITextResult(
            text="Cautious responder narrative.",
            model_name="gpt-test",
        )

    monkeypatch.setattr(
        service,
        "generate_openai_text",
        generate,
    )
    result = service.build_incident_briefing(
        session=object(),
        incident_id="incident:1",
        include_ai=True,
        tenant_id=TEST_TENANT,
    )

    assert result.ai_summary == (
        "Cautious responder narrative."
    )
    assert result.ai_status == HistoricalAiStatus.AVAILABLE
    assert len(calls) == 1


def test_missing_openai_key_preserves_briefing(
    monkeypatch,
) -> None:
    _wire(monkeypatch)
    result = service.build_incident_briefing(
        session=object(),
        incident_id="incident:1",
        include_ai=True,
        tenant_id=TEST_TENANT,
    )

    assert result.root_cause.root_event_id == "event:commit"
    assert result.ai_summary is None
    assert result.ai_status == (
        HistoricalAiStatus.UNAVAILABLE
    )


def test_openai_failure_preserves_briefing(
    monkeypatch,
) -> None:
    _wire(monkeypatch)
    monkeypatch.setattr(
        service,
        "openai_is_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        service,
        "generate_openai_text",
        lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError("provider failed")
        ),
    )
    result = service.build_incident_briefing(
        session=object(),
        incident_id="incident:1",
        include_ai=True,
        tenant_id=TEST_TENANT,
    )

    assert result.ai_status == HistoricalAiStatus.FAILED
    assert result.blast_radius.affected_entity_count == 3


def test_llm_output_cannot_alter_structured_facts(
    monkeypatch,
) -> None:
    _wire(monkeypatch)
    monkeypatch.setattr(
        service,
        "openai_is_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        service,
        "generate_openai_text",
        lambda **kwargs: OpenAITextResult(
            text="The owner is an invented team.",
            model_name="gpt-test",
        ),
    )
    result = service.build_incident_briefing(
        session=object(),
        incident_id="incident:1",
        include_ai=True,
        tenant_id=TEST_TENANT,
    )

    assert result.ai_summary == (
        "The owner is an invented team."
    )
    assert result.operational_context.ownership.owner_team == (
        "Payments Platform"
    )
    assert result.root_cause.causal_confidence == 0.9


def test_13c_regression_reference_is_preserved(
    monkeypatch,
) -> None:
    result = _build(monkeypatch)

    assert result.root_cause.evidence_references == [
        "evidence:temporal",
        "evidence:lineage",
        "evidence:entity",
        "evidence:topology",
    ]
    assert result.dependency_path[2].evidence_references == [
        "evidence:entity"
    ]


def test_14a_regression_values_are_preserved(
    monkeypatch,
) -> None:
    result = _build(monkeypatch)
    impact = result.operational_context.business_impact

    assert impact.resolved_entity_count == 3
    assert impact.highest_criticality == (
        ServiceCriticality.TIER_1
    )
    assert impact.routing_recommendation == (
        "Route the incident to pagerduty:payments."
    )


def test_14b_regression_action_risk_and_approval_preserved(
    monkeypatch,
) -> None:
    result = _build(monkeypatch)
    rollback = next(
        item
        for item in result.remediation.actions
        if item.action_id == "action:rollback"
    )

    assert rollback.risk == RecommendationRisk.HIGH
    assert rollback.requires_human_approval is True


def test_14c_regression_timing_is_preserved(
    monkeypatch,
) -> None:
    result = _build(
        monkeypatch,
        outcome=_outcome(),
    )

    assert result.outcome.time_to_mitigation_seconds == 300
    assert result.outcome.time_to_resolution_seconds == 900


def test_14d_14e_regression_counts_are_raw(
    monkeypatch,
) -> None:
    result = _build(monkeypatch)
    pattern = (
        result.historical_context
        .resolution_patterns[0]
    )

    assert pattern["observed_cases"] == 1
    assert pattern["effective_cases"] == 1
    assert result.remediation.overall_historical_support == (
        HistoricalActionSupportLevel.LIMITED
    )


def test_briefing_does_not_expose_execution_contracts(
    monkeypatch,
) -> None:
    result = _build(monkeypatch)

    def keys(value):
        if isinstance(value, dict):
            return {
                key
                for name, item in value.items()
                for key in ({name} | keys(item))
            }
        if isinstance(value, list):
            return set().union(
                *(keys(item) for item in value),
                set(),
            )
        return set()

    result_keys = keys(
        result.model_dump(mode="json")
    )

    assert result.remediation.read_only is True
    assert "execution_intent" not in result_keys
    assert "approval_id" not in result_keys
    assert "execute" not in result_keys


def test_authentication_and_route_are_registered() -> None:
    assert any(
        middleware.cls is ApiTokenAuthMiddleware
        for middleware in app.user_middleware
    )
    assert any(
        route.path
        == "/api/v1/incidents/{incident_id}/briefing"
        for route in briefing_api.router.routes
    )
    assert any(
        getattr(route, "original_router", None)
        is briefing_api.router
        for route in app.routes
    )


def test_briefing_route_requires_authentication(
    required_auth_app,
) -> None:
    client = TestClient(required_auth_app, headers=TEST_HEADERS)
    response = client.get(
        "/api/v1/incidents/incident%3A1/briefing"
    )

    assert response.status_code == 401


def test_missing_causal_analysis_uses_api_404(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        briefing_api,
        "build_incident_briefing",
        lambda **kwargs: (_ for _ in ()).throw(
            ValueError(
                "No causal analysis exists for this incident."
            )
        ),
    )

    with pytest.raises(HTTPException) as raised:
        briefing_api.get_incident_briefing(
            incident_id="incident:missing",
            include_ai=False,
            session=object(),
            tenant_context=TEST_CONTEXT,
        )

    assert raised.value.status_code == 404
    assert raised.value.detail == (
        "No causal analysis exists for this incident."
    )


def test_api_passes_single_ai_flag(
    monkeypatch,
) -> None:
    captured = {}
    expected = _build(monkeypatch)

    def build(**kwargs):
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(
        briefing_api,
        "build_incident_briefing",
        build,
    )
    result = briefing_api.get_incident_briefing(
        incident_id="incident:1",
        include_ai=True,
        session=object(),
        tenant_context=TEST_CONTEXT,
    )

    assert result is expected
    assert captured["include_ai"] is True
    assert captured["tenant_id"] == TEST_TENANT
    assert set(captured) == {
        "session",
        "incident_id",
        "include_ai",
        "tenant_id",
    }


def test_precomputed_plan_and_history_are_reused(
    monkeypatch,
) -> None:
    plan = _plan()
    history = _history()
    calls = []
    monkeypatch.setattr(
        response_service,
        "build_incident_response_plan",
        lambda **kwargs: calls.append("plan"),
    )
    monkeypatch.setattr(
        response_service,
        "build_historical_incident_intelligence",
        lambda **kwargs: calls.append("history"),
    )

    result = response_service.build_incident_response_intelligence(
        session=object(),
        incident_id="incident:1",
        response_plan=plan,
        historical_intelligence=history,
        tenant_id=TEST_TENANT,
    )

    assert calls == []
    assert result.baseline_response_plan is plan
    assert result.causal_analysis_id == "analysis:13c"


def test_orchestrator_passes_precomputed_results(
    monkeypatch,
) -> None:
    captured = {}
    context = _context()
    plan = _plan()
    history = _history()
    _wire(
        monkeypatch,
        context=context,
        plan=plan,
        history=history,
        captured=captured,
    )
    service.build_incident_briefing(
        session=object(), incident_id="incident:1", tenant_id=TEST_TENANT
    )

    assert captured["context_analysis"].analysis_id == (
        "analysis:13c"
    )
    assert captured["plan_context"] is context
    assert captured["plan_analysis"].analysis_id == (
        "analysis:13c"
    )
    assert captured["response_plan"] is plan
    assert captured["response_history"] is history


def test_operational_failure_preserves_core_rca(
    monkeypatch,
) -> None:
    _wire(monkeypatch)
    monkeypatch.setattr(
        service,
        "build_incident_operational_context",
        lambda **kwargs: (_ for _ in ()).throw(
            ValueError("ownership unavailable")
        ),
    )
    result = service.build_incident_briefing(
        session=object(), incident_id="incident:1", tenant_id=TEST_TENANT
    )

    assert result.root_cause.root_event_id == "event:commit"
    assert result.operational_context is None
    assert result.remediation is None
    assert any(
        "Operational context is unavailable"
        in warning
        for warning in result.warnings
    )


def test_service_has_no_execution_service_imports() -> None:
    source = inspect.getsource(service)

    assert "services.execution_readiness" not in source
    assert "services.action_approval" not in source
    assert "services.execution_transaction" not in source
