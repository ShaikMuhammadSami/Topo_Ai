from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.models.temporal import TemporalMetadata


class ChangeEventSource(str, Enum):
    TOPOLOGY_DIFF = "topology_diff"

    GIT = "git"
    GITHUB = "github"
    GITLAB = "gitlab"

    CI = "ci"
    CD = "cd"

    GITHUB_ACTIONS = "github_actions"
    JENKINS = "jenkins"
    AZURE_DEVOPS = "azure_devops"

    TERRAFORM = "terraform"
    KUBERNETES = "kubernetes"

    AWS_CLOUDTRAIL = "aws_cloudtrail"
    AZURE_ACTIVITY_LOG = "azure_activity_log"
    GCP_AUDIT_LOG = "gcp_audit_log"

    MANUAL = "manual"
    UNKNOWN = "unknown"


class ChangeEventKind(str, Enum):
    CODE = "code"
    PULL_REQUEST = "pull_request"

    PIPELINE = "pipeline"
    DEPLOYMENT = "deployment"
    ROLLOUT = "rollout"

    CONFIGURATION = "configuration"
    INFRASTRUCTURE = "infrastructure"
    SCALING = "scaling"

    SECURITY = "security"
    DATABASE = "database"

    TOPOLOGY = "topology"

    UNKNOWN = "unknown"


class ChangeEventRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ChangeEntityLinkType(str, Enum):
    EXPLICIT = "explicit"
    AUTOMATIC = "automatic"
    DERIVED = "derived"


class ChangeEventEntityReference(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    entity_id: str | None = None

    external_id: str | None = None

    provider_resource_id: str | None = None

    kind: str | None = None

    name: str | None = None

    namespace: str | None = None

    cluster_name: str | None = None


class ChangeEventCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    source: ChangeEventSource

    kind: ChangeEventKind = (
        ChangeEventKind.UNKNOWN
    )

    external_id: str | None = None

    # If this event originated from your
    # existing NormalizedChange/ChangeRecord.
    origin_change_id: str | None = None

    title: str = Field(
        min_length=1,
        max_length=1000,
    )

    summary: str | None = None

    actor: str | None = None

    occurred_at: str

    environment: str | None = None

    provider: str | None = None
    account_id: str | None = None
    region: str | None = None

    cluster_name: str | None = None
    namespace: str | None = None

    repository: str | None = None
    commit_sha: str | None = None

    pipeline_name: str | None = None
    release_version: str | None = None

    terraform_workspace: str | None = None

    risk_score: int | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    status: str = "observed"

    entity_refs: list[
        ChangeEventEntityReference
    ] = Field(
        default_factory=list
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )

    raw_payload: dict[str, Any] = Field(
        default_factory=dict
    )


class ChangeEventReceipt(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    event_id: str

    created: bool
    duplicate: bool

    risk_score: int

    risk_level: ChangeEventRiskLevel

    linked_entity_count: int


class ChangeEntityLinkView(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    link_id: str

    event_id: str

    entity_id: str

    link_type: ChangeEntityLinkType

    confidence: float

    reason: str | None = None

    snapshot_id: str | None = None

    created_at: str
    updated_at: str


class ChangeEventView(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    event_id: str

    event_fingerprint: str

    source: ChangeEventSource
    kind: ChangeEventKind

    external_id: str | None

    origin_change_id: str | None

    title: str

    summary: str | None
    actor: str | None

    occurred_at: str
    received_at: str

    temporal: TemporalMetadata | None = None

    environment: str | None

    provider: str | None
    account_id: str | None
    region: str | None

    cluster_name: str | None
    namespace: str | None

    repository: str | None
    commit_sha: str | None

    pipeline_name: str | None
    release_version: str | None

    terraform_workspace: str | None

    risk_score: int

    risk_level: ChangeEventRiskLevel

    status: str

    observation_count: int

    metadata: dict[str, Any]

    raw_payload: dict[str, Any]

    agent_id: str | None

    links: list[
        ChangeEntityLinkView
    ] = Field(
        default_factory=list
    )

    created_at: str
    updated_at: str


class ChangeCorrelationRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    snapshot_id: str | None = None


class ChangeCorrelationResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    event_id: str

    snapshot_id: str | None

    linked_entity_count: int

    links: list[
        ChangeEntityLinkView
    ]


class IncidentChangeCandidate(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    event: ChangeEventView

    score: float

    reasons: list[str] = Field(
        default_factory=list
    )

    direct_entity_matches: list[str] = (
        Field(default_factory=list)
    )

    neighboring_entity_matches: list[str] = (
        Field(default_factory=list)
    )

    minutes_before_incident: (
        float | None
    ) = None


class IncidentChangeAnalysisResponse(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    incident_id: str

    incident_time: str

    lookback_minutes: int
    after_minutes: int

    affected_entity_ids: list[str]

    candidate_count: int

    candidates: list[
        IncidentChangeCandidate
    ]

class AgentChangeEventBatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    events: list[
        ChangeEventCreate
    ] = Field(
        min_length=1,
        max_length=500,
    )


class AgentChangeEventBatchReceipt(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    received_count: int

    event_ids: list[str] = Field(
        default_factory=list
    )

    topology_affecting_count: int = 0
    checkpoint_requested: bool = False
    checkpoint_reason: str | None = None
