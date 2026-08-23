from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


TEMPORAL_VERSION = "tc3.v1"


class TimeOrigin(str, Enum):
    SOURCE_REPORTED = "source_reported"
    RUNTIME_OBSERVED = "runtime_observed"
    TOPO_OBSERVED = "topo_observed"
    DERIVED = "derived"
    INGESTION_FALLBACK = "ingestion_fallback"
    LEGACY_UNKNOWN = "legacy_unknown"


class TimeQuality(str, Enum):
    EXACT = "exact"
    BOUNDED = "bounded"
    FALLBACK = "fallback"
    UNKNOWN = "unknown"


class TemporalStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    LEGACY_UNSPECIFIED = "legacy_unspecified"


class TemporalMetadata(BaseModel):
    """TC-3 time interpretation for one durable fact.

    ``effective_at`` is the comparison time selected by the contract. It is
    not necessarily source time: ``time_origin`` and ``time_quality`` make
    fallback use explicit.
    """

    model_config = ConfigDict(extra="forbid")

    temporal_version: str = Field(default=TEMPORAL_VERSION, min_length=1)
    effective_at: datetime
    source_event_at: datetime | None = None
    observed_at: datetime | None = None
    recorded_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    time_origin: TimeOrigin
    time_quality: TimeQuality
    source_field: str | None = None
    source_time_authoritative: bool = False
    status: TemporalStatus = TemporalStatus.PARTIAL

    @field_validator(
        "effective_at",
        "source_event_at",
        "observed_at",
        "recorded_at",
        "valid_from",
        "valid_to",
    )
    @classmethod
    def require_aware_utc(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "TC-3 timestamps must include an explicit timezone"
            )
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_semantics(self) -> "TemporalMetadata":
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to < self.valid_from
        ):
            raise ValueError("valid_to cannot be earlier than valid_from")
        if self.source_time_authoritative and self.source_event_at is None:
            raise ValueError(
                "Authoritative source time requires source_event_at"
            )
        if (
            self.status == TemporalStatus.LEGACY_UNSPECIFIED
            and self.time_origin != TimeOrigin.LEGACY_UNKNOWN
        ):
            raise ValueError(
                "Legacy temporal status requires legacy_unknown origin"
            )
        return self
