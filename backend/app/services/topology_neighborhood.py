from __future__ import annotations

from collections import deque


def traverse_topology_neighborhood(
    start_entity_id: str,
    relationships,
    max_hops: int,
) -> list[str]:
    """Return bounded graph context without making an impact claim."""

    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(start_entity_id, 0)])

    while queue:
        entity_id, distance = queue.popleft()
        if entity_id in visited:
            continue
        visited.add(entity_id)
        if distance >= max_hops:
            continue

        for relationship in relationships:
            if relationship.source_entity_id == entity_id:
                queue.append((relationship.target_entity_id, distance + 1))
            elif relationship.target_entity_id == entity_id:
                queue.append((relationship.source_entity_id, distance + 1))

    return sorted(visited)
