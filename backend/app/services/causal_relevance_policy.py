from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Iterable

from app.models.causal_relevance import (
    CAUSAL_RELEVANCE_POLICY_VERSION,
    CandidateCausalRelevanceAudit,
    CausalPathHop,
    CausalPathSemantic,
    CausalPredicateSupport,
    CausalRelevanceStatus,
    CausalTraversalDirection,
)
from app.models.topology import GraphSnapshot, Relationship


@dataclass(frozen=True)
class CausalRelationshipPolicy:
    predicate: str
    tc2_direction: str
    traversal_direction: CausalTraversalDirection
    semantic_class: CausalPathSemantic
    support: CausalPredicateSupport
    reason: str
    allowed_source_kinds: tuple[str, ...] = ()
    allowed_effect_kinds: tuple[str, ...] = ()
    policy_version: str = CAUSAL_RELEVANCE_POLICY_VERSION


# This is intentionally an allow-list. A TC-2 predicate that is absent here,
# including a future enum member, has no causal traversal semantics.
CAUSAL_RELATIONSHIP_POLICIES: dict[str, CausalRelationshipPolicy] = {
    "attached_to": CausalRelationshipPolicy(
        predicate="attached_to",
        tc2_direction="attached object -> attachment target",
        traversal_direction=CausalTraversalDirection.NONE,
        semantic_class=CausalPathSemantic.RUNTIME_HOSTING,
        support=CausalPredicateSupport.UNSUPPORTED,
        reason=(
            "TC-2 uses attached_to across host, network, and cloud domains; "
            "CR-1 has no measured cross-domain causal rule."
        ),
    ),
    "calls": CausalRelationshipPolicy(
        predicate="calls",
        tc2_direction="caller -> destination",
        traversal_direction=CausalTraversalDirection.REVERSE,
        semantic_class=CausalPathSemantic.DEPENDENCY_IMPACT,
        support=CausalPredicateSupport.SUPPORTED,
        reason="A changed destination can affect its caller.",
    ),
    "contains": CausalRelationshipPolicy(
        predicate="contains",
        tc2_direction="scope/container -> member",
        traversal_direction=CausalTraversalDirection.NONE,
        semantic_class=CausalPathSemantic.STRUCTURAL_CONTEXT,
        support=CausalPredicateSupport.STRUCTURAL_ONLY,
        reason="Shared scope is context, not source-to-effect evidence.",
    ),
    "depends_on": CausalRelationshipPolicy(
        predicate="depends_on",
        tc2_direction="dependent -> dependency",
        traversal_direction=CausalTraversalDirection.REVERSE,
        semantic_class=CausalPathSemantic.DEPENDENCY_IMPACT,
        support=CausalPredicateSupport.SUPPORTED,
        reason="A changed dependency can affect its dependent.",
    ),
    "exposes": CausalRelationshipPolicy(
        predicate="exposes",
        tc2_direction="resource -> exposed endpoint/listener",
        traversal_direction=CausalTraversalDirection.FORWARD,
        semantic_class=CausalPathSemantic.RUNTIME_HOSTING,
        support=CausalPredicateSupport.SUPPORTED,
        reason="A resource mutation can affect its explicitly exposed endpoint.",
    ),
    "owns": CausalRelationshipPolicy(
        predicate="owns",
        tc2_direction="owner -> owned object",
        traversal_direction=CausalTraversalDirection.FORWARD,
        semantic_class=CausalPathSemantic.CONTROL_OWNERSHIP,
        support=CausalPredicateSupport.SUPPORTED,
        reason="A control/owner mutation can affect its owned runtime object.",
    ),
    "produces": CausalRelationshipPolicy(
        predicate="produces",
        tc2_direction="source revision/run -> artifact",
        traversal_direction=CausalTraversalDirection.FORWARD,
        semantic_class=CausalPathSemantic.ARTIFACT_LINEAGE,
        support=CausalPredicateSupport.SUPPORTED,
        reason="An explicit producer edge carries source-to-artifact lineage.",
    ),
    "protects": CausalRelationshipPolicy(
        predicate="protects",
        tc2_direction="intended control -> protected object (not uniform in AWS)",
        traversal_direction=CausalTraversalDirection.NONE,
        semantic_class=CausalPathSemantic.UNSUPPORTED_UNKNOWN,
        support=CausalPredicateSupport.UNSUPPORTED,
        reason="TC-2 documents an unresolved provider direction inconsistency.",
    ),
    "resolves_to": CausalRelationshipPolicy(
        predicate="resolves_to",
        tc2_direction="name/service -> declared resolution target",
        traversal_direction=CausalTraversalDirection.NONE,
        semantic_class=CausalPathSemantic.UNSUPPORTED_UNKNOWN,
        support=CausalPredicateSupport.UNSUPPORTED,
        reason="V1 has no measured DNS causal relevance scenario.",
    ),
    "routes_to": CausalRelationshipPolicy(
        predicate="routes_to",
        tc2_direction="routing source -> destination",
        traversal_direction=CausalTraversalDirection.NONE,
        semantic_class=CausalPathSemantic.UNSUPPORTED_UNKNOWN,
        support=CausalPredicateSupport.CONDITIONAL,
        reason="Static routing does not establish causal impact without evaluation.",
    ),
    "runs": CausalRelationshipPolicy(
        predicate="runs",
        tc2_direction="host/workload/owner -> running object",
        traversal_direction=CausalTraversalDirection.FORWARD,
        semantic_class=CausalPathSemantic.RUNTIME_HOSTING,
        support=CausalPredicateSupport.SUPPORTED,
        reason=(
            "Forward traversal supports existing host-to-runtime and legacy "
            "ReplicaSet-to-Pod observations without reverse sibling fan-out."
        ),
    ),
    "selects": CausalRelationshipPolicy(
        predicate="selects",
        tc2_direction="Service -> selected Pod",
        traversal_direction=CausalTraversalDirection.NONE,
        semantic_class=CausalPathSemantic.UNSUPPORTED_UNKNOWN,
        support=CausalPredicateSupport.CONDITIONAL,
        reason="Selector membership alone does not establish causal impact.",
    ),
    "triggers": CausalRelationshipPolicy(
        predicate="triggers",
        tc2_direction="source revision -> workflow run",
        traversal_direction=CausalTraversalDirection.FORWARD,
        semantic_class=CausalPathSemantic.ARTIFACT_LINEAGE,
        support=CausalPredicateSupport.SUPPORTED,
        reason="An observed trigger carries source-to-workflow lineage.",
    ),
    "uses": CausalRelationshipPolicy(
        predicate="uses",
        tc2_direction="workload/runtime object -> artifact",
        traversal_direction=CausalTraversalDirection.REVERSE,
        semantic_class=CausalPathSemantic.ARTIFACT_LINEAGE,
        support=CausalPredicateSupport.SUPPORTED,
        reason="An artifact mutation can affect an explicit runtime consumer.",
    ),
}


