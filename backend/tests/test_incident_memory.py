from __future__ import annotations
from app.db.models import IncidentOutcomeRecord
from domain_tenant_fixtures import TEST_CONTEXT, TEST_TENANT

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.api.incident_memory as memory_api
import app.services.incident_memory as memory
import app.services.incident_similarity as similarity
import app.services.llm_client as llm_client
from app.models.causal_rca import (
    CausalAnalysisResponse,
    CausalChainStep,
    CausalConfidenceLevel,
    CausalEdgeType,
    CausalHypothesis,
    CausalNode,
    CausalNodeType,
)
from app.models.incident_memory import (
    HistoricalIncidentFeatureProfile,
    HistoricalResolutionAction,
    HistoricalResolutionSummary,
    HistoricalSupportLevel,
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
    EntityOwnershipResolution,
    OwnershipSource,
    ServiceCriticality,
)
from app.models.topology import (
    Entity,
    EntityType,
    GraphSnapshot,
    Relationship,
    RelationshipType,
)
from app.services.llm_client import (
    OpenAITextResult,
)
from app.security.api_tokens import (
    ApiTokenAuthMiddleware,
)

NOW = datetime(
    2026,
    8,
    16,
    10,
    0,
    tzinfo=timezone.utc,
)


def _resolution(
    *,
    action_type: str = "rollback_deployment",
    effectiveness: ActionEffectiveness = (
        ActionEffectiveness.EFFECTIVE
    ),
    verdict: RcaVerdict = RcaVerdict.CONFIRMED,
) -> HistoricalResolutionSummary:
    return HistoricalResolutionSummary(
        rca_verdict=verdict,
        rca_confidence=0.9,
        primary_resolution_action=(
            HistoricalResolutionAction(
                action_instance_id="action:1",
                action_type=action_type,
                title="Rollback deployment",
                effectiveness=effectiveness,
            )
        ),
        time_to_mitigation_seconds=300,
        time_to_resolution_seconds=600,
        resolution_summary=(
            "Recorded rollback restored service."
        ),
    )


def _profile(
    incident_id: str,
    *,
    resolution: (
        HistoricalResolutionSummary | None
    ) = None,
    root_service: str = "payments-api",
    change_kind: str = "deployment",
    source: str = "github_actions",
    environment: str = "production",
    team: str = "payments",
    severity: str = "critical",
    affected: list[str] | None = None,
    neighbors: list[str] | None = None,
) -> HistoricalIncidentFeatureProfile:
    return HistoricalIncidentFeatureProfile(
        feature_fingerprint=(
            f"fingerprint:{incident_id}"
        ),
        incident_id=incident_id,
        incident_title=f"Incident {incident_id}",
        incident_time=NOW.isoformat(),
        resolved_at=(
            NOW.isoformat()
            if resolution is not None
            else None
        ),
        severity=severity,
        environment=environment,
        causal_analysis_id=(
            f"analysis:{incident_id}"
        ),
        topology_snapshot_id=(
            f"snapshot:{incident_id}"
        ),
        root_event_id=f"event:{incident_id}",
        root_event_title="Deploy payments",
        root_event_source=source,
        root_entity_id="entity:payments",
        root_entity_kind=(
            "KubernetesDeployment"
        ),
        root_service_name=root_service,
        causal_change_kind=change_kind,
        causal_change_source=source,
        owner_team=team,
        business_capability="checkout",
        criticality="tier_1",
        affected_entity_ids=(
            affected
            if affected is not None
            else [
                "entity:payments",
                "entity:checkout",
            ]
        ),
        affected_entity_kinds=[
            "KubernetesDeployment",
            "KubernetesService",
        ],
        topology_neighbor_ids=(
            neighbors
            if neighbors is not None
            else [
                "entity:checkout",
                "entity:database",
            ]
        ),
        topology_neighbor_kinds=[
            "KubernetesService",
            "Database",
        ],
        blast_radius_size=2,
        resolution=resolution,
    )


