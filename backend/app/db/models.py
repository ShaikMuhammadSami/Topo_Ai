from datetime import datetime, timezone

from sqlalchemy import (
    Float,
    Boolean,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    PrimaryKeyConstraint,
    CheckConstraint,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.db.database import Base
from app.db.domain_ownership import REQUIRED_OWNERSHIP_TABLES
from app.db.tenant_identity import TENANT_LOCAL_PRIMARY_KEYS
from app.db.secret_types import SecretBinary


class SecretRecord(Base):
    """Custody metadata only; intentionally outside the frozen domain mixin."""

    __tablename__ = "secret_records"
    __table_args__ = (
        UniqueConstraint("scope_kind", "scope_id", "owner_type", "owner_id", "purpose", name="uq_secret_records_binding"),
        CheckConstraint("(scope_kind = 'tenant' AND tenant_id IS NOT NULL AND scope_id = tenant_id) OR (scope_kind = 'installation' AND tenant_id IS NULL)", name="ck_secret_records_scope"),
        CheckConstraint("status IN ('active', 'revoked') AND active_version >= 1 AND row_version >= 1", name="ck_secret_records_state"),
        CheckConstraint("(previous_version IS NULL AND previous_accept_until IS NULL) OR (previous_version IS NOT NULL AND previous_accept_until IS NOT NULL AND previous_version >= 1 AND previous_version < active_version)", name="ck_secret_records_previous"),
    )
    secret_ref: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_type: Mapped[str] = mapped_column(String(40), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    active_version: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_accept_until: Mapped[str | None] = mapped_column(String(50), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(String(50), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(50), nullable=False)
    created_by_subject: Mapped[str] = mapped_column(String(500), nullable=False)
    updated_by_subject: Mapped[str] = mapped_column(String(500), nullable=False)
    revoked_at: Mapped[str | None] = mapped_column(String(50), nullable=True)

    def __repr__(self):
        return "SecretRecord(<metadata>)"


class SecretVersionRecord(Base):
    __tablename__ = "secret_versions"
    __table_args__ = (
        UniqueConstraint("secret_ref", "operation_id", name="uq_secret_versions_operation"),
        CheckConstraint("version >= 1 AND envelope_revision >= 1 AND overlap_seconds >= 0 AND overlap_seconds <= 86400", name="ck_secret_versions_state"),
    )
    secret_ref: Mapped[str] = mapped_column(String(64), ForeignKey("secret_records.secret_ref", name="fk_secret_versions_record"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(20), nullable=False)
    envelope_version: Mapped[int] = mapped_column(Integer, nullable=False)
    nonce: Mapped[bytes] = mapped_column(SecretBinary(12), nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(SecretBinary(), nullable=False)
    operation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    operation_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    overlap_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    envelope_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(String(50), nullable=False)
    created_by_subject: Mapped[str] = mapped_column(String(500), nullable=False)
    rewrapped_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rewrapped_by_subject: Mapped[str | None] = mapped_column(String(500), nullable=True)

    def __repr__(self):
        return "SecretVersionRecord(<protected>)"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TenantOwnedRecordMixin:
    """Server-authoritative ownership, required for every customer-owned row."""

    @declared_attr
    def tenant_id(cls) -> Mapped[str]:
        return mapped_column(
            String(255),
            nullable=cls.__tablename__ not in REQUIRED_OWNERSHIP_TABLES,
            primary_key=cls.__tablename__ in TENANT_LOCAL_PRIMARY_KEYS,
            index=True,
        )


class SnapshotRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "topology_snapshots"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "snapshot_id", name="pk_topology_snapshots"),
    )

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


class IdentityResolutionRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "identity_resolutions"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "snapshot_id", name="pk_identity_resolutions"),
    )

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


class IdentityOverrideRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "identity_overrides"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "cluster_name",
            "namespace",
            "entity_kind",
            "entity_name",
            name="uq_tenant_identity_override_target",
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


class SignalRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "signals"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "signal_id", name="pk_signals"),
    )

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


class ChangeRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "changes"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "change_id", name="pk_changes"),
    )

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


class IncidentAnalysisRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "incident_analyses"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "analysis_id", name="pk_incident_analyses"),
    )

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


class RecommendationRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = (
        "remediation_recommendations"
    )

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "recommendation_id", name="pk_remediation_recommendations"),
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


class RecoveryVerificationRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = (
        "recovery_verifications"
    )

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "verification_id", name="pk_recovery_verifications"),
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


class IncidentRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "incidents"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "incident_id", name="pk_incidents"),
    )

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


class IncidentOutcomeRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "incident_outcomes"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "outcome_id", name="pk_incident_outcomes"),
        Index(
            "ix_tenant_incident_outcomes_incident_id",
            "tenant_id",
            "incident_id",
            unique=True,
        ),
    )

    outcome_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    incident_id: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    causal_analysis_id: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    response_plan_reference: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    rca_verdict: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    mitigated_at: Mapped[
        str | None
    ] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    resolved_at: Mapped[
        str | None
    ] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    source_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
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


class OwnershipMappingRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "ownership_mappings"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "ownership_id", name="pk_ownership_mappings"),
        Index(
            "ix_tenant_ownership_mappings_fingerprint",
            "tenant_id",
            "fingerprint",
            unique=True,
        ),
    )

    ownership_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    fingerprint: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
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


class WebhookEndpointRecord(TenantOwnedRecordMixin, Base):
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


class WebhookDeliveryRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "webhook_deliveries"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "delivery_id", name="pk_webhook_deliveries"),
        UniqueConstraint(
            "tenant_id",
            "webhook_id",
            "event_id",
            name="uq_tenant_webhook_delivery_event",
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


class IncidentExplanationRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "incident_explanations"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "explanation_id", name="pk_incident_explanations"),
    )

    explanation_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    incident_id: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )

    topology_snapshot_id: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        index=True,
    )

    analysis_id: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        index=True,
    )

    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    model_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    prompt_version: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    grounding_hash: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    confidence: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    generated_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    evidence_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    warnings_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
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


class CopilotSessionRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "incident_copilot_sessions"

    session_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    incident_id: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    model_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="active",
        index=True,
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


class CopilotMessageRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "incident_copilot_messages"

    message_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    session_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    incident_id: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )

    role: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    provider: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    answer_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    confidence: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    evidence_ids_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )

    evidence_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )

    suggested_questions_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )

    warning: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )


class InvestigationPlanRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "incident_investigation_plans"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "plan_id", name="pk_incident_investigation_plans"),
    )

    plan_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    incident_id: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    objective: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    incident_summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    model_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    prompt_version: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    grounding_hash: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="active",
        index=True,
    )

    overall_confidence: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    evidence_gaps_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )

    warnings_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )

    evidence_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
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


class InvestigationStepRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "incident_investigation_steps"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "step_id", name="pk_incident_investigation_steps"),
        UniqueConstraint(
            "tenant_id",
            "plan_id",
            "sequence",
            name="uq_tenant_investigation_plan_sequence",
        ),
    )

    step_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    plan_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    incident_id: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )

    sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    objective: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    command_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    command: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    target: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )

    expected_observation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    success_criteria: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    failure_indication: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    evidence_ids_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        index=True,
    )

    finding: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    responder_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    completed_at: Mapped[str | None] = mapped_column(
        String(50),
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


class PostIncidentReportRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "post_incident_reports"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "report_id", name="pk_post_incident_reports"),
        UniqueConstraint(
            "tenant_id",
            "incident_id",
            "version",
            name="uq_tenant_post_incident_report_version",
        ),
    )

    report_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    incident_id: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="draft",
        index=True,
    )

    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    model_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    prompt_version: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    grounding_hash: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    overall_confidence: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    evidence_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    warnings_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )

    reviewer_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    review_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    reviewed_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    approved_at: Mapped[str | None] = mapped_column(
        String(50),
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


class ReportActionItemRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "post_incident_report_actions"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "action_item_id", name="pk_post_incident_report_actions"),
        UniqueConstraint(
            "tenant_id",
            "report_id",
            "sequence",
            name="uq_tenant_post_incident_report_action_sequence",
        ),
    )

    action_item_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    report_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    incident_id: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )

    sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    owner_team: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    owner_contact: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    priority: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    due_date: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    success_criteria: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    evidence_ids_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="open",
        index=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    completed_at: Mapped[str | None] = mapped_column(
        String(50),
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


class AgentEnrollmentTokenRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "agent_enrollment_tokens"

    enrollment_token_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )

    token_hint: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    label: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    max_uses: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    use_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    expires_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    last_used_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    revoked_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    created_by: Mapped[str | None] = mapped_column(
        String(255),
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


class TopoAgentRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "topo_agents"

    agent_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    agent_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="kubernetes",
        index=True,
    )

    cluster_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    environment: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )

    token_hint: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="enrolled",
        index=True,
    )

    collection_interval_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=300,
    )

    heartbeat_interval_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30,
    )

    namespace_scope_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )

    capabilities_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )

    labels_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )

    metadata_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )

    buffered_item_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    last_collection_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    last_seen_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    last_heartbeat_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    last_snapshot_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    enrolled_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )

    revoked_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
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


class RuntimeSensorRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "runtime_sensors"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "sensor_id", name="pk_runtime_sensors"),
        UniqueConstraint(
            "tenant_id",
            "agent_id",
            "node_name",
            "source",
            name="uq_tenant_runtime_sensor_agent_node_source",
        ),
    )

    sensor_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    agent_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    node_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    cluster_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    source: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="tetragon",
        index=True,
    )

    version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="enrolled",
        index=True,
    )

    heartbeat_interval_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30,
    )

    processed_event_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    dropped_event_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    parser_error_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    buffered_batch_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    submitted_batch_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    source_file: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    source_file_offset: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    capabilities_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )

    metadata_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )

    last_seen_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    last_heartbeat_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    last_batch_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
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


class RuntimeDependencyRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "runtime_dependencies"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "runtime_dependency_id", name="pk_runtime_dependencies"),
    )

    runtime_dependency_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    agent_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    sensor_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    cluster_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    node_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    source_namespace: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    source_pod_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    source_pod_uid: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    source_workload_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    source_container_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    source_binary: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        index=True,
    )

    source_pid: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    destination_name: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        index=True,
    )

    destination_address: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    destination_port: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    protocol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    direction: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="outbound",
        index=True,
    )

    observation_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    success_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    failure_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    first_seen_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    last_seen_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    metadata_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
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


class RuntimeProcessRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "runtime_processes"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "runtime_process_id", name="pk_runtime_processes"),
    )

    runtime_process_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    agent_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    sensor_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    cluster_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    node_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    exec_id: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        index=True,
    )

    pid: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    binary: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        index=True,
    )

    namespace: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    pod_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    pod_uid: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    container_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    parent_exec_id: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    exec_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    exit_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    last_exit_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    last_signal: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    first_seen_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    last_seen_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    metadata_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
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


class CloudAccountRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "cloud_accounts"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "cloud_account_id", name="pk_cloud_accounts"),
    )

    cloud_account_id: Mapped[str] = (
        mapped_column(
            String(255),
            primary_key=True,
        )
    )

    provider: Mapped[str] = (
        mapped_column(
            String(50),
            nullable=False,
            index=True,
        )
    )

    account_number: Mapped[str] = (
        mapped_column(
            String(255),
            nullable=False,
            index=True,
        )
    )

    display_name: Mapped[str] = (
        mapped_column(
            String(255),
            nullable=False,
        )
    )

    principal_arn: Mapped[
        str | None
    ] = mapped_column(
        String(1000),
        nullable=True,
    )

    metadata_json: Mapped[str] = (
        mapped_column(
            Text,
            nullable=False,
            default="{}",
        )
    )

    last_seen_at: Mapped[str] = (
        mapped_column(
            String(50),
            nullable=False,
            index=True,
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


class CloudResourceRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "cloud_resources"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "cloud_resource_id", name="pk_cloud_resources"),
    )

    cloud_resource_id: Mapped[str] = (
        mapped_column(
            String(1000),
            primary_key=True,
        )
    )

    provider: Mapped[str] = (
        mapped_column(
            String(50),
            nullable=False,
            index=True,
        )
    )

    account_id: Mapped[str] = (
        mapped_column(
            String(255),
            nullable=False,
            index=True,
        )
    )

    region: Mapped[str] = (
        mapped_column(
            String(100),
            nullable=False,
            index=True,
        )
    )

    resource_type: Mapped[str] = (
        mapped_column(
            String(100),
            nullable=False,
            index=True,
        )
    )

    resource_id: Mapped[str] = (
        mapped_column(
            String(1000),
            nullable=False,
            index=True,
        )
    )

    arn: Mapped[str | None] = (
        mapped_column(
            String(2000),
            nullable=True,
            index=True,
        )
    )

    name: Mapped[str] = (
        mapped_column(
            String(1000),
            nullable=False,
            index=True,
        )
    )

    status: Mapped[str | None] = (
        mapped_column(
            String(100),
            nullable=True,
            index=True,
        )
    )

    vpc_id: Mapped[str | None] = (
        mapped_column(
            String(255),
            nullable=True,
            index=True,
        )
    )

    subnet_ids_json: Mapped[str] = (
        mapped_column(
            Text,
            nullable=False,
            default="[]",
        )
    )

    tags_json: Mapped[str] = (
        mapped_column(
            Text,
            nullable=False,
            default="{}",
        )
    )

    properties_json: Mapped[str] = (
        mapped_column(
            Text,
            nullable=False,
            default="{}",
        )
    )

    observed_at: Mapped[str] = (
        mapped_column(
            String(50),
            nullable=False,
            index=True,
        )
    )

    agent_id: Mapped[str] = (
        mapped_column(
            String(255),
            nullable=False,
            index=True,
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


class BuildArtifactEvidenceRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "build_artifact_evidence"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "evidence_id", name="pk_build_artifact_evidence"),
        UniqueConstraint(
            "tenant_id",
            "provider",
            "repository_id",
            "workflow_run_id",
            "run_attempt",
            "image_digest",
            "provider_evidence_id",
            name="uq_tenant_build_artifact_provider_fact",
        ),
    )

    evidence_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    provider: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    repository_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    repository: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        index=True,
    )

    workflow_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    workflow_ref: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
    )

    workflow_run_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    run_attempt: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    commit_sha: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )

    artifact_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    image_repository: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        index=True,
    )

    image_reference: Mapped[str | None] = mapped_column(
        String(3000),
        nullable=True,
    )

    image_digest: Mapped[str] = mapped_column(
        String(71),
        nullable=False,
        index=True,
    )

    immutable_image_ref: Mapped[str] = mapped_column(
        String(3000),
        nullable=False,
    )

    provider_evidence_type: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
    )

    provider_evidence_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    provider_evidence_reference: Mapped[str] = mapped_column(
        String(3000),
        nullable=False,
    )

    provider_evidence_digest: Mapped[str] = mapped_column(
        String(71),
        nullable=False,
    )

    provider_build_record_digest: Mapped[str] = mapped_column(
        String(71),
        nullable=False,
    )

    provider_builder_id: Mapped[str] = mapped_column(
        String(3000),
        nullable=False,
    )

    provider_build_started_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    provider_build_finished_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    provider_run_updated_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    observed_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    temporal_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    completeness: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
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


class ChangeEventRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "change_events"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "event_id", name="pk_change_events"),
        Index(
            "ix_tenant_change_events_event_fingerprint",
            "tenant_id",
            "event_fingerprint",
            unique=True,
        ),
    )

    event_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    event_fingerprint: Mapped[str] = (
        mapped_column(
            String(128),
            nullable=False,
        )
    )

    source: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    kind: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    external_id: Mapped[
        str | None
    ] = mapped_column(
        String(1000),
        nullable=True,
        index=True,
    )

    origin_change_id: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )

    summary: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    actor: Mapped[
        str | None
    ] = mapped_column(
        String(500),
        nullable=True,
        index=True,
    )

    occurred_at: Mapped[str] = (
        mapped_column(
            String(50),
            nullable=False,
            index=True,
        )
    )

    received_at: Mapped[str] = (
        mapped_column(
            String(50),
            nullable=False,
            default=utc_now_iso,
            index=True,
        )
    )

    environment: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    provider: Mapped[
        str | None
    ] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    account_id: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    region: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    cluster_name: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    namespace: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    repository: Mapped[
        str | None
    ] = mapped_column(
        String(1000),
        nullable=True,
        index=True,
    )

    commit_sha: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    pipeline_name: Mapped[
        str | None
    ] = mapped_column(
        String(500),
        nullable=True,
        index=True,
    )

    release_version: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    terraform_workspace: Mapped[
        str | None
    ] = mapped_column(
        String(500),
        nullable=True,
        index=True,
    )

    risk_score: Mapped[int] = (
        mapped_column(
            Integer,
            nullable=False,
            default=0,
            index=True,
        )
    )

    risk_level: Mapped[str] = (
        mapped_column(
            String(30),
            nullable=False,
            default="low",
            index=True,
        )
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="observed",
        index=True,
    )

    observation_count: Mapped[int] = (
        mapped_column(
            Integer,
            nullable=False,
            default=1,
        )
    )

    metadata_json: Mapped[str] = (
        mapped_column(
            Text,
            nullable=False,
            default="{}",
        )
    )

    raw_payload_json: Mapped[str] = (
        mapped_column(
            Text,
            nullable=False,
            default="{}",
        )
    )

    agent_id: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
        index=True,
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


class ChangeEntityLinkRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "change_entity_links"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "link_id", name="pk_change_entity_links"),
        UniqueConstraint(
            "tenant_id",
            "event_id",
            "entity_id",
            "link_type",
            name="uq_tenant_change_event_entity_link",
        ),
    )

    link_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    event_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    entity_id: Mapped[str] = (
        mapped_column(
            String(1000),
            nullable=False,
            index=True,
        )
    )

    link_type: Mapped[str] = (
        mapped_column(
            String(50),
            nullable=False,
            index=True,
        )
    )

    confidence: Mapped[float] = (
        mapped_column(
            Float,
            nullable=False,
            default=0.0,
        )
    )

    reason: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    snapshot_id: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
        index=True,
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


class ChangeSourceRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "change_sources"

    source_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    source_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    secret_ref: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    config_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )

    filters_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="configured",
        index=True,
    )

    delivery_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    failure_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    last_event_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    last_success_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    last_error_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    last_error: Mapped[str | None] = mapped_column(
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


class ChangeSourceDeliveryRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "change_source_deliveries"

    __table_args__ = (
        Index(
            "ix_tenant_change_source_deliveries_delivery_key",
            "tenant_id",
            "delivery_key",
            unique=True,
        ),
    )

    delivery_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    source_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    delivery_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    source_delivery_id: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        index=True,
    )

    event_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="received",
        index=True,
    )

    payload_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    headers_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )

    payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )

    event_ids_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )

    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    received_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
        index=True,
    )

    processed_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )


class ChangeSourceDeadLetterRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "change_source_dead_letters"

    dead_letter_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    source_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    delivery_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    event_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
    )

    last_attempt_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    replayed_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    created_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )


class CausalAnalysisRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "causal_analyses"

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "analysis_id", name="pk_causal_analyses"),
    )

    analysis_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    incident_id: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        index=True,
    )

    generated_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    algorithm_version: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    candidate_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    hypothesis_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    top_hypothesis_score: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
        index=True,
    )

    top_root_event_id: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
        index=True,
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


class ActionApprovalRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "action_approvals"

    __table_args__ = (
        Index(
            "ix_tenant_action_approvals_pending_key",
            "tenant_id",
            "pending_key",
            unique=True,
        ),
    )

    approval_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )
    incident_id: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        index=True,
    )
    action_id: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        index=True,
    )
    action_family: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    risk: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    requires_human_approval: Mapped[bool] = (
        mapped_column(
            Boolean,
            nullable=False,
        )
    )
    policy_version: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    readiness_status_at_request: Mapped[str] = (
        mapped_column(
            String(50),
            nullable=False,
        )
    )

    evidence_fingerprint: Mapped[str] = (
        mapped_column(
            String(64),
            nullable=False,
            index=True,
        )
    )
    target_entity_ids_json: Mapped[str] = (
        mapped_column(
            Text,
            nullable=False,
            default="[]",
        )
    )
    target_change_event_id: Mapped[
        str | None
    ] = mapped_column(
        String(1000),
        nullable=True,
        index=True,
    )
    readiness_snapshot_json: Mapped[str] = (
        mapped_column(
            Text,
            nullable=False,
        )
    )

    # SQLite and PostgreSQL both permit multiple
    # NULL values in a UNIQUE column. The value is
    # populated only while pending, preventing
    # duplicate concurrent pending requests without
    # preventing a new request after a terminal state.
    pending_key: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    request_reason: Mapped[str | None] = (
        mapped_column(
            Text,
            nullable=True,
        )
    )
    requested_by_subject: Mapped[str] = (
        mapped_column(
            String(500),
            nullable=False,
            index=True,
        )
    )
    requested_by_display_name: Mapped[str] = (
        mapped_column(
            String(500),
            nullable=False,
        )
    )
    requested_by_roles_json: Mapped[str] = (
        mapped_column(
            Text,
            nullable=False,
            default="[]",
        )
    )
    requested_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    decided_by_subject: Mapped[str | None] = (
        mapped_column(
            String(500),
            nullable=True,
            index=True,
        )
    )
    decided_by_display_name: Mapped[
        str | None
    ] = mapped_column(
        String(500),
        nullable=True,
    )
    decided_by_roles_json: Mapped[str] = (
        mapped_column(
            Text,
            nullable=False,
            default="[]",
        )
    )
    decided_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
    decision_reason: Mapped[str | None] = (
        mapped_column(
            Text,
            nullable=True,
        )
    )

    expires_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    revoked_by_subject: Mapped[str | None] = (
        mapped_column(
            String(500),
            nullable=True,
            index=True,
        )
    )
    revoked_by_display_name: Mapped[
        str | None
    ] = mapped_column(
        String(500),
        nullable=True,
    )
    revoked_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
    revocation_reason: Mapped[str | None] = (
        mapped_column(
            Text,
            nullable=True,
        )
    )

    invalidated_at: Mapped[str | None] = (
        mapped_column(
            String(50),
            nullable=True,
            index=True,
        )
    )
    invalidation_reason: Mapped[str | None] = (
        mapped_column(
            Text,
            nullable=True,
        )
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


class ActionApprovalEventRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "action_approval_events"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "approval_id",
            "sequence",
            name="uq_tenant_action_approval_event_sequence",
        ),
    )

    event_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )
    sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    approval_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    incident_id: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        index=True,
    )
    action_id: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )
    from_status: Mapped[str | None] = (
        mapped_column(
            String(30),
            nullable=True,
        )
    )
    to_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    actor_subject: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )
    actor_display_name: Mapped[str] = (
        mapped_column(
            String(500),
            nullable=False,
        )
    )
    actor_roles_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    authentication_type: Mapped[str] = (
        mapped_column(
            String(100),
            nullable=False,
        )
    )

    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    evidence_fingerprint: Mapped[str] = (
        mapped_column(
            String(64),
            nullable=False,
            index=True,
        )
    )
    occurred_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )


class ExecutionIntentRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "execution_intents"

    __table_args__ = (
        Index(
            "ix_tenant_execution_intents_approval_id",
            "tenant_id",
            "approval_id",
            unique=True,
        ),
        Index(
            "ix_tenant_execution_intents_idempotency_key",
            "tenant_id",
            "idempotency_key",
            unique=True,
        ),
    )

    execution_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )
    incident_id: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        index=True,
    )
    approval_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    action_id: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        index=True,
    )
    action_family: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    approval_evidence_fingerprint: Mapped[str] = (
        mapped_column(
            String(64),
            nullable=False,
            index=True,
        )
    )
    policy_version: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    risk: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    target_entity_ids_json: Mapped[str] = (
        mapped_column(
            Text,
            nullable=False,
            default="[]",
        )
    )
    target_change_event_id: Mapped[
        str | None
    ] = mapped_column(
        String(1000),
        nullable=True,
        index=True,
    )
    execution_snapshot_json: Mapped[str] = (
        mapped_column(
            Text,
            nullable=False,
        )
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    created_by_subject: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )
    created_by_display_name: Mapped[str] = (
        mapped_column(
            String(500),
            nullable=False,
        )
    )
    created_by_roles_json: Mapped[str] = (
        mapped_column(
            Text,
            nullable=False,
            default="[]",
        )
    )
    created_by_authentication_type: Mapped[str] = (
        mapped_column(
            String(100),
            nullable=False,
        )
    )
    created_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    claimed_by_subject: Mapped[str | None] = (
        mapped_column(
            String(500),
            nullable=True,
            index=True,
        )
    )
    claimed_by_display_name: Mapped[
        str | None
    ] = mapped_column(
        String(500),
        nullable=True,
    )
    claimed_by_authentication_type: Mapped[
        str | None
    ] = mapped_column(
        String(100),
        nullable=True,
    )
    claimed_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
    claim_expires_at: Mapped[str | None] = (
        mapped_column(
            String(50),
            nullable=True,
            index=True,
        )
    )
    claim_token_hash: Mapped[str | None] = (
        mapped_column(
            String(64),
            nullable=True,
        )
    )
    claim_generation: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    cancelled_by_subject: Mapped[str | None] = (
        mapped_column(
            String(500),
            nullable=True,
            index=True,
        )
    )
    cancelled_by_display_name: Mapped[
        str | None
    ] = mapped_column(
        String(500),
        nullable=True,
    )
    cancelled_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
    cancellation_reason: Mapped[str | None] = (
        mapped_column(
            Text,
            nullable=True,
        )
    )

    invalidated_at: Mapped[str | None] = (
        mapped_column(
            String(50),
            nullable=True,
            index=True,
        )
    )
    invalidation_reason: Mapped[str | None] = (
        mapped_column(
            Text,
            nullable=True,
        )
    )
    expired_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
    expiration_reason: Mapped[str | None] = (
        mapped_column(
            Text,
            nullable=True,
        )
    )

    # Reserved receipt fields for a future adapter.
    # Block 14H never populates them.
    started_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    completed_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    failed_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    last_error_code: Mapped[str | None] = (
        mapped_column(
            String(255),
            nullable=True,
        )
    )
    last_error_message: Mapped[str | None] = (
        mapped_column(
            Text,
            nullable=True,
        )
    )
    result_reference: Mapped[str | None] = (
        mapped_column(
            String(1000),
            nullable=True,
        )
    )
    execution_performed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    row_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    updated_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=utc_now_iso,
    )


