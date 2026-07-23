from __future__ import annotations

import logging
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
    ) -> None:
        self.config = config
        self.client = client

        self.plugin_manager = (
            plugin_manager
        )

        self.buffer = buffer

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
                self.last_error = str(exc)

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

        except Exception as exc:
            self.last_collection_status = (
                "collection_failed"
            )

            self.last_error = (
                f"{type(exc).__name__}: "
                f"{exc}"
            )

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

            self.last_error = str(exc)

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