ACTIVE_TC2_PREDICATES = frozenset(CAUSAL_RELATIONSHIP_POLICIES)


_SEMANTIC_PRIORITY = {
    CausalPathSemantic.DIRECT_ENTITY: 0,
    CausalPathSemantic.CONTROL_OWNERSHIP: 1,
    CausalPathSemantic.ARTIFACT_LINEAGE: 2,
    CausalPathSemantic.DEPENDENCY_IMPACT: 3,
    CausalPathSemantic.RUNTIME_HOSTING: 4,
    CausalPathSemantic.OTHER_SUPPORTED: 5,
    CausalPathSemantic.STRUCTURAL_CONTEXT: 6,
    CausalPathSemantic.UNSUPPORTED_UNKNOWN: 7,
}


def policy_for_predicate(predicate: str) -> CausalRelationshipPolicy | None:
    """Return an explicit policy; unknown predicates never get a fallback."""

    return CAUSAL_RELATIONSHIP_POLICIES.get(str(predicate))


def topology_component_for_hops(hops: int | None) -> float:
    """The existing 13C distance mapping, centralized without score tuning."""

    if hops is None:
        return 0.0
    return {0: 1.00, 1: 0.85, 2: 0.65, 3: 0.45}.get(hops, 0.25)


def _path_semantic(
    classes: Iterable[CausalPathSemantic],
) -> CausalPathSemantic:
    unique = frozenset(classes)
    if not unique:
        return CausalPathSemantic.DIRECT_ENTITY
    if len(unique) == 1:
        return next(iter(unique))
    return CausalPathSemantic.OTHER_SUPPORTED