def _match(
    incident_id: str,
    *,
    action_type: str = "rollback_deployment",
    effectiveness: ActionEffectiveness = (
        ActionEffectiveness.EFFECTIVE
    ),
    verdict: RcaVerdict = RcaVerdict.CONFIRMED,
):
    current = _profile("current")
    historical = _profile(
        incident_id,
        resolution=_resolution(
            action_type=action_type,
            effectiveness=effectiveness,
            verdict=verdict,
        ),
    )
    result = similarity.historical_match(
        current,
        historical,
    )
    assert result is not None
    return result


def test_exact_technical_match_has_full_score(
) -> None:
    breakdown = (
        similarity.score_incident_similarity(
            _profile("current"),
            _profile(
                "historical",
                resolution=_resolution(),
            ),
        )
    )

    assert breakdown.weighted_total == 1.0
    assert breakdown.available_weight == 1.0
    assert sum(
        item.weighted_value
        for item in breakdown.factors.values()
    ) == pytest.approx(
        breakdown.weighted_total
    )


def test_weak_team_and_severity_match_stays_low(
) -> None:
    current = _profile("current")
    historical = _profile(
        "historical",
        resolution=_resolution(),
        root_service="catalog-api",
        change_kind="configuration",
        source="jenkins",
        environment="staging",
        affected=["entity:catalog"],
        neighbors=["entity:queue"],
    ).model_copy(
        update={
            "root_entity_kind": "Queue",
            "business_capability": "catalog",
            "affected_entity_kinds": ["Queue"],
            "topology_neighbor_kinds": ["Queue"],
        }
    )

    score = similarity.score_incident_similarity(
        current,
        historical,
    ).weighted_total

    assert score == pytest.approx(0.06)
    assert score < 0.15


def test_change_kind_weight_is_explicit() -> None:
    current = _profile("current")
    exact = _profile(
        "exact",
        resolution=_resolution(),
    )
    different = exact.model_copy(
        update={
            "causal_change_kind": (
                "configuration"
            )
        }
    )

    exact_score = (
        similarity.score_incident_similarity(
            current,
            exact,
        ).weighted_total
    )
    different_score = (
        similarity.score_incident_similarity(
            current,
            different,
        ).weighted_total
    )

    assert exact_score - different_score == (
        pytest.approx(0.18)
    )


def test_jaccard_and_topology_overlap_are_exact(
) -> None:
    assert similarity.jaccard_similarity(
        ["a", "b"],
        ["b", "c"],
    ) == pytest.approx(1 / 3)

    current = _profile(
        "current",
        neighbors=["a", "b"],
    )
    historical = _profile(
        "historical",
        resolution=_resolution(),
        neighbors=["b", "c"],
    )
    factor = (
        similarity.score_incident_similarity(
            current,
            historical,
        ).factors["topology_neighborhood"]
    )

    # ID overlap is 1/3; kinds are identical.
    assert factor.score == pytest.approx(
        (1 / 3) * 0.7 + 0.3,
        abs=1e-6,
    )


def test_missing_topology_scores_available_factors(
) -> None:
    current = _profile("current").model_copy(
        update={
            "topology_neighbor_ids": [],
            "topology_neighbor_kinds": [],
        }
    )
    historical = _profile(
        "historical",
        resolution=_resolution(),
    ).model_copy(
        update={
            "topology_neighbor_ids": [],
            "topology_neighbor_kinds": [],
        }
    )

    breakdown = (
        similarity.score_incident_similarity(
            current,
            historical,
        )
    )

    assert not breakdown.factors[
        "topology_neighborhood"
    ].available
    assert breakdown.weighted_total == (
        pytest.approx(0.86)
    )


def test_outcome_fields_do_not_affect_similarity(
) -> None:
    current = _profile("current")
    rollback = _profile(
        "historical",
        resolution=_resolution(
            action_type="rollback_deployment"
        ),
    )
    restart = rollback.model_copy(
        update={
            "resolution": _resolution(
                action_type="restart_workload",
                effectiveness=(
                    ActionEffectiveness
                    .INEFFECTIVE
                ),
                verdict=RcaVerdict.INCONCLUSIVE,
            )
        }
    )

    first = similarity.score_incident_similarity(
        current,
        rollback,
    ).weighted_total
    second = similarity.score_incident_similarity(
        current,
        restart,
    ).weighted_total

    assert first == second


