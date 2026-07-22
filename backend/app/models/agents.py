from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class AgentStatus(str, Enum):
    ENROLLED = "enrolled"
    ONLINE = "online"
    OFFLINE = "offline"
    REVOKED = "revoked"


class AgentEnrollmentTokenCreateRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    label: str | None = Field(
        default=None,
        max_length=255,
    )

    expires_in_minutes: int = Field(
        default=30,
        ge=1,
        le=10080,
    )

    max_uses: int = Field(
        default=1,
        ge=1,
        le=100,
    )


class AgentEnrollmentTokenResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    enrollment_token_id: str
    enrollment_token: str
    token_hint: str
    label: str | None
    max_uses: int
    expires_at: str
    created_at: str


class AgentConfigView(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    collection_interval_seconds: int
    heartbeat_interval_seconds: int
    namespace_scope: list[str]


class AgentEnrollRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    enrollment_token: str = Field(
        min_length=16,
        max_length=1000,
    )

    name: str = Field(
        min_length=1,
        max_length=255,
    )

    agent_type: str = Field(
        default="kubernetes",
        min_length=1,
        max_length=100,
    )

    cluster_name: str = Field(
        min_length=1,
        max_length=255,
    )

    environment: str | None = Field(
        default=None,
        max_length=100,
    )

    version: str = Field(
        min_length=1,
        max_length=50,
    )

    collection_interval_seconds: int = Field(
        default=300,
        ge=30,
        le=86400,
    )

    heartbeat_interval_seconds: int = Field(
        default=30,
        ge=10,
        le=3600,
    )

    namespace_scope: list[str] = Field(
        default_factory=list,
        max_length=500,
    )

    capabilities: list[str] = Field(
        default_factory=list,
        max_length=100,
    )

    labels: dict[str, str] = Field(
        default_factory=dict,
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )


class AgentEnrollResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    agent_id: str
    agent_token: str
    enrolled_at: str
    config: AgentConfigView


class AgentHeartbeatRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    version: str | None = Field(
        default=None,
        max_length=50,
    )

    buffered_item_count: int = Field(
        default=0,
        ge=0,
    )

    last_collection_status: str | None = Field(
        default=None,
        max_length=50,
    )

    last_error: str | None = Field(
        default=None,
        max_length=8000,
    )

    capabilities: list[str] = Field(
        default_factory=list,
        max_length=100,
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )


class AgentHeartbeatResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    agent_id: str
    status: AgentStatus
    received_at: str
    config: AgentConfigView


class AgentSnapshotSubmission(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    submission_id: str = Field(
        min_length=1,
        max_length=255,
    )

    collected_at: str

    cluster_name: str = Field(
        min_length=1,
        max_length=255,
    )

    environment: str | None = Field(
        default=None,
        max_length=100,
    )

    namespace_scope: list[str] = Field(
        default_factory=list,
    )

    collector_version: str = Field(
        min_length=1,
        max_length=50,
    )

    inventory: dict[
        str,
        list[dict[str, Any]],
    ]

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )


class AgentSnapshotReceipt(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    agent_id: str
    submission_id: str
    snapshot_id: str
    accepted_at: str
    entity_count: int
    relationship_count: int


class AgentSummary(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    agent_id: str
    name: str
    agent_type: str

    cluster_name: str
    environment: str | None

    version: str
    status: AgentStatus

    collection_interval_seconds: int
    heartbeat_interval_seconds: int

    namespace_scope: list[str]

    buffered_item_count: int

    last_collection_status: str | None
    last_error: str | None

    last_seen_at: str | None
    last_heartbeat_at: str | None
    last_snapshot_at: str | None

    enrolled_at: str
    revoked_at: str | None

    created_at: str
    updated_at: str


class AgentDetail(AgentSummary):
    capabilities: list[str]
    labels: dict[str, str]
    metadata: dict[str, Any]


class AgentHealthResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    agent_id: str
    status: AgentStatus
    last_heartbeat_at: str | None
    last_snapshot_at: str | None
    buffered_item_count: int
    last_collection_status: str | None
    last_error: str | None
    heartbeat_interval_seconds: int