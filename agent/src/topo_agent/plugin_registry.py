from __future__ import annotations

from topo_agent.config import (
    AgentConfig,
)
from topo_agent.plugin import (
    CollectorPlugin,
)
from topo_agent.plugin_manager import (
    PluginManager,
)
from topo_agent.plugins.docker import (
    DockerPlugin,
)
from topo_agent.plugins.host import (
    HostPlugin,
)
from topo_agent.plugins.kubernetes import (
    KubernetesPlugin,
)
from topo_agent.plugins.network import (
    NetworkPlugin,
)
from topo_agent.plugins.aws import (
    AwsPlugin,
)
from topo_agent.plugins.azure import (
    AzurePlugin,
)
PLUGIN_FACTORIES = {
    "aws":
        AwsPlugin,
    "azure":
        AzurePlugin,    
    "kubernetes":
        KubernetesPlugin,
    "docker":
        DockerPlugin,
    "host":
        HostPlugin,
    "network":
        NetworkPlugin,
}


def available_plugins(
) -> list[str]:
    return sorted(
        PLUGIN_FACTORIES
    )


def build_plugin_manager(
    config: AgentConfig,
    *,
    selected_plugins:
        list[str] | None = None,
) -> PluginManager:
    requested = (
        selected_plugins
        if selected_plugins is not None
        else config.enabled_plugins
    )

    normalized = []

    for name in requested:
        value = name.strip().lower()

        if (
            value
            and value not in normalized
        ):
            normalized.append(value)

    unknown = [
        name
        for name in normalized
        if name
        not in PLUGIN_FACTORIES
    ]

    if unknown:
        raise ValueError(
            "Unknown agent plugins: "
            + ", ".join(unknown)
        )

    plugins: list[
        CollectorPlugin
    ] = []

    for name in normalized:
        factory = PLUGIN_FACTORIES[
            name
        ]

        plugins.append(
            factory(config)
        )

    return PluginManager(
        plugins=plugins,
        cluster_name=(
            config.cluster_name
        ),
        environment=(
            config.environment
        ),
        namespace_scope=(
            config.namespaces
        ),
    )