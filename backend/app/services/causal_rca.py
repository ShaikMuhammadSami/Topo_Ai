from __future__ import annotations

import hashlib
import json
import math
from collections import deque
from datetime import (
    datetime,
    timezone,
)
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import (
    IncidentRecord,
    SnapshotRecord,
    utc_now_iso,
)
from app.models.causal_rca import (
    CAUSAL_EVIDENCE_LEDGER_VERSION,
    CausalAnalysisRequest,
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
from app.models.causal_candidates import (
    CAUSAL_CANDIDATE_ADMISSION_POLICY_VERSION,
    CAUSAL_CANDIDATE_POLICY_VERSION,
    CAUSAL_EVALUATION_BUDGET_POLICY_VERSION,
)
from app.models.causal_relevance import (
    CAUSAL_RELEVANCE_POLICY_VERSION,
    CandidateCausalRelevanceAudit,
)
from app.models.causal_projection import (
    CAUSAL_HYPOTHESIS_PROJECTION_POLICY_VERSION,
)
from app.models.causal_support import (
    CAUSAL_SUPPORT_GATE_POLICY_VERSION,
)
from app.models.confidence_semantics import CONFIDENCE_SEMANTICS_VERSION
from app.models.change_events import (
    IncidentChangeCandidate,
)
from app.models.topology import (
    GraphSnapshot,
)
from app.repositories.causal_analysis_repository import (
    save_causal_analysis,
)
from app.repositories.signal_repository import load_signal
from app.services.causal_evidence_ledger import (
    build_hypothesis_evidence_ledger,
)
from app.services.causal_candidate_policy import select_causal_candidates
from app.services.causal_evaluation_budget import (
    build_causal_candidate_evaluation_frontier,
)
from app.services.causal_relevance_policy import evaluate_causal_relevance
from app.services.causal_support_gate import classify_causal_support
from app.services.causal_hypothesis_projection import project_causal_hypotheses
from app.services.confidence_semantics import (
    ensure_analysis_confidence_semantics,
)
from app.services.incident_change_analysis import (
    analyze_incident_change_events,
)
from app.services.temporal_semantics import (
    safe_snapshot_record_at_or_before,
)


ALGORITHM_VERSION = "13c-causal-v1"


def _stable_id(
    prefix: str,
    *parts: object,
) -> str:
    raw = "|".join(
        str(part)
        for part in parts
    )

    digest = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:32]

    return f"{prefix}:{digest}"


def _parse_time(
    value: str,
) -> datetime:
    result = datetime.fromisoformat(
        value.replace(
            "Z",
            "+00:00",
        )
    )

    if result.tzinfo is None:
        result = result.replace(
            tzinfo=timezone.utc
        )

    return result


def _enum_value(
    value,
) -> str:
    if hasattr(
        value,
        "value",
    ):
        return str(value.value)

    return str(value)


def _event_node_id(
    event_id: str,
) -> str:
    return f"event|{event_id}"


def _entity_node_id(
    entity_id: str,
) -> str:
    return f"entity|{entity_id}"


def _incident_node_id(
    incident_id: str,
) -> str:
    return f"incident|{incident_id}"


def _snapshot_for_incident(
    session: Session,
    *,
    incident: IncidentRecord,
    incident_time: datetime,
) -> tuple[
    SnapshotRecord | None,
    GraphSnapshot | None,
]:
    snapshot_id = getattr(
        incident,
        "topology_snapshot_id",
        None,
    )

    if snapshot_id:
        record = session.get(
            SnapshotRecord,
            str(snapshot_id),
        )

        if record is not None:
            return (
                record,
                GraphSnapshot
                .model_validate_json(
                    record.payload_json
                ),
            )

    cluster_name = getattr(
        incident,
        "cluster_name",
        None,
    )

    if not cluster_name:
        return None, None
    record = safe_snapshot_record_at_or_before(
        session,
        cluster_name=str(cluster_name),
        namespace=getattr(incident, "namespace", None),
        boundary_at=incident_time,
    )
    if record is None:
        return None, None
    return (
        record,
        GraphSnapshot.model_validate_json(record.payload_json),
    )


def _entity_index(
    snapshot: GraphSnapshot | None,
) -> dict:
    if snapshot is None:
        return {}

    return {
        entity.id: entity
        for entity
        in snapshot.entities
    }


def _adjacency(
    snapshot: GraphSnapshot | None,
) -> dict[
    str,
    list[
        tuple[
            str,
            str,
        ]
    ],
]:
    result: dict[
        str,
        list[
            tuple[
                str,
                str,
            ]
        ],
    ] = {}

    if snapshot is None:
        return result

    for relationship in (
        snapshot.relationships
    ):
        source = (
            relationship
            .source_entity_id
        )

        target = (
            relationship
            .target_entity_id
        )

        relation = _enum_value(
            getattr(
                relationship,
                "type",
                "related",
            )
        )

        result.setdefault(
            source,
            [],
        ).append(
            (
                target,
                relation,
            )
        )

        # Causal proximity uses
        # undirected graph distance.
        result.setdefault(
            target,
            [],
        ).append(
            (
                source,
                relation,
            )
        )

    return result


