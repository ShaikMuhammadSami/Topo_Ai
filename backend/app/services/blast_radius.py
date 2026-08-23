from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.blast_radius import (
    BlastRadiusEntity,
    BlastRadiusResponse,
    DependencyPath,
)
from app.models.incident_records import IncidentRecordView
from app.models.topology import Entity, GraphSnapshot, Relationship
from app.repositories.incident_record_repository import load_incident_record
from app.repositories.signal_repository import (
    list_signals_by_incident_fingerprint,
    load_signal,
)
from app.repositories.topology_snapshot_repository import load_topology_snapshot
from app.services.blast_impact_policy import (
    BlastImpactSemantic,
    BlastTraversal,
    blast_policy_for,
)
from app.services.canonical_identity import (
    resolve_snapshot_entity_identity,
    resolved_snapshot_entity,
)
from app.services.incident_grouping import is_failure_signal
from app.services.pinned_runtime_health import (
    PinnedRuntimeHealth,
    pinned_pod_health,
)


MAX_DEPTH = 5

_SEMANTIC_PRIORITY = {
    BlastImpactSemantic.DIRECT_FAILURE: 0,
    BlastImpactSemantic.OBSERVED_CO_FAILURE: 1,
    BlastImpactSemantic.OWNERSHIP_ROLLUP: 2,
    BlastImpactSemantic.AGGREGATE_IMPACT: 3,
    BlastImpactSemantic.OPERATIONAL_IMPACT: 4,
    BlastImpactSemantic.STRUCTURAL_CONTEXT: 5,
    BlastImpactSemantic.UNKNOWN_UNPROVEN: 6,
}

_PREDICATE_PRIORITY = {
    "owns": 0,
    "routes_to": 1,
    "selects": 2,
    "depends_on": 3,
    "calls": 4,
    "uses": 5,
    "resolves_to": 6,
    "attached_to": 7,
    "exposes": 8,
    "runs": 9,
}


def traverse_blast_radius(
    start_entity_id: str,
    relationships,
    max_hops: int,
) -> list[str]:
    """Compatibility helper using explicit unconditional policy only.

    Product blast reasoning uses ``calculate_blast_radius_from_snapshot`` so
    conditional aggregate semantics have entities and pinned health available.
    """

    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(start_entity_id, 0)])
    ordered_relationships = sorted(
        relationships,
        key=lambda relationship: relationship.id,
    )

    while queue:
        entity_id, distance = queue.popleft()
        if entity_id in visited:
            continue
        visited.add(entity_id)
        if distance >= max_hops:
            continue

        for relationship in ordered_relationships:
            policy = blast_policy_for(
                relationship.relationship_type.value
            )
            if policy is None or policy.conditional:
                continue
            if (
                policy.allowed_traversal == BlastTraversal.REVERSE
                and relationship.target_entity_id == entity_id
            ):
                queue.append((relationship.source_entity_id, distance + 1))
            elif (
                policy.allowed_traversal == BlastTraversal.FORWARD
                and relationship.source_entity_id == entity_id
            ):
                queue.append((relationship.target_entity_id, distance + 1))

    return sorted(visited)


@dataclass(frozen=True)
class _PathEdge:
    relationship_id: str
    predicate: str
    traversal_direction: str
    relationship_origin: str | None
    relationship_source_system: str