def test_match_explains_matches_and_differences(
) -> None:
    current = _profile("current")
    historical = _profile(
        "old",
        resolution=_resolution(),
        environment="staging",
    )
    match = similarity.historical_match(
        current,
        historical,
    )

    assert match is not None
    assert "same root service" in (
        match.matched_factors
    )
    assert any(
        "Different environment" in item
        for item in match.differing_factors
    )


def test_match_order_is_score_then_quality_then_id(
) -> None:
    exact_b = _match("b")
    exact_a = _match("a")
    lower = _match("c").model_copy(
        update={"similarity_score": 0.5}
    )

    values = similarity.sort_historical_matches(
        [lower, exact_b, exact_a]
    )

    assert [item.incident_id for item in values] == [
        "a",
        "b",
        "c",
    ]


def test_single_case_never_has_strong_support(
) -> None:
    match = _match("one")
    patterns = (
        similarity.aggregate_resolution_patterns(
            [match]
        )
    )

    assert similarity.historical_support_level(
        [match],
        patterns,
    ) == HistoricalSupportLevel.LIMITED


def test_repeated_effective_pattern_can_be_strong(
) -> None:
    matches = [
        _match(f"incident:{index}")
        for index in range(3)
    ]
    patterns = (
        similarity.aggregate_resolution_patterns(
            matches
        )
    )

    assert patterns[0].observed_cases == 3
    assert patterns[0].effective_cases == 3
    assert similarity.historical_support_level(
        matches,
        patterns,
    ) == HistoricalSupportLevel.STRONG


def test_resolution_pattern_keeps_raw_counts(
) -> None:
    matches = [
        _match("effective"),
        _match(
            "ineffective",
            effectiveness=(
                ActionEffectiveness.INEFFECTIVE
            ),
        ),
        _match(
            "unknown",
            effectiveness=(
                ActionEffectiveness.UNKNOWN
            ),
        ),
    ]
    pattern = (
        similarity.aggregate_resolution_patterns(
            matches
        )[0]
    )

    assert pattern.observed_cases == 3
    assert pattern.effective_cases == 1
    assert pattern.ineffective_cases == 1
    assert (
        pattern.unknown_effectiveness_cases
        == 1
    )


def test_inconclusive_history_remains_labelled(
) -> None:
    match = _match(
        "inconclusive",
        verdict=RcaVerdict.INCONCLUSIVE,
    )

    assert match.resolution.rca_verdict == (
        RcaVerdict.INCONCLUSIVE
    )


def _incident(
    incident_id: str = "incident:old",
) -> IncidentRecordView:
    return IncidentRecordView(
        incident_id=incident_id,
        fingerprint=f"fingerprint:{incident_id}",
        status=IncidentStatus.RESOLVED,
        severity=IncidentSeverity.CRITICAL,
        title="Payments incident",
        summary="Payments failed.",
        cluster_name="production",
        namespace="payments",
        primary_signal_id="signal:1",
        topology_snapshot_id="snapshot:old",
        affected_entity_id="entity:payments",
        affected_object_kind=(
            "KubernetesDeployment"
        ),
        affected_object_name="payments-api",
        first_observed_at=NOW,
        last_observed_at=NOW,
        created_at=NOW,
        updated_at=NOW,
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
        affected_entity_id="entity:checkout",
        score=90,
        confidence=0.9,
        confidence_level=(
            CausalConfidenceLevel.HIGH
        ),
        summary="Commit deployed to payments.",
        chain=[
            CausalChainStep(
                order=1,
                node_id="event|event:deploy",
                node_type=(
                    CausalNodeType.CHANGE_EVENT
                ),
                label="Deploy payments",
            ),
            CausalChainStep(
                order=2,
                node_id="entity|entity:payments",
                node_type=CausalNodeType.ENTITY,
                label="payments-api",
                relation_from_previous=(
                    CausalEdgeType.TOUCHES_ENTITY
                ),
            ),
        ],
    )
    return CausalAnalysisResponse(
        analysis_id="analysis:old",
        incident_id="incident:old",
        incident_title="Payments incident",
        incident_time=NOW.isoformat(),
        topology_snapshot_id="snapshot:old",
        algorithm_version="13c-causal-v1",
        generated_at=NOW.isoformat(),
        parameters={},
        candidate_count=1,
        node_count=3,
        edge_count=2,
        evidence_count=1,
        hypothesis_count=1,
        top_hypothesis=hypothesis,
        hypotheses=[hypothesis],
        nodes=[
            CausalNode(
                node_id="event|event:deploy",
                node_type=(
                    CausalNodeType.CHANGE_EVENT
                ),
                label="Deploy payments",
                event_id="event:deploy",
                attributes={
                    "kind": "deployment",
                    "source": "github_actions",
                },
            ),
            CausalNode(
                node_id="entity|entity:payments",
                node_type=CausalNodeType.ENTITY,
                label="payments-api",
                entity_id="entity:payments",
            ),
        ],
    )


