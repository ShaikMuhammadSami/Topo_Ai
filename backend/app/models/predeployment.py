from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class PlannedChangeType(str, Enum):
    CONTAINER_IMAGE_UPDATE = (
        "container_image_update"
    )

    CONFIGURATION_CHANGE = (
        "configuration_change"
    )

    RESOURCE_LIMIT_CHANGE = (
        "resource_limit_change"
    )

    REPLICA_CHANGE = "replica_change"

    NETWORK_POLICY_CHANGE = (
        "network_policy_change"
    )

    SERVICE_ROUTING_CHANGE = (
        "service_routing_change"
    )

    SECRET_OR_CERTIFICATE_CHANGE = (
        "secret_or_certificate_change"
    )

    DATABASE_SCHEMA_CHANGE = (
        "database_schema_change"
    )

    OTHER = "other"


class ChangeRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DeploymentDecision(str, Enum):
    ALLOW = "allow"

    REVIEW_REQUIRED = (
        "review_required"
    )

    APPROVAL_REQUIRED = (
        "approval_required"
    )

    BLOCK_UNTIL_MITIGATED = (
        "block_until_mitigated"
    )


class PreDeploymentImpactRequest(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    snapshot_id: str = Field(
        min_length=3
    )

    entity_id: str = Field(
        min_length=3
    )

    change_type: PlannedChangeType

    change_summary: str = Field(
        min_length=3,
        max_length=2000,
    )

    max_depth: int = Field(
        default=5,
        ge=1,
        le=10,
    )

    metadata: dict[
        str,
        Any,
    ] = Field(
        default_factory=dict
    )


class PreDeploymentAffectedEntity(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    entity_id: str
    entity_kind: str
    entity_name: str

    namespace: str | None = None

    distance: int = Field(
        ge=0
    )

    impact: str

    impact_score: float = Field(
        ge=0.0,
        le=1.0,
    )

    relationship: str | None = None

    risk_score: float = Field(
        ge=0.0,
        le=1.0,
    )

    risk_reasons: list[str] = Field(
        default_factory=list
    )


class PreDeploymentDependencyPath(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    path: list[str]


class PreDeploymentImpactResponse(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    analysis_id: str
    algorithm_version: str
    generated_at: datetime

    snapshot_id: str

    root_entity_id: str
    root_entity_kind: str
    root_entity_name: str

    change_type: PlannedChangeType
    change_summary: str

    risk_score: float = Field(
        ge=0.0,
        le=1.0,
    )

    risk_level: ChangeRiskLevel
    deployment_decision: DeploymentDecision

    recommendation: str

    affected_entity_count: int
    downstream_entity_count: int

    direct_impact_count: int
    dependent_impact_count: int
    indirect_impact_count: int
    potential_impact_count: int

    high_risk_entity_count: int

    affected_entities: list[
        PreDeploymentAffectedEntity
    ] = Field(
        default_factory=list
    )

    dependency_paths: list[
        PreDeploymentDependencyPath
    ] = Field(
        default_factory=list
    )

    risk_factors: list[str] = Field(
        default_factory=list
    )

    warnings: list[str] = Field(
        default_factory=list
    )