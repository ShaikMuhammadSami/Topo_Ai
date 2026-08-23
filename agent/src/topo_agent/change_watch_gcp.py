from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from typing import Any

from google.cloud import logging_v2


class GcpAuditChangePoller:
    def __init__(
        self,
        *,
        project_ids: list[str],
        overlap_seconds: int = 60,
    ) -> None:
        self.project_ids = (
            project_ids
        )

        self.overlap_seconds = (
            overlap_seconds
        )

        self.last_poll = (
            datetime.now(
                timezone.utc
            )
            - timedelta(minutes=5)
        )

    def poll(
        self,
    ) -> list[dict[str, Any]]:
        now = datetime.now(
            timezone.utc
        )

        start = (
            self.last_poll
            - timedelta(
                seconds=(
                    self.overlap_seconds
                )
            )
        )

        events = []

        for project_id in (
            self.project_ids
        ):
            client = (
                logging_v2.Client(
                    project=project_id
                )
            )

            filter_value = (
                'protoPayload."@type"='
                '"type.googleapis.com/'
                'google.cloud.audit.AuditLog" '
                f'AND timestamp>="{start.isoformat()}" '
                f'AND timestamp<="{now.isoformat()}"'
            )

            entries = (
                client.list_entries(
                    resource_names=[
                        f"projects/{project_id}"
                    ],
                    filter_=filter_value,
                    order_by=(
                        logging_v2
                        .DESCENDING
                    ),
                    page_size=100,
                )
            )

            for entry in entries:
                payload = getattr(
                    entry,
                    "payload",
                    {},
                )

                if not isinstance(
                    payload,
                    dict,
                ):
                    continue

                method = str(
                    payload.get(
                        "methodName",
                        "unknown",
                    )
                )

                # Ignore common read-only
                # operations.
                lower_method = (
                    method.lower()
                )

                if any(
                    token in lower_method
                    for token in (
                        ".get",
                        ".list",
                        ".search",
                        ".read",
                    )
                ):
                    continue

                authentication = (
                    payload.get(
                        "authenticationInfo"
                    )
                    or {}
                )

                resource_name = (
                    payload.get(
                        "resourceName"
                    )
                )

                refs = []

                if resource_name:
                    refs.append(
                        {
                            "entity_id":
                                None,
                            "external_id":
                                None,
                            "provider_resource_id":
                                resource_name,
                            "kind":
                                None,
                            "name":
                                None,
                            "namespace":
                                None,
                            "cluster_name":
                                None,
                        }
                    )

                timestamp = getattr(
                    entry,
                    "timestamp",
                    None,
                )

                if hasattr(
                    timestamp,
                    "isoformat",
                ):
                    timestamp = (
                        timestamp.isoformat()
                    )

                insert_id = getattr(
                    entry,
                    "insert_id",
                    None,
                )

                events.append(
                    {
                        "source":
                            "gcp_audit_log",
                        "kind":
                            "infrastructure",
                        "external_id":
                            (
                                "gcp-audit:"
                                f"{project_id}:"
                                f"{insert_id or method}:"
                                f"{timestamp}"
                            ),
                        "origin_change_id":
                            None,
                        "title":
                            (
                                "GCP "
                                f"{method}"
                            ),
                        "summary":
                            None,
                        "actor":
                            authentication.get(
                                "principalEmail"
                            ),
                        "occurred_at":
                            (
                                timestamp
                                or now.isoformat()
                            ),
                        "environment":
                            None,
                        "provider":
                            "gcp",
                        "account_id":
                            project_id,
                        "region":
                            None,
                        "cluster_name":
                            None,
                        "namespace":
                            None,
                        "repository":
                            None,
                        "commit_sha":
                            None,
                        "pipeline_name":
                            None,
                        "release_version":
                            None,
                        "terraform_workspace":
                            None,
                        "risk_score":
                            None,
                        "status":
                            "observed",
                        "entity_refs":
                            refs,
                        "metadata": {
                            "method_name":
                                method,
                            "service_name":
                                payload.get(
                                    "serviceName"
                                ),
                            "_temporal": {
                                "source_time_available": bool(timestamp),
                                "source_field": "GCPAuditLog.timestamp",
                            },
                        },
                        "raw_payload": {},
                    }
                )

        self.last_poll = now

        return events
