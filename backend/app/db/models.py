from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SnapshotRecord(Base):
    __tablename__ = "topology_snapshots"

    snapshot_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    schema_version: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    collected_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    collector_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    collector_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    cluster_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    namespace: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    entity_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    relationship_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    evidence_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    scope_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )

class IdentityResolutionRecord(Base):
    __tablename__ = "identity_resolutions"

    snapshot_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    generated_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    identity_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    unresolved_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    excluded_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )

    updated_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )


class IdentityOverrideRecord(Base):
    __tablename__ = "identity_overrides"

    __table_args__ = (
        UniqueConstraint(
            "cluster_name",
            "namespace",
            "entity_kind",
            "entity_name",
            name="uq_identity_override_target",
        ),
    )

    override_id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )

    cluster_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    namespace: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    entity_kind: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    entity_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    action: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    canonical_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )

    updated_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )    

class SignalRecord(Base):
    __tablename__ = "signals"

    signal_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    fingerprint: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    signal_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    severity: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    source_system: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    action: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    first_observed_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    last_observed_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    occurrence_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    cluster_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    namespace: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    involved_entity_id: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        index=True,
    )

    involved_object_uid: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    involved_object_kind: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    involved_object_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )

    updated_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )

class ChangeRecord(Base):
    __tablename__ = "changes"

    change_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    fingerprint: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    change_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    importance: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    source_system: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    detected_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    from_snapshot_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    to_snapshot_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    cluster_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    namespace: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    entity_id: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        index=True,
    )

    entity_kind: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    entity_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    relationship_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    relationship_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )

    updated_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )

class IncidentAnalysisRecord(Base):
    __tablename__ = "incident_analyses"

    analysis_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    signal_id: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )

    topology_snapshot_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    algorithm_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    generated_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    incident_title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    cluster_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    namespace: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    candidate_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    hypothesis_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    top_hypothesis_title: Mapped[
        str | None
    ] = mapped_column(
        String(500),
        nullable=True,
    )

    top_hypothesis_score: Mapped[
        str | None
    ] = mapped_column(
        String(30),
        nullable=True,
    )

    payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )

    updated_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )

