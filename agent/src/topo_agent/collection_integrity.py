from __future__ import annotations

from typing import Any


COMPLETE_COLLECTION_STATUS = "success"
COMPLETE_PLUGIN_STATUSES = frozenset(
    {
        "success",
        "skipped_optional",
    }
)


def collection_integrity_error(
    payload: dict[str, Any],
) -> str | None:
    """Return a safe explanation when a snapshot is not complete.

    Current agents always declare collection and per-plugin status. A
    submission is replayable only when the overall collection and every
    enabled plugin are complete. Optional categories may be represented by
    ``skipped_optional``; required collection failures may not.
    """

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return "Collection completeness metadata is missing."

    plugins = metadata.get("plugins")
    if not isinstance(plugins, list):
        return "Plugin completeness metadata is missing."

    incomplete: list[str] = []
    for value in plugins:
        if not isinstance(value, dict):
            incomplete.append("unknown")
            continue

        status = str(value.get("status") or "missing")
        name = str(value.get("name") or "unknown")
        failures = value.get("collection_failures")
        resources: list[str] = []
        if isinstance(failures, list):
            for failure in failures:
                if not isinstance(failure, dict):
                    continue
                resource = str(
                    failure.get("resource") or "unknown"
                )
                status_code = failure.get("status_code")
                suffix = (
                    f" HTTP {status_code}"
                    if isinstance(status_code, int)
                    else " unavailable"
                )
                resources.append(resource + suffix)

        declared_errors = value.get("errors")
        has_errors = (
            isinstance(declared_errors, list)
            and bool(declared_errors)
        )
        completeness = value.get(
            "resource_completeness"
        )
        has_failed_resource = (
            isinstance(completeness, dict)
            and any(
                state not in {
                    "complete",
                    "skipped_optional",
                }
                for state in completeness.values()
            )
        )
        if (
            status in COMPLETE_PLUGIN_STATUSES
            and not resources
            and not has_errors
            and not has_failed_resource
        ):
            continue

        detail = ", ".join(resources)
        incomplete.append(
            f"{name} ({status}"
            + (f": {detail}" if detail else "")
            + ")"
        )

    if incomplete:
        return (
            "Required plugin collection is incomplete: "
            + "; ".join(incomplete)
            + "."
        )

    collection_status = metadata.get(
        "collection_status"
    )
    if collection_status != COMPLETE_COLLECTION_STATUS:
        return (
            "Topology collection is incomplete "
            f"(status={collection_status or 'missing'})."
        )

    declared_count = metadata.get("plugin_count")
    if (
        not isinstance(declared_count, int)
        or declared_count != len(plugins)
    ):
        return "Plugin completeness metadata is inconsistent."

    successful_count = metadata.get(
        "successful_plugin_count"
    )
    failed_count = metadata.get(
        "failed_plugin_count"
    )
    if (
        successful_count != len(plugins)
        or failed_count != 0
    ):
        return "Plugin completeness metadata is inconsistent."

    return None
