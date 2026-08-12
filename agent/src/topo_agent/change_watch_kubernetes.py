from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from typing import Any

from kubernetes import (
    client,
    config,
)


CHANGE_REASONS = {
    "ScalingReplicaSet",
    "SuccessfulCreate",
    "SuccessfulDelete",
    "Killing",
    "Pulled",
    "Failed",
    "FailedCreate",
    "FailedScheduling",
    "BackOff",
}


class KubernetesChangePoller:
    def __init__(
        self,
        *,
        cluster_name: str,
        overlap_seconds: int = 60,
    ) -> None:
        self.cluster_name = (
            cluster_name
        )

        self.overlap_seconds = (
            overlap_seconds
        )

        try:
            config.load_incluster_config()

        except Exception:
            config.load_kube_config()

        self.api = (
            client.CoreV1Api()
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

        response = (
            self.api
            .list_event_for_all_namespaces()
        )

        events = []

        for item in response.items:
            reason = item.reason or ""

            if reason not in CHANGE_REASONS:
                continue

            timestamp = (
                item.event_time
                or item.last_timestamp
                or item.first_timestamp
            )

            if timestamp is None:
                continue

            if (
                timestamp.tzinfo
                is None
            ):
                timestamp = (
                    timestamp.replace(
                        tzinfo=timezone.utc
                    )
                )

            if timestamp < start:
                continue

            involved = (
                item.involved_object
            )

            namespace = (
                involved.namespace
                or item.metadata.namespace
            )

            kind = (
                involved.kind
                or ""
            )

            name = (
                involved.name
                or ""
            )

            external_id = (
                involved.uid
            )

            events.append(
                {
                    "source":
                        "kubernetes",
                    "kind":
                        (
                            "scaling"
                            if reason
                            == "ScalingReplicaSet"
                            else
                            "topology"
                        ),
                    "external_id":
                        (
                            "k8s-event:"
                            f"{item.metadata.uid}"
                        ),
                    "origin_change_id":
                        None,
                    "title":
                        (
                            f"{reason} on "
                            f"{kind}/{name}"
                        ),
                    "summary":
                        item.message,
                    "actor":
                        item.reporting_component,
                    "occurred_at":
                        timestamp.isoformat(),
                    "environment":
                        None,
                    "provider":
                        "kubernetes",
                    "account_id":
                        None,
                    "region":
                        None,
                    "cluster_name":
                        self.cluster_name,
                    "namespace":
                        namespace,
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
                    "entity_refs": [
                        {
                            "entity_id":
                                None,
                            "external_id":
                                external_id,
                            "provider_resource_id":
                                None,
                            "kind":
                                (
                                    "Kubernetes"
                                    + kind
                                ),
                            "name":
                                name,
                            "namespace":
                                namespace,
                            "cluster_name":
                                self.cluster_name,
                        }
                    ],
                    "metadata": {
                        "reason":
                            reason,
                        "event_type":
                            item.type,
                    },
                    "raw_payload": {},
                }
            )

        self.last_poll = now

        return events