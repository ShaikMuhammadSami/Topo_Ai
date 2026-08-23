from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from hashlib import sha256
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
}


FAILURE_REASONS = {
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


def _failure_category(reason: str) -> str:
    normalized = reason.casefold()

    if "image" in normalized or "pull" in normalized:
        return "image"

    if "schedul" in normalized:
        return "scheduling"

    if any(
        value in normalized
        for value in ("mount", "volume", "attach")
    ):
        return "storage"

    return "health"


class KubernetesChangePoller:
    def __init__(
        self,
        *,
        cluster_name: str,
        namespaces: list[str] | None = None,
        kube_context: str | None = None,
        overlap_seconds: int = 60,
    ) -> None:
        self.cluster_name = (
            cluster_name
        )

        self.overlap_seconds = (
            overlap_seconds
        )
        self.namespaces = sorted(
            set(namespaces or [])
        )

        try:
            config.load_incluster_config()

        except Exception:
            config.load_kube_config(
                context=kube_context
            )

        self.api = (
            client.CoreV1Api()
        )

        self.last_poll = (
            datetime.now(
                timezone.utc
            )
            - timedelta(minutes=5)
        )
        self._failure_signals: list[
            dict[str, Any]
        ] = []
        self._failure_versions: dict[
            str,
            tuple[str, int],
        ] = {}
        self._pending_failure_versions: dict[
            str,
            tuple[str, tuple[str, int]],
        ] = {}

    def drain_failure_signals(
        self,
    ) -> list[dict[str, Any]]:
        signals = self._failure_signals
        self._failure_signals = []
        return signals

    def ack_failure_signals(
        self,
        signals: list[dict[str, Any]],
    ) -> None:
        for signal in signals:
            signal_id = str(
                signal.get("signal_id") or ""
            )
            pending = (
                self._pending_failure_versions.pop(
                    signal_id,
                    None,
                )
            )

            if pending is None:
                continue

            key, version = pending
            self._failure_versions[key] = version

        while len(self._failure_versions) > 5000:
            oldest = next(
                iter(self._failure_versions)
            )
            self._failure_versions.pop(oldest)

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

        if self.namespaces:
            items = []

            for namespace in self.namespaces:
                response = (
                    self.api.list_namespaced_event(
                        namespace=namespace
                    )
                )
                items.extend(response.items)

        else:
            response = (
                self.api
                .list_event_for_all_namespaces()
            )
            items = response.items

        events = []
        failure_signals: list[
            dict[str, Any]
        ] = []

        for item in items:
            reason = item.reason or ""

            if (
                reason not in CHANGE_REASONS
                and reason not in FAILURE_REASONS
            ):
                continue

            source_timestamp = (
                item.event_time
                or item.last_timestamp
                or item.first_timestamp
            )

            if source_timestamp is None:
                continue

            source_time_available = (
                source_timestamp.tzinfo
                is not None
            )
            timestamp = (
                source_timestamp.astimezone(
                    timezone.utc
                )
                if source_time_available
                else now
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

            if reason in FAILURE_REASONS:
                event_uid = str(
                    item.metadata.uid or ""
                )
                fingerprint_value = "|".join(
                    [
                        self.cluster_name,
                        namespace or "",
                        str(external_id or ""),
                        kind,
                        name,
                        reason,
                        str(
                            item.reporting_component
                            or ""
                        ),
                    ]
                )
                fingerprint = sha256(
                    fingerprint_value.encode(
                        "utf-8"
                    )
                ).hexdigest()
                signal_identity = (
                    event_uid
                    or fingerprint[:32]
                )
                occurrence_count = max(
                    int(item.count or 1),
                    1,
                )
                first_source_timestamp = (
                    item.first_timestamp
                    or item.event_time
                    or source_timestamp
                )
                last_source_timestamp = (
                    item.last_timestamp
                    or item.event_time
                    or source_timestamp
                )
                failure_source_time_available = (
                    first_source_timestamp.tzinfo
                    is not None
                )
                first_observed_at = (
                    first_source_timestamp.astimezone(
                        timezone.utc
                    )
                    if failure_source_time_available
                    else now
                )
                last_observed_at = (
                    last_source_timestamp.astimezone(
                        timezone.utc
                    )
                    if last_source_timestamp.tzinfo
                    is not None
                    else now
                )

                failure_version_key = (
                    event_uid
                    or fingerprint
                )
                failure_version = (
                    last_observed_at.isoformat(),
                    occurrence_count,
                )

                if (
                    self._failure_versions.get(
                        failure_version_key
                    )
                    == failure_version
                ):
                    continue

                signal_id = (
                    "signal:kubernetes-event:"
                    f"{self.cluster_name}:"
                    f"{signal_identity}"
                )
                self._pending_failure_versions[
                    signal_id
                ] = (
                    failure_version_key,
                    failure_version,
                )
                failure_signals.append(
                    {
                        "signal_id": signal_id,
                        "fingerprint": fingerprint,
                        "signal_type": (
                            "kubernetes_event"
                        ),
                        "severity": "error",
                        "category": (
                            _failure_category(reason)
                        ),
                        "source_system": "kubernetes",
                        "title": (
                            f"{reason} on {kind}/{name}"
                        ),
                        "summary": (
                            item.message
                            or "Kubernetes failure event"
                        ),
                        "reason": reason,
                        "action": item.action,
                        "first_observed_at": (
                            first_observed_at.isoformat()
                        ),
                        "last_observed_at": (
                            last_observed_at.isoformat()
                        ),
                        "temporal": {
                            "temporal_version": "tc3.v1",
                            "effective_at": (
                                first_observed_at.isoformat()
                            ),
                            "source_event_at": (
                                first_observed_at.isoformat()
                                if failure_source_time_available
                                else None
                            ),
                            "observed_at": now.isoformat(),
                            "recorded_at": None,
                            "valid_from": None,
                            "valid_to": None,
                            "time_origin": (
                                "source_reported"
                                if failure_source_time_available
                                else "topo_observed"
                            ),
                            "time_quality": (
                                "exact"
                                if failure_source_time_available
                                else "fallback"
                            ),
                            "source_field": (
                                "KubernetesEvent.first_timestamp/"
                                "event_time"
                                if failure_source_time_available
                                else "topo_agent.observed_at"
                            ),
                            "source_time_authoritative": (
                                failure_source_time_available
                            ),
                            "status": "complete",
                        },
                        "occurrence_count": (
                            occurrence_count
                        ),
                        "cluster_name": (
                            self.cluster_name
                        ),
                        "namespace": namespace,
                        "topology_snapshot_id": None,
                        "involved_entity_id": None,
                        "involved_object_uid": (
                            str(external_id)
                            if external_id
                            else None
                        ),
                        "involved_object_kind": kind,
                        "involved_object_name": name,
                        "reporting_controller": (
                            item.reporting_component
                        ),
                        "reporting_instance": None,
                        "attributes": {
                            "event_type": item.type,
                            "observation_source": (
                                "kubernetes_event_watch"
                            ),
                        },
                        "raw_payload": {},
                    }
                )

            if reason not in CHANGE_REASONS:
                continue

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
                        "_temporal": {
                            "source_time_available": (
                                source_time_available
                            ),
                            "source_field": (
                                "KubernetesEvent.event_time/"
                                "last_timestamp/first_timestamp"
                            ),
                        },
                    },
                    "raw_payload": {},
                }
            )

        self.last_poll = now
        self._failure_signals = failure_signals

        return events
