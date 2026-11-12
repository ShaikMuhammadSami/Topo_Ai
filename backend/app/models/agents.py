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
    enrollment_token: str = Field(repr=False)
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
        repr=False,
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
    agent_token: str = Field(repr=False)
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


def agent_snapshot_completeness_error(
    submission: AgentSnapshotSubmission,
) -> str | None:
    """Validate the declared collection-integrity contract.

    Older agents did not declare plugin completeness, so an entirely absent
    contract remains a supported legacy submission. Once any completeness
    field is declared, the collection must be successful and every enabled
    plugin must be successful (or explicitly optional and skipped). Declared
    partial or failed data is never topology evidence.
    """

    metadata = submission.metadata
    contract_keys = {
        "collection_status",
        "plugin_count",
        "successful_plugin_count",
        "failed_plugin_count",
        "plugins",
    }
    if not contract_keys.intersection(metadata):
        return None

    if metadata.get("collection_status") != "success":
        return (
            "Incomplete topology collections are not accepted."
        )

    plugins = metadata.get("plugins")
    plugin_contract_keys = {
        "plugin_count",
        "successful_plugin_count",
        "failed_plugin_count",
        "plugins",
    }
    if (
        plugins is None
        and not plugin_contract_keys.intersection(
            metadata
        )
    ):
        return None

    if not isinstance(plugins, list):
        return "Plugin completeness metadata is required."
    if not plugins:
        return "At least one completed plugin is required."

    allowed_statuses = {
        "success",
        "skipped_optional",
    }
    for plugin in plugins:
        if not isinstance(plugin, dict):
            return "Plugin completeness metadata is invalid."

        if plugin.get("status") not in allowed_statuses:
            return (
                "Incomplete plugin collections are not accepted."
            )

        errors = plugin.get("errors")
        if isinstance(errors, list) and errors:
            return (
                "Plugin collection errors are not accepted."
            )

        failures = plugin.get("collection_failures")
        if isinstance(failures, list) and failures:
            return (
                "Required resource collection failures are not accepted."
            )

        resource_completeness = plugin.get(
            "resource_completeness"
        )
        if (
            isinstance(resource_completeness, dict)
            and any(
                value not in {
                    "complete",
                    "skipped_optional",
                }
                for value in (
                    resource_completeness.values()
                )
            )
        ):
            return (
                "Incomplete required resource collections are not accepted."
            )

    declared_count = metadata.get("plugin_count")
    if (
        not isinstance(declared_count, int)
        or declared_count != len(plugins)
    ):
        return "Plugin completeness metadata is inconsistent."

    failed_count = metadata.get("failed_plugin_count")
    if failed_count != 0:
        return "Incomplete plugin collections are not accepted."

    successful_count = metadata.get(
        "successful_plugin_count"
    )
    if (
        successful_count != len(plugins)
    ):
        return "Plugin completeness metadata is inconsistent."

    return None


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

    checkpoint_created: bool = True
    checkpoint_reused: bool = False
    checkpoint_reason: str = (
        "periodic_reconcile"
    )
    state_digest: str | None = None
    detected_change_count: int = 0
    failure_signal_count: int = 0
    incident_created_count: int = 0
    incident_correlated_count: int = 0
    automatic_analysis_states: list[str] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(
        default_factory=list
    )


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

class AgentPluginStatusView(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    name: str
    status: str

    duration_ms: float | None = None

    capabilities: list[str] = Field(
        default_factory=list
    )

    errors: list[str] = Field(
        default_factory=list
    )

    inventory_counts: dict[
        str,
        int,
    ] = Field(
        default_factory=dict
    )


class AgentPluginsResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    agent_id: str

    enabled_plugins: list[str]

    plugins: list[
        AgentPluginStatusView
    ]

    updated_at: str
