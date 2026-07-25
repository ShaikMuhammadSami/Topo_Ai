from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from topo_agent import __version__
from topo_agent.client import (
    AgentApiClient,
    AgentClientError,
)
from topo_agent.config import (
    agent_home,
    load_agent_token,
)
from topo_agent.runtime_buffer import (
    RuntimeBatchBuffer,
)
from topo_agent.tetragon_parser import (
    TetragonAggregator,
)
from topo_agent.tetragon_tailer import (
    TetragonJsonTailer,
)


LOGGER = logging.getLogger(
    "topo-sensor"
)


def _boolean(
    value: str | None,
    default: bool,
) -> bool:
    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _integer(
    value: str | None,
    default: int,
) -> int:
    if value is None:
        return default

    try:
        return int(value)

    except ValueError:
        return default


def _sensor_id(
    cluster_name: str,
    node_name: str,
) -> str:
    digest = hashlib.sha256(
        (
            f"{cluster_name}|"
            f"{node_name}|tetragon"
        ).encode("utf-8")
    ).hexdigest()[:32]

    return f"runtime-sensor:{digest}"


@dataclass
class SensorConfig:
    backend_url: str

    agent_token: str

    cluster_name: str
    node_name: str
    sensor_id: str

    source_file: Path
    checkpoint_file: Path
    buffer_directory: Path

    batch_interval_seconds: int
    heartbeat_interval_seconds: int

    maximum_lines_per_read: int
    maximum_buffer_batches: int

    timeout_seconds: int
    max_retries: int
    retry_backoff_seconds: float

    verify_tls: bool

    @classmethod
    def from_environment(
        cls,
    ) -> "SensorConfig":
        token = (
            os.getenv(
                "TOPO_AGENT_TOKEN"
            )
            or load_agent_token()
        )

        if not token:
            raise ValueError(
                "TOPO_AGENT_TOKEN is "
                "not configured."
            )

        cluster_name = os.getenv(
            "TOPO_CLUSTER_NAME",
            "unknown-cluster",
        )

        node_name = os.getenv(
            "TOPO_SENSOR_NODE_NAME",
            os.getenv(
                "NODE_NAME",
                os.getenv(
                    "HOSTNAME",
                    "unknown-node",
                ),
            ),
        )

        source_file = Path(
            os.getenv(
                "TOPO_SENSOR_SOURCE_FILE",
                (
                    "/var/log/tetragon/"
                    "tetragon.log"
                ),
            )
        )

        state_directory = Path(
            os.getenv(
                "TOPO_SENSOR_STATE_DIR",
                str(
                    agent_home()
                    / "sensor"
                ),
            )
        )

        sensor_id = os.getenv(
            "TOPO_SENSOR_ID",
            _sensor_id(
                cluster_name,
                node_name,
            ),
        )

        return cls(
            backend_url=os.getenv(
                "TOPO_BACKEND_URL",
                (
                    "http://"
                    "127.0.0.1:8000"
                ),
            ).rstrip("/"),
            agent_token=token,
            cluster_name=cluster_name,
            node_name=node_name,
            sensor_id=sensor_id,
            source_file=source_file,
            checkpoint_file=(
                state_directory
                / "checkpoint.json"
            ),
            buffer_directory=(
                state_directory
                / "buffer"
            ),
            batch_interval_seconds=(
                _integer(
                    os.getenv(
                        "TOPO_SENSOR_BATCH_INTERVAL"
                    ),
                    15,
                )
            ),
            heartbeat_interval_seconds=(
                _integer(
                    os.getenv(
                        "TOPO_SENSOR_HEARTBEAT_INTERVAL"
                    ),
                    30,
                )
            ),
            maximum_lines_per_read=(
                _integer(
                    os.getenv(
                        "TOPO_SENSOR_MAX_LINES"
                    ),
                    10000,
                )
            ),
            maximum_buffer_batches=(
                _integer(
                    os.getenv(
                        "TOPO_SENSOR_MAX_BUFFER_BATCHES"
                    ),
                    200,
                )
            ),
            timeout_seconds=(
                _integer(
                    os.getenv(
                        "TOPO_SENSOR_TIMEOUT"
                    ),
                    30,
                )
            ),
            max_retries=(
                _integer(
                    os.getenv(
                        "TOPO_SENSOR_MAX_RETRIES"
                    ),
                    3,
                )
            ),
            retry_backoff_seconds=float(
                os.getenv(
                    "TOPO_SENSOR_RETRY_BACKOFF",
                    "1.0",
                )
            ),
            verify_tls=_boolean(
                os.getenv(
                    "TOPO_VERIFY_TLS"
                ),
                True,
            ),
        )