def _hop(relationship: Relationship) -> CausalPathHop | None:
    predicate = relationship.relationship_type.value
    policy = policy_for_predicate(predicate)
    if policy is None or policy.support != CausalPredicateSupport.SUPPORTED:
        return None
    if policy.traversal_direction == CausalTraversalDirection.FORWARD:
        source = relationship.source_entity_id
        target = relationship.target_entity_id
    elif policy.traversal_direction == CausalTraversalDirection.REVERSE:
        source = relationship.target_entity_id
        target = relationship.source_entity_id
    else:
        return None
    provenance = relationship.provenance
    return CausalPathHop(
        source_entity_id=source,
        target_entity_id=target,
        relationship_id=relationship.id,
        predicate=predicate,
        traversal_direction=policy.traversal_direction,
        semantic_class=policy.semantic_class,
        relationship_origin=provenance.origin if provenance is not None else None,
        relationship_source_system=relationship.source_system,
        relationship_source_component=(
            provenance.source_component if provenance is not None else None
        ),
        relationship_source_references=(
            list(provenance.source_references) if provenance is not None else []
        ),
        relationship_linker_version=(
            provenance.linker_version if provenance is not None else None
        ),
        relationship_provenance_completeness=(
            provenance.completeness
            if provenance is not None
            else "legacy_unspecified"
        ),
    )


def _audit(
    *,
    candidate_event_id: str,
    candidate_entity_id: str | None,
    affected_entity_id: str | None,
    status: CausalRelevanceStatus,
    semantic: CausalPathSemantic,
    entity_ids: Iterable[str] = (),
    hops: Iterable[CausalPathHop] = (),
    reason: str,
) -> CandidateCausalRelevanceAudit:
    selected_hops = list(hops)
    return CandidateCausalRelevanceAudit(
        candidate_event_id=candidate_event_id,
        candidate_entity_id=candidate_entity_id,
        affected_entity_id=affected_entity_id,
        relevance_status=status,
        path_semantic=semantic,
        path_entity_ids=list(entity_ids),
        path_relationship_ids=[item.relationship_id for item in selected_hops],
        path_predicates=[item.predicate for item in selected_hops],
        path_traversal_directions=[
            item.traversal_direction for item in selected_hops
        ],
        path_relationship_origins=[
            item.relationship_origin for item in selected_hops
        ],
        path_relationship_source_systems=[
            item.relationship_source_system for item in selected_hops
        ],
        path_hops=len(selected_hops),
        topology_component=topology_component_for_hops(
            len(selected_hops)
            if status in {CausalRelevanceStatus.DIRECT, CausalRelevanceStatus.SEMANTIC_PATH}
            else None
        ),
        hops=selected_hops,
        reason=reason,
    )


