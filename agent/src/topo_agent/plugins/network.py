from __future__ import annotations

import socket
from typing import Any

import psutil

from topo_agent import __version__
from topo_agent.config import (
    AgentConfig,
)
from topo_agent.plugin import (
    PluginCollectionResult,
    PluginDiagnostic,
)
from topo_agent.security import safe_exception_message


def _address(
    value: Any,
) -> tuple[
    str | None,
    int | None,
]:
    if not value:
        return None, None

    if hasattr(
        value,
        "ip",
    ):
        return (
            str(value.ip),
            int(value.port),
        )

    if isinstance(
        value,
        tuple,
    ) and len(value) >= 2:
        return (
            str(value[0]),
            int(value[1]),
        )

    return None, None


def _is_loopback(
    value: str | None,
) -> bool:
    if not value:
        return False

    return (
        value == "localhost"
        or value.startswith(
            "127."
        )
        or value == "::1"
    )


class NetworkPlugin:
    name = "network"
    version = __version__

    capabilities = (
        "network.listening_ports",
        "network.connections",
        "network.runtime_dependencies",
    )

    def __init__(
        self,
        config: AgentConfig,
    ) -> None:
        self.config = config

    def doctor(
        self,
    ) -> PluginDiagnostic:
        try:
            values = (
                psutil.net_connections(
                    kind="inet"
                )
            )

        except psutil.AccessDenied as exc:
            return PluginDiagnostic(
                name=self.name,
                status="failed",
                message=safe_exception_message(
                    exc, "Access to network connections was denied"
                ),
                capabilities=list(
                    self.capabilities
                ),
            )

        return PluginDiagnostic(
            name=self.name,
            status="available",
            capabilities=list(
                self.capabilities
            ),
            details={
                "connection_count":
                    len(values),
            },
        )

    def collect(
        self,
    ) -> PluginCollectionResult:
        hostname = socket.gethostname()

        listening_ports: list[
            dict[str, Any]
        ] = []

        connections: list[
            dict[str, Any]
        ] = []

        errors: list[str] = []

        try:
            values = (
                psutil.net_connections(
                    kind="inet"
                )
            )

        except psutil.AccessDenied as exc:
            return PluginCollectionResult(
                plugin_name=self.name,
                status="failed",
                capabilities=list(
                    self.capabilities
                ),
                errors=[safe_exception_message(
                    exc, "Access to network connections was denied"
                )],
            )

        for connection in values:
            local_address, local_port = (
                _address(
                    connection.laddr
                )
            )

            remote_address, remote_port = (
                _address(
                    connection.raddr
                )
            )

            if (
                not self.config
                .network_include_loopback
                and (
                    _is_loopback(
                        local_address
                    )
                    or _is_loopback(
                        remote_address
                    )
                )
            ):
                continue

            protocol = (
                "tcp"
                if connection.type
                == socket.SOCK_STREAM
                else "udp"
            )

            status = str(
                connection.status
                or ""
            )

            if (
                status.upper() == "LISTEN"
                and self.config
                .network_include_listening
            ):
                listening_ports.append(
                    {
                        "host_id":
                            hostname,
                        "pid":
                            connection.pid,
                        "protocol":
                            protocol,
                        "address":
                            local_address,
                        "port":
                            local_port,
                        "status":
                            status,
                    }
                )

                continue

            if (
                remote_address
                and self.config
                .network_include_established
            ):
                connections.append(
                    {
                        "host_id":
                            hostname,
                        "pid":
                            connection.pid,
                        "protocol":
                            protocol,
                        "status":
                            status,
                        "local_address":
                            local_address,
                        "local_port":
                            local_port,
                        "remote_address":
                            remote_address,
                        "remote_port":
                            remote_port,
                    }
                )

        return PluginCollectionResult(
            plugin_name=self.name,
            status=(
                "partial"
                if errors
                else "success"
            ),
            inventory={
                "listening_ports":
                    listening_ports,
                "network_connections":
                    connections,
            },
            capabilities=list(
                self.capabilities
            ),
            errors=errors,
            metadata={
                "listening_port_count":
                    len(
                        listening_ports
                    ),
                "connection_count":
                    len(connections),
            },
        )

    def close(
        self,
    ) -> None:
        return None
