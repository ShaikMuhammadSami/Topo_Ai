from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EntityType(str, Enum):
    APPLICATION = "application"
    CODE_REPOSITORY = "code_repository"
    SOURCE_REVISION = "source_revision"
    PIPELINE = "pipeline"
    ARTIFACT = "artifact"
    ENVIRONMENT = "environment"
    CLOUD_RESOURCE = "cloud_resource"
    COMPUTE = "compute"
    WORKLOAD = "workload"
    RUNTIME_INSTANCE = "runtime_instance"
    ENDPOINT = "endpoint"
    DATASTORE = "datastore"
    NETWORK = "network"
    SECURITY_ASSET = "security_asset"
    OBSERVABILITY = "observability"
    SIGNAL = "signal"
    INCIDENT = "incident"
    TEAM = "team"
    BUSINESS_CAPABILITY = "business_capability"
    UNKNOWN = "unknown"
    


class RelationshipType(str, Enum):
    CONTAINS = "contains"
    OWNS = "owns"
    PRODUCES = "produces"
    TRIGGERS = "triggers"
    DEPLOYS = "deploys"
    RUNS = "runs"
    SELECTS = "selects"
    EXPOSES = "exposes"
    ROUTES_TO = "routes_to"
    CALLS = "calls"
    DEPENDS_ON = "depends_on"
    USES = "uses"
    EMITS = "emits"
    OBSERVES = "observes"
    PROTECTS = "protects"
    RESOLVES_TO = "resolves_to"
    ATTACHED_TO = "attached_to"
    AFFECTS = "affects"
    DERIVED_FROM = "derived_from"
    UNKNOWN = "unknown"


class EvidenceType(str, Enum):
    DISCOVERY = "discovery"
    CHANGE = "change"
    CONFIGURATION = "configuration"
    EVENT = "event"
    METRIC = "metric"
    LOG = "log"
    TRACE = "trace"
    ALERT = "alert"
    RELATIONSHIP = "relationship"
    MANUAL = "manual"


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=3,
        description="Stable canonical identifier for this entity.",
    )

    entity_type: EntityType

    kind: str = Field(
        min_length=1,
        description="Source-specific kind, such as KubernetesDeployment.",
    )

    name: str = Field(min_length=1)

    source_system: str = Field(
        min_length=1,
        description="System that supplied this entity, such as kubernetes.",
    )

    external_id: str | None = Field(
        default=None,
        description="Original identifier used by the source system.",
    )

    environment: str | None = None

    observed_at: datetime

    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence that this entity identity is correct.",
    )

    labels: dict[str, str] = Field(default_factory=dict)

    properties: dict[str, Any] = Field(default_factory=dict)


class Relationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=3,
        description="Stable identifier for this relationship.",
    )

    source_entity_id: str
    target_entity_id: str

    relationship_type: RelationshipType

    source_system: str

    observed_at: datetime

    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
    )

    directed: bool = True

    evidence_ids: list[str] = Field(default_factory=list)

    properties: dict[str, Any] = Field(default_factory=dict)


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=3)

    evidence_type: EvidenceType

    source_system: str

    summary: str = Field(min_length=1)

    observed_at: datetime

    related_entity_ids: list[str] = Field(default_factory=list)

    related_relationship_ids: list[str] = Field(default_factory=list)

    payload: dict[str, Any] = Field(default_factory=dict)


class GraphSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"

    snapshot_id: str = Field(min_length=3)

    collected_at: datetime

    collector_name: str

    collector_version: str

    scope: dict[str, str] = Field(default_factory=dict)

    entities: list[Entity] = Field(default_factory=list)

    relationships: list[Relationship] = Field(default_factory=list)

    evidence: list[Evidence] = Field(default_factory=list)

    metadata: dict[str, Any] = Field(default_factory=dict)


class SnapshotValidationResult(BaseModel):
    valid: bool

    entity_count: int
    relationship_count: int
    evidence_count: int

    errors: list[str] = Field(default_factory=list)

    warnings: list[str] = Field(default_factory=list)