def evaluate_causal_relevance(
    snapshot: GraphSnapshot | None,
    *,
    candidate_event_id: str,
    candidate_entity_ids: Iterable[str],
    affected_entity_ids: Iterable[str],
    max_hops: int,
) -> CandidateCausalRelevanceAudit:
    """Find the best bounded semantic path in canonical source→effect order."""

    candidate_ids = sorted(set(candidate_entity_ids))
    affected_ids = sorted(set(affected_entity_ids))
    if snapshot is None:
        return _audit(
            candidate_event_id=candidate_event_id,
            candidate_entity_id=candidate_ids[0] if candidate_ids else None,
            affected_entity_id=affected_ids[0] if affected_ids else None,
            status=CausalRelevanceStatus.IDENTITY_UNRESOLVED,
            semantic=CausalPathSemantic.UNSUPPORTED_UNKNOWN,
            reason="Incident-pinned topology is unavailable; no path was inferred.",
        )

    snapshot_entity_ids = {entity.id for entity in snapshot.entities}
    starts = sorted(set(candidate_ids) & snapshot_entity_ids)
    targets = sorted(set(affected_ids) & snapshot_entity_ids)
    if not starts or not targets:
        return _audit(
            candidate_event_id=candidate_event_id,
            candidate_entity_id=starts[0] if starts else (candidate_ids[0] if candidate_ids else None),
            affected_entity_id=targets[0] if targets else (affected_ids[0] if affected_ids else None),
            status=CausalRelevanceStatus.IDENTITY_UNRESOLVED,
            semantic=CausalPathSemantic.UNSUPPORTED_UNKNOWN,
            reason=(
                "Candidate or affected identity is not present in the incident-pinned "
                "topology; no latest-topology fallback was used."
            ),
        )

    direct = sorted(set(starts) & set(targets))
    if direct:
        entity_id = direct[0]
        return _audit(
            candidate_event_id=candidate_event_id,
            candidate_entity_id=entity_id,
            affected_entity_id=entity_id,
            status=CausalRelevanceStatus.DIRECT,
            semantic=CausalPathSemantic.DIRECT_ENTITY,
            entity_ids=[entity_id],
            reason="The candidate directly applies to the incident affected entity.",
        )

    adjacency: dict[str, list[CausalPathHop]] = {}
    for relationship in sorted(snapshot.relationships, key=lambda item: item.id):
        hop = _hop(relationship)
        if hop is not None:
            adjacency.setdefault(hop.source_entity_id, []).append(hop)
    for values in adjacency.values():
        values.sort(key=lambda item: (item.relationship_id, item.target_entity_id))

    # State includes the semantic-class set because a pure ownership path and
    # a mixed path reaching the same intermediate node can have different
    # final priorities. No relationship serialization order is consulted.
    queue: list[tuple] = []
    best: dict[tuple[str, tuple[str, ...]], tuple] = {}
    for start in starts:
        order = (0, 0, (), (start,))
        heapq.heappush(queue, (order, start, (), (start,), ()))

    target_set = set(targets)
    while queue:
        order, node, class_values, entity_path, path_hops = heapq.heappop(queue)
        state = (node, class_values)
        previous = best.get(state)
        if previous is not None and previous <= order:
            continue
        best[state] = order

        if node in target_set and path_hops:
            semantic = _path_semantic(
                CausalPathSemantic(value) for value in class_values
            )
            return _audit(
                candidate_event_id=candidate_event_id,
                candidate_entity_id=entity_path[0],
                affected_entity_id=node,
                status=CausalRelevanceStatus.SEMANTIC_PATH,
                semantic=semantic,
                entity_ids=entity_path,
                hops=path_hops,
                reason=(
                    "A supported source-to-effect path exists in incident-pinned "
                    f"topology using {', '.join(item.predicate for item in path_hops)}."
                ),
            )
        if len(path_hops) >= max_hops:
            continue

        for next_hop in adjacency.get(node, []):
            if next_hop.target_entity_id in entity_path:
                continue
            next_classes = tuple(
                sorted(set(class_values) | {next_hop.semantic_class.value})
            )
            semantic = _path_semantic(
                CausalPathSemantic(value) for value in next_classes
            )
            next_entities = (*entity_path, next_hop.target_entity_id)
            next_hops = (*path_hops, next_hop)
            next_order = (
                _SEMANTIC_PRIORITY[semantic],
                len(next_hops),
                tuple(item.relationship_id for item in next_hops),
                next_entities,
            )
            heapq.heappush(
                queue,
                (
                    next_order,
                    next_hop.target_entity_id,
                    next_classes,
                    next_entities,
                    next_hops,
                ),
            )

    return _audit(
        candidate_event_id=candidate_event_id,
        candidate_entity_id=starts[0],
        affected_entity_id=targets[0],
        status=CausalRelevanceStatus.NO_SUPPORTED_PATH,
        semantic=CausalPathSemantic.UNSUPPORTED_UNKNOWN,
        reason=(
            "No supported causal path connects the candidate to an affected "
            "entity in the incident-pinned topology. This is missing support, "
            "not contradiction."
        ),
    )