class ExecutionIntentEventRecord(TenantOwnedRecordMixin, Base):
    __tablename__ = "execution_intent_events"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "execution_id",
            "sequence",
            name="uq_tenant_execution_intent_event_sequence",
        ),
    )

    event_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )
    sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    execution_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    incident_id: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        index=True,
    )
    approval_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    action_id: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )
    from_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )
    to_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    actor_subject: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )
    actor_display_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    actor_roles_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    authentication_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    claim_generation: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    occurred_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )


class AuthSessionRecord(Base):
    """Digest-only, server-side authority for a human browser session."""

    __tablename__ = "auth_sessions"

    __table_args__ = (
        UniqueConstraint(
            "session_secret_digest",
            name="uq_auth_sessions_secret_digest",
        ),
    )

    session_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )
    session_secret_digest: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    csrf_digest: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    subject: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    roles_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    source_authentication_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    source_credential_digest: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    issued_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    absolute_expires_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    idle_expires_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    last_seen_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    revoked_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )


class AuthApiCredentialRecord(Base):
    """Digest-only authority for a named human or service API caller."""

    __tablename__ = "auth_api_credentials"

    __table_args__ = (
        UniqueConstraint(
            "credential_secret_digest",
            name="uq_auth_api_credentials_secret_digest",
        ),
    )

    credential_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    credential_secret_digest: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    credential_hint: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    caller_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )
    subject: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    roles_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String(50), nullable=False)
    created_by_subject: Mapped[str] = mapped_column(String(500), nullable=False)
    expires_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    revoked_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
    revoked_by_subject: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    last_used_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
    updated_at: Mapped[str] = mapped_column(String(50), nullable=False)


class TenantRecord(Base):
    """Durable customer security-boundary identity."""

    __tablename__ = "tenants"

    __table_args__ = (
        Index("ix_tenants_status", "status"),
    )

    tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[str] = mapped_column(String(50), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(50), nullable=False)
    created_by_subject: Mapped[str] = mapped_column(String(500), nullable=False)


class TenantMembershipRecord(Base):
    """A stable human subject's permission to enter one tenant."""

    __tablename__ = "tenant_memberships"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "subject",
            name="uq_tenant_memberships_tenant_subject",
        ),
        Index("ix_tenant_memberships_subject", "subject"),
        Index("ix_tenant_memberships_tenant_id", "tenant_id"),
        Index(
            "ix_tenant_memberships_active_resolution",
            "tenant_id",
            "subject",
            "status",
        ),
    )

    membership_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[str] = mapped_column(String(50), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(50), nullable=False)
    created_by_subject: Mapped[str] = mapped_column(String(500), nullable=False)


class ServiceApiTenantBindingRecord(Base):
    """Immutable V1 tenant binding for one named service API credential."""

    __tablename__ = "service_api_tenant_bindings"

    __table_args__ = (
        UniqueConstraint(
            "credential_id",
            name="uq_service_api_tenant_bindings_credential_id",
        ),
        Index("ix_service_api_tenant_bindings_tenant_id", "tenant_id"),
    )

    binding_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    credential_id: Mapped[str] = mapped_column(String(255), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[str] = mapped_column(String(50), nullable=False)
    created_by_subject: Mapped[str] = mapped_column(String(500), nullable=False)
