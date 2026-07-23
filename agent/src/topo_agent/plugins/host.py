from __future__ import annotations

import os
import platform
import socket
import subprocess
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


def _systemd_services(
) -> list[dict[str, Any]]:
    if os.name == "nt":
        return []

    try:
        result = subprocess.run(
            [
                "systemctl",
                "list-units",
                "--type=service",
                "--all",
                "--no-legend",
                "--no-pager",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    except (
        OSError,
        subprocess.TimeoutExpired,
    ):
        return []

    services = []

    for line in (
        result.stdout.splitlines()
    ):
        parts = line.split(
            None,
            4,
        )

        if len(parts) < 4:
            continue

        services.append(
            {
                "name": parts[0],
                "load_state":
                    parts[1],
                "active_state":
                    parts[2],
                "sub_state":
                    parts[3],
                "description": (
                    parts[4]
                    if len(parts) > 4
                    else None
                ),
                "manager": "systemd",
            }
        )

    return services


def _windows_services(
) -> list[dict[str, Any]]:
    if not hasattr(
        psutil,
        "win_service_iter",
    ):
        return []

    services = []

    try:
        values = (
            psutil.win_service_iter()
        )

    except Exception:
        return []

    for service in values:
        try:
            info = service.as_dict()

        except Exception:
            continue

        services.append(
            {
                "name":
                    info.get(
                        "name"
                    ),
                "display_name":
                    info.get(
                        "display_name"
                    ),
                "status":
                    info.get(
                        "status"
                    ),
                "start_type":
                    info.get(
                        "start_type"
                    ),
                "username":
                    info.get(
                        "username"
                    ),
                "manager":
                    "windows-service-manager",
            }
        )

    return services


class HostPlugin:
    name = "host"
    version = __version__

    capabilities = (
        "host.identity",
        "host.processes",
        "host.services",
    )

    def __init__(
        self,
        config: AgentConfig,
    ) -> None:
        self.config = config

    def doctor(
        self,
    ) -> PluginDiagnostic:
        return PluginDiagnostic(
            name=self.name,
            status="available",
            capabilities=list(
                self.capabilities
            ),
            details={
                "hostname":
                    socket.gethostname(),
                "platform":
                    platform.platform(),
                "process_count":
                    len(
                        psutil.pids()
                    ),
            },
        )

    def collect(
        self,
    ) -> PluginCollectionResult:
        hostname = socket.gethostname()

        host = {
            "id": hostname,
            "name": hostname,
            "fqdn":
                socket.getfqdn(),
            "platform":
                platform.system(),
            "platform_release":
                platform.release(),
            "platform_version":
                platform.version(),
            "architecture":
                platform.machine(),
            "processor":
                platform.processor(),
            "boot_time":
                psutil.boot_time(),
            "cpu_count":
                psutil.cpu_count(),
            "memory_total":
                psutil
                .virtual_memory()
                .total,
        }

        processes: list[
            dict[str, Any]
        ] = []

        attributes = [
            "pid",
            "ppid",
            "name",
            "exe",
            "create_time",
            "status",
        ]

        if (
            self.config
            .collect_process_username
        ):
            attributes.append(
                "username"
            )

        for process in (
            psutil.process_iter(
                attributes
            )
        ):
            try:
                info = process.info

            except (
                psutil.NoSuchProcess,
                psutil.AccessDenied,
            ):
                continue

            processes.append(
                {
                    "pid":
                        info.get(
                            "pid"
                        ),
                    "ppid":
                        info.get(
                            "ppid"
                        ),
                    "name":
                        info.get(
                            "name"
                        ),
                    "exe":
                        info.get(
                            "exe"
                        ),
                    "create_time":
                        info.get(
                            "create_time"
                        ),
                    "status":
                        info.get(
                            "status"
                        ),
                    "username":
                        info.get(
                            "username"
                        )
                        if (
                            self.config
                            .collect_process_username
                        )
                        else None,
                    "host_id":
                        hostname,
                }
            )

        services = [
            *_systemd_services(),
            *_windows_services(),
        ]

        return PluginCollectionResult(
            plugin_name=self.name,
            status="success",
            inventory={
                "hosts": [host],
                "processes": processes,
                "system_services":
                    services,
            },
            capabilities=list(
                self.capabilities
            ),
            metadata={
                "process_count":
                    len(processes),
                "service_count":
                    len(services),
            },
        )

    def close(
        self,
    ) -> None:
        return None