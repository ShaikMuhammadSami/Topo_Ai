from __future__ import annotations

import hashlib
from collections import (
    defaultdict,
    deque,
)

from sqlalchemy.orm import Session

from app.models.network_dependency import (
    NetworkDependencyAnalysisResponse,
    NetworkDependencyEdge,
    NetworkDependencyIssue,
    NetworkDependencyPath,
    NetworkEntityView,
    NetworkIssueSeverity,
)
from app.repositories.snapshot_repository import (
    load_snapshot,
)


NETWORK_RELATIONSHIPS = {
    "selects",
    "exposes",
    "routes_to",
    "calls",
    "depends_on",
    "resolves_to",
    "protects",
    "attached_to",
}


NETWORK_KINDS = {
    "KubernetesIngress",
    "KubernetesService",
    "KubernetesEndpointSlice",
    "NetworkEndpoint",
    "ExternalEndpoint",
    "DNSName",
}


def _issue_id(
    code: str,
    entity_id: str | None,
    summary: str,
) -> str:
    value = "|".join(
        [
            code,
            entity_id or "",
            summary,
        ]
    )

    digest = hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:24]

    return f"network-issue:{digest}"


def _namespace(
    entity,
) -> str | None:
    value = entity.properties.get(
        "namespace"
    )

    return (
        str(value)
        if value is not None
        else None
    )


def _entity_type_value(
    entity,
) -> str:
    value = entity.entity_type

    return (
        value.value
        if hasattr(value, "value")
        else str(value)
    )


