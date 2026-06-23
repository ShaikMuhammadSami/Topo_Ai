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