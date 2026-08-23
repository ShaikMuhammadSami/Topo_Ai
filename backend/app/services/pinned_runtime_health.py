from __future__ import annotations

from enum import Enum
from typing import Any

from app.models.topology import Entity


class PinnedRuntimeHealth(str, Enum):
    READY = "ready"
    FAILED = "failed"
    UNKNOWN = "unknown"


PINNED_FAILURE_REASONS = frozenset(
    {
        "BackOff",
        "CrashLoopBackOff",
        "CreateContainerConfigError",
        "CreateContainerError",
        "ErrImagePull",
        "Failed",
        "ImagePullBackOff",
        "OOMKilled",
        "RunContainerError",
        "Unknown",
    }
)


def _container_reasons(properties: dict[str, Any]) -> set[str]:
    reasons: set[str] = set()
    containers = properties.get("container_statuses") or []

    if not isinstance(containers, list):
        return reasons

    for container in containers:
        if not isinstance(container, dict):
            continue

        candidates = (
            container.get("waiting_reason"),
            container.get("terminated_reason"),
            container.get("reason"),
        )

        for candidate in candidates:
            if candidate:
                reasons.add(str(candidate))

        state = container.get("state")
        if not isinstance(state, dict):
            continue

        for state_name in ("waiting", "terminated"):
            state_value = state.get(state_name)
            if isinstance(state_value, dict) and state_value.get("reason"):
                reasons.add(str(state_value["reason"]))

    return reasons


def pinned_pod_health(entity: Entity) -> PinnedRuntimeHealth:
    """Classify only structured state stored in the pinned snapshot."""

    if entity.kind != "KubernetesPod":
        return PinnedRuntimeHealth.UNKNOWN

    properties = entity.properties
    phase = str(properties.get("phase") or "")
    reasons = _container_reasons(properties)

    if phase in {"Failed", "Unknown"} or reasons & PINNED_FAILURE_REASONS:
        return PinnedRuntimeHealth.FAILED

    if properties.get("ready") is True and phase in {"", "Running"}:
        return PinnedRuntimeHealth.READY

    return PinnedRuntimeHealth.UNKNOWN
