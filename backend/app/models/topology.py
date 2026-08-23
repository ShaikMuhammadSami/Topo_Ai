from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class RelationshipOrigin(str, Enum):
    """How a relationship assertion entered the topology graph."""

    OBSERVED = "observed"
    DECLARED = "declared"
    DERIVED = "derived"
    INFERRED = "inferred"


class RelationshipProvenanceCompleteness(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    LEGACY_UNSPECIFIED = "legacy_unspecified"


class RelationshipConfidenceSemantics(str, Enum):
    """A score is a deterministic heuristic, not a probability."""

    HEURISTIC_SCORE = "heuristic_score"


class RelationshipSourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_type: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    source_system: str = Field(min_length=1)
    attributes: dict[str, Any] = Field(default_factory=dict)


class RelationshipProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: RelationshipOrigin
    source_component: str = Field(min_length=1)
    source_references: list[RelationshipSourceReference] = Field(
        default_factory=list,
    )
    linker_version: str = Field(min_length=1)
    completeness: RelationshipProvenanceCompleteness


class RelationshipHistoricalValidation(BaseModel):
    """Optional later validation; deliberately separate from origin."""

    model_config = ConfigDict(extra="forbid")

    historically_confirmed: bool
    validated_at: datetime | None = None
    evidence_ids: list[str] = Field(default_factory=list)


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

    aliases: list[str] = Field(
        default_factory=list,
        description=(
            "Explicit, deterministic legacy graph identifiers that may "
            "resolve to this entity within the entity's source scope."
        ),
    )

    identity_version: str = Field(
        default="legacy",
        min_length=1,
        description=(
            "Version of the source-specific graph identity algorithm. "
            "Snapshots created before TC-1 load as legacy without being "
            "rewritten."
        ),
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

    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Optional deterministic heuristic score. It is not a "
            "calibrated probability. Observed and declared edges omit it."
        ),
    )

    confidence_semantics: (
        RelationshipConfidenceSemantics | None
    ) = None

    directed: bool = True

    evidence_ids: list[str] = Field(default_factory=list)

    provenance: RelationshipProvenance | None = Field(
        default=None,
        description=(
            "TC-2 assertion provenance. Historical edges without this "
            "field remain legacy/unspecified and are not rewritten."
        ),
    )

    historical_validation: (
        RelationshipHistoricalValidation | None
    ) = Field(
        default=None,
        description=(
            "Independent historical outcome validation, when available."
        ),
    )

    properties: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_tc2_confidence(self) -> "Relationship":
        if self.provenance is None:
            return self

        if self.confidence is None:
            if self.confidence_semantics is not None:
                raise ValueError(
                    "confidence_semantics requires a confidence value"
                )
            return self

        if self.provenance.origin != RelationshipOrigin.INFERRED:
            raise ValueError(
                "Only inferred TC-2 relationships may carry a numeric "
                "relationship confidence"
            )

        if (
            self.confidence_semantics
            != RelationshipConfidenceSemantics.HEURISTIC_SCORE
        ):
            raise ValueError(
                "Inferred relationship confidence must be labeled as a "
                "heuristic score"
            )

        return self


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
