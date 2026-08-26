from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Iterable

from app.models.causal_candidates import (
    CAUSAL_CANDIDATE_ADMISSION_POLICY_VERSION,
    CandidateAdmissionBasis,
    CandidateAdmissionEvidenceReference,
    LineageAdmissionReason,
    LineageAdmissionState,
    LineagePathAudit,
)
from app.models.causal_relevance import (
    CAUSAL_RELEVANCE_POLICY_VERSION,
    CAUSAL_RELEVANCE_TOPOLOGY_POLICY_VERSION,
    CandidateCausalRelevanceAudit,
    CausalPathHop,
    CausalPathSemantic,
    CausalPredicateSupport,
    CausalRelevanceResolutionBasis,
    CausalRelevanceStatus,
    CausalTopologyPathState,
    CausalTraversalDirection,
    LineageRelevanceAnchorAudit,
    LineageRelevanceBridgeState,
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
    policy_version: str = CAUSAL_RELEVANCE_TOPOLOGY_POLICY_VERSION


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


@dataclass(frozen=True)
class TopologyPathEvaluation:
    """Policy-neutral output from the one accepted topology path engine."""

    source_entity_id: str | None
    affected_entity_id: str | None
    status: CausalRelevanceStatus
    semantic: CausalPathSemantic
    entity_ids: tuple[str, ...] = ()
    hops: tuple[CausalPathHop, ...] = ()
    reason: str = ""


def _topology_result_order(result: TopologyPathEvaluation) -> tuple:
    return (
        _SEMANTIC_PRIORITY[result.semantic],
        len(result.hops),
        tuple(item.relationship_id for item in result.hops),
        result.entity_ids,
        result.source_entity_id or "",
    )


def evaluate_topology_path(
    snapshot: GraphSnapshot | None,
    *,
    source_entity_ids: Iterable[str],
    affected_entity_ids: Iterable[str],
    max_hops: int,
) -> TopologyPathEvaluation:
    """Evaluate one bounded path with the unchanged v1 topology semantics."""

    source_ids = sorted(set(source_entity_ids))
    affected_ids = sorted(set(affected_entity_ids))
    if snapshot is None:
        return TopologyPathEvaluation(
            source_entity_id=source_ids[0] if source_ids else None,
            affected_entity_id=affected_ids[0] if affected_ids else None,
            status=CausalRelevanceStatus.IDENTITY_UNRESOLVED,
            semantic=CausalPathSemantic.UNSUPPORTED_UNKNOWN,
            reason="Incident-pinned topology is unavailable; no path was inferred.",
        )

    snapshot_entity_ids = {entity.id for entity in snapshot.entities}
    starts = sorted(set(source_ids) & snapshot_entity_ids)
    targets = sorted(set(affected_ids) & snapshot_entity_ids)
    if not starts or not targets:
        return TopologyPathEvaluation(
            source_entity_id=(
                starts[0] if starts else (source_ids[0] if source_ids else None)
            ),
            affected_entity_id=(
                targets[0]
                if targets
                else (affected_ids[0] if affected_ids else None)
            ),
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
        return TopologyPathEvaluation(
            source_entity_id=entity_id,
            affected_entity_id=entity_id,
            status=CausalRelevanceStatus.DIRECT,
            semantic=CausalPathSemantic.DIRECT_ENTITY,
            entity_ids=(entity_id,),
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
            return TopologyPathEvaluation(
                source_entity_id=entity_path[0],
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

    return TopologyPathEvaluation(
        source_entity_id=starts[0],
        affected_entity_id=targets[0],
        status=CausalRelevanceStatus.NO_SUPPORTED_PATH,
        semantic=CausalPathSemantic.UNSUPPORTED_UNKNOWN,
        reason=(
            "No supported causal path connects the candidate to an affected "
            "entity in the incident-pinned topology. This is missing support, "
            "not contradiction."
        ),
    )


def _audit(
    *,
    candidate_event_id: str,
    candidate_entity_id: str | None,
    result: TopologyPathEvaluation,
    policy_version: str,
    resolution_basis: CausalRelevanceResolutionBasis,
    relevance_anchor_entity_id: str | None = None,
    relevance_anchor_kind: str | None = None,
    bridge_state: LineageRelevanceBridgeState = (
        LineageRelevanceBridgeState.NOT_APPLICABLE
    ),
    bridge_reason: str | None = None,
    bridge_path_ids: Iterable[str] = (),
    bridge_evidence_refs: Iterable[CandidateAdmissionEvidenceReference] = (),
    bridge_source_change_id: str | None = None,
    bridge_revision: str | None = None,
    bridge_run_ids: Iterable[str] = (),
    bridge_image_digest: str | None = None,
    bridge_score: float | None = None,
    topology_path_state: CausalTopologyPathState | None = None,
    anchor_audits: Iterable[LineageRelevanceAnchorAudit] = (),
    reason: str | None = None,
) -> CandidateCausalRelevanceAudit:
    selected_hops = list(result.hops)
    if topology_path_state is None:
        topology_path_state = (
            CausalTopologyPathState.SUPPORTED
            if result.status
            in {CausalRelevanceStatus.DIRECT, CausalRelevanceStatus.SEMANTIC_PATH}
            else (
                CausalTopologyPathState.NOT_EVALUATED
                if result.status == CausalRelevanceStatus.IDENTITY_UNRESOLVED
                else CausalTopologyPathState.UNSUPPORTED
            )
        )
    return CandidateCausalRelevanceAudit(
        candidate_event_id=candidate_event_id,
        candidate_entity_id=candidate_entity_id,
        affected_entity_id=result.affected_entity_id,
        relevance_policy_version=policy_version,
        resolution_basis=resolution_basis,
        relevance_anchor_entity_id=relevance_anchor_entity_id,
        relevance_anchor_kind=relevance_anchor_kind,
        bridge_state=bridge_state,
        bridge_reason=bridge_reason,
        bridge_path_ids=list(bridge_path_ids),
        bridge_evidence_refs=list(bridge_evidence_refs),
        bridge_source_change_id=bridge_source_change_id,
        bridge_revision=bridge_revision,
        bridge_run_ids=list(bridge_run_ids),
        bridge_image_digest=bridge_image_digest,
        bridge_score=bridge_score,
        topology_path_state=topology_path_state,
        anchor_audits=list(anchor_audits),
        relevance_status=result.status,
        path_semantic=result.semantic,
        path_entity_ids=list(result.entity_ids),
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
            if result.status
            in {CausalRelevanceStatus.DIRECT, CausalRelevanceStatus.SEMANTIC_PATH}
            else None
        ),
        hops=selected_hops,
        reason=reason or result.reason,
    )


def _value(value: object | None) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return str(raw)


def _deduplicated_references(
    values: Iterable[CandidateAdmissionEvidenceReference],
) -> list[CandidateAdmissionEvidenceReference]:
    result: dict[tuple[str, str, str], CandidateAdmissionEvidenceReference] = {}
    for item in values:
        key = (item.reference_type, item.reference, item.source_system)
        result[key] = item
    return [result[key] for key in sorted(result)]


_RUNTIME_TOPOLOGY_REFERENCE_TYPES = frozenset(
    {
        "container_image_reference",
        "graph_entity_id",
        "kubernetes_owner_reference_uid",
        "kubernetes_requested_image_reference",
        "kubernetes_runtime_image_id",
        "kubernetes_runtime_status_image",
        "topology_relationship",
    }
)


def _bridge_references(
    values: Iterable[CandidateAdmissionEvidenceReference],
) -> list[CandidateAdmissionEvidenceReference]:
    """Keep SC-2 provider provenance separate from topology observations."""

    return _deduplicated_references(
        item
        for item in values
        if item.reference_type not in _RUNTIME_TOPOLOGY_REFERENCE_TYPES
        and item.source_system.casefold() != "kubernetes"
    )


def _unresolved_result(
    *,
    affected_entity_ids: Iterable[str],
    reason: str,
) -> TopologyPathEvaluation:
    affected_ids = sorted(set(affected_entity_ids))
    return TopologyPathEvaluation(
        source_entity_id=None,
        affected_entity_id=affected_ids[0] if affected_ids else None,
        status=CausalRelevanceStatus.IDENTITY_UNRESOLVED,
        semantic=CausalPathSemantic.UNSUPPORTED_UNKNOWN,
        reason=reason,
    )


def _anchor_audit(
    *,
    anchor_entity_id: str,
    anchor_kind: str,
    image_digest: str,
    paths: list[LineagePathAudit],
    evidence_refs: list[CandidateAdmissionEvidenceReference],
    result: TopologyPathEvaluation,
    bridge_state: LineageRelevanceBridgeState,
    bridge_reason: str,
) -> LineageRelevanceAnchorAudit:
    supported = result.status in {
        CausalRelevanceStatus.DIRECT,
        CausalRelevanceStatus.SEMANTIC_PATH,
    }
    return LineageRelevanceAnchorAudit(
        anchor_entity_id=anchor_entity_id,
        anchor_kind=anchor_kind,
        image_digest=image_digest,
        bridge_state=bridge_state,
        bridge_reason=bridge_reason,
        bridge_path_ids=sorted({item.path_id for item in paths}),
        bridge_evidence_refs=evidence_refs,
        source_change_id=paths[0].canonical_change_id,
        revision=paths[0].revision,
        run_ids=sorted({item.run_id for item in paths}),
        provider_evidence_ids=sorted(
            {
                evidence_id
                for item in paths
                for evidence_id in item.provider_evidence_ids
            }
        ),
        topology_path_state=(
            CausalTopologyPathState.SUPPORTED
            if supported
            else (
                CausalTopologyPathState.NOT_EVALUATED
                if result.status == CausalRelevanceStatus.IDENTITY_UNRESOLVED
                else CausalTopologyPathState.UNSUPPORTED
            )
        ),
        topology_path_semantic=result.semantic,
        topology_path_entity_ids=list(result.entity_ids),
        topology_path_relationship_ids=[
            item.relationship_id for item in result.hops
        ],
        topology_hops=len(result.hops),
        topology_component=topology_component_for_hops(
            len(result.hops) if supported else None
        ),
        reason=result.reason,
    )


def evaluate_causal_relevance(
    snapshot: GraphSnapshot | None,
    *,
    candidate_event_id: str,
    candidate_entity_ids: Iterable[str],
    affected_entity_ids: Iterable[str],
    max_hops: int,
    relevance_policy_version: str = CAUSAL_RELEVANCE_POLICY_VERSION,
    candidate_admission_policy_version: str | None = None,
    admission_basis: Iterable[CandidateAdmissionBasis | str] = (),
    lineage_admission_state: LineageAdmissionState | str | None = None,
    lineage_admission_reason: LineageAdmissionReason | str | None = None,
    lineage_paths: Iterable[LineagePathAudit] = (),
    admission_evidence_refs: Iterable[
        CandidateAdmissionEvidenceReference
    ] = (),
) -> CandidateCausalRelevanceAudit:
    """Resolve topology-native or exact-lineage-anchored causal relevance.

    V2 consumes only persisted SC-2 admission context. It performs no provider,
    registry, current-topology, or fuzzy identity lookup. Both modes call the
    same v1 topology path evaluator, and the provenance bridge adds no score.
    """

    candidate_ids = sorted(set(candidate_entity_ids))
    affected_ids = sorted(set(affected_entity_ids))
    if relevance_policy_version not in {
        CAUSAL_RELEVANCE_TOPOLOGY_POLICY_VERSION,
        CAUSAL_RELEVANCE_POLICY_VERSION,
    }:
        result = _unresolved_result(
            affected_entity_ids=affected_ids,
            reason=(
                "unsupported_policy_version: causal relevance policy "
                f"'{relevance_policy_version}' is not recognized."
            ),
        )
        return _audit(
            candidate_event_id=candidate_event_id,
            candidate_entity_id=None,
            result=result,
            policy_version=relevance_policy_version,
            resolution_basis=CausalRelevanceResolutionBasis.UNRESOLVED,
            bridge_state=LineageRelevanceBridgeState.INELIGIBLE,
            bridge_reason="unsupported_policy_version",
        )

    # V1 and topology-native V2 use the same engine and exact candidate IDs.
    snapshot_ids = (
        {entity.id for entity in snapshot.entities} if snapshot is not None else set()
    )
    native_starts = sorted(set(candidate_ids) & snapshot_ids)
    if (
        relevance_policy_version == CAUSAL_RELEVANCE_TOPOLOGY_POLICY_VERSION
        or native_starts
        or (snapshot is None and candidate_ids)
    ):
        result = evaluate_topology_path(
            snapshot,
            source_entity_ids=candidate_ids,
            affected_entity_ids=affected_ids,
            max_hops=max_hops,
        )
        return _audit(
            candidate_event_id=candidate_event_id,
            candidate_entity_id=result.source_entity_id,
            result=result,
            policy_version=relevance_policy_version,
            resolution_basis=(
                CausalRelevanceResolutionBasis.TOPOLOGY_ENTITY
                if native_starts
                else CausalRelevanceResolutionBasis.UNRESOLVED
            ),
        )

    if snapshot is None:
        result = _unresolved_result(
            affected_entity_ids=affected_ids,
            reason=(
                "pinned_topology_missing: incident-pinned topology is "
                "unavailable; no latest-topology fallback was used."
            ),
        )
        return _audit(
            candidate_event_id=candidate_event_id,
            candidate_entity_id=None,
            result=result,
            policy_version=relevance_policy_version,
            resolution_basis=CausalRelevanceResolutionBasis.UNRESOLVED,
            bridge_state=LineageRelevanceBridgeState.INCOMPLETE,
            bridge_reason="pinned_topology_missing",
        )

    target_ids = sorted(set(affected_ids) & snapshot_ids)
    if not target_ids:
        result = _unresolved_result(
            affected_entity_ids=affected_ids,
            reason=(
                "candidate_identity_unresolved: affected identity is not "
                "present in incident-pinned topology."
            ),
        )
        return _audit(
            candidate_event_id=candidate_event_id,
            candidate_entity_id=None,
            result=result,
            policy_version=relevance_policy_version,
            resolution_basis=CausalRelevanceResolutionBasis.UNRESOLVED,
            bridge_state=LineageRelevanceBridgeState.INCOMPLETE,
            bridge_reason="candidate_identity_unresolved",
        )

    basis_values = {_value(item) for item in admission_basis}
    state = _value(lineage_admission_state)
    admission_reason = _value(lineage_admission_reason)
    eligibility_reason: str | None = None
    if (
        candidate_admission_policy_version
        != CAUSAL_CANDIDATE_ADMISSION_POLICY_VERSION
    ):
        eligibility_reason = "lineage_admission_policy_not_eligible"
    elif state != LineageAdmissionState.ADMITTED.value:
        eligibility_reason = "lineage_admission_not_eligible"
    elif admission_reason != LineageAdmissionReason.EXACT_IMMUTABLE_LINEAGE.value:
        eligibility_reason = "lineage_admission_not_eligible"
    elif CandidateAdmissionBasis.EXACT_IMMUTABLE_LINEAGE.value not in basis_values:
        eligibility_reason = "lineage_admission_not_eligible"

    paths = sorted(
        list(lineage_paths),
        key=lambda item: (
            item.image_entity_id or "",
            item.image_digest,
            item.path_id,
        ),
    )
    evidence_refs = _deduplicated_references(admission_evidence_refs)
    bridge_evidence_refs = _bridge_references(evidence_refs)
    if eligibility_reason is None and not paths:
        eligibility_reason = "lineage_bridge_missing"
    if eligibility_reason is None and not bridge_evidence_refs:
        eligibility_reason = "lineage_bridge_evidence_missing"

    if eligibility_reason is not None:
        result = _unresolved_result(
            affected_entity_ids=target_ids,
            reason=(
                f"{eligibility_reason}: the source candidate has no usable "
                "exact immutable-lineage relevance anchor."
            ),
        )
        return _audit(
            candidate_event_id=candidate_event_id,
            candidate_entity_id=None,
            result=result,
            policy_version=relevance_policy_version,
            resolution_basis=CausalRelevanceResolutionBasis.UNRESOLVED,
            bridge_state=LineageRelevanceBridgeState.INELIGIBLE,
            bridge_reason=eligibility_reason,
        )

    for path in paths:
        if path.canonical_change_id != candidate_event_id:
            reason = "lineage_candidate_mismatch"
            result = _unresolved_result(
                affected_entity_ids=target_ids,
                reason=f"{reason}: persisted lineage belongs to another candidate.",
            )
            return _audit(
                candidate_event_id=candidate_event_id,
                candidate_entity_id=None,
                result=result,
                policy_version=relevance_policy_version,
                resolution_basis=CausalRelevanceResolutionBasis.UNRESOLVED,
                bridge_state=LineageRelevanceBridgeState.CONFLICT,
                bridge_reason=reason,
            )
        if (
            not path.image_entity_id
            or not path.image_entity_kind
            or not path.provider_evidence_ids
            or path.image_entity_id not in path.entity_ids
            or path.affected_entity_id not in target_ids
        ):
            reason = "lineage_bridge_incomplete"
            result = _unresolved_result(
                affected_entity_ids=target_ids,
                reason=(
                    f"{reason}: persisted lineage lacks an explicit exact "
                    "artifact anchor or required evidence."
                ),
            )
            return _audit(
                candidate_event_id=candidate_event_id,
                candidate_entity_id=None,
                result=result,
                policy_version=relevance_policy_version,
                resolution_basis=CausalRelevanceResolutionBasis.UNRESOLVED,
                bridge_state=LineageRelevanceBridgeState.INCOMPLETE,
                bridge_reason=reason,
            )

    revisions = {item.revision for item in paths}
    if len(revisions) != 1:
        reason = "lineage_anchor_identity_conflict"
        result = _unresolved_result(
            affected_entity_ids=target_ids,
            reason=f"{reason}: admitted paths disagree on source revision.",
        )
        return _audit(
            candidate_event_id=candidate_event_id,
            candidate_entity_id=None,
            result=result,
            policy_version=relevance_policy_version,
            resolution_basis=CausalRelevanceResolutionBasis.UNRESOLVED,
            bridge_state=LineageRelevanceBridgeState.CONFLICT,
            bridge_reason=reason,
        )

    grouped: dict[tuple[str, str, str], list[LineagePathAudit]] = {}
    identity_by_entity: dict[str, set[tuple[str, str]]] = {}
    for path in paths:
        assert path.image_entity_id is not None
        assert path.image_entity_kind is not None
        identity_by_entity.setdefault(path.image_entity_id, set()).add(
            (path.image_entity_kind, path.image_digest)
        )
        grouped.setdefault(
            (path.image_entity_id, path.image_entity_kind, path.image_digest), []
        ).append(path)
    if any(len(values) != 1 for values in identity_by_entity.values()):
        reason = "lineage_anchor_identity_conflict"
        result = _unresolved_result(
            affected_entity_ids=target_ids,
            reason=(
                f"{reason}: one anchor entity has conflicting immutable "
                "identity claims."
            ),
        )
        return _audit(
            candidate_event_id=candidate_event_id,
            candidate_entity_id=None,
            result=result,
            policy_version=relevance_policy_version,
            resolution_basis=CausalRelevanceResolutionBasis.UNRESOLVED,
            bridge_state=LineageRelevanceBridgeState.CONFLICT,
            bridge_reason=reason,
        )

    entity_by_id = {entity.id: entity for entity in snapshot.entities}
    evaluated: list[
        tuple[
            tuple[str, str, str],
            list[LineagePathAudit],
            TopologyPathEvaluation,
            LineageRelevanceAnchorAudit,
        ]
    ] = []
    for anchor_key in sorted(grouped):
        anchor_id, anchor_kind, digest = anchor_key
        anchor_paths = grouped[anchor_key]
        entity = entity_by_id.get(anchor_id)
        rejection: str | None = None
        if entity is None:
            rejection = "lineage_anchor_not_in_pinned_topology"
        elif anchor_kind != "ContainerImage" or entity.kind != anchor_kind:
            rejection = "lineage_anchor_identity_conflict"
        elif (
            entity.properties.get("immutable") is not True
            or str(entity.properties.get("digest") or "").lower() != digest
            or str(entity.external_id or "").lower() != digest
        ):
            rejection = "lineage_anchor_identity_conflict"

        if rejection is not None:
            anchor_result = _unresolved_result(
                affected_entity_ids=target_ids,
                reason=(
                    f"{rejection}: exact admitted anchor '{anchor_id}' is not "
                    "usable in incident-pinned topology."
                ),
            )
            anchor_audit = _anchor_audit(
                anchor_entity_id=anchor_id,
                anchor_kind=anchor_kind,
                image_digest=digest,
                paths=anchor_paths,
                evidence_refs=bridge_evidence_refs,
                result=anchor_result,
                bridge_state=(
                    LineageRelevanceBridgeState.CONFLICT
                    if rejection == "lineage_anchor_identity_conflict"
                    else LineageRelevanceBridgeState.INCOMPLETE
                ),
                bridge_reason=rejection,
            )
        else:
            anchor_result = evaluate_topology_path(
                snapshot,
                source_entity_ids=[anchor_id],
                affected_entity_ids=target_ids,
                max_hops=max_hops,
            )
            anchor_audit = _anchor_audit(
                anchor_entity_id=anchor_id,
                anchor_kind=anchor_kind,
                image_digest=digest,
                paths=anchor_paths,
                evidence_refs=bridge_evidence_refs,
                result=anchor_result,
                bridge_state=LineageRelevanceBridgeState.VALID,
                bridge_reason="exact_immutable_lineage_anchor",
            )
        evaluated.append((anchor_key, anchor_paths, anchor_result, anchor_audit))

    supported = [
        item
        for item in evaluated
        if item[2].status
        in {CausalRelevanceStatus.DIRECT, CausalRelevanceStatus.SEMANTIC_PATH}
    ]
    selected_pool = supported or evaluated
    selected_key, selected_paths, selected_result, selected_audit = min(
        selected_pool,
        key=lambda item: (_topology_result_order(item[2]), item[0]),
    )
    anchor_id, anchor_kind, digest = selected_key
    all_anchor_audits = [item[3] for item in evaluated]
    selected_supported = bool(supported)
    final_reason = (
        "supported: an admitted exact immutable-lineage anchor reaches an "
        "affected entity through the existing incident-pinned topology path policy."
        if selected_supported
        else (
            selected_result.reason
            if selected_result.status == CausalRelevanceStatus.IDENTITY_UNRESOLVED
            else (
                "lineage_topology_path_missing: the exact lineage bridge is valid, "
                "but no supported incident-pinned topology path reaches the "
                "affected entity."
            )
        )
    )
    return _audit(
        candidate_event_id=candidate_event_id,
        candidate_entity_id=None,
        result=selected_result,
        policy_version=relevance_policy_version,
        resolution_basis=(
            CausalRelevanceResolutionBasis.EXACT_IMMUTABLE_LINEAGE_ANCHOR
        ),
        relevance_anchor_entity_id=anchor_id,
        relevance_anchor_kind=anchor_kind,
        bridge_state=selected_audit.bridge_state,
        bridge_reason=selected_audit.bridge_reason,
        bridge_path_ids=selected_audit.bridge_path_ids,
        bridge_evidence_refs=bridge_evidence_refs,
        bridge_source_change_id=candidate_event_id,
        bridge_revision=selected_paths[0].revision,
        bridge_run_ids=selected_audit.run_ids,
        bridge_image_digest=digest,
        bridge_score=0.0,
        topology_path_state=selected_audit.topology_path_state,
        anchor_audits=all_anchor_audits,
        reason=final_reason,
    )