def _pinned_relationship_metadata(
    snapshot: GraphSnapshot | None,
    *,
    left_entity_id: str,
    right_entity_id: str,
) -> dict[str, Any]:
    """Return deterministic edge evidence from the supplied pinned snapshot."""

    if snapshot is None:
        return {}

    matches = [
        relationship
        for relationship in snapshot.relationships
        if (
            relationship.source_entity_id == left_entity_id
            and relationship.target_entity_id == right_entity_id
        )
        or (
            relationship.source_entity_id == right_entity_id
            and relationship.target_entity_id == left_entity_id
        )
    ]

    if not matches:
        return {}

    relationship = sorted(matches, key=lambda item: item.id)[0]
    provenance = (
        relationship.provenance.model_dump(mode="json")
        if relationship.provenance is not None
        else None
    )

    return {
        "topology_snapshot_id": snapshot.snapshot_id,
        "relationship_id": relationship.id,
        "relationship_type": relationship.relationship_type.value,
        "relationship_direction": (
            "forward"
            if relationship.source_entity_id == left_entity_id
            else "reverse"
        ),
        "relationship_source_system": relationship.source_system,
        "relationship_observed_at": (
            relationship.observed_at.isoformat()
        ),
        "relationship_confidence": relationship.confidence,
        "relationship_confidence_semantics": (
            relationship.confidence_semantics.value
            if relationship.confidence_semantics is not None
            else None
        ),
        "relationship_provenance": provenance,
        "relationship_provenance_status": (
            provenance["completeness"]
            if provenance is not None
            else "legacy_unspecified"
        ),
    }


def _shortest_path(
    adjacency: dict,
    *,
    start: str,
    targets: set[str],
    max_hops: int,
) -> list[str] | None:
    if start in targets:
        return [start]

    queue = deque(
        [
            (
                start,
                [start],
            )
        ]
    )

    visited = {
        start
    }

    while queue:
        node, path = queue.popleft()

        hops = len(path) - 1

        if hops >= max_hops:
            continue

        for neighbor, _ in (
            adjacency.get(
                node,
                [],
            )
        ):
            if neighbor in visited:
                continue

            new_path = [
                *path,
                neighbor,
            ]

            if neighbor in targets:
                return new_path

            visited.add(neighbor)

            queue.append(
                (
                    neighbor,
                    new_path,
                )
            )

    return None


def _candidate_link_ids(
    candidate: IncidentChangeCandidate,
) -> set[str]:
    result = set()

    for link in candidate.event.links:
        if link.entity_id:
            result.add(
                link.entity_id
            )

    result.update(
        candidate.direct_entity_matches
    )

    result.update(
        candidate.neighboring_entity_matches
    )

    return result


def _event_chain_confidence(
    earlier: IncidentChangeCandidate,
    later: IncidentChangeCandidate,
) -> tuple[
    float,
    list[str],
]:
    earlier_temporal = getattr(earlier.event, "temporal", None)
    later_temporal = getattr(later.event, "temporal", None)
    earlier_time = (
        earlier_temporal.effective_at
        if earlier_temporal is not None
        else _parse_time(earlier.event.occurred_at)
    )
    later_time = (
        later_temporal.effective_at
        if later_temporal is not None
        else _parse_time(later.event.occurred_at)
    )

    if earlier_time >= later_time:
        return 0.0, []

    gap_minutes = (
        later_time
        - earlier_time
    ).total_seconds() / 60

    if gap_minutes > 180:
        return 0.0, []

    score = 0.0

    reasons = []

    if (
        earlier.event.commit_sha
        and later.event.commit_sha
        and earlier.event.commit_sha
        == later.event.commit_sha
    ):
        score += 0.45

        reasons.append(
            "Same commit SHA."
        )

    if (
        earlier.event.repository
        and later.event.repository
        and earlier.event.repository
        == later.event.repository
    ):
        score += 0.20

        reasons.append(
            "Same repository."
        )

    if (
        earlier.event.release_version
        and later.event.release_version
        and earlier.event.release_version
        == later.event.release_version
    ):
        score += 0.25

        reasons.append(
            "Same release version."
        )

    if (
        earlier.event.pipeline_name
        and later.event.pipeline_name
        and earlier.event.pipeline_name
        == later.event.pipeline_name
    ):
        score += 0.15

        reasons.append(
            "Same pipeline."
        )

    earlier_entities = (
        _candidate_link_ids(
            earlier
        )
    )

    later_entities = (
        _candidate_link_ids(
            later
        )
    )

    shared_entities = (
        earlier_entities
        & later_entities
    )

    if shared_entities:
        score += 0.35

        reasons.append(
            "Events touch the same "
            "topology entity."
        )

    if (
        earlier.event.cluster_name
        and later.event.cluster_name
        and earlier.event.cluster_name
        == later.event.cluster_name
    ):
        score += 0.10

        reasons.append(
            "Same cluster."
        )

    if (
        earlier.event.namespace
        and later.event.namespace
        and earlier.event.namespace
        == later.event.namespace
    ):
        score += 0.10

        reasons.append(
            "Same namespace."
        )

    earlier_source = _enum_value(
        earlier.event.source
    )

    later_source = _enum_value(
        later.event.source
    )

    delivery_sources = {
        "github",
        "github_actions",
        "gitlab",
        "jenkins",
        "azure_devops",
        "terraform",
    }

    observed_sources = {
        "topology_diff",
        "kubernetes",
        "aws_cloudtrail",
        "azure_activity_log",
        "gcp_audit_log",
    }

    if (
        earlier_source
        in delivery_sources
        and later_source
        in observed_sources
    ):
        score += 0.10

        reasons.append(
            "Delivery event precedes "
            "an observed infrastructure "
            "change."
        )

    # Shorter gaps increase credibility.
    if gap_minutes <= 15:
        score += 0.10

        reasons.append(
            "Events occurred within "
            "15 minutes."
        )

    elif gap_minutes <= 60:
        score += 0.05

        reasons.append(
            "Events occurred within "
            "one hour."
        )

    return min(
        score,
        0.98,
    ), reasons


