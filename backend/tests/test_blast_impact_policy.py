from __future__ import annotations
from domain_tenant_fixtures import TEST_TENANT, seed_domain_tenant

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import IncidentRecord, utc_now_iso
from app.models.blast_radius import BlastRadiusEntity, BlastRadiusResponse
from app.models.topology import (
    Entity,
    EntityType,
    GraphSnapshot,
    Relationship,
    RelationshipType,
)
from app.services.blast_impact_policy import (
    ACTIVE_BLAST_PREDICATES,
    BLAST_IMPACT_POLICIES,
    BLAST_POLICY_VERSION,
    BlastImpactSemantic,
    BlastPolicyMaturity,
    BlastTraversal,
    blast_policy_for,
)
from app.services.blast_radius import (
    MAX_DEPTH,
    calculate_blast_radius_from_snapshot,
    calculate_blast_radius,
    calculate_impact_score,
    traverse_blast_radius,
)
from app.repositories.snapshot_repository import save_snapshot
from app.services.pinned_runtime_health import (
    PinnedRuntimeHealth,
    pinned_pod_health,
)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[2]
CONTRACT = (
    ROOT
    / "docs"
    / "architecture"
    / "blast-radius"
    / "impact-propagation-v1.json"
)


def _entity(
    entity_id: str,
    *,
    kind: str = "KubernetesPod",
    name: str | None = None,
    properties: dict | None = None,
) -> Entity:
    return Entity(
        id=entity_id,
        entity_type=EntityType.WORKLOAD,
        kind=kind,
        name=name or entity_id,
        source_system="kubernetes",
        external_id=f"uid:{entity_id}",
        observed_at=NOW,
        properties={"namespace": "payments", **(properties or {})},
    )


def _relationship(
    relationship_id: str,
    source: str,
    target: str,
    predicate: RelationshipType,
) -> Relationship:
    return Relationship(
        id=relationship_id,
        source_entity_id=source,
        target_entity_id=target,
        relationship_type=predicate,
        source_system="kubernetes",
        observed_at=NOW,
    )


def _snapshot(
    entities: list[Entity],
    relationships: list[Relationship],
    *,
    snapshot_id: str = "snapshot:incident",
) -> GraphSnapshot:
    return GraphSnapshot(
        snapshot_id=snapshot_id,
        collected_at=NOW,
        collector_name="test",
        collector_version="1",
        scope={"cluster": "production", "namespace": "payments"},
        entities=entities,
        relationships=relationships,
    )


def _blast(
    snapshot: GraphSnapshot,
    root: str = "pod:failed",
    failure_evidence: dict[str, set[str]] | None = None,
) -> BlastRadiusResponse:
    return calculate_blast_radius_from_snapshot(
        incident_id="incident:test",
        snapshot=snapshot,
        root_entity_id=root,
        failure_evidence=failure_evidence or {root: {"signal:root"}},
    )


def _ids(result: BlastRadiusResponse) -> set[str]:
    return {item.entity_id for item in result.affected_entities}


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine)
    return Session(engine)


def _incident(
    session: Session,
    *,
    snapshot_id: str | None,
    incident_id: str = "incident:pinned",
) -> None:
    now = utc_now_iso()
    session.add(
        IncidentRecord(
            incident_id=incident_id,
            fingerprint="fingerprint:pinned",
            status="open",
            severity="error",
            title="Pinned blast incident",
            summary="Historical blast must remain pinned.",
            cluster_name="production",
            namespace="payments",
            primary_signal_id="signal:root",
            topology_snapshot_id=snapshot_id,
            affected_entity_id="pod:failed",
            affected_object_kind="Pod",
            affected_object_name="pod:failed",
            first_observed_at=NOW.isoformat(),
            last_observed_at=NOW.isoformat(),
            recommendation_count=0,
            occurrence_count=1,
            created_at=now,
            updated_at=now,
            tenant_id=TEST_TENANT,
        )
    )
    session.commit()


def _pod(
    entity_id: str,
    *,
    ready: bool | None,
    reason: str | None = None,
) -> Entity:
    properties: dict = {"phase": "Running", "ready": ready}
    if reason:
        properties["phase"] = "Pending"
        properties["container_statuses"] = [
            {
                "ready": False,
                "waiting_reason": reason,
                "terminated_reason": None,
            }
        ]
    return _entity(entity_id, properties=properties)


