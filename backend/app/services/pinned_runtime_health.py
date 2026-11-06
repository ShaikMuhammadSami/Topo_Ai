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
        "InvalidImageName",
        "OOMKilled",
        "RunContainerError",
        "Unknown",
    }
)


def active_container_failure_reasons(
    properties: dict[str, Any],
    *,
    supported_reasons: frozenset[str] = (
        PINNED_FAILURE_REASONS
    ),
) -> set[str]:
    """
    Return current failures plus historical context
    only when a container is actively failing.
    """

    reasons: set[str] = set()
    containers = properties.get("container_statuses") or []

    if not isinstance(containers, list):
        return reasons

    for container in containers:
        if not isinstance(container, dict):
            continue

        current_candidates = [
            container.get("waiting_reason"),
            container.get("terminated_reason"),
            container.get("reason"),
        ]

        state = container.get("state")

        if isinstance(state, dict):
            for state_name in (
                "waiting",
                "terminated",
            ):
                state_value = state.get(state_name)
                if (
                    isinstance(state_value, dict)
                    and state_value.get("reason")
                ):
                    current_candidates.append(
                        state_value["reason"]
                    )

        current_reasons = {
            candidate
            for candidate in current_candidates
            if isinstance(candidate, str)
            and candidate in supported_reasons
        }
        reasons.update(current_reasons)

        # lastState is retained as historical evidence, but it is actionable
        # only while the same container has a current supported failure.
        if not current_reasons:
            continue

        historical_candidates = [
            container.get("last_terminated_reason")
        ]
        last_state = container.get("last_state")

        if isinstance(last_state, dict):
            terminated = last_state.get(
                "terminated"
            )

            if isinstance(terminated, dict):
                historical_candidates.append(
                    terminated.get("reason")
                )

        reasons.update(
            candidate
            for candidate in historical_candidates
            if isinstance(candidate, str)
            and candidate in supported_reasons
        )

    return reasons


def pinned_pod_health(entity: Entity) -> PinnedRuntimeHealth:
    """Classify only structured state stored in the pinned snapshot."""

    if entity.kind != "KubernetesPod":
        return PinnedRuntimeHealth.UNKNOWN

    properties = entity.properties
    phase = str(properties.get("phase") or "")
    reasons = active_container_failure_reasons(
        properties
    )

    if phase in {"Failed", "Unknown"} or reasons & PINNED_FAILURE_REASONS:
        return PinnedRuntimeHealth.FAILED

    if properties.get("ready") is True and phase in {"", "Running"}:
        return PinnedRuntimeHealth.READY

    return PinnedRuntimeHealth.UNKNOWN