class RecommendationRecord(Base):
    __tablename__ = (
        "remediation_recommendations"
    )

    recommendation_id: Mapped[
        str
    ] = mapped_column(
        String(255),
        primary_key=True,
    )

    analysis_id: Mapped[str] = (
        mapped_column(
            String(255),
            nullable=False,
            index=True,
        )
    )

    hypothesis_id: Mapped[str] = (
        mapped_column(
            String(255),
            nullable=False,
            index=True,
        )
    )

    signal_id: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )

    change_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    algorithm_version: Mapped[
        str
    ] = mapped_column(
        String(50),
        nullable=False,
    )

    generated_at: Mapped[str] = (
        mapped_column(
            String(50),
            nullable=False,
            index=True,
        )
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    action_type: Mapped[str] = (
        mapped_column(
            String(100),
            nullable=False,
            index=True,
        )
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    confidence: Mapped[str] = (
        mapped_column(
            String(30),
            nullable=False,
        )
    )

    risk: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    cluster_name: Mapped[str] = (
        mapped_column(
            String(255),
            nullable=False,
            index=True,
        )
    )

    namespace: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    target_entity_id: Mapped[
        str | None
    ] = mapped_column(
        String(500),
        nullable=True,
        index=True,
    )

    target_entity_kind: Mapped[
        str | None
    ] = mapped_column(
        String(100),
        nullable=True,
    )

    target_entity_name: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
    )

    applied_at: Mapped[
        str | None
    ] = mapped_column(
        String(50),
        nullable=True,
    )

    payload_json: Mapped[str] = (
        mapped_column(
            Text,
            nullable=False,
        )
    )

    created_at: Mapped[str] = (
        mapped_column(
            String(50),
            nullable=False,
            default=utc_now_iso,
        )
    )

    updated_at: Mapped[str] = (
        mapped_column(
            String(50),
            nullable=False,
            default=utc_now_iso,
        )
    )

class RecoveryVerificationRecord(Base):
    __tablename__ = (
        "recovery_verifications"
    )

    verification_id: Mapped[
        str
    ] = mapped_column(
        String(255),
        primary_key=True,
    )

    recommendation_id: Mapped[
        str
    ] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    analysis_id: Mapped[str] = (
        mapped_column(
            String(255),
            nullable=False,
            index=True,
        )
    )

    signal_id: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )

    pre_snapshot_id: Mapped[
        str
    ] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    post_snapshot_id: Mapped[
        str
    ] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    algorithm_version: Mapped[
        str
    ] = mapped_column(
        String(100),
        nullable=False,
    )

    generated_at: Mapped[str] = (
        mapped_column(
            String(50),
            nullable=False,
            index=True,
        )
    )

    applied_at: Mapped[str] = (
        mapped_column(
            String(50),
            nullable=False,
        )
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    confidence: Mapped[str] = (
        mapped_column(
            String(30),
            nullable=False,
        )
    )

    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    cluster_name: Mapped[str] = (
        mapped_column(
            String(255),
            nullable=False,
            index=True,
        )
    )

    namespace: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    target_entity_id: Mapped[
        str | None
    ] = mapped_column(
        String(500),
        nullable=True,
        index=True,
    )

    target_entity_kind: Mapped[
        str | None
    ] = mapped_column(
        String(100),
        nullable=True,
    )

    target_entity_name: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
    )

    passed_count: Mapped[int] = (
        mapped_column(
            Integer,
            nullable=False,
        )
    )

    failed_count: Mapped[int] = (
        mapped_column(
            Integer,
            nullable=False,
        )
    )

    unknown_count: Mapped[int] = (
        mapped_column(
            Integer,
            nullable=False,
        )
    )

    payload_json: Mapped[str] = (
        mapped_column(
            Text,
            nullable=False,
        )
    )

    created_at: Mapped[str] = (
        mapped_column(
            String(50),
            nullable=False,
            default=utc_now_iso,
        )
    )

    updated_at: Mapped[str] = (
        mapped_column(
            String(50),
            nullable=False,
            default=utc_now_iso,
        )
    )

class IncidentRecord(Base):
    __tablename__ = "incidents"

    incident_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    fingerprint: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    severity: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    cluster_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    namespace: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    primary_signal_id: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )

    latest_signal_id: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        index=True,
    )

    topology_snapshot_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    affected_entity_id: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        index=True,
    )

    affected_object_kind: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    affected_object_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    first_observed_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    last_observed_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    latest_analysis_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    top_hypothesis_title: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    top_hypothesis_score: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    recommendation_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    latest_recommendation_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    recovery_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    latest_recovery_verification_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    occurrence_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    status_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )

    updated_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )

class OwnershipMappingRecord(Base):
    __tablename__ = "ownership_mappings"

    ownership_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    fingerprint: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
    )

    # Highest-priority exact match.
    entity_id: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        index=True,
    )

    # Stable service/workload identity.
    service_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    cluster_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    namespace: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    entity_kind: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    entity_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    environment: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    owner_team: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    owner_email: Mapped[str | None] = mapped_column(
        String(320),
        nullable=True,
    )

    oncall_contact: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    repository_url: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    business_capability: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    criticality: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="tier_3",
        index=True,
    )

    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="manual",
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )

    updated_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )

class WebhookEndpointRecord(Base):
    __tablename__ = "webhook_endpoints"

    webhook_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    url: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
    )

    event_types_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    headers_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )

    # Development implementation.
    # Move this to encrypted storage or a secret
    # manager before production use.
    signing_secret: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    timeout_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
    )

    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
    )

    created_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )

    updated_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )


class WebhookDeliveryRecord(Base):
    __tablename__ = "webhook_deliveries"

    __table_args__ = (
        UniqueConstraint(
            "webhook_id",
            "event_id",
            name="uq_webhook_delivery_event",
        ),
    )

    delivery_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    webhook_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    event_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    resource_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    resource_id: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    response_status: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    response_body: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    requested_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    completed_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )

    updated_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )