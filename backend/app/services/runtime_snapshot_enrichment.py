from __future__ import annotations

import hashlib
from datetime import (
    datetime,
    timedelta,
    timezone,
)

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    RuntimeDependencyRecord,
    TopoAgentRecord,
)
from app.models.topology import (
    Entity,
    EntityType,
    GraphSnapshot,
    Relationship,
    RelationshipOrigin,
    RelationshipType,
)
from app.services.relationship_provenance import (
    relationship_provenance,
    source_reference,
)


def _digest(
    value: str,
    length: int = 24,
) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:length]


def _enum_member(
    enum_type: type,
    names: tuple[str, ...],
):
    for name in names:
        member = getattr(
            enum_type,
            name,
            None,
        )

        if member is not None:
            return member

    return next(iter(enum_type))


def _entity_type(
    *names: str,
):
    return _enum_member(
        EntityType,
        tuple(names)
        + ("UNKNOWN",),
    )


def _relationship_type(
    *names: str,
):
    return _enum_member(
        RelationshipType,
        tuple(names)
        + ("UNKNOWN",),
    )


def enrich_snapshot_with_runtime_dependencies(
    session: Session,
    *,
    agent: TopoAgentRecord,
    snapshot: GraphSnapshot,
    window_minutes: int = 30,
) -> GraphSnapshot:
    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(
            minutes=window_minutes
        )
    ).isoformat()

    statement = (
        select(RuntimeDependencyRecord)
        .where(
            RuntimeDependencyRecord.agent_id
            == agent.agent_id,
            RuntimeDependencyRecord
            .last_seen_at
            >= cutoff,
        )
    )

    dependencies = list(
        session.scalars(
            statement
        ).all()
    )

    if not dependencies:
        return snapshot

    entities = list(
        snapshot.entities
    )

    relationships = list(
        snapshot.relationships
    )

    entity_ids = {
        entity.id
        for entity in entities
    }

    relationship_keys = {
        (
            item.source_entity_id,
            item.relationship_type.value,
            item.target_entity_id,
        )
        for item in relationships
    }

    pods_by_uid: dict[str, str] = {}
    pods_by_name: dict[
        tuple[str, str],
        str,
    ] = {}

    containers_by_id: dict[str, str] = {}

    for entity in entities:
        if (
            entity.kind
            == "KubernetesPod"
        ):
            if entity.external_id:
                pods_by_uid[
                    entity.external_id
                ] = entity.id

            namespace = str(
                entity.properties.get(
                    "namespace",
                    "",
                )
            )

            pods_by_name[
                (
                    namespace,
                    entity.name,
                )
            ] = entity.id

        if entity.kind == "Container":
            values = [
                entity.external_id,
                str(
                    entity.properties.get(
                        "id",
                        "",
                    )
                ),
                str(
                    entity.properties.get(
                        "short_id",
                        "",
                    )
                ),
            ]

            for value in values:
                if value:
                    containers_by_id[
                        value
                    ] = entity.id
                    containers_by_id[
                        value[:12]
                    ] = entity.id

    runtime_entity_count = 0
    runtime_relationship_count = 0

    for dependency in dependencies:
        source_id = None

        if dependency.source_container_id:
            source_id = (
                containers_by_id.get(
                    dependency
                    .source_container_id
                )
                or containers_by_id.get(
                    dependency
                    .source_container_id[:12]
                )
            )

        if (
            source_id is None
            and dependency.source_pod_uid
        ):
            source_id = pods_by_uid.get(
                dependency.source_pod_uid
            )

        if (
            source_id is None
            and dependency.source_pod_name
        ):
            source_id = pods_by_name.get(
                (
                    dependency
                    .source_namespace
                    or "",
                    dependency
                    .source_pod_name,
                )
            )

        if source_id is None:
            continue

        endpoint_identity = "|".join(
            [
                dependency.protocol,
                dependency
                .destination_address,
                str(
                    dependency
                    .destination_port
                ),
                dependency
                .destination_name
                or "",
            ]
        )

        endpoint_id = (
            "runtime-endpoint:"
            + _digest(
                endpoint_identity
            )
        )

        if endpoint_id not in entity_ids:
            display_name = (
                dependency.destination_name
                or (
                    f"{dependency.protocol}://"
                    f"{dependency.destination_address}:"
                    f"{dependency.destination_port}"
                )
            )

            entities.append(
                Entity(
                    id=endpoint_id,
                    entity_type=_entity_type(
                        "ENDPOINT",
                        "NETWORK",
                        "EXTERNAL",
                    ),
                    kind=(
                        "RuntimeNetworkEndpoint"
                    ),
                    name=display_name,
                    source_system=(
                        "tetragon"
                    ),
                    external_id=(
                        f"{dependency.destination_address}:"
                        f"{dependency.destination_port}"
                    ),
                    environment=(
                        agent.environment
                    ),
                    observed_at=(
                        dependency
                        .last_seen_at
                    ),
                    confidence=0.95,
                    labels={},
                    properties={
                        "address":
                            dependency
                            .destination_address,
                        "port":
                            dependency
                            .destination_port,
                        "protocol":
                            dependency.protocol,
                        "dns_name":
                            dependency
                            .destination_name,
                        "observation_count":
                            dependency
                            .observation_count,
                        "success_count":
                            dependency
                            .success_count,
                        "failure_count":
                            dependency
                            .failure_count,
                        "first_seen_at":
                            dependency
                            .first_seen_at,
                        "last_seen_at":
                            dependency
                            .last_seen_at,
                        "sensor_id":
                            dependency
                            .sensor_id,
                        "node_name":
                            dependency
                            .node_name,
                    },
                )
            )

            entity_ids.add(endpoint_id)
            runtime_entity_count += 1

        relation = _relationship_type(
            "CALLS"
        )

        key = (
            source_id,
            relation.value,
            endpoint_id,
        )

        if key in relationship_keys:
            continue

        relationship_keys.add(key)

        relationship_id = (
            "relationship:"
            + _digest(
                "|".join(
                    [
                        source_id,
                        relation.value,
                        endpoint_id,
                    ]
                )
            )
        )

        relationships.append(
            Relationship(
                id=relationship_id,
                source_entity_id=source_id,
                target_entity_id=(
                    endpoint_id
                ),
                relationship_type=relation,
                source_system="tetragon",
                observed_at=(
                    dependency.last_seen_at
                ),
                directed=True,
                evidence_ids=[],
                provenance=relationship_provenance(
                    predicate=relation,
                    origin=RelationshipOrigin.OBSERVED,
                    source_component=(
                        "backend.app.services.runtime_snapshot_enrichment"
                    ),
                    source_references=[
                        source_reference(
                            reference_type="runtime_dependency_record",
                            reference=(
                                dependency.runtime_dependency_id
                            ),
                            source_system="tetragon",
                            attributes={
                                "sensor_id": dependency.sensor_id,
                                "observation_count": (
                                    dependency.observation_count
                                ),
                                "first_seen_at": (
                                    dependency.first_seen_at
                                ),
                                "last_seen_at": (
                                    dependency.last_seen_at
                                ),
                            },
                        )
                    ],
                    linker_version="tetragon-network-linker:v1",
                ),
                properties={
                    "runtime_observed":
                        True,
                    "protocol":
                        dependency.protocol,
                    "direction":
                        dependency.direction,
                    "observation_count":
                        dependency
                        .observation_count,
                    "success_count":
                        dependency
                        .success_count,
                    "failure_count":
                        dependency
                        .failure_count,
                    "first_seen_at":
                        dependency
                        .first_seen_at,
                    "last_seen_at":
                        dependency
                        .last_seen_at,
                },
            )
        )

        runtime_relationship_count += 1

    return snapshot.model_copy(
        update={
            "entities": entities,
            "relationships":
                relationships,
            "metadata": {
                **snapshot.metadata,
                "ebpf_runtime_overlay": {
                    "window_minutes":
                        window_minutes,
                    "dependency_record_count":
                        len(dependencies),
                    "added_entity_count":
                        runtime_entity_count,
                    "added_relationship_count":
                        runtime_relationship_count,
                },
            },
        }
    )