def _service_graph(
    *,
    sibling_ready: bool | None,
    sibling_reason: str | None = None,
    include_target_universe: bool = True,
) -> GraphSnapshot:
    entities = [
        _pod("pod:failed", ready=False, reason="ErrImagePull"),
        _pod("pod:sibling", ready=sibling_ready, reason=sibling_reason),
        _entity("rs:one", kind="KubernetesReplicaSet"),
        _entity("deployment:one", kind="KubernetesDeployment"),
        _entity("service:one", kind="KubernetesService"),
    ]
    relationships = [
        _relationship("rel:dep-rs", "deployment:one", "rs:one", RelationshipType.OWNS),
        _relationship("rel:rs-root", "rs:one", "pod:failed", RelationshipType.OWNS),
        _relationship("rel:rs-sibling", "rs:one", "pod:sibling", RelationshipType.OWNS),
        _relationship("rel:route-root", "service:one", "pod:failed", RelationshipType.ROUTES_TO),
        _relationship("rel:route-sibling", "service:one", "pod:sibling", RelationshipType.ROUTES_TO),
    ]
    if include_target_universe:
        relationships.extend(
            [
                _relationship("rel:select-root", "service:one", "pod:failed", RelationshipType.SELECTS),
                _relationship("rel:select-sibling", "service:one", "pod:sibling", RelationshipType.SELECTS),
            ]
        )
    return _snapshot(entities, relationships)


def test_contains_never_propagates_impact() -> None:
    graph = _snapshot(
        [_entity("pod:failed"), _entity("namespace:one", kind="KubernetesNamespace")],
        [_relationship("rel:contains", "namespace:one", "pod:failed", RelationshipType.CONTAINS)],
    )
    assert _ids(_blast(graph)) == {"pod:failed"}


def test_contains_cannot_reverse_then_fan_out_to_sibling() -> None:
    graph = _snapshot(
        [_entity("pod:failed"), _entity("pod:healthy"), _entity("namespace:one", kind="KubernetesNamespace")],
        [
            _relationship("rel:contains-a", "namespace:one", "pod:failed", RelationshipType.CONTAINS),
            _relationship("rel:contains-b", "namespace:one", "pod:healthy", RelationshipType.CONTAINS),
        ],
    )
    assert _ids(_blast(graph)) == {"pod:failed"}


def test_namespace_is_not_operational_blast() -> None:
    result = _blast(
        _snapshot(
            [_entity("pod:failed"), _entity("namespace:one", kind="KubernetesNamespace")],
            [_relationship("rel:contains", "namespace:one", "pod:failed", RelationshipType.CONTAINS)],
        )
    )
    assert all(item.entity_kind != "KubernetesNamespace" for item in result.affected_entities)


def test_owns_rolls_child_failure_to_owner() -> None:
    result = _blast(
        _snapshot(
            [_entity("pod:failed"), _entity("rs:one", kind="KubernetesReplicaSet")],
            [_relationship("rel:owns", "rs:one", "pod:failed", RelationshipType.OWNS)],
        )
    )
    owner = next(item for item in result.affected_entities if item.entity_id == "rs:one")
    assert owner.impact_semantic == BlastImpactSemantic.OWNERSHIP_ROLLUP
    assert owner.path_traversal_directions == ["reverse"]


def test_pod_replicaset_deployment_uses_owns_path() -> None:
    result = _blast(_service_graph(sibling_ready=True))
    deployment = next(item for item in result.affected_entities if item.entity_id == "deployment:one")
    assert deployment.path_relationship_ids == ["rel:rs-root", "rel:dep-rs"]
    path = next(path for path in result.dependency_paths if path.path[-1] == "deployment:one")
    assert path.predicates == ["owns", "owns"]


def test_owner_rollup_does_not_fan_out_to_healthy_sibling() -> None:
    assert "pod:sibling" not in _ids(_blast(_service_graph(sibling_ready=True)))


def test_explicit_failed_sibling_is_observed_co_failure() -> None:
    result = _blast(_service_graph(sibling_ready=False, sibling_reason="ErrImagePull"))
    sibling = next(item for item in result.affected_entities if item.entity_id == "pod:sibling")
    assert sibling.impact_semantic == BlastImpactSemantic.OBSERVED_CO_FAILURE
    assert "pinned-health:pod:sibling" in sibling.evidence_ids


def test_correlated_signal_seed_is_observed_co_failure() -> None:
    graph = _snapshot([_entity("pod:failed"), _entity("pod:second")], [])
    result = _blast(
        graph,
        failure_evidence={
            "pod:failed": {"signal:one"},
            "pod:second": {"signal:two"},
        },
    )
    second = next(item for item in result.affected_entities if item.entity_id == "pod:second")
    assert second.impact_semantic == BlastImpactSemantic.OBSERVED_CO_FAILURE