def _snapshot() -> GraphSnapshot:
    entities = [
        Entity(
            id="entity:payments",
            entity_type=EntityType.APPLICATION,
            kind="KubernetesDeployment",
            name="payments-api",
            source_system="kubernetes",
            environment="production",
            observed_at=NOW,
        ),
        Entity(
            id="entity:database",
            entity_type=EntityType.DATASTORE,
            kind="Database",
            name="payments-db",
            source_system="cloud",
            environment="production",
            observed_at=NOW,
        ),
    ]
    return GraphSnapshot(
        snapshot_id="snapshot:old",
        collected_at=NOW,
        collector_name="test",
        collector_version="1",
        scope={
            "cluster": "production",
            "environment": "production",
        },
        entities=entities,
        relationships=[
            Relationship(
                id="relationship:1",
                source_entity_id=(
                    "entity:payments"
                ),
                target_entity_id=(
                    "entity:database"
                ),
                relationship_type=(
                    RelationshipType.DEPENDS_ON
                ),
                source_system="test",
                observed_at=NOW,
            )
        ],
    )


def _outcome() -> IncidentOutcome:
    root = OutcomeRootCause(
        event_id="event:commit",
        entity_id="entity:payments",
        event_source="github",
        title="Payment retry change",
        source=OutcomeFactSource.INFERRED,
    )
    action = IncidentResponseActionObservation(
        action_instance_id="action:rollback",
        response_plan_action_id="plan:rollback",
        action_type="rollback_deployment",
        title="Rollback deployment",
        source="responder",
        result=ResponseActionResult.SUCCESSFUL,
        recovery_confirmed=True,
        effectiveness=(
            ActionEffectiveness.EFFECTIVE
        ),
        effectiveness_reason="Recovery confirmed.",
    )
    return IncidentOutcome(
        outcome_id="outcome:old",
        incident_id="incident:old",
        status=IncidentStatus.RESOLVED,
        causal_analysis_id="analysis:old",
        historical_topology_snapshot_id=(
            "snapshot:old"
        ),
        started_at=NOW,
        resolved_at=NOW,
        time_to_resolution_seconds=600,
        original_root_cause=root,
        rca_verdict=RcaVerdict.CONFIRMED,
        rca_confidence=0.9,
        resolution_summary="Rollback restored service.",
        actions_taken=[action],
        primary_resolution_action=action,
    )


