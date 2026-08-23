from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.temporal import TemporalMetadata


class ChangeType(str, Enum):
    ENTITY_ADDED = "entity_added"
    ENTITY_REMOVED = "entity_removed"
    ENTITY_UPDATED = "entity_updated"

    RELATIONSHIP_ADDED = "relationship_added"
    RELATIONSHIP_REMOVED = "relationship_removed"
    RELATIONSHIP_UPDATED = "relationship_updated"


class ChangeCategory(str, Enum):
    DEPLOYMENT = "deployment"
    SCALING = "scaling"
    IMAGE = "image"
    CONFIGURATION = "configuration"
    RUNTIME = "runtime"
    SERVICE = "service"
    NETWORKING = "networking"
    TOPOLOGY = "topology"
    OTHER = "other"


class ChangeImportance(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class NormalizedChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_id: str
    fingerprint: str

    change_type: ChangeType
    category: ChangeCategory
    importance: ChangeImportance

    source_system: str = "snapshot-diff"

    title: str
    summary: str

    detected_at: datetime

    temporal: TemporalMetadata | None = None

    from_snapshot_id: str
    to_snapshot_id: str

    cluster_name: str
    namespace: str | None = None

    entity_id: str | None = None
    entity_kind: str | None = None
    entity_name: str | None = None

    relationship_id: str | None = None
    relationship_type: str | None = None

    source_entity_id: str | None = None
    target_entity_id: str | None = None

    changed_fields: dict[
        str,
        dict[str, Any],
    ] = Field(default_factory=dict)

    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None

    related_entity_ids: list[str] = Field(
        default_factory=list
    )

    attributes: dict[str, Any] = Field(
        default_factory=dict
    )


class ChangeSummary(BaseModel):
    change_id: str

    change_type: ChangeType
    category: ChangeCategory
    importance: ChangeImportance

    title: str
    summary: str

    detected_at: datetime

    temporal: TemporalMetadata | None = None

    from_snapshot_id: str
    to_snapshot_id: str

    cluster_name: str
    namespace: str | None

    entity_id: str | None
    entity_kind: str | None
    entity_name: str | None

    relationship_id: str | None
    relationship_type: str | None


class ChangeIngestionResult(BaseModel):
    from_snapshot_id: str
    to_snapshot_id: str

    cluster_name: str
    namespace: str | None

    detected_count: int
    created_count: int
    updated_count: int

    type_counts: dict[str, int] = Field(
        default_factory=dict
    )

    category_counts: dict[str, int] = Field(
        default_factory=dict
    )

    importance_counts: dict[str, int] = Field(
        default_factory=dict
    )
