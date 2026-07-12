from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


class ServiceCriticality(str, Enum):
    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"
    TIER_4 = "tier_4"


class OwnershipSource(str, Enum):
    MANUAL = "manual"
    IMPORTED = "imported"
    ENTITY_METADATA = "entity_metadata"
    UNRESOLVED = "unresolved"


class BusinessImpactLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class OwnershipMappingCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    entity_id: str | None = None
    service_name: str | None = None

    cluster_name: str | None = None
    namespace: str | None = None

    entity_kind: str | None = None
    entity_name: str | None = None

    environment: str | None = None

    owner_team: str = Field(
        min_length=1,
        max_length=255,
    )

    owner_email: str | None = Field(
        default=None,
        max_length=320,
    )

    oncall_contact: str | None = Field(
        default=None,
        max_length=500,
    )

    repository_url: str | None = Field(
        default=None,
        max_length=1000,
    )

    business_capability: str | None = Field(
        default=None,
        max_length=255,
    )

    criticality: ServiceCriticality = (
        ServiceCriticality.TIER_3
    )

    source: OwnershipSource = (
        OwnershipSource.MANUAL
    )

    notes: str | None = Field(
        default=None,
        max_length=4000,
    )

    @model_validator(mode="after")
    def validate_selector(
        self,
    ) -> "OwnershipMappingCreate":
        has_exact_entity = bool(
            self.entity_id
        )

        has_service_selector = bool(
            self.service_name
        )

        has_object_selector = bool(
            self.entity_kind
            and self.entity_name
        )

        if not (
            has_exact_entity
            or has_service_selector
            or has_object_selector
        ):
            raise ValueError(
                "Provide entity_id, service_name, "
                "or both entity_kind and entity_name."
            )

        return self


class OwnershipMappingView(BaseModel):
    ownership_id: str

    entity_id: str | None
    service_name: str | None

    cluster_name: str | None
    namespace: str | None

    entity_kind: str | None
    entity_name: str | None

    environment: str | None

    owner_team: str
    owner_email: str | None
    oncall_contact: str | None

    repository_url: str | None
    business_capability: str | None

    criticality: ServiceCriticality
    source: OwnershipSource

    active: bool
    notes: str | None

    created_at: str
    updated_at: str


class EntityOwnershipResolution(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    resolved: bool

    entity_id: str
    entity_kind: str
    entity_name: str

    service_name: str | None = None

    cluster_name: str | None = None
    namespace: str | None = None

    owner_team: str | None = None
    owner_email: str | None = None
    oncall_contact: str | None = None

    repository_url: str | None = None
    business_capability: str | None = None

    criticality: ServiceCriticality | None = None

    source: OwnershipSource

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    matched_ownership_id: str | None = None
    resolution_reason: str


class AffectedEntityOwnership(BaseModel):
    entity_id: str
    entity_kind: str
    entity_name: str

    impact: str
    distance: int
    impact_score: float

    ownership: EntityOwnershipResolution


class IncidentOwnershipImpact(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    incident_id: str

    business_impact_level: BusinessImpactLevel

    affected_entity_count: int
    resolved_entity_count: int
    unresolved_entity_count: int

    affected_team_count: int
    affected_capability_count: int

    highest_criticality: ServiceCriticality | None

    owner_teams: list[str] = Field(
        default_factory=list
    )

    business_capabilities: list[str] = Field(
        default_factory=list
    )

    oncall_contacts: list[str] = Field(
        default_factory=list
    )

    repositories: list[str] = Field(
        default_factory=list
    )

    routing_recommendation: str

    affected_entities: list[
        AffectedEntityOwnership
    ] = Field(
        default_factory=list
    )

    warnings: list[str] = Field(
        default_factory=list
    )