def test_historical_profile_uses_pinned_snapshot(
    monkeypatch,
) -> None:
    outcome = _outcome()
    record = IncidentOutcomeRecord(
        payload_json=outcome.model_dump_json(),
        source_json=json.dumps(
            {
                "response_plan": {
                    "actions": [
                        {
                            "action_id": ("plan:rollback"),
                            "runbook_url": ("https://runbooks/rollback"),
                        }
                    ]
                }
            }
        ),
    )
    loaded_snapshots = []
    monkeypatch.setattr(
        memory,
        "load_incident_record",
        lambda **kwargs: _incident(),
    )
    monkeypatch.setattr(
        memory,
        "load_causal_analysis",
        lambda session, analysis_id, **_tenant_kwargs: (_analysis()),
    )

    def load_snapshot(**kwargs):
        loaded_snapshots.append(
            kwargs["snapshot_id"]
        )
        return _snapshot()

    monkeypatch.setattr(
        memory,
        "load_topology_snapshot",
        load_snapshot,
    )
    monkeypatch.setattr(
        memory,
        "resolve_entity_ownership",
        lambda **kwargs: (
            EntityOwnershipResolution(
                resolved=True,
                entity_id="entity:payments",
                entity_kind=(
                    "KubernetesDeployment"
                ),
                entity_name="payments-api",
                service_name="payments-api",
                owner_team="payments",
                business_capability="checkout",
                criticality=(
                    ServiceCriticality.TIER_1
                ),
                source=OwnershipSource.MANUAL,
                confidence=1,
                resolution_reason="Exact mapping.",
            )
        ),
    )
    monkeypatch.setattr(
        memory,
        "calculate_incident_ownership_impact",
        lambda **kwargs: (_ for _ in ()).throw(
            ValueError("impact unavailable")
        ),
    )

    profile = memory.build_historical_incident_profile(
        session=object(), record=record, tenant_id=TEST_TENANT
    )

    assert profile is not None
    assert loaded_snapshots == ["snapshot:old"]
    assert profile.root_entity_id == (
        "entity:payments"
    )
    assert profile.topology_neighbor_ids == [
        "entity:database"
    ]
    assert (
        profile.resolution
        .primary_resolution_action
        .runbook_url
        == "https://runbooks/rollback"
    )


def test_missing_causal_analysis_is_controlled(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        memory,
        "load_incident_record",
        lambda **kwargs: _incident("incident:current"),
    )
    monkeypatch.setattr(
        memory,
        "latest_causal_analysis",
        lambda session, incident_id, **_tenant_kwargs: None,
    )
    monkeypatch.setattr(
        memory,
        "load_topology_snapshot",
        lambda **kwargs: _snapshot(),
    )
    monkeypatch.setattr(
        memory,
        "calculate_incident_ownership_impact",
        lambda **kwargs: (_ for _ in ()).throw(
            ValueError("context unavailable")
        ),
    )

    profile = memory.build_current_incident_profile(
        session=object(), incident_id="incident:current", tenant_id=TEST_TENANT
    )

    assert profile.root_event_id is None
    assert any(
        item == (
            "Causal analysis unavailable; "
            "similarity is based on reduced context."
        )
        for item in profile.warnings
    )


def _patched_history_service(
    monkeypatch,
    *,
    include_history: bool = True,
) -> None:
    monkeypatch.setattr(
        similarity,
        "build_current_incident_profile",
        lambda session, incident_id, **_tenant_kwargs: (_profile("current")),
    )
    records = (
        [SimpleNamespace(key="old")]
        if include_history
        else []
    )
    monkeypatch.setattr(
        similarity,
        "list_incident_outcome_records",
        lambda session, **kwargs: records,
    )
    monkeypatch.setattr(
        similarity,
        "build_historical_incident_profile",
        lambda session, record, **_tenant_kwargs: _profile(
            "old",
            resolution=_resolution(),
        ),
    )


def test_current_incident_is_excluded_from_history_query(
    monkeypatch,
) -> None:
    captured = {}
    monkeypatch.setattr(
        similarity,
        "build_current_incident_profile",
        lambda session, incident_id, **_tenant_kwargs: (_profile("current")),
    )

    def list_records(session, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(
        similarity,
        "list_incident_outcome_records",
        list_records,
    )

    result = similarity.build_historical_incident_intelligence(
        session=object(), incident_id="current", tenant_id=TEST_TENANT
    )

    assert captured["exclude_incident_id"] == (
        "current"
    )
    assert captured["limit"] == 500
    assert result.matches == []
    assert result.historical_support_level == (
        HistoricalSupportLevel.NONE
    )


def test_missing_openai_key_keeps_structured_result(
    monkeypatch,
) -> None:
    _patched_history_service(monkeypatch)
    monkeypatch.setattr(
        similarity,
        "openai_is_configured",
        lambda: False,
    )

    result = similarity.build_historical_incident_intelligence(
        session=object(), incident_id="current", include_ai=True, tenant_id=TEST_TENANT
    )

    assert len(result.matches) == 1
    assert result.ai_summary is None
    assert result.ai_status.value == (
        "unavailable"
    )


def test_openai_failure_does_not_change_scores(
    monkeypatch,
) -> None:
    _patched_history_service(monkeypatch)
    monkeypatch.setattr(
        similarity,
        "openai_is_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        similarity,
        "generate_openai_text",
        lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError("provider down")
        ),
    )

    deterministic = similarity.build_historical_incident_intelligence(
        session=object(), incident_id="current", tenant_id=TEST_TENANT
    )
    enriched = similarity.build_historical_incident_intelligence(
        session=object(), incident_id="current", include_ai=True, tenant_id=TEST_TENANT
    )

    assert enriched.ai_status.value == "failed"
    assert (
        enriched.matches[0].similarity_score
        == deterministic.matches[0]
        .similarity_score
    )