@dataclass(frozen=True)
class _ImpactCandidate:
    entity_id: str
    semantic: BlastImpactSemantic
    distance: int
    path: tuple[str, ...]
    edges: tuple[_PathEdge, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    aggregate_evidence_items: tuple[tuple[str, object], ...] = ()

    @property
    def aggregate_evidence(self) -> dict[str, object] | None:
        if not self.aggregate_evidence_items:
            return None
        return dict(self.aggregate_evidence_items)

    @property
    def selection_key(self) -> tuple[object, ...]:
        return (
            _SEMANTIC_PRIORITY[self.semantic],
            self.distance,
            tuple(
                _PREDICATE_PRIORITY.get(edge.predicate, 100)
                for edge in self.edges
            ),
            tuple(edge.relationship_id for edge in self.edges),
            self.path,
        )


@dataclass(frozen=True)
class _AggregateAvailability:
    impacted: bool
    known: bool
    evidence: dict[str, object]


def calculate_impact_score(distance: int) -> float:
    """Legacy deterministic priority heuristic; not a probability."""

    if distance == 0:
        return 1.0
    if distance == 1:
        return 0.85
    if distance == 2:
        return 0.65
    if distance == 3:
        return 0.45
    return 0.25


def impact_label(distance: int) -> str:
    if distance == 0:
        return "direct"
    if distance == 1:
        return "dependent"
    if distance == 2:
        return "indirect"
    return "potential"


def calculate_risk_score(entity: BlastRadiusEntity) -> float:
    """Legacy distance-adjusted risk heuristic; not a probability."""

    impact_mapping = {
        "direct": 0.9,
        "dependent": 0.75,
        "indirect": 0.5,
        "potential": 0.3,
    }
    base_score = impact_mapping.get(entity.impact, 0.1)
    adjusted = base_score * (1 - entity.distance * 0.05)
    return max(min(adjusted, 1.0), 0.0)


def _relationship_origin(relationship: Relationship) -> str | None:
    if relationship.provenance is None:
        return None
    return relationship.provenance.origin.value


def _path_edge(
    relationship: Relationship,
    traversal_direction: str,
) -> _PathEdge:
    return _PathEdge(
        relationship_id=relationship.id,
        predicate=relationship.relationship_type.value,
        traversal_direction=traversal_direction,
        relationship_origin=_relationship_origin(relationship),
        relationship_source_system=relationship.source_system,
    )


def _resolve_signal_entity(
    snapshot: GraphSnapshot,
    signal,
) -> Entity | None:
    attempts = (
        {"identifier": signal.involved_entity_id},
        {
            "source_native_id": signal.involved_object_uid,
            "source_system": signal.source_system,
            "cluster_name": signal.cluster_name,
            "namespace": signal.namespace,
        },
        {
            "source_system": signal.source_system,
            "kind": signal.involved_object_kind,
            "name": signal.involved_object_name,
            "cluster_name": signal.cluster_name,
            "namespace": signal.namespace,
        },
    )

    for parameters in attempts:
        if not any(parameters.values()):
            continue
        resolution = resolve_snapshot_entity_identity(
            snapshot,
            **parameters,
        )
        entity = resolved_snapshot_entity(snapshot, resolution)
        if entity is not None:
            return entity

    return None


def _incident_failure_evidence(
    session: Session,
    incident: IncidentRecordView,
    snapshot: GraphSnapshot,
    root_entity_id: str,
) -> dict[str, set[str]]:
    """Load only correlated durable failures bound to the same snapshot."""

    evidence: dict[str, set[str]] = {
        root_entity_id: {incident.primary_signal_id},
    }
    summaries = list_signals_by_incident_fingerprint(
        session,
        cluster_name=incident.cluster_name,
        namespace=incident.namespace,
        fingerprint=incident.fingerprint,
        limit=200,
    )

    for summary in summaries:
        signal = load_signal(session, summary.signal_id)
        if signal is None or not is_failure_signal(signal):
            continue
        if signal.topology_snapshot_id != snapshot.snapshot_id:
            continue
        if signal.first_observed_at > incident.last_observed_at:
            continue

        entity = _resolve_signal_entity(snapshot, signal)
        if entity is None:
            continue
        evidence.setdefault(entity.id, set()).add(signal.signal_id)

    return evidence


def _add_pinned_co_failures(
    snapshot: GraphSnapshot,
    failure_evidence: dict[str, set[str]],
) -> None:
    """Add explicitly failed siblings, never merely co-owned siblings."""

    entities = {entity.id: entity for entity in snapshot.entities}
    direct_ids = set(failure_evidence)
    owner_ids = {
        relationship.source_entity_id
        for relationship in snapshot.relationships
        if relationship.relationship_type.value == "owns"
        and relationship.target_entity_id in direct_ids
    }

    for relationship in snapshot.relationships:
        if relationship.relationship_type.value != "owns":
            continue
        if relationship.source_entity_id not in owner_ids:
            continue
        sibling = entities.get(relationship.target_entity_id)
        if sibling is None or sibling.id in failure_evidence:
            continue
        if pinned_pod_health(sibling) != PinnedRuntimeHealth.FAILED:
            continue
        failure_evidence[sibling.id] = {
            snapshot.snapshot_id,
            f"pinned-health:{sibling.id}",
        }


def _service_target_availability(
    snapshot: GraphSnapshot,
    service_id: str,
    failed_entity_ids: set[str],
) -> _AggregateAvailability:
    entities = {entity.id: entity for entity in snapshot.entities}
    service = entities.get(service_id)

    if service is None or service.kind != "KubernetesService":
        return _AggregateAvailability(
            impacted=False,
            known=False,
            evidence={
                "aggregate_evaluator": (
                    "kubernetes_service_backend_availability_v1"
                ),
                "reason": "unsupported_aggregate_source",
            },
        )

    selected_relationships = sorted(
        (
            relationship
            for relationship in snapshot.relationships
            if relationship.source_entity_id == service_id
            and relationship.relationship_type.value == "selects"
            and entities.get(relationship.target_entity_id) is not None
            and entities[relationship.target_entity_id].kind == "KubernetesPod"
        ),
        key=lambda relationship: relationship.id,
    )
    target_ids = sorted(
        {
            relationship.target_entity_id
            for relationship in selected_relationships
        }
    )

    if not target_ids:
        return _AggregateAvailability(
            impacted=False,
            known=False,
            evidence={
                "aggregate_evaluator": (
                    "kubernetes_service_backend_availability_v1"
                ),
                "reason": "aggregate_target_universe_unknown",
                "selected_target_count": 0,
                "ready_or_serving_target_count": 0,
                "failed_or_unavailable_target_count": 0,
                "unknown_target_count": 0,
            },
        )

    ready_ids: list[str] = []
    failed_ids: list[str] = []
    unknown_ids: list[str] = []

    for target_id in target_ids:
        target = entities[target_id]
        if target_id in failed_entity_ids:
            failed_ids.append(target_id)
            continue
        health = pinned_pod_health(target)
        if health == PinnedRuntimeHealth.READY:
            ready_ids.append(target_id)
        elif health == PinnedRuntimeHealth.FAILED:
            failed_ids.append(target_id)
        else:
            unknown_ids.append(target_id)

    evidence: dict[str, object] = {
        "aggregate_evaluator": (
            "kubernetes_service_backend_availability_v1"
        ),
        "target_universe_source": "pinned_selects_relationships",
        "selected_target_count": len(target_ids),
        "ready_or_serving_target_count": len(ready_ids),
        "failed_or_unavailable_target_count": len(failed_ids),
        "unknown_target_count": len(unknown_ids),
        "selected_target_ids": target_ids,
        "ready_or_serving_target_ids": ready_ids,
        "failed_or_unavailable_target_ids": failed_ids,
        "unknown_target_ids": unknown_ids,
        "target_relationship_ids": [
            relationship.id for relationship in selected_relationships
        ],
        "snapshot_id": snapshot.snapshot_id,
    }
    known = not unknown_ids
    impacted = known and not ready_ids and len(failed_ids) == len(target_ids)

    if ready_ids:
        evidence["reason"] = "serving_backend_remains"
    elif unknown_ids:
        evidence["reason"] = "aggregate_health_unknown"
    elif impacted:
        evidence["reason"] = "zero_serving_backends"

    return _AggregateAvailability(
        impacted=impacted,
        known=known,
        evidence=evidence,
    )


def _candidate_with_edge(
    current: _ImpactCandidate,
    *,
    neighbor_id: str,
    semantic: BlastImpactSemantic,
    relationship: Relationship,
    traversal_direction: str,
    aggregate_evidence: dict[str, object] | None = None,
) -> _ImpactCandidate:
    return _ImpactCandidate(
        entity_id=neighbor_id,
        semantic=semantic,
        distance=current.distance + 1,
        path=(*current.path, neighbor_id),
        edges=(
            *current.edges,
            _path_edge(relationship, traversal_direction),
        ),
        evidence_ids=current.evidence_ids,
        aggregate_evidence_items=tuple(
            sorted((aggregate_evidence or {}).items())
        ),
    )


def _semantic_blast_candidates(
    snapshot: GraphSnapshot,
    *,
    root_entity_id: str,
    failure_evidence: dict[str, set[str]],
) -> tuple[dict[str, _ImpactCandidate], list[str]]:
    entities = {entity.id: entity for entity in snapshot.entities}
    relationships = sorted(
        snapshot.relationships,
        key=lambda relationship: (
            relationship.relationship_type.value,
            relationship.source_entity_id,
            relationship.target_entity_id,
            relationship.id,
        ),
    )
    by_state: dict[
        tuple[str, BlastImpactSemantic],
        _ImpactCandidate,
    ] = {}
    best_by_entity: dict[str, _ImpactCandidate] = {}
    queue: deque[_ImpactCandidate] = deque()
    warnings: set[str] = set()
    failed_entity_ids = set(failure_evidence)
    aggregate_cache: dict[str, _AggregateAvailability] = {}

    def offer(candidate: _ImpactCandidate) -> None:
        if candidate.entity_id not in entities:
            return
        state_key = (candidate.entity_id, candidate.semantic)
        existing_state = by_state.get(state_key)
        if (
            existing_state is not None
            and existing_state.selection_key <= candidate.selection_key
        ):
            return
        by_state[state_key] = candidate
        existing_entity = best_by_entity.get(candidate.entity_id)
        if (
            existing_entity is None
            or candidate.selection_key < existing_entity.selection_key
        ):
            best_by_entity[candidate.entity_id] = candidate
        queue.append(candidate)

    for entity_id in sorted(failure_evidence):
        semantic = (
            BlastImpactSemantic.DIRECT_FAILURE
            if entity_id == root_entity_id
            else BlastImpactSemantic.OBSERVED_CO_FAILURE
        )
        offer(
            _ImpactCandidate(
                entity_id=entity_id,
                semantic=semantic,
                distance=0,
                path=(entity_id,),
                evidence_ids=tuple(sorted(failure_evidence[entity_id])),
            )
        )

    while queue:
        current = queue.popleft()
        if by_state.get((current.entity_id, current.semantic)) != current:
            continue
        if current.distance >= MAX_DEPTH:
            continue

        for relationship in relationships:
            predicate = relationship.relationship_type.value
            policy = blast_policy_for(predicate)
            if policy is None:
                warnings.add(f"unsupported_blast_predicate:{predicate}")
                continue
            if current.semantic not in policy.can_expand_from_states:
                continue

            neighbor_id: str | None = None
            traversal_direction: str | None = None
            if (
                policy.allowed_traversal == BlastTraversal.REVERSE
                and relationship.target_entity_id == current.entity_id
            ):
                neighbor_id = relationship.source_entity_id
                traversal_direction = "reverse"
            elif (
                policy.allowed_traversal == BlastTraversal.FORWARD
                and relationship.source_entity_id == current.entity_id
            ):
                neighbor_id = relationship.target_entity_id
                traversal_direction = "forward"
            elif (
                policy.allowed_traversal == BlastTraversal.CONDITIONAL_REVERSE
                and relationship.target_entity_id == current.entity_id
            ):
                neighbor_id = relationship.source_entity_id
                traversal_direction = "reverse"

            if neighbor_id is None or traversal_direction is None:
                continue

            if policy.aggregate_evaluator:
                source = entities.get(neighbor_id)
                target = entities.get(current.entity_id)
                if (
                    source is None
                    or target is None
                    or source.kind != "KubernetesService"
                    or target.kind != "KubernetesPod"
                ):
                    continue
                availability = aggregate_cache.get(source.id)
                if availability is None:
                    availability = _service_target_availability(
                        snapshot,
                        source.id,
                        failed_entity_ids,
                    )
                    aggregate_cache[source.id] = availability
                if not availability.known:
                    warnings.add(f"aggregate_health_unknown:{source.id}")
                if not availability.impacted:
                    continue
                offer(
                    _candidate_with_edge(
                        current,
                        neighbor_id=neighbor_id,
                        semantic=BlastImpactSemantic.AGGREGATE_IMPACT,
                        relationship=relationship,
                        traversal_direction=traversal_direction,
                        aggregate_evidence=availability.evidence,
                    )
                )
                continue

            offer(
                _candidate_with_edge(
                    current,
                    neighbor_id=neighbor_id,
                    semantic=policy.impact_semantic,
                    relationship=relationship,
                    traversal_direction=traversal_direction,
                )
            )

    return best_by_entity, sorted(warnings)


def calculate_blast_radius_from_snapshot(
    *,
    incident_id: str,
    snapshot: GraphSnapshot,
    root_entity_id: str,
    root_entity_name: str | None = None,
    failure_evidence: dict[str, set[str]] | None = None,
) -> BlastRadiusResponse:
    """Pure pinned-snapshot semantic traversal used by product and tests."""

    resolution = resolve_snapshot_entity_identity(
        snapshot,
        identifier=root_entity_id,
    )
    root_entity = resolved_snapshot_entity(snapshot, resolution)
    if root_entity is None:
        raise ValueError(
            "Incident affected entity could not be resolved in its pinned "
            "topology snapshot"
        )

    evidence = {
        entity_id: set(values)
        for entity_id, values in (failure_evidence or {}).items()
    }
    evidence.setdefault(root_entity.id, set())
    _add_pinned_co_failures(snapshot, evidence)
    candidates, warnings = _semantic_blast_candidates(
        snapshot,
        root_entity_id=root_entity.id,
        failure_evidence=evidence,
    )
    entities = {entity.id: entity for entity in snapshot.entities}
    impacted: list[BlastRadiusEntity] = []
    paths: list[DependencyPath] = []

    for candidate in sorted(
        candidates.values(),
        key=lambda item: (
            item.distance,
            _SEMANTIC_PRIORITY[item.semantic],
            item.entity_id,
        ),
    ):
        entity = entities[candidate.entity_id]
        blast_entity = BlastRadiusEntity(
            entity_id=entity.id,
            entity_kind=entity.kind,
            entity_name=entity.name,
            namespace=entity.properties.get("namespace"),
            distance=candidate.distance,
            impact=impact_label(candidate.distance),
            impact_score=calculate_impact_score(candidate.distance),
            relationship=(
                candidate.edges[-1].predicate if candidate.edges else None
            ),
            impact_semantic=candidate.semantic,
            evidence_ids=list(candidate.evidence_ids),
            path_relationship_ids=[
                edge.relationship_id for edge in candidate.edges
            ],
            path_traversal_directions=[
                edge.traversal_direction for edge in candidate.edges
            ],
            path_relationship_origins=[
                edge.relationship_origin for edge in candidate.edges
            ],
            path_relationship_source_systems=[
                edge.relationship_source_system for edge in candidate.edges
            ],
            aggregate_evidence=candidate.aggregate_evidence,
        )
        blast_entity.risk_score = calculate_risk_score(blast_entity)
        impacted.append(blast_entity)

        if candidate.distance > 0:
            paths.append(
                DependencyPath(
                    path=list(candidate.path),
                    relationship_ids=[
                        edge.relationship_id for edge in candidate.edges
                    ],
                    predicates=[edge.predicate for edge in candidate.edges],
                    traversal_directions=[
                        edge.traversal_direction for edge in candidate.edges
                    ],
                    relationship_origins=[
                        edge.relationship_origin for edge in candidate.edges
                    ],
                    relationship_source_systems=[
                        edge.relationship_source_system
                        for edge in candidate.edges
                    ],
                    impact_semantic=candidate.semantic,
                )
            )

    return BlastRadiusResponse(
        incident_id=incident_id,
        root_entity_id=root_entity.id,
        root_entity_name=root_entity_name or root_entity.name,
        affected_entity_count=len(impacted),
        direct_impact_count=sum(item.distance == 0 for item in impacted),
        indirect_impact_count=sum(item.distance == 1 for item in impacted),
        potential_impact_count=sum(item.distance >= 2 for item in impacted),
        affected_entities=impacted,
        dependency_paths=sorted(
            paths,
            key=lambda item: (
                len(item.path),
                tuple(item.path),
                tuple(item.relationship_ids),
            ),
        ),
        warnings=warnings,
    )


def calculate_blast_radius(
    session: Session,
    incident_id: str,
) -> BlastRadiusResponse:
    incident = load_incident_record(
        session=session,
        incident_id=incident_id,
    )
    if incident is None:
        raise ValueError("Incident not found")
    if not incident.affected_entity_id:
        raise ValueError("Incident has no affected entity")
    if not incident.topology_snapshot_id:
        raise ValueError("Incident does not reference a topology snapshot")

    snapshot = load_topology_snapshot(
        session=session,
        snapshot_id=incident.topology_snapshot_id,
    )
    if snapshot is None:
        raise ValueError("Topology snapshot not found")

    root_resolution = resolve_snapshot_entity_identity(
        snapshot,
        identifier=incident.affected_entity_id,
    )
    root_entity = resolved_snapshot_entity(snapshot, root_resolution)
    if root_entity is None:
        raise ValueError(
            "Incident affected entity could not be resolved in its pinned "
            "topology snapshot"
        )

    failure_evidence = _incident_failure_evidence(
        session,
        incident,
        snapshot,
        root_entity.id,
    )
    return calculate_blast_radius_from_snapshot(
        incident_id=incident_id,
        snapshot=snapshot,
        root_entity_id=root_entity.id,
        root_entity_name=root_entity.name,
        failure_evidence=failure_evidence,
    )