def analyze_network_dependencies(
    session: Session,
    snapshot_id: str,
    max_depth: int = 5,
) -> NetworkDependencyAnalysisResponse:
    snapshot = load_snapshot(
        session=session,
        snapshot_id=snapshot_id,
    )

    if snapshot is None:
        raise ValueError(
            "Topology snapshot not found: "
            f"{snapshot_id}"
        )

    entity_map = {
        entity.id: entity
        for entity in snapshot.entities
    }

    network_relationships = [
        relationship
        for relationship
        in snapshot.relationships
        if (
            relationship
            .relationship_type.value
            in NETWORK_RELATIONSHIPS
        )
    ]

    participating_ids: set[str] = set()

    edges: list[
        NetworkDependencyEdge
    ] = []

    issues: list[
        NetworkDependencyIssue
    ] = []

    for relationship in (
        network_relationships
    ):
        source_exists = (
            relationship.source_entity_id
            in entity_map
        )

        target_exists = (
            relationship.target_entity_id
            in entity_map
        )

        resolved = (
            source_exists
            and target_exists
        )

        participating_ids.add(
            relationship.source_entity_id
        )

        participating_ids.add(
            relationship.target_entity_id
        )

        edges.append(
            NetworkDependencyEdge(
                relationship_id=(
                    relationship.id
                ),
                source_entity_id=(
                    relationship
                    .source_entity_id
                ),
                target_entity_id=(
                    relationship
                    .target_entity_id
                ),
                relationship_type=(
                    relationship
                    .relationship_type.value
                ),
                resolved=resolved,
                properties=(
                    relationship.properties
                ),
            )
        )

        if not resolved:
            summary = (
                "Network relationship points "
                "to a missing entity."
            )

            issues.append(
                NetworkDependencyIssue(
                    issue_id=_issue_id(
                        "dangling_relationship",
                        relationship
                        .source_entity_id,
                        summary,
                    ),
                    severity=(
                        NetworkIssueSeverity
                        .ERROR
                    ),
                    code=(
                        "dangling_relationship"
                    ),
                    summary=summary,
                    entity_id=(
                        relationship
                        .source_entity_id
                    ),
                    details={
                        "target_entity_id":
                            relationship
                            .target_entity_id,
                        "relationship_type":
                            relationship
                            .relationship_type
                            .value,
                    },
                )
            )

    for entity in snapshot.entities:
        if entity.kind in NETWORK_KINDS:
            participating_ids.add(
                entity.id
            )

    network_entities = [
        entity
        for entity in snapshot.entities
        if entity.id in participating_ids
    ]

    service_lookup = {
        (
            _namespace(entity),
            entity.name,
        ): entity
        for entity in network_entities
        if entity.kind
        == "KubernetesService"
    }

    outgoing_by_entity: dict[
        str,
        list,
    ] = defaultdict(list)

    incoming_by_entity: dict[
        str,
        list,
    ] = defaultdict(list)

    for relationship in (
        network_relationships
    ):
        outgoing_by_entity[
            relationship.source_entity_id
        ].append(relationship)

        incoming_by_entity[
            relationship.target_entity_id
        ].append(relationship)

    for entity in network_entities:
        if (
            entity.kind
            == "KubernetesIngress"
        ):
            for backend in (
                entity.properties.get(
                    "backends",
                    [],
                )
            ):
                service_name = (
                    backend.get(
                        "service_name"
                    )
                )

                key = (
                    _namespace(entity),
                    service_name,
                )

                if key in service_lookup:
                    continue

                summary = (
                    "Ingress backend Service "
                    f"'{service_name}' was not found."
                )

                issues.append(
                    NetworkDependencyIssue(
                        issue_id=_issue_id(
                            "missing_ingress_backend",
                            entity.id,
                            summary,
                        ),
                        severity=(
                            NetworkIssueSeverity
                            .ERROR
                        ),
                        code=(
                            "missing_ingress_backend"
                        ),
                        summary=summary,
                        entity_id=entity.id,
                        entity_name=(
                            entity.name
                        ),
                        details=backend,
                    )
                )

        if (
            entity.kind
            == "KubernetesService"
        ):
            service_type = (
                entity.properties.get(
                    "service_type"
                )
            )

            if (
                service_type
                == "ExternalName"
            ):
                continue

            relationships = (
                outgoing_by_entity.get(
                    entity.id,
                    [],
                )
            )

            has_backends = any(
                relationship
                .relationship_type.value
                in {
                    "selects",
                    "exposes",
                    "routes_to",
                }
                for relationship
                in relationships
            )

            if not has_backends:
                summary = (
                    "Service has no selected Pods "
                    "or EndpointSlices."
                )

                issues.append(
                    NetworkDependencyIssue(
                        issue_id=_issue_id(
                            "service_without_backends",
                            entity.id,
                            summary,
                        ),
                        severity=(
                            NetworkIssueSeverity
                            .WARNING
                        ),
                        code=(
                            "service_without_backends"
                        ),
                        summary=summary,
                        entity_id=entity.id,
                        entity_name=(
                            entity.name
                        ),
                        details={
                            "selector":
                                entity.properties
                                .get("selector"),
                        },
                    )
                )

        if (
            entity.kind
            == "KubernetesEndpointSlice"
        ):
            ready = int(
                entity.properties.get(
                    "ready_endpoint_count",
                    0,
                )
            )

            total = int(
                entity.properties.get(
                    "total_endpoint_count",
                    0,
                )
            )

            if total == 0 or ready == 0:
                summary = (
                    "EndpointSlice has no ready "
                    "network endpoints."
                )

                issues.append(
                    NetworkDependencyIssue(
                        issue_id=_issue_id(
                            "no_ready_endpoints",
                            entity.id,
                            summary,
                        ),
                        severity=(
                            NetworkIssueSeverity
                            .ERROR
                        ),
                        code=(
                            "no_ready_endpoints"
                        ),
                        summary=summary,
                        entity_id=entity.id,
                        entity_name=(
                            entity.name
                        ),
                        details={
                            "ready": ready,
                            "total": total,
                        },
                    )
                )

        if entity.kind in {
            "ExternalEndpoint",
            "DNSName",
        }:
            status = (
                entity.properties.get(
                    "resolution_status"
                )
            )

            if status in {
                "failed",
                "unresolved",
            }:
                summary = (
                    "External dependency could "
                    "not be resolved."
                )

                issues.append(
                    NetworkDependencyIssue(
                        issue_id=_issue_id(
                            "unresolved_external_dependency",
                            entity.id,
                            summary,
                        ),
                        severity=(
                            NetworkIssueSeverity
                            .WARNING
                        ),
                        code=(
                            "unresolved_external_dependency"
                        ),
                        summary=summary,
                        entity_id=entity.id,
                        entity_name=(
                            entity.name
                        ),
                    )
                )

    adjacency: dict[
        str,
        list[tuple[str, str]],
    ] = defaultdict(list)

    incoming_count: dict[
        str,
        int,
    ] = defaultdict(int)

    for relationship in (
        network_relationships
    ):
        adjacency[
            relationship.source_entity_id
        ].append(
            (
                relationship
                .target_entity_id,
                relationship
                .relationship_type.value,
            )
        )

        incoming_count[
            relationship.target_entity_id
        ] += 1

    roots = [
        entity.id
        for entity in network_entities
        if (
            entity.kind
            == "KubernetesIngress"
        )
    ]

    if not roots:
        roots = [
            entity.id
            for entity in network_entities
            if (
                outgoing_by_entity.get(
                    entity.id
                )
                and incoming_count[
                    entity.id
                ] == 0
            )
        ]

    paths: list[
        NetworkDependencyPath
    ] = []

    path_keys: set[
        tuple[str, ...]
    ] = set()

    for root_id in roots:
        queue = deque(
            [
                (
                    root_id,
                    [root_id],
                    [],
                )
            ]
        )

        while queue:
            (
                current_id,
                entity_path,
                relation_path,
            ) = queue.popleft()

            if (
                len(relation_path)
                >= max_depth
            ):
                continue

            neighbours = adjacency.get(
                current_id,
                [],
            )

            if (
                not neighbours
                and len(entity_path) > 1
            ):
                key = tuple(entity_path)

                if key not in path_keys:
                    path_keys.add(key)

                    paths.append(
                        NetworkDependencyPath(
                            entity_ids=(
                                entity_path
                            ),
                            relationship_types=(
                                relation_path
                            ),
                        )
                    )

                continue

            for (
                target_id,
                relation_type,
            ) in neighbours:
                if target_id in entity_path:
                    continue

                new_entity_path = [
                    *entity_path,
                    target_id,
                ]

                new_relation_path = [
                    *relation_path,
                    relation_type,
                ]

                key = tuple(
                    new_entity_path
                )

                if key not in path_keys:
                    path_keys.add(key)

                    paths.append(
                        NetworkDependencyPath(
                            entity_ids=(
                                new_entity_path
                            ),
                            relationship_types=(
                                new_relation_path
                            ),
                        )
                    )

                queue.append(
                    (
                        target_id,
                        new_entity_path,
                        new_relation_path,
                    )
                )

                if len(paths) >= 500:
                    break

            if len(paths) >= 500:
                break

    entity_views = [
        NetworkEntityView(
            entity_id=entity.id,
            entity_type=(
                _entity_type_value(
                    entity
                )
            ),
            entity_kind=entity.kind,
            entity_name=entity.name,
            namespace=_namespace(
                entity
            ),
            properties=(
                entity.properties
            ),
        )
        for entity in network_entities
    ]

    return (
        NetworkDependencyAnalysisResponse(
            snapshot_id=snapshot_id,
            entity_count=len(
                entity_views
            ),
            relationship_count=len(
                edges
            ),
            path_count=len(paths),
            issue_count=len(issues),
            ingress_count=sum(
                entity.entity_kind
                == "KubernetesIngress"
                for entity
                in entity_views
            ),
            service_count=sum(
                entity.entity_kind
                == "KubernetesService"
                for entity
                in entity_views
            ),
            endpoint_slice_count=sum(
                entity.entity_kind
                == "KubernetesEndpointSlice"
                for entity
                in entity_views
            ),
            external_endpoint_count=sum(
                entity.entity_kind
                in {
                    "ExternalEndpoint",
                    "DNSName",
                }
                for entity
                in entity_views
            ),
            entities=entity_views,
            relationships=edges,
            dependency_paths=paths,
            issues=issues,
        )
    )