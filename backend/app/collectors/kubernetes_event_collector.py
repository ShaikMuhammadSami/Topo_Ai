from __future__ import annotations

import re
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from kubernetes import client

from app.models.signals import (
    NormalizedSignal,
    SignalCategory,
    SignalSeverity,
    SignalType,
)
from app.models.topology import GraphSnapshot
from app.models.temporal import (
    TemporalMetadata,
    TemporalStatus,
    TimeOrigin,
    TimeQuality,
)


ERROR_REASONS = {
    "BackOff",
    "CrashLoopBackOff",
    "ErrImagePull",
    "ImagePullBackOff",
    "Failed",
    "FailedScheduling",
    "FailedMount",
    "FailedAttachVolume",
    "FailedCreate",
    "FailedKillPod",
    "FailedPostStartHook",
    "FailedPreStopHook",
    "Unhealthy",
}

def _reporting_information(
    event: Any,
) -> tuple[str | None, str | None]:
    """
    Support both CoreV1Event and EventsV1Event
    reporting field names.
    """
    reporting_controller = (
        getattr(
            event,
            "reporting_controller",
            None,
        )
        or getattr(
            event,
            "reporting_component",
            None,
        )
    )

    reporting_instance = getattr(
        event,
        "reporting_instance",
        None,
    )

    source = getattr(
        event,
        "source",
        None,
    )

    if source:
        reporting_controller = (
            reporting_controller
            or getattr(
                source,
                "component",
                None,
            )
        )

        reporting_instance = (
            reporting_instance
            or getattr(
                source,
                "host",
                None,
            )
        )

    return (
        reporting_controller,
        reporting_instance,
    )

def _safe_identifier(
    value: str,
) -> str:
    return re.sub(
        r"[^a-zA-Z0-9._-]+",
        "_",
        value,
    )


def _to_utc(
    value: datetime | None,
    fallback: datetime,
) -> datetime:
    if value is None:
        return fallback

    if value.tzinfo is None:
        # Kubernetes API timestamps are normally RFC3339/aware. A naive
        # value has ambiguous source semantics, so use the explicitly
        # labeled collection observation instead of silently declaring UTC.
        return fallback

    return value.astimezone(
        timezone.utc
    )


def _event_times(
    event: Any,
    collected_at: datetime,
) -> tuple[datetime, datetime]:
    first_observed = (
        event.first_timestamp
        or event.event_time
        or event.metadata.creation_timestamp
        or collected_at
    )

    series_last_observed = None

    if event.series:
        series_last_observed = (
            event.series.last_observed_time
        )

    last_observed = (
        series_last_observed
        or event.last_timestamp
        or event.event_time
        or event.metadata.creation_timestamp
        or collected_at
    )

    return (
        _to_utc(
            first_observed,
            collected_at,
        ),
        _to_utc(
            last_observed,
            collected_at,
        ),
    )


def _source_event_time(event: Any) -> tuple[datetime | None, str | None]:
    candidates = (
        (event.first_timestamp, "KubernetesEvent.first_timestamp"),
        (event.event_time, "KubernetesEvent.event_time"),
        (
            event.metadata.creation_timestamp,
            "KubernetesEvent.metadata.creation_timestamp",
        ),
    )
    for value, field_name in candidates:
        if value is None or value.tzinfo is None:
            continue
        return value.astimezone(timezone.utc), field_name
    return None, None


def _event_count(
    event: Any,
) -> int:
    if event.series and event.series.count:
        return max(
            int(event.series.count),
            1,
        )

    if event.count:
        return max(
            int(event.count),
            1,
        )

    return 1


def _severity(
    event_type: str | None,
    reason: str | None,
) -> SignalSeverity:
    if reason in ERROR_REASONS:
        return SignalSeverity.ERROR

    if (
        event_type
        and event_type.lower()
        == "warning"
    ):
        return SignalSeverity.WARNING

    return SignalSeverity.INFO


def _category(
    reason: str | None,
) -> SignalCategory:
    normalized = (
        reason
        or ""
    ).lower()

    if any(
        item in normalized
        for item in (
            "image",
            "pull",
        )
    ):
        return SignalCategory.IMAGE

    if any(
        item in normalized
        for item in (
            "schedule",
            "preempt",
        )
    ):
        return SignalCategory.SCHEDULING

    if any(
        item in normalized
        for item in (
            "mount",
            "volume",
            "attach",
        )
    ):
        return SignalCategory.STORAGE

    if any(
        item in normalized
        for item in (
            "unhealthy",
            "probe",
            "backoff",
            "crash",
        )
    ):
        return SignalCategory.HEALTH

    if any(
        item in normalized
        for item in (
            "created",
            "started",
            "killing",
            "scaled",
            "successful",
            "pulled",
        )
    ):
        return SignalCategory.LIFECYCLE

    if any(
        item in normalized
        for item in (
            "config",
            "invalid",
        )
    ):
        return SignalCategory.CONFIGURATION

    return SignalCategory.OTHER


def _fingerprint(
    cluster_name: str,
    namespace: str | None,
    object_uid: str | None,
    object_kind: str | None,
    object_name: str | None,
    reason: str | None,
    reporting_controller: str | None,
) -> str:
    raw_value = "|".join(
        [
            cluster_name,
            namespace or "",
            object_uid or "",
            object_kind or "",
            object_name or "",
            reason or "",
            reporting_controller or "",
        ]
    )

    return sha256(
        raw_value.encode("utf-8")
    ).hexdigest()


