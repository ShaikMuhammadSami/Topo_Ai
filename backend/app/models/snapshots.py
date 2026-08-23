from typing import Any

from pydantic import BaseModel, Field

from app.models.topology import Entity, Relationship


class SnapshotSummary(BaseModel):
    snapshot_id: str
    schema_version: str
    collected_at: str
    collector_name: str
    collector_version: str
    cluster_name: str | None
    namespace: str | None
    entity_count: int
    relationship_count: int
    evidence_count: int
    checkpoint_reason: str | None = None
    state_digest: str | None = None


class EntityChange(BaseModel):
    entity_id: str
    kind: str
    name: str

    changed_fields: dict[str, dict[str, Any]] = Field(
        default_factory=dict
    )


class RelationshipChange(BaseModel):
    relationship_id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: str

    changed_fields: dict[str, dict[str, Any]] = Field(
        default_factory=dict
    )


class SnapshotDiffResult(BaseModel):
    from_snapshot_id: str
    to_snapshot_id: str

    added_entities: list[Entity] = Field(
        default_factory=list
    )

    removed_entities: list[Entity] = Field(
        default_factory=list
    )

    changed_entities: list[EntityChange] = Field(
        default_factory=list
    )

    added_relationships: list[Relationship] = Field(
        default_factory=list
    )

    removed_relationships: list[Relationship] = Field(
        default_factory=list
    )

    changed_relationships: list[RelationshipChange] = Field(
        default_factory=list
    )

    summary: dict[str, int] = Field(
        default_factory=dict
    )
