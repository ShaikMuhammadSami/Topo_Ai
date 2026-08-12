from __future__ import annotations

import json
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from typing import Any

import boto3


READ_EVENT_PREFIXES = (
    "Get",
    "List",
    "Describe",
    "Head",
    "Lookup",
)


class AwsCloudTrailChangePoller:
    def __init__(
        self,
        *,
        regions: list[str],
        profile: str | None = None,
        overlap_seconds: int = 60,
    ) -> None:
        self.regions = regions

        self.overlap_seconds = (
            overlap_seconds
        )

        self.session = boto3.Session(
            profile_name=profile
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

        for region in self.regions:
            client = (
                self.session.client(
                    "cloudtrail",
                    region_name=region,
                )
            )

            token = None

            while True:
                kwargs = {
                    "StartTime": start,
                    "EndTime": now,
                    "MaxResults": 50,
                }

                if token:
                    kwargs[
                        "NextToken"
                    ] = token

                response = (
                    client.lookup_events(
                        **kwargs
                    )
                )

                for item in response.get(
                    "Events",
                    [],
                ):
                    event_name = str(
                        item.get(
                            "EventName",
                            "unknown",
                        )
                    )

                    if event_name.startswith(
                        READ_EVENT_PREFIXES
                    ):
                        continue

                    cloudtrail_event = {}

                    raw = item.get(
                        "CloudTrailEvent"
                    )

                    if raw:
                        try:
                            cloudtrail_event = (
                                json.loads(raw)
                            )

                        except Exception:
                            cloudtrail_event = {}

                    if (
                        cloudtrail_event.get(
                            "readOnly"
                        )
                        is True
                    ):
                        continue

                    resources = []

                    for resource in item.get(
                        "Resources",
                        [],
                    ):
                        name = resource.get(
                            "ResourceName"
                        )

                        if not name:
                            continue

                        resources.append(
                            {
                                "entity_id": None,
                                "external_id": None,
                                "provider_resource_id":
                                    str(name),
                                "kind": (
                                    resource.get(
                                        "ResourceType"
                                    )
                                ),
                                "name": None,
                                "namespace": None,
                                "cluster_name": None,
                            }
                        )

                    event_time = item.get(
                        "EventTime"
                    )

                    if hasattr(
                        event_time,
                        "isoformat",
                    ):
                        event_time = (
                            event_time
                            .isoformat()
                        )

                    events.append(
                        {
                            "source":
                                "aws_cloudtrail",
                            "kind":
                                "infrastructure",
                            "external_id":
                                (
                                    "cloudtrail:"
                                    f"{item.get('EventId')}"
                                ),
                            "origin_change_id":
                                None,
                            "title":
                                (
                                    "AWS "
                                    f"{event_name}"
                                ),
                            "summary":
                                (
                                    cloudtrail_event
                                    .get(
                                        "eventSource"
                                    )
                                ),
                            "actor":
                                item.get(
                                    "Username"
                                ),
                            "occurred_at":
                                (
                                    event_time
                                    or now.isoformat()
                                ),
                            "environment":
                                None,
                            "provider":
                                "aws",
                            "account_id":
                                cloudtrail_event.get(
                                    "recipientAccountId"
                                ),
                            "region":
                                region,
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
                                resources,
                            "metadata": {
                                "event_name":
                                    event_name,
                                "event_source":
                                    cloudtrail_event
                                    .get(
                                        "eventSource"
                                    ),
                                "request_id":
                                    cloudtrail_event
                                    .get(
                                        "requestID"
                                    ),
                            },
                            "raw_payload": {},
                        }
                    )

                token = response.get(
                    "NextToken"
                )

                if not token:
                    break

        self.last_poll = now

        return events