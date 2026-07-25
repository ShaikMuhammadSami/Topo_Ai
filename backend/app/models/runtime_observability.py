from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class RuntimeSensorStatus(str, Enum):
    ENROLLED = "enrolled"
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"


class RuntimeSourceIdentity(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    namespace: str | None = None
    pod_name: str | None = None
    pod_uid: str | None = None
    workload_name: str | None = None

    container_id: str | None = None

    binary: str | None = None
    pid: int | None = None
    exec_id: str | None = None


class RuntimeDestinationIdentity(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    name: str | None = None

    address: str = Field(
        min_length=1,
        max_length=255,
    )

    port: int = Field(
        ge=0,
        le=65535,
    )


class RuntimeDependencyObservation(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    source: RuntimeSourceIdentity

    destination: RuntimeDestinationIdentity

    protocol: str = Field(
        min_length=1,
        max_length=20,
    )

    direction: str = Field(
        default="outbound",
        max_length=20,
    )

    observation_count: int = Field(
        default=1,
        ge=1,
    )

    success_count: int = Field(
        default=0,
        ge=0,
    )

    failure_count: int = Field(
        default=0,
        ge=0,
    )

    first_seen_at: str
    last_seen_at: str

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )


class RuntimeProcessObservation(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    exec_id: str | None = None
    pid: int | None = None

    binary: str = Field(
        min_length=1,
        max_length=1000,
    )

    namespace: str | None = None
    pod_name: str | None = None
    pod_uid: str | None = None
    container_id: str | None = None

    parent_exec_id: str | None = None

    exec_count: int = Field(
        default=0,
        ge=0,
    )

    exit_count: int = Field(
        default=0,
        ge=0,
    )

    last_exit_code: int | None = None
    last_signal: str | None = None

    first_seen_at: str
    last_seen_at: str

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )


class RuntimeEventBatchRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    batch_id: str = Field(
        min_length=1,
        max_length=255,
    )

    sensor_id: str = Field(
        min_length=1,
        max_length=255,
    )

    node_name: str = Field(
        min_length=1,
        max_length=255,
    )

    cluster_name: str = Field(
        min_length=1,
        max_length=255,
    )

    source: str = Field(
        default="tetragon",
        max_length=100,
    )

    version: str = Field(
        min_length=1,
        max_length=50,
    )

    window_start: str
    window_end: str

    dependencies: list[
        RuntimeDependencyObservation
    ] = Field(
        default_factory=list,
        max_length=10000,
    )

    processes: list[
        RuntimeProcessObservation
    ] = Field(
        default_factory=list,
        max_length=10000,
    )

    processed_event_count: int = Field(
        ge=0,
    )

    dropped_event_count: int = Field(
        ge=0,
    )

    parser_error_count: int = Field(
        ge=0,
    )

    buffered_batch_count: int = Field(
        default=0,
        ge=0,
    )

    source_file: str | None = Field(
        default=None,
        max_length=1000,
    )

    source_file_offset: int = Field(
        default=0,
        ge=0,
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )


class RuntimeEventBatchReceipt(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    batch_id: str
    sensor_id: str
    agent_id: str

    accepted_at: str

    dependency_count: int
    process_count: int


class RuntimeSensorHeartbeatRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    sensor_id: str
    node_name: str
    cluster_name: str

    source: str = "tetragon"
    version: str

    heartbeat_interval_seconds: int = Field(
        default=30,
        ge=5,
        le=3600,
    )

    processed_event_count: int = Field(
        default=0,
        ge=0,
    )

    dropped_event_count: int = Field(
        default=0,
        ge=0,
    )

    parser_error_count: int = Field(
        default=0,
        ge=0,
    )

    buffered_batch_count: int = Field(
        default=0,
        ge=0,
    )

    source_file: str | None = None

    source_file_offset: int = Field(
        default=0,
        ge=0,
    )

    last_error: str | None = Field(
        default=None,
        max_length=8000,
    )

    capabilities: list[str] = Field(
        default_factory=list,
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )


class RuntimeSensorHeartbeatResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    sensor_id: str
    agent_id: str
    status: RuntimeSensorStatus
    received_at: str


class RuntimeSensorView(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    sensor_id: str
    agent_id: str

    node_name: str
    cluster_name: str

    source: str
    version: str

    status: RuntimeSensorStatus

    heartbeat_interval_seconds: int

    processed_event_count: int
    dropped_event_count: int
    parser_error_count: int
    buffered_batch_count: int
    submitted_batch_count: int

    source_file: str | None
    source_file_offset: int

    last_error: str | None

    capabilities: list[str]
    metadata: dict[str, Any]

    last_seen_at: str | None
    last_heartbeat_at: str | None
    last_batch_at: str | None

    created_at: str
    updated_at: str


class RuntimeDependencyView(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    runtime_dependency_id: str

    agent_id: str
    sensor_id: str

    cluster_name: str
    node_name: str

    source_namespace: str | None
    source_pod_name: str | None
    source_pod_uid: str | None
    source_workload_name: str | None
    source_container_id: str | None
    source_binary: str | None
    source_pid: int | None

    destination_name: str | None
    destination_address: str
    destination_port: int

    protocol: str
    direction: str

    observation_count: int
    success_count: int
    failure_count: int

    first_seen_at: str
    last_seen_at: str

    metadata: dict[str, Any]