def test_partial_backend_failure_excludes_service() -> None:
    assert "service:one" not in _ids(_blast(_service_graph(sibling_ready=True)))


def test_complete_backend_failure_includes_service() -> None:
    result = _blast(_service_graph(sibling_ready=False, sibling_reason="ErrImagePull"))
    service = next(item for item in result.affected_entities if item.entity_id == "service:one")
    assert service.impact_semantic == BlastImpactSemantic.AGGREGATE_IMPACT
    assert service.aggregate_evidence["ready_or_serving_target_count"] == 0
    assert service.aggregate_evidence["failed_or_unavailable_target_count"] == 2
    assert service.aggregate_evidence["reason"] == "zero_serving_backends"


def test_unknown_backend_health_excludes_service() -> None:
    result = _blast(_service_graph(sibling_ready=None))
    assert "service:one" not in _ids(result)
    assert result.warnings == ["aggregate_health_unknown:service:one"]


def test_unknown_target_universe_excludes_service() -> None:
    result = _blast(
        _service_graph(
            sibling_ready=False,
            sibling_reason="ErrImagePull",
            include_target_universe=False,
        )
    )
    assert "service:one" not in _ids(result)
    assert result.warnings == ["aggregate_health_unknown:service:one"]


def test_impacted_service_does_not_mark_backends_by_forward_selects() -> None:
    graph = _service_graph(sibling_ready=True)
    result = _blast(graph, root="service:one", failure_evidence={"service:one": {"signal:service"}})
    assert _ids(result) == {"service:one"}


@pytest.mark.parametrize(
    ("predicate", "expected"),
    [
        (RelationshipType.DEPENDS_ON, {"dependency:one", "dependent:one"}),
        (RelationshipType.CALLS, {"dependency:one", "dependent:one"}),
        (RelationshipType.USES, {"dependency:one", "dependent:one"}),
        (RelationshipType.RESOLVES_TO, {"dependency:one", "dependent:one"}),
        (RelationshipType.ATTACHED_TO, {"dependency:one", "dependent:one"}),
    ],
)
def test_dependency_like_predicates_propagate_only_reverse(
    predicate: RelationshipType,
    expected: set[str],
) -> None:
    graph = _snapshot(
        [_entity("dependent:one"), _entity("dependency:one")],
        [_relationship("rel:dependency", "dependent:one", "dependency:one", predicate)],
    )
    assert _ids(_blast(graph, root="dependency:one")) == expected
    assert _ids(_blast(graph, root="dependent:one")) == {"dependent:one"}


def test_exposes_propagates_only_forward() -> None:
    graph = _snapshot(
        [_entity("resource:one"), _entity("endpoint:one", kind="Endpoint")],
        [_relationship("rel:exposes", "resource:one", "endpoint:one", RelationshipType.EXPOSES)],
    )
    assert _ids(_blast(graph, root="resource:one")) == {"resource:one", "endpoint:one"}
    assert _ids(_blast(graph, root="endpoint:one")) == {"endpoint:one"}


def test_runs_propagates_forward_but_not_from_rollup_state() -> None:
    graph = _snapshot(
        [_entity("pod:failed"), _entity("owner:one", kind="KubernetesDeployment"), _entity("pod:healthy")],
        [
            _relationship("rel:owns", "owner:one", "pod:failed", RelationshipType.OWNS),
            _relationship("rel:runs", "owner:one", "pod:healthy", RelationshipType.RUNS),
        ],
    )
    assert _ids(_blast(graph)) == {"pod:failed", "owner:one"}
    assert _ids(_blast(graph, root="owner:one")) == {"owner:one", "pod:healthy"}


@pytest.mark.parametrize(
    "predicate",
    [RelationshipType.PRODUCES, RelationshipType.PROTECTS, RelationshipType.TRIGGERS],
)
def test_non_impact_predicates_do_not_propagate(predicate: RelationshipType) -> None:
    graph = _snapshot(
        [_entity("pod:failed"), _entity("other:one")],
        [_relationship("rel:lineage", "pod:failed", "other:one", predicate)],
    )
    assert _ids(_blast(graph)) == {"pod:failed"}


def test_unknown_predicate_is_conservative() -> None:
    graph = _snapshot(
        [_entity("pod:failed"), _entity("other:one")],
        [_relationship("rel:unknown", "pod:failed", "other:one", RelationshipType.UNKNOWN)],
    )
    result = _blast(graph)
    assert _ids(result) == {"pod:failed"}
    assert result.warnings == ["unsupported_blast_predicate:unknown"]