class TopoRuntimeSensor:
    def __init__(
        self,
        config: SensorConfig,
    ) -> None:
        self.config = config

        self.client = AgentApiClient(
            backend_url=(
                config.backend_url
            ),
            token=(
                config.agent_token
            ),
            timeout_seconds=(
                config.timeout_seconds
            ),
            verify_tls=(
                config.verify_tls
            ),
            max_retries=(
                config.max_retries
            ),
            retry_backoff_seconds=(
                config
                .retry_backoff_seconds
            ),
        )

        self.tailer = TetragonJsonTailer(
            source_file=(
                config.source_file
            ),
            checkpoint_file=(
                config.checkpoint_file
            ),
        )

        self.aggregator = (
            TetragonAggregator()
        )

        self.buffer = RuntimeBatchBuffer(
            config.buffer_directory,
            maximum_batches=(
                config
                .maximum_buffer_batches
            ),
        )

        self.total_processed = 0
        self.total_dropped = 0
        self.total_parser_errors = 0

        self.last_error: str | None = None

    def close(
        self,
    ) -> None:
        self.client.close()

    def doctor(
        self,
    ) -> dict[str, Any]:
        source_status = (
            "available"
            if self.config
            .source_file.exists()
            else "missing"
        )

        source_readable = False

        if (
            self.config
            .source_file.exists()
        ):
            try:
                with (
                    self.config
                    .source_file.open(
                        "r",
                        encoding="utf-8",
                        errors="replace",
                    )
                ):
                    source_readable = True

            except OSError:
                source_readable = False

        health = self.client.health()

        return {
            "sensor_id":
                self.config.sensor_id,
            "node_name":
                self.config.node_name,
            "cluster_name":
                self.config.cluster_name,
            "backend":
                health.get(
                    "status",
                    "available",
                ),
            "source_file":
                str(
                    self.config
                    .source_file
                ),
            "source_status":
                source_status,
            "source_readable":
                source_readable,
            "source_offset":
                self.tailer.offset,
            "buffered_batches":
                self.buffer.size(),
            "version": __version__,
        }

    def read_events(
        self,
    ) -> int:
        events, malformed = (
            self.tailer.read_available(
                maximum_lines=(
                    self.config
                    .maximum_lines_per_read
                )
            )
        )

        self.aggregator.record_parser_errors(
            malformed
        )

        for event in events:
            try:
                self.aggregator.ingest(
                    event
                )

            except Exception:
                self.aggregator.parser_error_count += 1

                LOGGER.exception(
                    "Unable to parse "
                    "Tetragon event."
                )

        return len(events)

    def replay_buffer(
        self,
    ) -> int:
        sent = 0

        for path in self.buffer.pending():
            batch = self.buffer.load(
                path
            )

            try:
                self.client.submit_runtime_batch(
                    batch
                )

            except AgentClientError as exc:
                self.last_error = str(exc)
                break

            self.buffer.remove(path)
            sent += 1

        return sent

    def flush(
        self,
    ) -> dict[str, Any] | None:
        batch = (
            self.aggregator.build_batch(
                sensor_id=(
                    self.config.sensor_id
                ),
                node_name=(
                    self.config.node_name
                ),
                cluster_name=(
                    self.config.cluster_name
                ),
                version=__version__,
                buffered_batch_count=(
                    self.buffer.size()
                ),
                source_file=str(
                    self.config
                    .source_file
                ),
                source_file_offset=(
                    self.tailer.offset
                ),
                heartbeat_interval_seconds=(
                    self.config
                    .heartbeat_interval_seconds
                ),
            )
        )

        if batch is None:
            return None

        self.total_processed += int(
            batch[
                "processed_event_count"
            ]
        )

        self.total_dropped += int(
            batch[
                "dropped_event_count"
            ]
        )

        self.total_parser_errors += int(
            batch[
                "parser_error_count"
            ]
        )

        try:
            receipt = (
                self.client
                .submit_runtime_batch(
                    batch
                )
            )

        except AgentClientError as exc:
            self.buffer.enqueue(
                batch
            )

            self.last_error = str(exc)

            LOGGER.warning(
                "Runtime batch buffered: %s",
                exc,
            )

            return None

        self.last_error = None

        return receipt

    def heartbeat(
        self,
    ) -> dict[str, Any]:
        return self.client.sensor_heartbeat(
            {
                "sensor_id":
                    self.config.sensor_id,
                "node_name":
                    self.config.node_name,
                "cluster_name":
                    self.config.cluster_name,
                "source": "tetragon",
                "version": __version__,
                "heartbeat_interval_seconds":
                    self.config
                    .heartbeat_interval_seconds,
                "processed_event_count":
                    self.total_processed,
                "dropped_event_count":
                    self.total_dropped,
                "parser_error_count":
                    self
                    .total_parser_errors,
                "buffered_batch_count":
                    self.buffer.size(),
                "source_file": str(
                    self.config
                    .source_file
                ),
                "source_file_offset":
                    self.tailer.offset,
                "last_error":
                    self.last_error,
                "capabilities": [
                    (
                        "ebpf.process."
                        "lifecycle"
                    ),
                    (
                        "ebpf.network."
                        "connect"
                    ),
                    (
                        "ebpf.network."
                        "accept"
                    ),
                    (
                        "ebpf.dns."
                        "resolver"
                    ),
                ],
                "metadata": {
                    "batch_interval_seconds":
                        self.config
                        .batch_interval_seconds,
                },
            }
        )

    def run_once(
        self,
    ) -> dict[str, Any]:
        replayed = (
            self.replay_buffer()
        )

        events = self.read_events()

        receipt = self.flush()

        heartbeat = self.heartbeat()

        return {
            "events_read": events,
            "replayed_batches":
                replayed,
            "receipt": receipt,
            "heartbeat": heartbeat,
            "buffered_batches":
                self.buffer.size(),
        }

    def run(
        self,
    ) -> None:
        LOGGER.info(
            "Topo sensor started on "
            "node %s.",
            self.config.node_name,
        )

        next_flush = time.monotonic()
        next_heartbeat = time.monotonic()

        while True:
            self.read_events()

            now = time.monotonic()

            if now >= next_flush:
                self.replay_buffer()
                self.flush()

                next_flush = (
                    now
                    + self.config
                    .batch_interval_seconds
                )

            if now >= next_heartbeat:
                try:
                    self.heartbeat()

                except AgentClientError as exc:
                    self.last_error = (
                        str(exc)
                    )

                    LOGGER.warning(
                        "Sensor heartbeat "
                        "failed: %s",
                        exc,
                    )

                next_heartbeat = (
                    now
                    + self.config
                    .heartbeat_interval_seconds
                )

            time.sleep(1)