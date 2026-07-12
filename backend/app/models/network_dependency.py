from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class NetworkIssueSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class NetworkEntityView(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    entity_id: str
    entity_type: str
    entity_kind: str
    entity_name: str

    namespace: str | None = None

    properties: dict[str, Any] = Field(
        default_factory=dict
    )


class NetworkDependencyEdge(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    relationship_id: str

    source_entity_id: str
    target_entity_id: str

    relationship_type: str

    resolved: bool

    properties: dict[str, Any] = Field(
        default_factory=dict
    )


class NetworkDependencyPath(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    entity_ids: list[str]
    relationship_types: list[str]


class NetworkDependencyIssue(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    issue_id: str
    severity: NetworkIssueSeverity
    code: str
    summary: str

    entity_id: str | None = None
    entity_name: str | None = None

    details: dict[str, Any] = Field(
        default_factory=dict
    )


class NetworkDependencyAnalysisResponse(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    snapshot_id: str

    entity_count: int
    relationship_count: int
    path_count: int
    issue_count: int

    ingress_count: int
    service_count: int
    endpoint_slice_count: int
    external_endpoint_count: int

    entities: list[
        NetworkEntityView
    ] = Field(
        default_factory=list
    )

    relationships: list[
        NetworkDependencyEdge
    ] = Field(
        default_factory=list
    )

    dependency_paths: list[
        NetworkDependencyPath
    ] = Field(
        default_factory=list
    )

    issues: list[
        NetworkDependencyIssue
    ] = Field(
        default_factory=list
    )