def test_openai_summary_is_annotation_only(
    monkeypatch,
) -> None:
    _patched_history_service(monkeypatch)
    monkeypatch.setattr(
        similarity,
        "openai_is_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        similarity,
        "generate_openai_text",
        lambda **kwargs: OpenAITextResult(
            text=(
                "Invented score 0.01 must not "
                "replace structured data."
            ),
            model_name="test-model",
        ),
    )

    result = similarity.build_historical_incident_intelligence(
        session=object(), incident_id="current", include_ai=True, tenant_id=TEST_TENANT
    )

    assert result.ai_status.value == "available"
    assert result.ai_provider == "openai"
    assert result.matches[0].similarity_score == 1


def test_central_client_uses_responses_api(
    monkeypatch,
) -> None:
    captured = {}

    class Responses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output_text="Grounded summary."
            )

    monkeypatch.setattr(
        llm_client,
        "_openai_client",
        lambda: SimpleNamespace(
            responses=Responses()
        ),
    )
    result = llm_client.generate_openai_text(
        system_prompt="Explain evidence.",
        evidence_payload={
            "authorization": "Bearer secretvalue123",
            "incident_id": "incident:1",
        },
        model_name="gpt-5-mini",
    )

    assert result.text == "Grounded summary."
    assert captured["model"] == "gpt-5-mini"
    assert captured["store"] is False
    assert "secretvalue123" not in (
        captured["input"]
    )


def test_openai_is_default_but_can_be_disabled(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )
    monkeypatch.delenv(
        "TOPO_AI_LLM_PROVIDER",
        raising=False,
    )

    assert llm_client.resolve_configured_provider(
        "auto"
    ) == "openai"

    monkeypatch.setenv(
        "TOPO_AI_LLM_PROVIDER",
        "deterministic",
    )

    assert llm_client.resolve_configured_provider(
        "auto"
    ) == "deterministic"


def test_missing_incident_api_error_is_controlled(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        memory_api,
        "build_historical_incident_intelligence",
        lambda **kwargs: (_ for _ in ()).throw(
            ValueError("Incident not found: missing")
        ),
    )

    with pytest.raises(HTTPException) as raised:
        memory_api.get_historical_incident_intelligence(
            incident_id="missing",
            limit=5,
            min_similarity=0.25,
            include_ai=False,
            session=object(),
            tenant_context=TEST_CONTEXT,
        )

    assert raised.value.status_code == 404
    assert "Incident not found" in (
        raised.value.detail
    )


def test_new_and_existing_incident_routes_are_registered(
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
        "historical-intelligence"
    ) in paths
    assert (
        "/api/v1/incidents/{incident_id}/"
        "causal-rca/latest"
    ) in paths
    assert (
        "/api/v1/incidents/{incident_id}/"
        "operational-context"
    ) in paths
    assert (
        "/api/v1/incidents/{incident_id}/"
        "response-plan"
    ) in paths
    assert (
        "/api/v1/incidents/{incident_id}/"
        "outcome"
    ) in paths
    assert (
        "/api/v1/incidents/{incident_id}/"
        "ownership-impact"
    ) in paths
    assert any(
        item.cls is ApiTokenAuthMiddleware
        for item in app.user_middleware
    )
