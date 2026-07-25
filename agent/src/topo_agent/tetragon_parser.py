from __future__ import annotations

import hashlib
from collections import Counter
from datetime import (
    datetime,
    timezone,
)
from typing import Any
from uuid import uuid4


EVENT_KEYS = (
    "process_connect",
    "process_accept",
    "process_exec",
    "process_exit",
    "process_kprobe",
    "process_tracepoint",
)


def _utc_now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _event_payload(
    event: dict[str, Any],
) -> tuple[
    str | None,
    dict[str, Any] | None,
]:
    for key in EVENT_KEYS:
        value = event.get(key)

        if isinstance(value, dict):
            return key, value

    return None, None


def _integer(
    value: Any,
) -> int | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return int(value)

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    try:
        text = str(value).strip()

        if not text:
            return None

        return int(
            text,
            0,
        )

    except (
        ValueError,
        TypeError,
    ):
        return None


def _first_string(
    value: Any,
    keys: set[str],
) -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if (
                key.lower() in keys
                and isinstance(
                    item,
                    (str, int, float),
                )
            ):
                text = str(item).strip()

                if text:
                    return text

        for item in value.values():
            result = _first_string(
                item,
                keys,
            )

            if result:
                return result

    if isinstance(value, list):
        for item in value:
            result = _first_string(
                item,
                keys,
            )

            if result:
                return result

    return None


def _first_integer(
    value: Any,
    keys: set[str],
) -> int | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in keys:
                result = _integer(item)

                if result is not None:
                    return result

        for item in value.values():
            result = _first_integer(
                item,
                keys,
            )

            if result is not None:
                return result

    if isinstance(value, list):
        for item in value:
            result = _first_integer(
                item,
                keys,
            )

            if result is not None:
                return result

    return None


def _container_id(
    value: Any,
) -> str | None:
    result = _first_string(
        value,
        {
            "container_id",
            "containerid",
            "docker_id",
            "dockerid",
        },
    )

    if not result:
        return None

    if "://" in result:
        result = result.split(
            "://",
            1,
        )[1]

    return result


def _process_identity(
    payload: dict[str, Any],
) -> dict[str, Any]:
    process = payload.get(
        "process",
        {},
    )

    if not isinstance(process, dict):
        process = {}

    pod = process.get(
        "pod",
        payload.get(
            "pod",
            {},
        ),
    )

    if not isinstance(pod, dict):
        pod = {}

    container = pod.get(
        "container",
        process.get(
            "container",
            {},
        ),
    )

    if not isinstance(container, dict):
        container = {}

    workload = pod.get(
        "workload",
        {},
    )

    workload_name = None

    if isinstance(workload, dict):
        workload_name = (
            workload.get("name")
            or workload.get(
                "workload_name"
            )
        )

    elif workload:
        workload_name = str(
            workload
        )

    binary = (
        process.get("binary")
        or process.get("name")
        or payload.get("binary")
    )

    pid = _integer(
        process.get("pid")
        or process.get("tid")
    )

    return {
        "namespace": (
            pod.get("namespace")
            or process.get(
                "namespace"
            )
        ),
        "pod_name": (
            pod.get("name")
            or pod.get("pod_name")
        ),
        "pod_uid": (
            pod.get("uid")
            or pod.get("pod_uid")
        ),
        "workload_name":
            workload_name,
        "container_id": (
            _container_id(container)
            or _container_id(process)
            or _container_id(payload)
        ),
        "binary": (
            str(binary)
            if binary
            else None
        ),
        "pid": pid,
        "exec_id": (
            process.get("exec_id")
            or process.get("execid")
        ),
        "parent_exec_id": (
            process.get(
                "parent_exec_id"
            )
            or process.get(
                "parent_execid"
            )
        ),
    }