def test_aggregate_service_can_propagate_to_caller() -> None:
    base = _service_graph(sibling_ready=False, sibling_reason="ErrImagePull")
    graph = base.model_copy(
        update={
            "entities": [*base.entities, _entity("caller:one", kind="Application")],
            "relationships": [
                *base.relationships,
                _relationship("rel:calls", "caller:one", "service:one", RelationshipType.CALLS),
            ],
        }
    )
    caller = next(item for item in _blast(graph).affected_entities if item.entity_id == "caller:one")
    assert caller.impact_semantic == BlastImpactSemantic.OPERATIONAL_IMPACT


def test_semantically_preferred_ownership_path_wins() -> None:
    graph = _snapshot(
        [_entity("pod:failed"), _entity("owner:one", kind="KubernetesDeployment")],
        [
            _relationship("rel:owns", "owner:one", "pod:failed", RelationshipType.OWNS),
            _relationship("rel:calls", "owner:one", "pod:failed", RelationshipType.CALLS),
        ],
    )
    owner = next(item for item in _blast(graph).affected_entities if item.entity_id == "owner:one")
    assert owner.impact_semantic == BlastImpactSemantic.OWNERSHIP_ROLLUP
    assert owner.path_relationship_ids == ["rel:owns"]


def test_path_selection_is_independent_of_relationship_order() -> None:
    graph = _service_graph(sibling_ready=False, sibling_reason="ErrImagePull")
    first = _blast(graph).model_dump(mode="json")
    reversed_graph = graph.model_copy(update={"relationships": list(reversed(graph.relationships))})
    second = _blast(reversed_graph).model_dump(mode="json")
    assert first == second


def test_traversal_is_bounded_by_existing_depth_limit() -> None:
    entities = [_entity(f"entity:{index}") for index in range(MAX_DEPTH + 3)]
    relationships = [
        _relationship(
            f"rel:{index}",
            f"entity:{index + 1}",
            f"entity:{index}",
            RelationshipType.DEPENDS_ON,
        )
        for index in range(MAX_DEPTH + 2)
    ]
    result = _blast(_snapshot(entities, relationships), root="entity:0")
    assert max(item.distance for item in result.affected_entities) == MAX_DEPTH
    assert f"entity:{MAX_DEPTH + 1}" not in _ids(result)


def test_cycles_terminate_safely() -> None:
    graph = _snapshot(
        [_entity("entity:a"), _entity("entity:b"), _entity("entity:c")],
        [
            _relationship("rel:ab", "entity:b", "entity:a", RelationshipType.DEPENDS_ON),
            _relationship("rel:bc", "entity:c", "entity:b", RelationshipType.DEPENDS_ON),
            _relationship("rel:ca", "entity:a", "entity:c", RelationshipType.DEPENDS_ON),
        ],
    )
    result = _blast(graph, root="entity:a")
    assert _ids(result) == {"entity:a", "entity:b", "entity:c"}


def test_structured_pod_health_classification() -> None:
    assert pinned_pod_health(_pod("pod:ready", ready=True)) == PinnedRuntimeHealth.READY
    assert pinned_pod_health(_pod("pod:failed", ready=False, reason="CrashLoopBackOff")) == PinnedRuntimeHealth.FAILED
    assert pinned_pod_health(_pod("pod:unknown", ready=False)) == PinnedRuntimeHealth.UNKNOWN


def test_legacy_api_construction_remains_compatible() -> None:
    entity = BlastRadiusEntity(
        entity_id="entity:legacy",
        entity_name="legacy",
        distance=0,
        impact="direct",
        impact_score=1.0,
    )
    response = BlastRadiusResponse(
        incident_id="incident:legacy",
        root_entity_id="entity:legacy",
        root_entity_name="legacy",
        affected_entity_count=1,
        direct_impact_count=1,
        indirect_impact_count=0,
        potential_impact_count=0,
        affected_entities=[entity],
    )
    assert response.blast_policy_version == BLAST_POLICY_VERSION
    assert entity.impact_score_semantics == "distance_heuristic_not_probability"


def test_impact_score_formula_is_unchanged_and_not_probability() -> None:
    assert [calculate_impact_score(value) for value in range(5)] == [1.0, 0.85, 0.65, 0.45, 0.25]


def test_compatibility_traversal_is_directional() -> None:
    relationship = _relationship(
        "rel:depends",
        "dependent:one",
        "dependency:one",
        RelationshipType.DEPENDS_ON,
    )
    assert traverse_blast_radius("dependency:one", [relationship], 5) == ["dependency:one", "dependent:one"]
    assert traverse_blast_radius("dependent:one", [relationship], 5) == ["dependent:one"]