def _signal_id(
    cluster_name: str,
    event_uid: str | None,
    fingerprint: str,
) -> str:
    safe_cluster = _safe_identifier(
        cluster_name
    )

    identity = (
        event_uid
        or fingerprint[:32]
    )

    return (
        f"signal:kubernetes-event:"
        f"{safe_cluster}:{identity}"
    )


class KubernetesEventCollector:
    def __init__(
        self,
        core_api: client.CoreV1Api,
        cluster_name: str,
        namespace: str | None,
    ) -> None:
        self.core_api = core_api
        self.cluster_name = cluster_name
        self.namespace = namespace

        self.api_client = client.ApiClient()

    def _list_events(self) -> list[Any]:
        if self.namespace:
            return (
                self.core_api
                .list_namespaced_event(
                    namespace=self.namespace
                )
                .items
            )

        return (
            self.core_api
            .list_event_for_all_namespaces()
            .items
        )

    def collect(
        self,
        snapshot: GraphSnapshot,
    ) -> list[NormalizedSignal]:
        collected_at = datetime.now(
            timezone.utc
        )

        entities_by_uid = {
            str(entity.external_id): entity
            for entity in snapshot.entities
            if entity.external_id
        }

        signals: list[
            NormalizedSignal
        ] = []

        for event in self._list_events():
            involved = (
                event.involved_object
            )

            object_uid = (
                str(involved.uid)
                if involved
                and involved.uid
                else None
            )

            object_kind = (
                involved.kind
                if involved
                else None
            )

            object_name = (
                involved.name
                if involved
                else None
            )

            namespace = (
                involved.namespace
                if involved
                and involved.namespace
                else event.metadata.namespace
            )

            reason = event.reason
            
            reporting_controller = (
                getattr(
                    event,
                    "reporting_controller",
                    None,
                )
                or getattr(
                    event,
                    "reporting_component",
                    None,
                )
            )

            if (
                not reporting_controller
                and getattr(event, "source", None)
            ):
                reporting_controller = getattr(
                    event.source,
                    "component",
                    None,
                )

            reporting_instance = getattr(
                event,
                "reporting_instance",
                None
            )

            if (
                not reporting_instance
                and getattr(event, "source", None)
            ):
                reporting_instance = getattr(
                    event.source,
                    "host",
                    None
                )

            fingerprint = _fingerprint(
                cluster_name=(
                    self.cluster_name
                ),
                namespace=namespace,
                object_uid=object_uid,
                object_kind=object_kind,
                object_name=object_name,
                reason=reason,
                reporting_controller=(
                    reporting_controller
                ),
            )

            event_uid = (
                str(event.metadata.uid)
                if event.metadata.uid
                else None
            )

            first_observed_at, (
                last_observed_at
            ) = _event_times(
                event=event,
                collected_at=collected_at,
            )
            source_event_at, source_field = _source_event_time(event)
            effective_at = source_event_at or collected_at
            temporal = TemporalMetadata(
                effective_at=effective_at,
                source_event_at=source_event_at,
                observed_at=collected_at,
                time_origin=(
                    TimeOrigin.SOURCE_REPORTED
                    if source_event_at is not None
                    else TimeOrigin.TOPO_OBSERVED
                ),
                time_quality=(
                    TimeQuality.EXACT
                    if source_event_at is not None
                    else TimeQuality.FALLBACK
                ),
                source_field=source_field,
                source_time_authoritative=(
                    source_event_at is not None
                ),
                status=TemporalStatus.PARTIAL,
            )

            involved_entity = (
                entities_by_uid.get(
                    object_uid or ""
                )
            )

            message = (
                event.message
                or "Kubernetes event"
            )

            title_parts = [
                reason
                or "Kubernetes event",
            ]

            if object_kind and object_name:
                title_parts.append(
                    f"{object_kind}/"
                    f"{object_name}"
                )

            raw_payload = (
                self.api_client
                .sanitize_for_serialization(
                    event
                )
            )

            signals.append(
                NormalizedSignal(
                    signal_id=_signal_id(
                        cluster_name=(
                            self.cluster_name
                        ),
                        event_uid=event_uid,
                        fingerprint=fingerprint,
                    ),
                    fingerprint=fingerprint,
                    signal_type=(
                        SignalType
                        .KUBERNETES_EVENT
                    ),
                    severity=_severity(
                        event_type=event.type,
                        reason=reason,
                    ),
                    category=_category(
                        reason
                    ),
                    source_system=(
                        "kubernetes"
                    ),
                    title=" — ".join(
                        title_parts
                    ),
                    summary=message,
                    reason=reason,
                    action=event.action,
                    first_observed_at=(
                        first_observed_at
                    ),
                    last_observed_at=(
                        last_observed_at
                    ),
                    temporal=temporal,
                    occurrence_count=(
                        _event_count(event)
                    ),
                    cluster_name=(
                        self.cluster_name
                    ),
                    namespace=namespace,
                    involved_entity_id=(
                        involved_entity.id
                        if involved_entity
                        else None
                    ),
                    involved_object_uid=(
                        object_uid
                    ),
                    involved_object_kind=(
                        object_kind
                    ),
                    involved_object_name=(
                        object_name
                    ),
                    reporting_controller=(
                        reporting_controller
                    ),
                    reporting_instance=(
                        reporting_instance
                    ),
                    attributes={
                        "event_type": (
                            event.type
                        ),
                        "api_version": (
                            involved.api_version
                            if involved
                            else None
                        ),
                        "field_path": (
                            involved.field_path
                            if involved
                            else None
                        ),
                    },
                    raw_payload=(
                        raw_payload
                        if isinstance(
                            raw_payload,
                            dict,
                        )
                        else {}
                    ),
                )
            )

        return signals
