from __future__ import annotations

import logging
from topo_agent.security import safe_exception_message
import time
from typing import Any

from topo_agent import __version__
from topo_agent.buffer import (
    SnapshotBuffer,
)
from topo_agent.client import (
    AgentApiClient,
    AgentClientError,
)
from topo_agent.config import (
    AgentConfig,
)
from topo_agent.plugin_manager import (
    PluginManager,
)


LOGGER = logging.getLogger(
    "topo-agent"
)


class AgentRunner:
    def __init__(
        self,
        *,
        config: AgentConfig,
        client: AgentApiClient,
        plugin_manager:
            PluginManager,
        buffer: SnapshotBuffer,
        change_watch_runner: Any | None = None,
    ) -> None:
        self.config = config
        self.client = client

        self.plugin_manager = (
            plugin_manager
        )

        self.buffer = buffer
        self.change_watch_runner = (
            change_watch_runner
        )

        self.last_collection_status: (
            str | None
        ) = None

        self.last_error: (
            str | None
        ) = None

    def heartbeat(
        self,
    ) -> dict[str, Any]:
        return self.client.heartbeat(
            {
                "version":
                    __version__,
                "buffered_item_count":
                    self.buffer.size(),
                "last_collection_status":
                    self
                    .last_collection_status,
                "last_error":
                    self.last_error,
                "capabilities":
                    self
                    .plugin_manager
                    .capabilities(),
                "metadata": {
                    "enabled_plugins":
                        self
                        .plugin_manager
                        .plugin_names(),
                    "plugins":
                        self
                        .plugin_manager
                        .status_snapshot(),
                },
            }
        )

    def replay_buffer(
        self,
    ) -> int:
        sent = 0

        for path in self.buffer.pending():
            payload = self.buffer.load(
                path
            )

            try:
                self.client.submit_snapshot(
                    payload
                )

            except AgentClientError as exc:
                self.last_error = safe_exception_message(exc, "Agent heartbeat failed")

                LOGGER.warning(
                    "Unable to replay "
                    "buffered snapshot %s: %s",
                    path.name,
                    exc,
                )

                break

            self.buffer.remove(path)
            sent += 1

        return sent

    def collect_once(
        self,
        *,
        checkpoint_reason: str = (
            "periodic_reconcile"
        ),
        trigger_event_ids: (
            list[str] | None
        ) = None,
        trigger_signal_ids: (
            list[str] | None
        ) = None,
        trigger_signal_observations: (
            dict[str, str] | None
        ) = None,
    ) -> dict[str, Any] | None:
        LOGGER.info(
            "Starting plugin-based "
            "topology collection."
        )

        try:
            submission = (
                self.plugin_manager
                .collect()
            )
            metadata = dict(
                submission.get(
                    "metadata",
                    {},
                )
            )
            metadata[
                "checkpoint_reason"
            ] = checkpoint_reason
            metadata[
                "trigger_event_ids"
            ] = list(
                dict.fromkeys(
                    trigger_event_ids or []
                )
            )
            metadata[
                "trigger_signal_ids"
            ] = list(
                dict.fromkeys(
                    trigger_signal_ids or []
                )
            )
            metadata[
                "trigger_signal_observations"
            ] = dict(
                trigger_signal_observations or {}
            )
            submission["metadata"] = metadata

        except Exception as exc:
            self.last_collection_status = (
                "collection_failed"
            )

            self.last_error = safe_exception_message(exc, "Topology collection failed")

            LOGGER.exception(
                "Topology collection failed."
            )

            return None

        collection_status = (
            submission.get(
                "metadata",
                {},
            ).get(
                "collection_status",
                "unknown",
            )
        )

        try:
            receipt = (
                self.client
                .submit_snapshot(
                    submission
                )
            )

        except AgentClientError as exc:
            buffered_path = (
                self.buffer.enqueue(
                    submission
                )
            )

            self.last_collection_status = (
                "buffered"
            )

            self.last_error = safe_exception_message(exc, "Agent collection failed")

            LOGGER.warning(
                "Snapshot submission failed. "
                "Buffered at %s: %s",
                buffered_path,
                exc,
            )

            return None

        self.last_collection_status = (
            collection_status
        )

        self.last_error = None

        LOGGER.info(
            "Snapshot accepted: %s",
            receipt.get(
                "snapshot_id"
            ),
        )

        return receipt

    def process_change_watch_once(
        self,
    ) -> dict[str, Any]:
        if self.change_watch_runner is None:
            return {
                "checkpoint_requested": False,
                "failure_signal_count": 0,
                "snapshot_id": None,
            }

        watch_result = (
            self.change_watch_runner.run_once()
        )
        trigger_ids: list[str] = []
        checkpoint_requested = False
        failure_signals: list[
            dict[str, Any]
        ] = []

        for value in watch_result.values():
            if not isinstance(value, dict):
                continue

            checkpoint_requested = (
                checkpoint_requested
                or bool(
                    value.get(
                        "checkpoint_requested"
                    )
                )
            )
            trigger_ids.extend(
                str(item)
                for item in value.get(
                    "event_ids",
                    [],
                )
            )
            failure_signals.extend(
                item
                for item in value.get(
                    "failure_signals",
                    [],
                )
                if isinstance(item, dict)
            )

        receipt = None

        if checkpoint_requested or failure_signals:
            failure_signal_ids = [
                str(signal["signal_id"])
                for signal in failure_signals
                if signal.get("signal_id")
            ]
            failure_observations = {
                str(signal["signal_id"]): str(
                    signal["first_observed_at"]
                )
                for signal in failure_signals
                if signal.get("signal_id")
                and signal.get("first_observed_at")
            }
            receipt = self.collect_once(
                checkpoint_reason=(
                    "incident_boundary"
                    if failure_signals
                    else "automatic_change"
                ),
                trigger_event_ids=trigger_ids,
                trigger_signal_ids=(
                    failure_signal_ids
                ),
                trigger_signal_observations=(
                    failure_observations
                ),
            )

        if failure_signals:
            pinned_snapshot_id = (
                receipt.get("snapshot_id")
                if receipt is not None
                else None
            )

            if pinned_snapshot_id:
                failure_signals = [
                    {
                        **signal,
                        "topology_snapshot_id": (
                            pinned_snapshot_id
                        ),
                    }
                    for signal in failure_signals
                ]

            self.client.submit_failure_signals(
                failure_signals
            )

            if receipt is not None:
                (
                    self.change_watch_runner
                    .ack_failure_signals(
                        failure_signals
                    )
                )

        return {
            "checkpoint_requested": (
                checkpoint_requested
            ),
            "failure_signal_count": len(
                failure_signals
            ),
            "snapshot_id": (
                receipt.get("snapshot_id")
                if receipt is not None
                else None
            ),
        }

    def run(
        self,
    ) -> None:
        LOGGER.info(
            "Topo Agent started for "
            "cluster %s with plugins: %s",
            self.config.cluster_name,
            ", ".join(
                self.plugin_manager
                .plugin_names()
            ),
        )

        next_heartbeat = 0.0
        next_collection = 0.0
        next_change_watch = 0.0

        while True:
            now = time.monotonic()

            if now >= next_heartbeat:
                try:
                    self.heartbeat()

                except AgentClientError as exc:
                    LOGGER.warning(
                        "Heartbeat failed: %s",
                        exc,
                    )

                next_heartbeat = (
                    now
                    + self.config
                    .heartbeat_interval_seconds
                )

            if (
                self.change_watch_runner
                is not None
                and now >= next_change_watch
            ):
                try:
                    lifecycle = (
                        self.process_change_watch_once()
                    )

                    if lifecycle["snapshot_id"]:
                        next_collection = (
                            now
                            + self.config
                            .collection_interval_seconds
                        )

                except Exception:
                    LOGGER.exception(
                        "Change-watch cycle failed."
                    )

                next_change_watch = (
                    now
                    + self.config
                    .change_watch_interval_seconds
                )

            if now >= next_collection:
                try:
                    replayed = (
                        self.replay_buffer()
                    )

                    if replayed:
                        LOGGER.info(
                            "Replayed %s "
                            "buffered snapshots.",
                            replayed,
                        )

                    self.collect_once()

                except Exception:
                    LOGGER.exception(
                        "Unexpected collection "
                        "cycle failure."
                    )

                next_collection = (
                    now
                    + self.config
                    .collection_interval_seconds
                )

            time.sleep(1)

    def close(
        self,
    ) -> None:
        self.plugin_manager.close()
        self.client.close()
