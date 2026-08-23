from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.canonical_identity import (
    CanonicalIdentityResolutionStatus,
)
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
from app.services.canonical_identity import (
    resolve_equivalent_snapshot_entity,
)


IDENTITY_REPRESENTATION_FIELDS = {
    "id",
    "external_id",
    "aliases",
    "identity_version",
    "observed_at",
}


@dataclass(frozen=True)
class SnapshotIdentityAlignment:
    """One-to-one entity equivalence between two supplied snapshots."""

    before_to_after: dict[str, str]


@dataclass(frozen=True)
class SnapshotRelationshipAlignment:
    """One-to-one relationship equivalence after endpoint alignment."""

    before_to_after: dict[str, str]


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


def entity_material_data(
    entity: Entity,
) -> dict[str, Any]:
    """Return customer-observable entity state, excluding identity form."""

    return entity.model_dump(
        mode="json",
        exclude=IDENTITY_REPRESENTATION_FIELDS,
    )


def relationship_material_data(
    relationship: Relationship,
    *,
    endpoint_id_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return relationship state with optionally aligned endpoint IDs."""

    result = relationship.model_dump(
        mode="json",
        exclude={
            "id",
            "observed_at",
            "evidence_ids",
        },
    )
    if endpoint_id_map:
        result["source_entity_id"] = endpoint_id_map.get(
            relationship.source_entity_id,
            relationship.source_entity_id,
        )
        result["target_entity_id"] = endpoint_id_map.get(
            relationship.target_entity_id,
            relationship.target_entity_id,
        )
    return result


def align_snapshot_entities(
    before: GraphSnapshot,
    after: GraphSnapshot,
) -> SnapshotIdentityAlignment:
    """Build deterministic mutual identity alignment for two snapshots.

    Exact raw IDs are preserved first. Remaining entities are paired only
    when TC-1 resolution succeeds uniquely in both directions. Restricting
    resolution to these supplied snapshots prevents latest-topology or
    repository fallback, while the mutual check prevents duplicate legacy
    identities from being silently collapsed.
    """

    before_entities = {
        entity.id: entity
        for entity in before.entities
    }
    after_entities = {
        entity.id: entity
        for entity in after.entities
    }
    exact_ids = set(before_entities).intersection(after_entities)
    matches = {
        entity_id: entity_id
        for entity_id in sorted(exact_ids)
    }

    unmatched_before = [
        entity
        for entity in before.entities
        if entity.id not in exact_ids
    ]
    unmatched_after = [
        entity
        for entity in after.entities
        if entity.id not in exact_ids
    ]
    if not unmatched_before or not unmatched_after:
        return SnapshotIdentityAlignment(before_to_after=matches)

    before_unmatched_snapshot = before.model_copy(
        update={
            "entities": unmatched_before,
            "relationships": [],
        }
    )
    after_unmatched_snapshot = after.model_copy(
        update={
            "entities": unmatched_after,
            "relationships": [],
        }
    )

    forward = {
        entity.id: resolve_equivalent_snapshot_entity(
            before_unmatched_snapshot,
            after_unmatched_snapshot,
            entity,
        )
        for entity in unmatched_before
    }
    reverse = {
        entity.id: resolve_equivalent_snapshot_entity(
            after_unmatched_snapshot,
            before_unmatched_snapshot,
            entity,
        )
        for entity in unmatched_after
    }

    for before_id in sorted(forward):
        resolution = forward[before_id]
        if (
            resolution.status
            != CanonicalIdentityResolutionStatus.RESOLVED
            or not resolution.resolved_entity_id
        ):
            continue

        after_id = resolution.resolved_entity_id
        reverse_resolution = reverse.get(after_id)
        if (
            reverse_resolution is None
            or reverse_resolution.status
            != CanonicalIdentityResolutionStatus.RESOLVED
            or reverse_resolution.resolved_entity_id != before_id
        ):
            continue

        matches[before_id] = after_id

    return SnapshotIdentityAlignment(before_to_after=matches)


def _relationship_key(
    relationship: Relationship,
    *,
    endpoint_id_map: dict[str, str] | None = None,
) -> tuple[str, str, str] | None:
    source_id = relationship.source_entity_id
    target_id = relationship.target_entity_id
    if endpoint_id_map is not None:
        source_id = endpoint_id_map.get(source_id, "")
        target_id = endpoint_id_map.get(target_id, "")
        if not source_id or not target_id:
            return None

    return (
        source_id,
        target_id,
        relationship.relationship_type.value,
    )


def align_snapshot_relationships(
    before: GraphSnapshot,
    after: GraphSnapshot,
    entity_alignment: SnapshotIdentityAlignment,
) -> SnapshotRelationshipAlignment:
    """Align edges only when their aligned endpoints and type are unique."""

    before_relationships = {
        relationship.id: relationship
        for relationship in before.relationships
    }
    after_relationships = {
        relationship.id: relationship
        for relationship in after.relationships
    }
    exact_ids = set(before_relationships).intersection(
        after_relationships
    )
    matches = {
        relationship_id: relationship_id
        for relationship_id in sorted(exact_ids)
    }

    before_by_key: dict[
        tuple[str, str, str],
        list[Relationship],
    ] = {}
    for relationship in before.relationships:
        if relationship.id in exact_ids:
            continue
        key = _relationship_key(
            relationship,
            endpoint_id_map=entity_alignment.before_to_after,
        )
        if key is not None:
            before_by_key.setdefault(key, []).append(relationship)

    after_by_key: dict[
        tuple[str, str, str],
        list[Relationship],
    ] = {}
    for relationship in after.relationships:
        if relationship.id in exact_ids:
            continue
        key = _relationship_key(relationship)
        if key is not None:
            after_by_key.setdefault(key, []).append(relationship)

    for key in sorted(set(before_by_key).intersection(after_by_key)):
        before_candidates = before_by_key[key]
        after_candidates = after_by_key[key]
        if len(before_candidates) != 1 or len(after_candidates) != 1:
            continue
        matches[before_candidates[0].id] = after_candidates[0].id

    return SnapshotRelationshipAlignment(before_to_after=matches)


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
    entity_alignment = align_snapshot_entities(before, after)
    matched_before_entity_ids = set(entity_alignment.before_to_after)
    matched_after_entity_ids = set(entity_alignment.before_to_after.values())

    added_entity_ids = set(after_entities) - matched_after_entity_ids
    removed_entity_ids = set(before_entities) - matched_before_entity_ids

    changed_entities: list[EntityChange] = []
    for before_id, after_id in sorted(
        entity_alignment.before_to_after.items(),
        key=lambda item: (item[1], item[0]),
    ):
        before_entity = before_entities[before_id]
        after_entity = after_entities[after_id]
        changes = _changed_fields(
            before=entity_material_data(before_entity),
            after=entity_material_data(after_entity),
        )
        if not changes:
            continue
        changed_entities.append(
            EntityChange(
                entity_id=after_id,
                before_entity_id=before_id,
                after_entity_id=after_id,
                kind=after_entity.kind,
                name=after_entity.name,
                changed_fields=changes,
            )
        )

    before_relationships = {
        relationship.id: relationship
        for relationship in before.relationships
    }
    after_relationships = {
        relationship.id: relationship
        for relationship in after.relationships
    }
    relationship_alignment = align_snapshot_relationships(
        before,
        after,
        entity_alignment,
    )
    matched_before_relationship_ids = set(
        relationship_alignment.before_to_after
    )
    matched_after_relationship_ids = set(
        relationship_alignment.before_to_after.values()
    )
    added_relationship_ids = (
        set(after_relationships) - matched_after_relationship_ids
    )
    removed_relationship_ids = (
        set(before_relationships) - matched_before_relationship_ids
    )

    changed_relationships: list[RelationshipChange] = []
    for before_id, after_id in sorted(
        relationship_alignment.before_to_after.items(),
        key=lambda item: (item[1], item[0]),
    ):
        before_relationship = before_relationships[before_id]
        after_relationship = after_relationships[after_id]
        changes = _changed_fields(
            before=relationship_material_data(
                before_relationship,
                endpoint_id_map=entity_alignment.before_to_after,
            ),
            after=relationship_material_data(after_relationship),
        )
        if not changes:
            continue
        changed_relationships.append(
            RelationshipChange(
                relationship_id=after_id,
                before_relationship_id=before_id,
                after_relationship_id=after_id,
                source_entity_id=after_relationship.source_entity_id,
                target_entity_id=after_relationship.target_entity_id,
                relationship_type=(
                    after_relationship.relationship_type.value
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
        for relationship_id in sorted(added_relationship_ids)
    ]
    removed_relationships = [
        before_relationships[relationship_id]
        for relationship_id in sorted(removed_relationship_ids)
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
            "removed_entities": len(removed_entities),
            "changed_entities": len(changed_entities),
            "added_relationships": len(added_relationships),
            "removed_relationships": len(removed_relationships),
            "changed_relationships": len(changed_relationships),
        },
    )
