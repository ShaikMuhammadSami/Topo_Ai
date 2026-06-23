from typing import Any

from app.models.snapshots import (
    EntityChange,
    RelationshipChange,
    SnapshotDiffResult,
)
from app.models.topology import (
    Entity,
    GraphSnapshot,
    Relationship,
)


def _changed_fields(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    changes: dict[str, dict[str, Any]] = {}

    all_keys = set(before) | set(after)

    for key in sorted(all_keys):
        before_value = before.get(key)
        after_value = after.get(key)

        if before_value == after_value:
            continue

        changes[key] = {
            "before": before_value,
            "after": after_value,
        }

    return changes


def _entity_comparison_data(
    entity: Entity,
) -> dict[str, Any]:
    """
    Exclude observed_at because it changes on every collection.
    """
    return entity.model_dump(
        mode="json",
        exclude={
            "id",
            "observed_at",
        },
    )


def _relationship_comparison_data(
    relationship: Relationship,
) -> dict[str, Any]:
    """
    Exclude observation time and evidence IDs because both are
    generated for every new snapshot.
    """
    return relationship.model_dump(
        mode="json",
        exclude={
            "id",
            "observed_at",
            "evidence_ids",
        },
    )


def compare_snapshots(
    before: GraphSnapshot,
    after: GraphSnapshot,
) -> SnapshotDiffResult:
    before_entities = {
        entity.id: entity
        for entity in before.entities
    }

    after_entities = {
        entity.id: entity
        for entity in after.entities
    }

    before_relationships = {
        relationship.id: relationship
        for relationship in before.relationships
    }

    after_relationships = {
        relationship.id: relationship
        for relationship in after.relationships
    }

    before_entity_ids = set(before_entities)
    after_entity_ids = set(after_entities)

    before_relationship_ids = set(
        before_relationships
    )
    after_relationship_ids = set(
        after_relationships
    )

    added_entity_ids = (
        after_entity_ids - before_entity_ids
    )

    removed_entity_ids = (
        before_entity_ids - after_entity_ids
    )

    common_entity_ids = (
        before_entity_ids & after_entity_ids
    )

    added_relationship_ids = (
        after_relationship_ids
        - before_relationship_ids
    )

    removed_relationship_ids = (
        before_relationship_ids
        - after_relationship_ids
    )

    common_relationship_ids = (
        before_relationship_ids
        & after_relationship_ids
    )

    changed_entities: list[EntityChange] = []

    for entity_id in sorted(common_entity_ids):
        before_entity = before_entities[entity_id]
        after_entity = after_entities[entity_id]

        changes = _changed_fields(
            before=_entity_comparison_data(
                before_entity
            ),
            after=_entity_comparison_data(
                after_entity
            ),
        )

        if not changes:
            continue

        changed_entities.append(
            EntityChange(
                entity_id=entity_id,
                kind=after_entity.kind,
                name=after_entity.name,
                changed_fields=changes,
            )
        )

    changed_relationships: list[
        RelationshipChange
    ] = []

    for relationship_id in sorted(
        common_relationship_ids
    ):
        before_relationship = (
            before_relationships[relationship_id]
        )

        after_relationship = (
            after_relationships[relationship_id]
        )

        changes = _changed_fields(
            before=_relationship_comparison_data(
                before_relationship
            ),
            after=_relationship_comparison_data(
                after_relationship
            ),
        )

        if not changes:
            continue

        changed_relationships.append(
            RelationshipChange(
                relationship_id=relationship_id,
                source_entity_id=(
                    after_relationship.source_entity_id
                ),
                target_entity_id=(
                    after_relationship.target_entity_id
                ),
                relationship_type=(
                    after_relationship
                    .relationship_type
                    .value
                ),
                changed_fields=changes,
            )
        )

    added_entities = [
        after_entities[entity_id]
        for entity_id in sorted(added_entity_ids)
    ]

    removed_entities = [
        before_entities[entity_id]
        for entity_id in sorted(removed_entity_ids)
    ]

    added_relationships = [
        after_relationships[relationship_id]
        for relationship_id in sorted(
            added_relationship_ids
        )
    ]

    removed_relationships = [
        before_relationships[relationship_id]
        for relationship_id in sorted(
            removed_relationship_ids
        )
    ]

    return SnapshotDiffResult(
        from_snapshot_id=before.snapshot_id,
        to_snapshot_id=after.snapshot_id,
        added_entities=added_entities,
        removed_entities=removed_entities,
        changed_entities=changed_entities,
        added_relationships=added_relationships,
        removed_relationships=removed_relationships,
        changed_relationships=changed_relationships,
        summary={
            "added_entities": len(added_entities),
            "removed_entities": len(
                removed_entities
            ),
            "changed_entities": len(
                changed_entities
            ),
            "added_relationships": len(
                added_relationships
            ),
            "removed_relationships": len(
                removed_relationships
            ),
            "changed_relationships": len(
                changed_relationships
            ),
        },
    )