from __future__ import annotations

from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.models.topology import (
    Entity,
    Relationship,
)


class CloudAccountView(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    cloud_account_id: str

    provider: str
    account_number: str
    display_name: str

    principal_arn: str | None

    metadata: dict[str, Any]

    last_seen_at: str
    created_at: str
    updated_at: str


class CloudResourceView(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    cloud_resource_id: str

    provider: str
    account_id: str
    region: str

    resource_type: str
    resource_id: str

    arn: str | None
    name: str
    status: str | None

    vpc_id: str | None
    subnet_ids: list[str]

    tags: dict[str, str]

    properties: dict[str, Any]

    observed_at: str
    agent_id: str


class CloudTopologyResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    snapshot_id: str | None

    provider: str
    account_id: str | None
    region: str | None

    entities: list[Entity] = Field(
        default_factory=list
    )

    relationships: list[
        Relationship
    ] = Field(
        default_factory=list
    )


class AgentCloudStatusResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    agent_id: str

    enabled: bool
    provider: str

    status: str

    account_id: str | None

    account_ids: list[str] = Field(
        default_factory=list
    )

    regions: list[str] = Field(
        default_factory=list
    )

    resource_count: int

    errors: list[str] = Field(
        default_factory=list
    )

    last_heartbeat_at: str | None

    updated_at: str