def test_incident_pin_is_mandatory_and_latest_is_not_used() -> None:
    session = _session()
    try:
        save_snapshot(
            session,
            _service_graph(sibling_ready=True).model_copy(
                update={"snapshot_id": "snapshot:latest-only"}
            ),
            tenant_id=TEST_TENANT,
        )
        _incident(session, snapshot_id=None)
        with pytest.raises(
            ValueError,
            match="does not reference a topology snapshot",
        ):
            calculate_blast_radius(session, "incident:pinned", tenant_id=TEST_TENANT)
    finally:
        session.close()


def test_later_topology_cannot_change_historical_blast() -> None:
    session = _session()
    try:
        pinned = _service_graph(sibling_ready=True).model_copy(
            update={"snapshot_id": "snapshot:pinned-partial"}
        )
        later = _service_graph(
            sibling_ready=False,
            sibling_reason="ErrImagePull",
        ).model_copy(update={"snapshot_id": "snapshot:later-outage"})
        save_snapshot(session, pinned, tenant_id=TEST_TENANT)
        _incident(session, snapshot_id=pinned.snapshot_id)
        before = calculate_blast_radius(
            session, "incident:pinned", tenant_id=TEST_TENANT
        )
        save_snapshot(session, later, tenant_id=TEST_TENANT)
        after = calculate_blast_radius(
            session, "incident:pinned", tenant_id=TEST_TENANT
        )
        assert before.model_dump(mode="json") == after.model_dump(mode="json")
        assert "service:one" not in _ids(after)
    finally:
        session.close()


def test_later_recovery_cannot_rewrite_pinned_service_outage() -> None:
    session = _session()
    try:
        pinned = _service_graph(
            sibling_ready=False,
            sibling_reason="ErrImagePull",
        ).model_copy(update={"snapshot_id": "snapshot:pinned-outage"})
        later = _service_graph(sibling_ready=True).model_copy(
            update={"snapshot_id": "snapshot:later-recovery"}
        )
        save_snapshot(session, pinned, tenant_id=TEST_TENANT)
        _incident(session, snapshot_id=pinned.snapshot_id)
        save_snapshot(session, later, tenant_id=TEST_TENANT)
        result = calculate_blast_radius(
            session, "incident:pinned", tenant_id=TEST_TENANT
        )
        assert "service:one" in _ids(result)
        service = next(item for item in result.affected_entities if item.entity_id == "service:one")
        assert service.aggregate_evidence["snapshot_id"] == "snapshot:pinned-outage"
    finally:
        session.close()


@pytest.mark.parametrize("predicate", sorted(ACTIVE_BLAST_PREDICATES))
def test_every_active_predicate_has_explicit_policy(predicate: str) -> None:
    assert blast_policy_for(predicate) is not None


def test_policy_registry_has_no_implicit_active_fallback() -> None:
    assert set(BLAST_IMPACT_POLICIES) == ACTIVE_BLAST_PREDICATES
    assert blast_policy_for("not_a_tc2_predicate") is None


def test_contains_and_unsupported_policy_maturity_is_explicit() -> None:
    assert BLAST_IMPACT_POLICIES["contains"].maturity == BlastPolicyMaturity.NON_PROPAGATING
    assert BLAST_IMPACT_POLICIES["produces"].maturity == BlastPolicyMaturity.UNSUPPORTED_FOR_IMPACT_V1
    assert BLAST_IMPACT_POLICIES["contains"].allowed_traversal == BlastTraversal.NONE


def test_policy_machine_contract_does_not_drift() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["policy_version"] == BLAST_POLICY_VERSION
    assert set(payload["active_predicates"]) == ACTIVE_BLAST_PREDICATES
    by_predicate = {item["predicate"]: item for item in payload["policies"]}
    assert set(by_predicate) == ACTIVE_BLAST_PREDICATES

    for predicate, policy in BLAST_IMPACT_POLICIES.items():
        contract = by_predicate[predicate]
        assert contract["relationship_direction"] == policy.relationship_direction
        assert contract["impact_semantic"] == policy.impact_semantic.value
        assert contract["allowed_traversal"] == policy.allowed_traversal.value
        assert contract["conditional"] is policy.conditional
        assert contract["aggregate_evaluator"] == policy.aggregate_evaluator
        assert contract["can_expand_from_states"] == [state.value for state in policy.can_expand_from_states]
        assert contract["maturity"] == policy.maturity.value
        assert contract["policy_version"] == policy.policy_version