def _kind_prior(
    kind: str,
) -> float:
    return {
        "deployment": 1.00,
        "infrastructure": 0.95,
        "configuration": 0.85,
        "security": 0.85,
        "database": 0.85,
        "scaling": 0.70,
        "topology": 0.65,
        "pipeline": 0.55,
        "code": 0.50,
        "pull_request": 0.35,
        "unknown": 0.30,
    }.get(
        kind,
        0.30,
    )


def _confidence_level(
    confidence: float,
) -> CausalConfidenceLevel:
    if confidence >= 0.75:
        return (
            CausalConfidenceLevel.HIGH
        )

    if confidence >= 0.50:
        return (
            CausalConfidenceLevel.MEDIUM
        )

    return CausalConfidenceLevel.LOW


def analyze_causal_rca(
    session: Session,
    *,
    incident_id: str,
    request: CausalAnalysisRequest,
    persist: bool = True,
) -> CausalAnalysisResponse:
    incident = session.get(
        IncidentRecord,
        incident_id,
    )

    if incident is None:
        raise ValueError(
            "Incident not found."
        )

    change_analysis = (
        analyze_incident_change_events(
            session,
            incident_id=incident_id,
            lookback_minutes=(
                request.lookback_minutes
            ),
            after_minutes=(
                request.after_minutes
            ),
            minimum_score=(
                request.minimum_change_score
            ),
            limit=500,
        )
    )

    incident_time = _parse_time(
        change_analysis.incident_time
    )

    snapshot_record, snapshot = (
        _snapshot_for_incident(
            session,
            incident=incident,
            incident_time=(
                incident_time
            ),
        )
    )

    entity_by_id = _entity_index(
        snapshot
    )

    all_candidates = list(change_analysis.candidates)
    candidate_selection = select_causal_candidates(
        all_candidates,
        limit=request.max_hypotheses,
        entity_kind_by_id={
            entity_id: entity.kind
            for entity_id, entity in entity_by_id.items()
        },
    )
    candidate_evaluation = build_causal_candidate_evaluation_frontier(
        all_candidates,
        ordinary_candidates=candidate_selection.selected_candidates,
        ordinary_selection_audit=candidate_selection.audit,
        ordinary_shortlist_limit=request.max_hypotheses,
        policy_version=CAUSAL_EVALUATION_BUDGET_POLICY_VERSION,
    )
    candidates = list(candidate_evaluation.candidates)

    affected_entity_ids = set(
        change_analysis
        .affected_entity_ids
    )

    nodes: dict[
        str,
        CausalNode,
    ] = {}

    edges: dict[
        str,
        CausalEdge,
    ] = {}

    evidence: dict[
        str,
        CausalEvidenceItem,
    ] = {}

    def add_evidence(
        *,
        evidence_type:
            CausalEvidenceType,
        source: str,
        title: str,
        detail: str,
        weight: float,
        observed_at:
            str | None = None,
        event_id:
            str | None = None,
        entity_id:
            str | None = None,
        attributes:
            dict | None = None,
    ) -> str:
        evidence_id = _stable_id(
            "evidence",
            evidence_type.value,
            source,
            title,
            event_id,
            entity_id,
            detail,
        )

        if evidence_id not in evidence:
            evidence[
                evidence_id
            ] = CausalEvidenceItem(
                evidence_id=evidence_id,
                evidence_type=(
                    evidence_type
                ),
                source=source,
                title=title,
                detail=detail,
                observed_at=(
                    observed_at
                ),
                event_id=event_id,
                entity_id=entity_id,
                weight=max(
                    0,
                    min(weight, 1),
                ),
                attributes=(
                    attributes or {}
                ),
            )

        return evidence_id

    def add_edge(
        *,
        source_node_id: str,
        target_node_id: str,
        relation:
            CausalEdgeType,
        confidence: float,
        reasons: list[str],
        evidence_ids: list[str],
    ) -> CausalEdge:
        edge_id = _stable_id(
            "causal-edge",
            source_node_id,
            target_node_id,
            relation.value,
        )

        existing = edges.get(
            edge_id
        )

        if existing is None:
            edge = CausalEdge(
                edge_id=edge_id,
                source_node_id=(
                    source_node_id
                ),
                target_node_id=(
                    target_node_id
                ),
                relation=relation,
                confidence=max(
                    0,
                    min(
                        confidence,
                        1,
                    ),
                ),
                reasons=reasons,
                evidence_ids=(
                    evidence_ids
                ),
            )

            edges[edge_id] = edge

            return edge

        if confidence > (
            existing.confidence
        ):
            existing.confidence = (
                confidence
            )

        existing.reasons = list(
            dict.fromkeys(
                [
                    *existing.reasons,
                    *reasons,
                ]
            )
        )

        existing.evidence_ids = list(
            dict.fromkeys(
                [
                    *existing
                    .evidence_ids,
                    *evidence_ids,
                ]
            )
        )

        return existing

    incident_node = CausalNode(
        node_id=_incident_node_id(
            incident_id
        ),
        node_type=(
            CausalNodeType.INCIDENT
        ),
        label=str(
            getattr(
                incident,
                "title",
                incident_id,
            )
        ),
        occurred_at=(
            change_analysis
            .incident_time
        ),
        attributes={
            "severity":
                getattr(
                    incident,
                    "severity",
                    None,
                ),
            "status":
                getattr(
                    incident,
                    "status",
                    None,
                ),
            "cluster_name":
                getattr(
                    incident,
                    "cluster_name",
                    None,
                ),
            "namespace":
                getattr(
                    incident,
                    "namespace",
                    None,
                ),
        },
    )

    nodes[
        incident_node.node_id
    ] = incident_node

    for entity_id in (
        affected_entity_ids
    ):
        entity = entity_by_id.get(
            entity_id
        )

        label = (
            entity.name
            if entity
            else entity_id
        )

        node = CausalNode(
            node_id=(
                _entity_node_id(
                    entity_id
                )
            ),
            node_type=(
                CausalNodeType.ENTITY
            ),
            label=label,
            entity_id=entity_id,
            attributes={
                "kind":
                    (
                        entity.kind
                        if entity
                        else None
                    ),
                "affected":
                    True,
            },
        )

        nodes[node.node_id] = node

        evidence_id = add_evidence(
            evidence_type=(
                CausalEvidenceType
                .INCIDENT
            ),
            source="incident",
            title=(
                "Incident affected "
                "entity"
            ),
            detail=(
                f"Incident references "
                f"{entity_id}."
            ),
            weight=1.0,
            entity_id=entity_id,
        )

        add_edge(
            source_node_id=node.node_id,
            target_node_id=(
                incident_node.node_id
            ),
            relation=(
                CausalEdgeType
                .CULMINATES_IN
            ),
            confidence=1.0,
            reasons=[
                (
                    "Entity is directly "
                    "affected by the "
                    "incident."
                )
            ],
            evidence_ids=[
                evidence_id
            ],
        )

    candidate_by_event = {
        candidate.event.event_id:
            candidate
        for candidate
        in candidates
    }

    temporal_evidence_by_event = {}

    event_entity_edge = {}

    best_entity_path_by_event: dict[
        str,
        list[str] | None,
    ] = {}

    relevance_by_event: dict[str, CandidateCausalRelevanceAudit] = {}

    for candidate in (
        candidates
    ):
        event = candidate.event

        event_id = event.event_id

        event_node = CausalNode(
            node_id=_event_node_id(
                event_id
            ),
            node_type=(
                CausalNodeType
                .CHANGE_EVENT
            ),
            label=event.title,
            occurred_at=(
                event.occurred_at
            ),
            event_id=event_id,
            attributes={
                "source":
                    _enum_value(
                        event.source
                    ),
                "kind":
                    _enum_value(
                        event.kind
                    ),
                "risk_score":
                    event.risk_score,
                "risk_level":
                    _enum_value(
                        event.risk_level
                    ),
                "origin_change_id":
                    event
                    .origin_change_id,
                "repository":
                    event.repository,
                "commit_sha":
                    event.commit_sha,
                "pipeline_name":
                    event.pipeline_name,
                "release_version":
                    event.release_version,
                "cluster_name":
                    event.cluster_name,
                "namespace":
                    event.namespace,
                "temporal": (
                    event.temporal.model_dump(mode="json")
                    if event.temporal is not None
                    else None
                ),
            },
        )

        nodes[
            event_node.node_id
        ] = event_node

        minutes = (
            candidate
            .minutes_before_incident
        )

        temporal_weight = 0.0

        if minutes is not None:
            if minutes >= 0:
                temporal_weight = (
                    math.exp(
                        -minutes / 90
                    )
                )

                detail = (
                    f"Change occurred "
                    f"{minutes:.2f} minutes "
                    "before the incident."
                )

            else:
                temporal_weight = (
                    0.05
                    * math.exp(
                        -abs(minutes)
                        / 30
                    )
                )

                detail = (
                    f"Change occurred "
                    f"{abs(minutes):.2f} "
                    "minutes after the "
                    "incident began."
                )

        else:
            detail = (
                "No reliable temporal "
                "distance was available."
            )

        temporal_evidence_id = (
            add_evidence(
                evidence_type=(
                    CausalEvidenceType
                    .TEMPORAL
                ),
                source="change-event",
                title=(
                    "Temporal proximity"
                ),
                detail=detail,
                weight=(
                    temporal_weight
                ),
                observed_at=(
                    (
                        event.temporal.observed_at
                        or event.temporal.recorded_at
                    ).isoformat()
                    if (
                        event.temporal is not None
                        and (
                            event.temporal.observed_at
                            or event.temporal.recorded_at
                        )
                    )
                    else None
                ),
                event_id=event_id,
            )
        )

        temporal_evidence_by_event[
            event_id
        ] = temporal_evidence_id

        linked_ids = (
            _candidate_link_ids(
                candidate
            )
        )

        for linked_id in linked_ids:
            entity = entity_by_id.get(
                linked_id
            )

            entity_node_id = (
                _entity_node_id(
                    linked_id
                )
            )

            if (
                entity_node_id
                not in nodes
            ):
                nodes[
                    entity_node_id
                ] = CausalNode(
                    node_id=(
                        entity_node_id
                    ),
                    node_type=(
                        CausalNodeType
                        .ENTITY
                    ),
                    label=(
                        entity.name
                        if entity
                        else linked_id
                    ),
                    entity_id=linked_id,
                    attributes={
                        "kind":
                            (
                                entity.kind
                                if entity
                                else None
                            )
                    },
                )

            matching_links = [
                link
                for link
                in event.links
                if link.entity_id
                == linked_id
            ]

            confidence = 0.75

            reason = (
                "Change event correlates "
                "with this topology "
                "entity."
            )

            if matching_links:
                best_link = max(
                    matching_links,
                    key=lambda item:
                        item.confidence,
                )

                confidence = (
                    best_link.confidence
                )

                reason = (
                    best_link.reason
                    or reason
                )

            evidence_id = add_evidence(
                evidence_type=(
                    CausalEvidenceType
                    .ENTITY_LINK
                ),
                source="change-correlation",
                title=(
                    "Change-to-entity "
                    "correlation"
                ),
                detail=reason,
                weight=confidence,
                event_id=event_id,
                entity_id=linked_id,
                attributes={
                    "link_confidence":
                        confidence
                },
            )

            edge = add_edge(
                source_node_id=(
                    event_node.node_id
                ),
                target_node_id=(
                    entity_node_id
                ),
                relation=(
                    CausalEdgeType
                    .TOUCHES_ENTITY
                ),
                confidence=confidence,
                reasons=[
                    reason
                ],
                evidence_ids=[
                    evidence_id
                ],
            )

            event_entity_edge[
                (
                    event_id,
                    linked_id,
                )
            ] = edge

        relevance = evaluate_causal_relevance(
            snapshot,
            candidate_event_id=event_id,
            candidate_entity_ids=linked_ids,
            affected_entity_ids=affected_entity_ids,
            max_hops=request.max_topology_hops,
            candidate_admission_policy_version=(
                candidate.candidate_admission_policy_version
            ),
            admission_basis=candidate.admission_basis,
            lineage_admission_state=candidate.lineage_admission_state,
            lineage_admission_reason=candidate.lineage_admission_reason,
            lineage_paths=candidate.lineage_paths,
            admission_evidence_refs=candidate.admission_evidence_refs,
        )
        relevance_by_event[event_id] = relevance
        best_path = (
            list(relevance.path_entity_ids)
            if relevance.path_entity_ids
            else None
        )

        best_entity_path_by_event[
            event_id
        ] = best_path

        if best_path:
            for index, semantic_hop in enumerate(relevance.hops):
                left_id = (
                    semantic_hop.source_entity_id
                )

                right_id = (
                    semantic_hop.target_entity_id
                )

                left_entity = (
                    entity_by_id.get(
                        left_id
                    )
                )

                right_entity = (
                    entity_by_id.get(
                        right_id
                    )
                )

                for current_id, current in (
                    (
                        left_id,
                        left_entity,
                    ),
                    (
                        right_id,
                        right_entity,
                    ),
                ):
                    node_id = (
                        _entity_node_id(
                            current_id
                        )
                    )

                    if node_id not in nodes:
                        nodes[
                            node_id
                        ] = CausalNode(
                            node_id=node_id,
                            node_type=(
                                CausalNodeType
                                .ENTITY
                            ),
                            label=(
                                current.name
                                if current
                                else current_id
                            ),
                            entity_id=(
                                current_id
                            ),
                            attributes={
                                "kind":
                                    (
                                        current.kind
                                        if current
                                        else None
                                    )
                            },
                        )

                hop_confidence = max(
                    0.45,
                    0.90
                    - (
                        index
                        * 0.10
                    ),
                )

                evidence_id = (
                    add_evidence(
                        evidence_type=(
                            CausalEvidenceType
                            .TOPOLOGY
                        ),
                        source="topology",
                        title=(
                            "Topology "
                            "dependency path"
                        ),
                        detail=(
                            f"{left_id} reaches "
                            f"{right_id} through "
                            f"{semantic_hop.predicate}/"
                            f"{semantic_hop.traversal_direction.value}."
                        ),
                        weight=(
                            hop_confidence
                        ),
                        entity_id=(
                            right_id
                        ),
                        attributes={
                            "topology_snapshot_id": snapshot.snapshot_id,
                            "causal_relevance_policy_version": (
                                CAUSAL_RELEVANCE_POLICY_VERSION
                            ),
                            "path_semantic": relevance.path_semantic.value,
                            "relationship_id": semantic_hop.relationship_id,
                            "relationship_type": semantic_hop.predicate,
                            "relationship_direction": (
                                semantic_hop.traversal_direction.value
                            ),
                            "relationship_source_system": (
                                semantic_hop.relationship_source_system
                            ),
                            "relationship_provenance_status": (
                                semantic_hop
                                .relationship_provenance_completeness.value
                            ),
                        },
                    )
                )

                add_edge(
                    source_node_id=(
                        _entity_node_id(
                            left_id
                        )
                    ),
                    target_node_id=(
                        _entity_node_id(
                            right_id
                        )
                    ),
                    relation=(
                        CausalEdgeType
                        .TOPOLOGY_PATH
                    ),
                    confidence=(
                        hop_confidence
                    ),
                    reasons=[
                        (
                            "The selected TC-2 edge is allowed by "
                            f"{relevance.relevance_policy_version} in canonical "
                            "source-to-effect direction."
                        )
                    ],
                    evidence_ids=[
                        evidence_id
                    ],
                )

    # -----------------------------------------------------------
    # Event → event lineage
    # -----------------------------------------------------------

    event_lineage_edges: dict[
        tuple[str, str],
        CausalEdge,
    ] = {}

    incoming_edges: dict[
        str,
        list[CausalEdge],
    ] = {}

    for later in candidates:
        possible = []

        for earlier in candidates:
            if (
                earlier.event.event_id
                == later.event.event_id
            ):
                continue

            confidence, reasons = (
                _event_chain_confidence(
                    earlier,
                    later,
                )
            )

            if confidence < 0.35:
                continue

            possible.append(
                (
                    confidence,
                    earlier,
                    reasons,
                )
            )

        # Avoid graph explosion.
        possible.sort(
            key=lambda item:
                item[0],
            reverse=True,
        )

        for (
            confidence,
            earlier,
            reasons,
        ) in possible[:2]:
            evidence_id = (
                add_evidence(
                    evidence_type=(
                        CausalEvidenceType
                        .EVENT_LINEAGE
                    ),
                    source="change-lineage",
                    title=(
                        "Operational event "
                        "lineage"
                    ),
                    detail=(
                        " ".join(reasons)
                    ),
                    weight=confidence,
                    observed_at=(
                        later.event
                        .occurred_at
                    ),
                    event_id=(
                        later.event
                        .event_id
                    ),
                    attributes={
                        "predecessor_event_id":
                            (
                                earlier.event
                                .event_id
                            )
                    },
                )
            )

            edge = add_edge(
                source_node_id=(
                    _event_node_id(
                        earlier.event
                        .event_id
                    )
                ),
                target_node_id=(
                    _event_node_id(
                        later.event
                        .event_id
                    )
                ),
                relation=(
                    CausalEdgeType
                    .PRECEDES
                ),
                confidence=confidence,
                reasons=reasons,
                evidence_ids=[
                    evidence_id
                ],
            )

            event_lineage_edges[
                (
                    earlier.event
                    .event_id,
                    later.event
                    .event_id,
                )
            ] = edge

            incoming_edges.setdefault(
                later.event.event_id,
                [],
            ).append(edge)

    def best_event_chain(
        target_event_id: str,
        *,
        max_depth: int = 4,
    ) -> list[str]:
        chain = [
            target_event_id
        ]

        current = (
            target_event_id
        )

        visited = {
            current
        }

        for _ in range(max_depth):
            incoming = (
                incoming_edges.get(
                    current,
                    [],
                )
            )

            if not incoming:
                break

            incoming = sorted(
                incoming,
                key=lambda item:
                    item.confidence,
                reverse=True,
            )

            selected = None

            for edge in incoming:
                predecessor = (
                    edge
                    .source_node_id
                    .removeprefix(
                        "event|"
                    )
                )

                if predecessor in visited:
                    continue

                selected = predecessor
                break

            if selected is None:
                break

            chain.insert(
                0,
                selected,
            )

            visited.add(
                selected
            )

            current = selected

        return chain

    # -----------------------------------------------------------
    # Build hypotheses
    # -----------------------------------------------------------

    raw_hypotheses = []

    primary_signal = None
    primary_signal_id = getattr(
        incident,
        "primary_signal_id",
        None,
    )
    if primary_signal_id:
        primary_signal = load_signal(
            session,
            str(primary_signal_id),
        )

    for candidate in candidates:
        event = candidate.event

        event_id = event.event_id

        entity_path = (
            best_entity_path_by_event
            .get(event_id)
        )

        relevance = relevance_by_event[event_id]

        if entity_path:
            distance = (
                len(entity_path) - 1
            )

            topology_component = relevance.topology_component

        else:
            distance = None

            topology_component = 0.0

        minutes = (
            candidate
            .minutes_before_incident
        )

        if minutes is None:
            temporal_component = 0.0

        elif minutes >= 0:
            temporal_component = (
                math.exp(
                    -minutes / 90
                )
            )

        else:
            temporal_component = (
                0.05
                * math.exp(
                    -abs(minutes)
                    / 30
                )
            )

        lineage = incoming_edges.get(
            event_id,
            [],
        )

        lineage_component = (
            max(
                (
                    edge.confidence
                    for edge
                    in lineage
                ),
                default=0.0,
            )
        )

        kind = _enum_value(
            event.kind
        )

        score = (
            # Existing 13A evidence.
            candidate.score * 0.40

            # Topology connection.
            + topology_component * 25

            # Time before incident.
            + temporal_component * 15

            # Type of change.
            + _kind_prior(
                kind
            ) * 10

            # Delivery → observed
            # change continuity.
            + lineage_component * 10
        )

        score = max(
            0,
            min(score, 100),
        )

        confidence = (
            score / 100
        )

        event_chain = (
            best_event_chain(
                event_id
            )
        )

        root_event_id = (
            event_chain[0]
        )

        root_candidate = (
            candidate_by_event[
                root_event_id
            ]
        )

        root_event = (
            root_candidate.event
        )

        chain_steps = []

        supporting_evidence_ids = []

        previous_event_id = None

        for chain_event_id in (
            event_chain
        ):
            chain_candidate = (
                candidate_by_event[
                    chain_event_id
                ]
            )

            chain_event = (
                chain_candidate.event
            )

            relation = None

            edge_confidence = None

            if previous_event_id:
                edge = (
                    event_lineage_edges
                    .get(
                        (
                            previous_event_id,
                            chain_event_id,
                        )
                    )
                )

                if edge:
                    relation = (
                        edge.relation
                    )

                    edge_confidence = (
                        edge.confidence
                    )

                    supporting_evidence_ids.extend(
                        edge.evidence_ids
                    )

            chain_steps.append(
                CausalChainStep(
                    order=len(
                        chain_steps
                    )
                    + 1,
                    node_id=(
                        _event_node_id(
                            chain_event_id
                        )
                    ),
                    node_type=(
                        CausalNodeType
                        .CHANGE_EVENT
                    ),
                    label=(
                        chain_event.title
                    ),
                    relation_from_previous=(
                        relation
                    ),
                    confidence_from_previous=(
                        edge_confidence
                    ),
                )
            )

            previous_event_id = (
                chain_event_id
            )

        supporting_evidence_ids.append(
            temporal_evidence_by_event[
                event_id
            ]
        )

        affected_entity_id = None

        if entity_path:
            first_entity_id = (
                entity_path[0]
            )

            event_to_entity = (
                event_entity_edge.get(
                    (
                        event_id,
                        first_entity_id,
                    )
                )
            )

            if event_to_entity:
                supporting_evidence_ids.extend(
                    event_to_entity
                    .evidence_ids
                )

                chain_steps.append(
                    CausalChainStep(
                        order=len(
                            chain_steps
                        )
                        + 1,
                        node_id=(
                            _entity_node_id(
                                first_entity_id
                            )
                        ),
                        node_type=(
                            CausalNodeType
                            .ENTITY
                        ),
                        label=(
                            nodes[
                                _entity_node_id(
                                    first_entity_id
                                )
                            ].label
                        ),
                        relation_from_previous=(
                            CausalEdgeType
                            .TOUCHES_ENTITY
                        ),
                        confidence_from_previous=(
                            event_to_entity
                            .confidence
                        ),
                    )
                )

            for entity_id in (
                entity_path[1:]
            ):
                chain_steps.append(
                    CausalChainStep(
                        order=len(
                            chain_steps
                        )
                        + 1,
                        node_id=(
                            _entity_node_id(
                                entity_id
                            )
                        ),
                        node_type=(
                            CausalNodeType
                            .ENTITY
                        ),
                        label=(
                            nodes[
                                _entity_node_id(
                                    entity_id
                                )
                            ].label
                        ),
                        relation_from_previous=(
                            CausalEdgeType
                            .TOPOLOGY_PATH
                        ),
                        confidence_from_previous=(
                            0.75
                        ),
                    )
                )

            affected_entity_id = (
                entity_path[-1]
            )

        chain_steps.append(
            CausalChainStep(
                order=len(
                    chain_steps
                )
                + 1,
                node_id=(
                    incident_node.node_id
                ),
                node_type=(
                    CausalNodeType
                    .INCIDENT
                ),
                label=(
                    incident_node.label
                ),
                relation_from_previous=(
                    CausalEdgeType
                    .CULMINATES_IN
                ),
                confidence_from_previous=(
                    1.0
                    if affected_entity_id
                    else None
                ),
            )
        )

        reasons = list(
            candidate.reasons
        )

        if entity_path:
            reasons.append(
                (
                    "Change reaches an affected incident entity through "
                    f"a {relevance.path_semantic.value} source-to-effect "
                    f"path within {len(entity_path)-1} topology hops."
                )
            )
        else:
            reasons.append(relevance.reason)

        if len(event_chain) > 1:
            reasons.append(
                (
                    "The change is part "
                    "of a correlated "
                    "operational event "
                    "chain."
                )
            )

        if root_event_id != event_id:
            title = (
                f"{root_event.title} "
                f"→ {event.title}"
            )

        else:
            title = event.title

        if minutes is not None:
            timing_text = (
                f"{abs(minutes):.1f} "
                "minutes "
                + (
                    "before"
                    if minutes >= 0
                    else "after"
                )
                + " incident start"
            )

        else:
            timing_text = (
                "with unknown temporal "
                "distance"
            )

        summary = (
            "Probable causal chain "
            f"rooted at "
            f"{_enum_value(root_event.source)} "
            f"event '{root_event.title}'. "
            f"The target change "
            f"'{event.title}' occurred "
            f"{timing_text}. "
            + (
                "A semantic incident-time topology path connects it to the "
                "incident."
                if entity_path
                else (
                    "No supported incident-time topology path was found; "
                    "the change remains an alternative based on independent "
                    "change and temporal evidence."
                )
            )
        )

        hypothesis_id = _stable_id(
            "causal-hypothesis",
            incident_id,
            root_event_id,
            event_id,
            affected_entity_id,
        )

        evidence_ledger = build_hypothesis_evidence_ledger(
            hypothesis_id=hypothesis_id,
            candidate=candidate,
            candidate_by_event=candidate_by_event,
            event_chain=event_chain,
            entity_path=entity_path,
            incident=incident,
            incident_time=incident_time,
            snapshot=snapshot,
            primary_signal=primary_signal,
            path_relationship_ids=(
                relevance.path_relationship_ids
            ),
        )
        support_gate = classify_causal_support(
            candidate_event_id=event_id,
            relevance=relevance,
            ledger=evidence_ledger,
        )

        raw_hypotheses.append(
            CausalHypothesis(
                hypothesis_id=(
                    hypothesis_id
                ),
                rank=0,
                root_event_id=(
                    root_event_id
                ),
                root_source=(
                    _enum_value(
                        root_event.source
                    )
                ),
                root_title=(
                    root_event.title
                ),
                target_event_id=(
                    event_id
                ),
                target_title=(
                    event.title
                ),
                affected_entity_id=(
                    affected_entity_id
                ),
                score=round(
                    score,
                    2,
                ),
                confidence=round(
                    confidence,
                    4,
                ),
                confidence_level=(
                    _confidence_level(
                        confidence
                    )
                ),
                minutes_before_incident=(
                    minutes
                ),
                summary=summary,
                reasons=list(
                    dict.fromkeys(
                        reasons
                    )
                ),
                supporting_evidence_ids=list(
                    dict.fromkeys(
                        supporting_evidence_ids
                    )
                ),
                evidence_ledger=evidence_ledger,
                support_gate=support_gate,
                chain=chain_steps,
            )
        )

    # Keep the strongest hypothesis
    # for each root operational event.
    best_by_root = {}

    for hypothesis in raw_hypotheses:
        current = best_by_root.get(
            hypothesis.root_event_id
        )

        if (
            current is None
            or hypothesis.score
            > current.score
        ):
            best_by_root[
                hypothesis.root_event_id
            ] = hypothesis

    evaluated_hypotheses = list(
        best_by_root.values()
    )

    hypothesis_projection = project_causal_hypotheses(
        evaluated_hypotheses,
        diagnostic_limit=request.max_hypotheses,
        supported_limit=request.max_hypotheses,
    )
    hypotheses = list(hypothesis_projection.evaluated_hypotheses)
    hypotheses_by_id = {
        hypothesis.hypothesis_id: hypothesis for hypothesis in hypotheses
    }
    diagnostic_hypotheses = [
        hypotheses_by_id[hypothesis_id]
        for hypothesis_id in hypothesis_projection.diagnostic_hypothesis_ids
    ]

    analysis_fingerprint = {
        "incident_id":
            incident_id,
        "snapshot_id":
            (
                snapshot_record.snapshot_id
                if snapshot_record
                else None
            ),
        "event_ids":
            sorted(
                candidate.event.event_id
                for candidate in all_candidates
            ),
        "request":
            request.model_dump(
                mode="json"
            ),
        "algorithm":
            ALGORITHM_VERSION,
        "candidate_policy":
            CAUSAL_CANDIDATE_POLICY_VERSION,
        "candidate_admission_policy":
            CAUSAL_CANDIDATE_ADMISSION_POLICY_VERSION,
        "causal_evaluation_budget_policy":
            CAUSAL_EVALUATION_BUDGET_POLICY_VERSION,
        "causal_relevance_policy":
            CAUSAL_RELEVANCE_POLICY_VERSION,
        "evidence_ledger":
            CAUSAL_EVIDENCE_LEDGER_VERSION,
        "confidence_semantics":
            CONFIDENCE_SEMANTICS_VERSION,
        "causal_support_gate":
            CAUSAL_SUPPORT_GATE_POLICY_VERSION,
        "causal_hypothesis_projection":
            CAUSAL_HYPOTHESIS_PROJECTION_POLICY_VERSION,
    }

    analysis_id = _stable_id(
        "causal-analysis",
        json.dumps(
            analysis_fingerprint,
            sort_keys=True,
            default=str,
        ),
    )

    analysis = (
        CausalAnalysisResponse(
            analysis_id=analysis_id,
            incident_id=incident_id,
            incident_title=str(
                getattr(
                    incident,
                    "title",
                    incident_id,
                )
            ),
            incident_time=(
                change_analysis
                .incident_time
            ),
            topology_snapshot_id=(
                snapshot_record.snapshot_id
                if snapshot_record
                else None
            ),
            algorithm_version=(
                ALGORITHM_VERSION
            ),
            candidate_policy_version=(
                CAUSAL_CANDIDATE_POLICY_VERSION
            ),
            candidate_admission_policy_version=(
                CAUSAL_CANDIDATE_ADMISSION_POLICY_VERSION
            ),
            lineage_admission_audit=list(
                change_analysis.lineage_admission_audit
            ),
            candidate_selection_audit=list(
                candidate_selection.audit
            ),
            evaluation_policy_version=(
                CAUSAL_EVALUATION_BUDGET_POLICY_VERSION
            ),
            candidate_evaluation_audit=list(
                candidate_evaluation.audit
            ),
            evaluation_budget_audit=(
                candidate_evaluation.budget
            ),
            causal_relevance_policy_version=(
                CAUSAL_RELEVANCE_POLICY_VERSION
            ),
            support_policy_version=(
                CAUSAL_SUPPORT_GATE_POLICY_VERSION
            ),
            projection_policy_version=(
                CAUSAL_HYPOTHESIS_PROJECTION_POLICY_VERSION
            ),
            diagnostic_hypothesis_ids=list(
                hypothesis_projection.diagnostic_hypothesis_ids
            ),
            supported_hypothesis_ids=list(
                hypothesis_projection.supported_hypothesis_ids
            ),
            hypothesis_projection_audit=list(
                hypothesis_projection.audit
            ),
            hypothesis_projection_summary=(
                hypothesis_projection.summary
            ),
            candidate_relevance_audit=[
                relevance_by_event[candidate.event.event_id]
                for candidate in candidates
            ],
            generated_at=(
                utc_now_iso()
            ),
            parameters=(
                request.model_dump(
                    mode="json"
                )
            ),
            candidate_count=(
                len(all_candidates)
            ),
            node_count=len(nodes),
            edge_count=len(edges),
            evidence_count=(
                len(evidence)
            ),
            hypothesis_count=(
                len(hypotheses)
            ),
            top_hypothesis=(
                diagnostic_hypotheses[0]
                if diagnostic_hypotheses
                else None
            ),
            hypotheses=hypotheses,
            nodes=list(
                nodes.values()
            ),
            edges=list(
                edges.values()
            ),
            evidence=list(
                evidence.values()
            ),
        )
    )

    analysis = ensure_analysis_confidence_semantics(analysis)

    if persist:
        analysis = save_causal_analysis(
            session,
            analysis=analysis,
        )

    return analysis
