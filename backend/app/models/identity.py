from datetime import datetime
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)




class IdentityMatchMethod(str, Enum):
    LABEL_EXACT = "label_exact"
    OWNER_REFERENCE = "owner_reference"
    SERVICE_SELECTOR = "service_selector"
    IMAGE_REFERENCE = "image_reference"
    NAME_HEURISTIC = "name_heuristic"
    MANUAL_OVERRIDE = "manual_override"


class IdentityOverrideAction(str, Enum):
    ASSIGN = "assign"
    EXCLUDE = "exclude"


class IdentityRole(str, Enum):
    DEPLOYMENT = "deployment"
    REPLICA_SET = "replica_set"
    POD = "pod"
    SERVICE = "service"


class IdentityMember(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    kind: str
    name: str
    role: IdentityRole

    match_method: IdentityMatchMethod

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    evidence: list[str] = Field(
        default_factory=list
    )


class LogicalIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity_id: str
    canonical_name: str

    cluster: str | None = None
    namespace: str | None = None
    environment: str | None = None

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    members: list[IdentityMember] = Field(
        default_factory=list
    )

    image_references: list[str] = Field(
        default_factory=list
    )

    aliases: list[str] = Field(
        default_factory=list
    )

    warnings: list[str] = Field(
        default_factory=list
    )


class IdentityResolutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    generated_at: datetime

    identities: list[LogicalIdentity] = Field(
        default_factory=list
    )

    unresolved_entity_ids: list[str] = Field(
        default_factory=list
    )

    excluded_entity_ids: list[str] = Field(
        default_factory=list
    )

    warnings: list[str] = Field(
        default_factory=list
    )


class IdentityOverrideCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_name: str = Field(min_length=1)
    namespace: str = Field(min_length=1)

    entity_kind: str = Field(min_length=1)
    entity_name: str = Field(min_length=1)

    action: IdentityOverrideAction

    canonical_name: str | None = None

    reason: str = Field(
        min_length=3,
        max_length=1000,
    )

    @model_validator(mode="after")
    def validate_override(
        self,
    ) -> "IdentityOverrideCreate":
        if (
            self.action
            == IdentityOverrideAction.ASSIGN
            and not self.canonical_name
        ):
            raise ValueError(
                "canonical_name is required "
                "for an assign override."
            )

        return self


class IdentityOverrideView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    override_id: str

    cluster_name: str
    namespace: str

    entity_kind: str
    entity_name: str

    action: IdentityOverrideAction

    canonical_name: str | None
    reason: str

    active: bool

    created_at: datetime
    updated_at: datetime


class IdentityResolutionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    generated_at: datetime

    identity_count: int
    unresolved_count: int
    excluded_count: int