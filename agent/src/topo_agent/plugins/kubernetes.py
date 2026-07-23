from __future__ import annotations

from topo_agent import __version__
from topo_agent.collector import (
    KubernetesCollector,
)
from topo_agent.config import (
    AgentConfig,
)
from topo_agent.plugin import (
    PluginCollectionResult,
    PluginDiagnostic,
)


class KubernetesPlugin:
    name = "kubernetes"
    version = __version__

    capabilities = (
        "kubernetes.namespaces",
        "kubernetes.nodes",
        "kubernetes.deployments",
        "kubernetes.replicasets",
        "kubernetes.pods",
        "kubernetes.services",
        "kubernetes.ingresses",
        "kubernetes.endpointslices",
    )

    def __init__(
        self,
        config: AgentConfig,
    ) -> None:
        self.collector = (
            KubernetesCollector(config)
        )

    def doctor(
        self,
    ) -> PluginDiagnostic:
        result = self.collector.doctor()

        return PluginDiagnostic(
            name=self.name,
            status="available",
            capabilities=list(
                self.capabilities
            ),
            details=result,
        )

    def collect(
        self,
    ) -> PluginCollectionResult:
        submission = (
            self.collector.collect()
        )

        metadata = submission.get(
            "metadata",
            {},
        )

        errors = metadata.get(
            "collection_errors",
            [],
        )

        return PluginCollectionResult(
            plugin_name=self.name,
            status=(
                "partial"
                if errors
                else "success"
            ),
            inventory=submission.get(
                "inventory",
                {},
            ),
            capabilities=list(
                self.capabilities
            ),
            errors=[
                str(item)
                for item in errors
            ],
            metadata={
                "access_mode":
                    metadata.get(
                        "access_mode"
                    ),
            },
        )

    def close(
        self,
    ) -> None:
        return None