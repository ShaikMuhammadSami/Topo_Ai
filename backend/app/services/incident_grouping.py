from __future__ import annotations

from hashlib import sha256

from app.models.signals import (
    NormalizedSignal,
    SignalSeverity,
)


FAILURE_SEVERITIES = {
    SignalSeverity.WARNING,
    SignalSeverity.ERROR,
    SignalSeverity.CRITICAL,
}


SEVERITY_PRIORITY = {
    SignalSeverity.CRITICAL: 4,
    SignalSeverity.ERROR: 3,
    SignalSeverity.WARNING: 2,
    SignalSeverity.INFO: 1,
}


def is_failure_signal(
    signal: NormalizedSignal,
) -> bool:
    return signal.severity in FAILURE_SEVERITIES


def stable_kubernetes_object_name(
    signal: NormalizedSignal,
) -> str | None:
    name = signal.involved_object_name

    if not name:
        return None

    kind = signal.involved_object_kind

    if kind == "Pod":
        parts = name.split("-")

        if len(parts) >= 3:
            return "-".join(parts[:-2])

        return name

    if kind == "ReplicaSet":
        parts = name.split("-")

        if len(parts) >= 2:
            return "-".join(parts[:-1])

        return name

    return name


def incident_group_subject(
    signal: NormalizedSignal,
) -> str:
    stable_name = (
        stable_kubernetes_object_name(
            signal
        )
    )

    if stable_name:
        return (
            f"workload:{stable_name}"
        )

    if signal.involved_entity_id:
        return (
            f"entity:{signal.involved_entity_id}"
        )

    if (
        signal.involved_object_kind
        and signal.involved_object_name
    ):
        return (
            f"{signal.involved_object_kind}:"
            f"{signal.involved_object_name}"
        )

    return (
        signal.reason
        or signal.category.value
        or "unknown"
    )


def incident_fingerprint(
    signal: NormalizedSignal,
) -> str:
    """
    Stable workload-level incident key.

    This intentionally does not include the
    exact event reason, because Failed,
    BackOff, ErrImagePull and ImagePullBackOff
    can describe the same incident.
    """

    value = "|".join(
        [
            "incident-group-v2",
            signal.cluster_name,
            signal.namespace or "",
            incident_group_subject(
                signal
            ),
        ]
    )

    return sha256(
        value.encode("utf-8")
    ).hexdigest()


def incident_group_label(
    signal: NormalizedSignal,
) -> str:
    return incident_group_subject(
        signal
    ).replace(":", "/")


def signal_priority_key(
    signal: NormalizedSignal,
) -> tuple[int, str, int, str]:
    return (
        SEVERITY_PRIORITY.get(
            signal.severity,
            0,
        ),
        signal.last_observed_at.isoformat(),
        signal.occurrence_count,
        signal.signal_id,
    )