def _socket_candidate(
    value: Any,
) -> dict[str, Any] | None:
    if isinstance(value, dict):
        address_keys = {
            "address",
            "ip",
            "daddr",
            "destination_address",
            "remote_address",
        }

        port_keys = {
            "port",
            "dport",
            "destination_port",
            "remote_port",
        }

        lowered = {
            str(key).lower()
            for key in value
        }

        # A dictionary is considered a socket value
        # only when it contains both an address field
        # and a port field.
        if (
            lowered & address_keys
            and lowered & port_keys
        ):
            return value

        # Tetragon commonly wraps socket values in
        # one of these fields.
        for preferred in (
            "sock_arg",
            "socket",
            "sock",
            "destination",
            "remote",
        ):
            nested = value.get(preferred)

            if isinstance(
                nested,
                (dict, list),
            ):
                result = _socket_candidate(
                    nested
                )

                if result is not None:
                    return result

        # Search other nested event arguments.
        for nested in value.values():
            result = _socket_candidate(
                nested
            )

            if result is not None:
                return result

    if isinstance(value, list):
        for item in value:
            result = _socket_candidate(
                item
            )

            if result is not None:
                return result

    return None

def _socket_identity(
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    candidate = _socket_candidate(
        payload
    )

    if candidate is None:
        return None

    destination = candidate.get(
        "destination",
        {},
    )

    if not isinstance(
        destination,
        dict,
    ):
        destination = {}

    remote = candidate.get(
        "remote",
        {},
    )

    if not isinstance(remote, dict):
        remote = {}

    destination_address = (
        candidate.get("daddr")
        or candidate.get(
            "destination_address"
        )
        or candidate.get(
            "remote_address"
        )
        or candidate.get("address")
        or candidate.get("ip")
        or destination.get("ip")
        or destination.get("address")
        or remote.get("ip")
        or remote.get("address")
    )

    destination_port = (
        _integer(
            candidate.get("dport")
        )
        or _integer(
            candidate.get(
                "destination_port"
            )
        )
        or _integer(
            candidate.get(
                "remote_port"
            )
        )
        or _integer(
            candidate.get("port")
        )
        or _integer(
            destination.get("port")
        )
        or _integer(
            remote.get("port")
        )
    )

    if (
        not destination_address
        or destination_port is None
    ):
        return None

    protocol = (
        candidate.get("protocol")
        or candidate.get("proto")
        or payload.get("protocol")
        or "tcp"
    )

    source_address = (
        candidate.get("saddr")
        or candidate.get(
            "source_address"
        )
        or candidate.get(
            "local_address"
        )
    )

    source_port = (
        _integer(
            candidate.get("sport")
        )
        or _integer(
            candidate.get(
                "source_port"
            )
        )
        or _integer(
            candidate.get(
                "local_port"
            )
        )
    )

    return {
        "destination_address":
            str(destination_address),
        "destination_port":
            destination_port,
        "protocol":
            str(protocol).lower(),
        "source_address": (
            str(source_address)
            if source_address
            else None
        ),
        "source_port":
            source_port,
    }


def _dns_name(
    payload: dict[str, Any],
    destination_port: int,
) -> str | None:
    if destination_port != 53:
        return None

    return _first_string(
        payload,
        {
            "dns_name",
            "query_name",
            "queryname",
            "fqdn",
            "dns_query",
        },
    )


def _return_value(
    payload: dict[str, Any],
) -> int | None:
    direct = (
        payload.get("return_value")
        or payload.get("return")
        or payload.get("result")
    )

    result = _integer(direct)

    if result is not None:
        return result

    return _first_integer(
        direct,
        {
            "value",
            "int_arg",
            "return_value",
        },
    )


def _event_time(
    event: dict[str, Any],
) -> str:
    value = (
        event.get("time")
        or event.get("timestamp")
    )

    return (
        str(value)
        if value
        else _utc_now_iso()
    )


def _dependency_key(
    source: dict[str, Any],
    socket_value: dict[str, Any],
    dns_name: str | None,
    direction: str,
) -> str:
    identity = "|".join(
        [
            str(
                source.get(
                    "namespace"
                )
                or ""
            ),
            str(
                source.get(
                    "pod_uid"
                )
                or ""
            ),
            str(
                source.get(
                    "pod_name"
                )
                or ""
            ),
            str(
                source.get(
                    "container_id"
                )
                or ""
            ),
            str(
                source.get(
                    "binary"
                )
                or ""
            ),
            str(
                socket_value[
                    "destination_address"
                ]
            ),
            str(
                socket_value[
                    "destination_port"
                ]
            ),
            str(
                socket_value[
                    "protocol"
                ]
            ),
            dns_name or "",
            direction,
        ]
    )

    return hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()


def _process_key(
    process: dict[str, Any],
    observed_at: str,
) -> str:
    identity = "|".join(
        [
            str(
                process.get("exec_id")
                or ""
            ),
            str(
                process.get(
                    "container_id"
                )
                or ""
            ),
            str(
                process.get("pid")
                or ""
            ),
            str(
                process.get("binary")
                or ""
            ),
            observed_at,
        ]
    )

    return hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()


class TetragonAggregator:
    def __init__(
        self,
    ) -> None:
        self.window_start = (
            _utc_now_iso()
        )

        self.dependencies: dict[
            str,
            dict[str, Any],
        ] = {}

        self.processes: dict[
            str,
            dict[str, Any],
        ] = {}

        self.event_types: Counter[
            str
        ] = Counter()

        self.processed_event_count = 0
        self.dropped_event_count = 0
        self.parser_error_count = 0

    def record_parser_errors(
        self,
        count: int,
    ) -> None:
        self.parser_error_count += count

    def ingest(
        self,
        event: dict[str, Any],
    ) -> None:
        event_name, payload = (
            _event_payload(event)
        )

        if (
            event_name is None
            or payload is None
        ):
            self.dropped_event_count += 1
            return

        self.processed_event_count += 1
        self.event_types[event_name] += 1

        observed_at = _event_time(
            event
        )

        process = _process_identity(
            payload
        )

        if event_name in {
            "process_exec",
            "process_exit",
        }:
            binary = process.get(
                "binary"
            )

            if binary:
                key = (
                    process.get(
                        "exec_id"
                    )
                    or _process_key(
                        process,
                        observed_at,
                    )
                )

                record = self.processes.get(
                    str(key)
                )

                if record is None:
                    record = {
                        "exec_id":
                            process.get(
                                "exec_id"
                            ),
                        "pid":
                            process.get("pid"),
                        "binary": binary,
                        "namespace":
                            process.get(
                                "namespace"
                            ),
                        "pod_name":
                            process.get(
                                "pod_name"
                            ),
                        "pod_uid":
                            process.get(
                                "pod_uid"
                            ),
                        "container_id":
                            process.get(
                                "container_id"
                            ),
                        "parent_exec_id":
                            process.get(
                                "parent_exec_id"
                            ),
                        "exec_count": 0,
                        "exit_count": 0,
                        "last_exit_code":
                            None,
                        "last_signal": None,
                        "first_seen_at":
                            observed_at,
                        "last_seen_at":
                            observed_at,
                        "metadata": {},
                    }

                    self.processes[
                        str(key)
                    ] = record

                record["last_seen_at"] = (
                    observed_at
                )

                if (
                    event_name
                    == "process_exec"
                ):
                    record["exec_count"] += 1

                else:
                    record["exit_count"] += 1

                    record[
                        "last_exit_code"
                    ] = _first_integer(
                        payload,
                        {
                            "status",
                            "exit_code",
                            "code",
                        },
                    )

                    record[
                        "last_signal"
                    ] = _first_string(
                        payload,
                        {
                            "signal",
                            "signal_name",
                        },
                    )

        socket_value = _socket_identity(
            payload
        )

        if socket_value is None:
            return

        function_name = (
            str(
                payload.get(
                    "function_name"
                )
                or payload.get(
                    "function"
                )
                or payload.get(
                    "call"
                )
                or ""
            ).lower()
        )

        network_event = (
            event_name
            in {
                "process_connect",
                "process_accept",
            }
            or any(
                marker in function_name
                for marker in (
                    "connect",
                    "accept",
                    "sendmsg",
                )
            )
        )

        if not network_event:
            return

        direction = (
            "inbound"
            if (
                event_name
                == "process_accept"
                or "accept"
                in function_name
            )
            else "outbound"
        )

        destination_port = (
            socket_value[
                "destination_port"
            ]
        )

        dns_name = _dns_name(
            payload,
            destination_port,
        )

        key = _dependency_key(
            process,
            socket_value,
            dns_name,
            direction,
        )

        record = self.dependencies.get(
            key
        )

        if record is None:
            record = {
                "source": {
                    "namespace":
                        process.get(
                            "namespace"
                        ),
                    "pod_name":
                        process.get(
                            "pod_name"
                        ),
                    "pod_uid":
                        process.get(
                            "pod_uid"
                        ),
                    "workload_name":
                        process.get(
                            "workload_name"
                        ),
                    "container_id":
                        process.get(
                            "container_id"
                        ),
                    "binary":
                        process.get(
                            "binary"
                        ),
                    "pid":
                        process.get("pid"),
                    "exec_id":
                        process.get(
                            "exec_id"
                        ),
                },
                "destination": {
                    "name": dns_name,
                    "address":
                        socket_value[
                            "destination_address"
                        ],
                    "port":
                        destination_port,
                },
                "protocol":
                    socket_value[
                        "protocol"
                    ],
                "direction": direction,
                "observation_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "first_seen_at":
                    observed_at,
                "last_seen_at":
                    observed_at,
                "metadata": {
                    "source_address":
                        socket_value.get(
                            "source_address"
                        ),
                    "source_port":
                        socket_value.get(
                            "source_port"
                        ),
                    "event_name":
                        event_name,
                    "function_name":
                        function_name
                        or None,
                    "dns_resolver":
                        destination_port
                        == 53,
                },
            }

            self.dependencies[key] = (
                record
            )

        record["observation_count"] += 1
        record["last_seen_at"] = (
            observed_at
        )

        return_value = _return_value(
            payload
        )

        if (
            return_value is not None
            and return_value < 0
        ):
            record["failure_count"] += 1

        else:
            record["success_count"] += 1

    def build_batch(
        self,
        *,
        sensor_id: str,
        node_name: str,
        cluster_name: str,
        version: str,
        buffered_batch_count: int,
        source_file: str,
        source_file_offset: int,
        heartbeat_interval_seconds: int,
    ) -> dict[str, Any] | None:
        window_end = _utc_now_iso()

        has_content = bool(
            self.dependencies
            or self.processes
            or self.processed_event_count
        )

        if not has_content:
            return None

        value = {
            "batch_id": (
                "runtime-batch:"
                + uuid4().hex
            ),
            "sensor_id": sensor_id,
            "node_name": node_name,
            "cluster_name":
                cluster_name,
            "source": "tetragon",
            "version": version,
            "window_start":
                self.window_start,
            "window_end": window_end,
            "dependencies": list(
                self.dependencies.values()
            ),
            "processes": list(
                self.processes.values()
            ),
            "processed_event_count":
                self.processed_event_count,
            "dropped_event_count":
                self.dropped_event_count,
            "parser_error_count":
                self.parser_error_count,
            "buffered_batch_count":
                buffered_batch_count,
            "source_file": source_file,
            "source_file_offset":
                source_file_offset,
            "metadata": {
                "event_types":
                    dict(
                        self.event_types
                    ),
                "heartbeat_interval_seconds":
                    heartbeat_interval_seconds,
            },
        }

        self.window_start = window_end
        self.dependencies = {}
        self.processes = {}
        self.event_types = Counter()

        self.processed_event_count = 0
        self.dropped_event_count = 0
        self.parser_error_count = 0

        return value