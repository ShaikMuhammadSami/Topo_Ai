from collections import deque

from sqlalchemy.orm import Session

from app.models.blast_radius import (
    BlastRadiusEntity,
    BlastRadiusResponse,
    DependencyPath,
)

from app.repositories.topology_snapshot_repository import (
    load_topology_snapshot,
)
from app.repositories.incident_record_repository import (
    load_incident_record,
)


MAX_DEPTH = 5

def traverse_blast_radius(
    start_entity_id: str,
    relationships,
    max_hops: int,
):
    visited = set()
    queue = deque()

    queue.append(
        (
            start_entity_id,
            0
        )
    )

    while queue:
        current, hops = queue.popleft()

        if current in visited:
            continue

        visited.add(current)

        if hops >= max_hops:
            continue

        for relationship in relationships:

            if relationship.source_entity_id == current:
                queue.append(
                    (
                        relationship.target_entity_id,
                        hops + 1
                    )
                )

            if relationship.target_entity_id == current:
                queue.append(
                    (
                        relationship.source_entity_id,
                        hops + 1
                    )
                )

    return list(visited)

def calculate_impact_score(
    distance: int,
) -> float:

    if distance == 0:
        return 1.0

    if distance == 1:
        return 0.85

    if distance == 2:
        return 0.65

    if distance == 3:
        return 0.45

    return 0.25



def impact_label(
    distance: int,
) -> str:

    if distance == 0:
        return "direct"

    if distance == 1:
        return "dependent"

    if distance == 2:
        return "indirect"

    return "potential"



def calculate_blast_radius(
    session: Session,
    incident_id: str,
) -> BlastRadiusResponse:


    incident = load_incident_record(
        session=session,
        incident_id=incident_id,
    )


    if incident is None:
        raise ValueError(
            "Incident not found"
        )


    if not incident.affected_entity_id:
        raise ValueError(
            "Incident has no affected entity"
        )


    graph = load_topology_snapshot(
        session=session,
        snapshot_id=incident.topology_snapshot_id,
    )
    entities = graph.entities
    relationships = graph.relationships

    if graph is None:
        raise ValueError(
            "Topology snapshot not found"
        )
    


    visited = set()

    queue = deque()


    queue.append(
        (
            incident.affected_entity_id,
            0,
            [
                incident.affected_entity_id
            ],
            None
        )
    )


    impacted = []

    paths = []


    while queue:

        entity_id, distance, path , relation= (
            queue.popleft()
        )


        if entity_id in visited:
            continue


        visited.add(entity_id)


        entity = next(
            (
                item
                for item in entities
                if item.id == entity_id
            ),
            None,
        )

        if entity is None:
            continue


        impacted.append(
            BlastRadiusEntity(
                entity_id=entity_id,
                entity_kind=(
                    entity.kind
                ),
                entity_name=(
                    entity.name
                ),
                namespace=(
                    entity.properties.get("namespace")
                ),
                distance=distance,
                impact=(
                    impact_label(
                        distance
                    )
                ),
                impact_score=(
                    calculate_impact_score(
                        distance
                    )
                ),
                relationship=relation,
            )
        )


        if distance > 0:
            paths.append(
                DependencyPath(
                    path=path
                )
            )


        if distance >= MAX_DEPTH:
            continue


        neighbours = []


        for relationship in relationships:
            neighbour = None

            if relationship.source_entity_id == entity_id:
                neighbour = relationship.target_entity_id

            elif relationship.target_entity_id == entity_id:
                neighbour = relationship.source_entity_id


        # for neighbour in neighbours:

            if neighbour and neighbour not in visited:

                queue.append(
                    (
                        neighbour,
                        distance + 1,
                        path + [
                            neighbour
                        ],
                        relationship.relationship_type.value
                    )
                )


    direct = [
        item
        for item in impacted
        if item.distance == 0
    ]


    indirect = [
        item
        for item in impacted
        if item.distance == 1
    ]


    potential = [
        item
        for item in impacted
        if item.distance >= 2
    ]


    return BlastRadiusResponse(

        incident_id=incident_id,

        root_entity_id=(
            incident
            .affected_entity_id
        ),

        root_entity_name=(
            incident
            .affected_object_name
            or "unknown"
        ),

        affected_entity_count=(
            len(impacted)
        ),

        direct_impact_count=(
            len(direct)
        ),

        indirect_impact_count=(
            len(indirect)
        ),

        potential_impact_count=(
            len(potential)
        ),

        affected_entities=sorted(
            impacted,
            key=lambda item: (
                item.distance,
                -item.impact_score,
            ),
        ),

        dependency_paths=paths,

    )