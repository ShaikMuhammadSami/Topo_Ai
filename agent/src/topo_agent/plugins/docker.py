from __future__ import annotations

from typing import Any

import docker
from docker.errors import (
    DockerException,
)

from topo_agent import __version__
from topo_agent.config import (
    AgentConfig,
)
from topo_agent.plugin import (
    PluginCollectionResult,
    PluginDiagnostic,
)
from topo_agent.security import safe_exception_message


def _string_map(
    value: Any,
) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}

    return {
        str(key): str(item)
        for key, item in value.items()
    }


class DockerPlugin:
    name = "docker"
    version = __version__

    capabilities = (
        "docker.engine",
        "docker.containers",
        "docker.networks",
        "docker.ports",
    )

    def __init__(
        self,
        config: AgentConfig,
    ) -> None:
        if config.docker_base_url:
            self.client = (
                docker.DockerClient(
                    base_url=(
                        config
                        .docker_base_url
                    )
                )
            )
        else:
            self.client = (
                docker.from_env()
            )

    def doctor(
        self,
    ) -> PluginDiagnostic:
        try:
            info = self.client.info()

        except DockerException as exc:
            return PluginDiagnostic(
                name=self.name,
                status="failed",
                message=safe_exception_message(exc, "Docker discovery failed"),
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
                "server_version":
                    info.get(
                        "ServerVersion"
                    ),
                "operating_system":
                    info.get(
                        "OperatingSystem"
                    ),
                "containers":
                    info.get(
                        "Containers"
                    ),
                "containers_running":
                    info.get(
                        "ContainersRunning"
                    ),
            },
        )

    def collect(
        self,
    ) -> PluginCollectionResult:
        info = self.client.info()

        containers: list[
            dict[str, Any]
        ] = []

        networks: list[
            dict[str, Any]
        ] = []

        for network in (
            self.client.networks.list()
        ):
            attrs = network.attrs or {}

            networks.append(
                {
                    "id": network.id,
                    "name": network.name,
                    "driver":
                        attrs.get(
                            "Driver"
                        ),
                    "scope":
                        attrs.get(
                            "Scope"
                        ),
                    "internal":
                        attrs.get(
                            "Internal",
                            False,
                        ),
                    "labels":
                        _string_map(
                            attrs.get(
                                "Labels"
                            )
                        ),
                    "ipam":
                        attrs.get(
                            "IPAM",
                            {},
                        ),
                }
            )

        for container in (
            self.client
            .containers
            .list(all=True)
        ):
            attrs = container.attrs or {}

            config = attrs.get(
                "Config",
                {},
            )

            state = attrs.get(
                "State",
                {},
            )

            network_settings = (
                attrs.get(
                    "NetworkSettings",
                    {},
                )
            )

            connected_networks = []

            for (
                network_name,
                network_value,
            ) in (
                network_settings.get(
                    "Networks",
                    {},
                )
                or {}
            ).items():
                connected_networks.append(
                    {
                        "name":
                            network_name,
                        "network_id":
                            network_value
                            .get(
                                "NetworkID"
                            ),
                        "ip_address":
                            network_value
                            .get(
                                "IPAddress"
                            ),
                        "gateway":
                            network_value
                            .get(
                                "Gateway"
                            ),
                    }
                )

            ports = []

            for (
                container_port,
                bindings,
            ) in (
                network_settings.get(
                    "Ports",
                    {},
                )
                or {}
            ).items():
                ports.append(
                    {
                        "container_port":
                            container_port,
                        "bindings":
                            bindings or [],
                    }
                )

            labels = _string_map(
                config.get(
                    "Labels"
                )
            )

            containers.append(
                {
                    "id": container.id,
                    "short_id":
                        container.short_id,
                    "name":
                        container.name,
                    "image":
                        config.get(
                            "Image"
                        ),
                    "status":
                        container.status,
                    "state":
                        state.get(
                            "Status"
                        ),
                    "pid":
                        state.get(
                            "Pid"
                        ),
                    "started_at":
                        state.get(
                            "StartedAt"
                        ),
                    "finished_at":
                        state.get(
                            "FinishedAt"
                        ),
                    "labels": labels,
                    "networks":
                        connected_networks,
                    "ports": ports,
                    "compose_project":
                        labels.get(
                            "com.docker.compose."
                            "project"
                        ),
                    "compose_service":
                        labels.get(
                            "com.docker.compose."
                            "service"
                        ),
                    "kubernetes_pod_name":
                        labels.get(
                            "io.kubernetes."
                            "pod.name"
                        ),
                    "kubernetes_namespace":
                        labels.get(
                            "io.kubernetes."
                            "pod.namespace"
                        ),
                }
            )

        return PluginCollectionResult(
            plugin_name=self.name,
            status="success",
            inventory={
                "docker_hosts": [
                    {
                        "id":
                            info.get(
                                "ID"
                            ),
                        "name":
                            info.get(
                                "Name"
                            ),
                        "server_version":
                            info.get(
                                "ServerVersion"
                            ),
                        "operating_system":
                            info.get(
                                "OperatingSystem"
                            ),
                        "architecture":
                            info.get(
                                "Architecture"
                            ),
                    }
                ],
                "docker_containers":
                    containers,
                "docker_networks":
                    networks,
            },
            capabilities=list(
                self.capabilities
            ),
            metadata={
                "container_count":
                    len(containers),
                "network_count":
                    len(networks),
            },
        )

    def close(
        self,
    ) -> None:
        self.client.close()
