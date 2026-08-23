from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import SignalRecord, SnapshotRecord
from app.models.temporal import (
    TemporalMetadata,
    TemporalStatus,
    TimeOrigin,
    TimeQuality,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_utc(
    value: str | datetime,
    *,
    allow_legacy_naive: bool = False,
) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    if result.tzinfo is None or result.utcoffset() is None:
        if not allow_legacy_naive:
            raise ValueError(
                "Timestamp has no timezone and cannot be authoritative"
            )
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def try_parse_utc(
    value: str | datetime | None,
    *,
    allow_legacy_naive: bool = False,
) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return parse_utc(
            value,
            allow_legacy_naive=allow_legacy_naive,
        )
    except (TypeError, ValueError):
        return None


def build_temporal_metadata(
    *,
    source_event_at: str | datetime | None,
    observed_at: str | datetime | None,
    recorded_at: str | datetime,
    source_time_trusted: bool,
    source_field: str | None = None,
    source_origin: TimeOrigin = TimeOrigin.SOURCE_REPORTED,
    source_quality: TimeQuality = TimeQuality.EXACT,
    fallback_origin: TimeOrigin = TimeOrigin.INGESTION_FALLBACK,
    fallback_quality: TimeQuality = TimeQuality.FALLBACK,
    valid_from: str | datetime | None = None,
    valid_to: str | datetime | None = None,
) -> TemporalMetadata:
    source = try_parse_utc(source_event_at)
    observed = try_parse_utc(observed_at)
    recorded = parse_utc(recorded_at)
    valid_start = try_parse_utc(valid_from)
    valid_end = try_parse_utc(valid_to)

    authoritative = bool(source_time_trusted and source is not None)
    if authoritative:
        effective = source
        origin = source_origin
        quality = source_quality
    else:
        effective = observed or recorded
        origin = fallback_origin
        quality = fallback_quality

    status = (
        TemporalStatus.COMPLETE
        if authoritative and observed is not None
        else TemporalStatus.PARTIAL
    )
    return TemporalMetadata(
        effective_at=effective,
        source_event_at=source,
        observed_at=observed,
        recorded_at=recorded,
        valid_from=valid_start,
        valid_to=valid_end,
        time_origin=origin,
        time_quality=quality,
        source_field=source_field,
        source_time_authoritative=authoritative,
        status=status,
    )


def observation_temporal_metadata(
    *,
    observed_at: str | datetime,
    recorded_at: str | datetime,
    origin: TimeOrigin = TimeOrigin.TOPO_OBSERVED,
    source_field: str | None = None,
) -> TemporalMetadata:
    observed = parse_utc(observed_at, allow_legacy_naive=True)
    return TemporalMetadata(
        effective_at=observed,
        observed_at=observed,
        recorded_at=parse_utc(recorded_at),
        time_origin=origin,
        time_quality=TimeQuality.BOUNDED,
        source_field=source_field,
        source_time_authoritative=False,
        status=TemporalStatus.COMPLETE,
    )


def legacy_temporal_metadata(
    *,
    effective_at: str | datetime,
    recorded_at: str | datetime | None = None,
) -> TemporalMetadata:
    effective = parse_utc(effective_at, allow_legacy_naive=True)
    recorded = try_parse_utc(
        recorded_at,
        allow_legacy_naive=True,
    )
    return TemporalMetadata(
        effective_at=effective,
        recorded_at=recorded,
        time_origin=TimeOrigin.LEGACY_UNKNOWN,
        time_quality=TimeQuality.UNKNOWN,
        source_time_authoritative=False,
        status=TemporalStatus.LEGACY_UNSPECIFIED,
    )


def temporal_from_metadata(
    metadata: dict[str, Any] | None,
    *,
    legacy_effective_at: str | datetime,
    legacy_recorded_at: str | datetime | None = None,
) -> TemporalMetadata:
    raw = (metadata or {}).get("temporal")
    if isinstance(raw, dict):
        try:
            return TemporalMetadata.model_validate(raw)
        except ValueError:
            pass
    return legacy_temporal_metadata(
        effective_at=legacy_effective_at,
        recorded_at=legacy_recorded_at,
    )


def record_metadata(record: Any) -> dict[str, Any]:
    raw = getattr(record, "metadata_json", "{}")
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def change_event_temporal(record: Any) -> TemporalMetadata:
    return temporal_from_metadata(
        record_metadata(record),
        legacy_effective_at=record.occurred_at,
        legacy_recorded_at=getattr(record, "created_at", None),
    )


def safe_snapshot_record_at_or_before(
    session: Session,
    *,
    cluster_name: str,
    boundary_at: str | datetime,
    namespace: str | None = None,
    limit: int = 500,
) -> SnapshotRecord | None:
    """Return a scope-compatible checkpoint no later than the boundary.

    Comparison is performed on parsed UTC datetimes instead of lexicographic
    ISO strings, so equivalent offsets cannot reorder history.
    """

    boundary = parse_utc(boundary_at, allow_legacy_naive=True)
    statement = select(SnapshotRecord).where(
        SnapshotRecord.cluster_name == cluster_name
    )
    if namespace:
        statement = statement.where(
            or_(
                SnapshotRecord.namespace == namespace,
                SnapshotRecord.namespace == "*",
                SnapshotRecord.namespace.is_(None),
            )
        )
    records = list(
        session.scalars(
            statement.order_by(
                SnapshotRecord.created_at.desc()
            ).limit(limit)
        ).all()
    )
    safe: list[tuple[datetime, SnapshotRecord]] = []
    for record in records:
        collected = try_parse_utc(
            record.collected_at,
            allow_legacy_naive=True,
        )
        if collected is not None and collected <= boundary:
            safe.append((collected, record))
    if not safe:
        return None
    return max(safe, key=lambda item: item[0])[1]


def incident_operational_time(
    session: Session,
    incident: Any,
) -> datetime:
    """Earliest defensible customer/runtime failure observation.

    The primary signal's effective time is authoritative when TC-3 metadata
    exists. Historical incidents retain their legacy first_observed_at
    interpretation without rewriting the row.
    """

    signal_id = getattr(incident, "primary_signal_id", None)
    if signal_id:
        record = session.get(SignalRecord, str(signal_id))
        if record is not None:
            try:
                payload = json.loads(record.payload_json or "{}")
            except (json.JSONDecodeError, TypeError):
                payload = {}
            raw = payload.get("temporal") if isinstance(payload, dict) else None
            if isinstance(raw, dict):
                try:
                    return TemporalMetadata.model_validate(raw).effective_at
                except ValueError:
                    pass
    return parse_utc(
        str(incident.first_observed_at),
        allow_legacy_naive=True,
    )
