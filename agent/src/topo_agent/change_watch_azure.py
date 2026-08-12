from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from typing import Any

import httpx
from azure.identity import (
    DefaultAzureCredential,
)


class AzureActivityChangePoller:
    def __init__(
        self,
        *,
        subscription_ids: list[str],
        overlap_seconds: int = 60,
    ) -> None:
        self.subscription_ids = (
            subscription_ids
        )

        self.overlap_seconds = (
            overlap_seconds
        )

        self.credential = (
            DefaultAzureCredential()
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

        token = (
            self.credential.get_token(
                "https://management.azure.com/"
                ".default"
            ).token
        )

        headers = {
            "Authorization":
                f"Bearer {token}"
        }

        events = []

        with httpx.Client(
            timeout=30.0
        ) as client:
            for subscription_id in (
                self.subscription_ids
            ):
                filter_value = (
                    "eventTimestamp ge "
                    f"'{start.isoformat()}' "
                    "and eventTimestamp le "
                    f"'{now.isoformat()}'"
                )

                url = (
                    "https://management.azure.com/"
                    "subscriptions/"
                    f"{subscription_id}/"
                    "providers/microsoft.insights/"
                    "eventtypes/management/values"
                )

                response = client.get(
                    url,
                    headers=headers,
                    params={
                        "api-version":
                            "2015-04-01",
                        "$filter":
                            filter_value,
                    },
                )

                response.raise_for_status()

                values = response.json().get(
                    "value",
                    [],
                )

                for item in values:
                    category = (
                        item.get(
                            "category"
                        )
                        or {}
                    )

                    category_value = (
                        category.get(
                            "value"
                        )
                        if isinstance(
                            category,
                            dict,
                        )
                        else str(category)
                    )

                    if (
                        str(
                            category_value
                        ).lower()
                        not in {
                            "administrative",
                            "security",
                            "policy",
                        }
                    ):
                        continue

                    operation = (
                        item.get(
                            "operationName"
                        )
                        or {}
                    )

                    if isinstance(
                        operation,
                        dict,
                    ):
                        operation_name = (
                            operation.get(
                                "localizedValue"
                            )
                            or operation.get(
                                "value"
                            )
                            or "Azure change"
                        )

                    else:
                        operation_name = (
                            str(operation)
                        )

                    resource_id = (
                        item.get(
                            "resourceId"
                        )
                    )

                    refs = []

                    if resource_id:
                        refs.append(
                            {
                                "entity_id":
                                    None,
                                "external_id":
                                    None,
                                "provider_resource_id":
                                    resource_id,
                                "kind": None,
                                "name": None,
                                "namespace":
                                    None,
                                "cluster_name":
                                    None,
                            }
                        )

                    events.append(
                        {
                            "source":
                                "azure_activity_log",
                            "kind":
                                (
                                    "security"
                                    if str(
                                        category_value
                                    ).lower()
                                    == "security"
                                    else
                                    "infrastructure"
                                ),
                            "external_id":
                                (
                                    "azure-activity:"
                                    f"{item.get('eventDataId')}"
                                ),
                            "origin_change_id":
                                None,
                            "title":
                                operation_name,
                            "summary":
                                None,
                            "actor":
                                item.get(
                                    "caller"
                                ),
                            "occurred_at":
                                (
                                    item.get(
                                        "eventTimestamp"
                                    )
                                    or now.isoformat()
                                ),
                            "environment":
                                None,
                            "provider":
                                "azure",
                            "account_id":
                                subscription_id,
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
                                "correlation_id":
                                    item.get(
                                        "correlationId"
                                    ),
                                "category":
                                    category_value,
                                "resource_group":
                                    item.get(
                                        "resourceGroupName"
                                    ),
                            },
                            "raw_payload": {},
                        }
                    )

        self.last_poll = now

        return events