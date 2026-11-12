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
        status = str(
            result.get(
                "kubernetes_access",
                "unavailable",
            )
        )
        messages = {
            "denied": (
                "Kubernetes discovery permissions are denied for one or more "
                "required read checks."
            ),
            "degraded": (
                "Kubernetes discovery access is incomplete for one or more "
                "required read checks."
            ),
            "unavailable": (
                "The Kubernetes API is unavailable for required discovery "
                "checks."
            ),
        }

        return PluginDiagnostic(
            name=self.name,
            status=status,
            message=messages.get(status),
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
                "resource_completeness":
                    metadata.get(
                        "resource_completeness",
                        {},
                    ),
                "collection_failures":
                    metadata.get(
                        "collection_failures",
                        [],
                    ),
                "skipped_optional":
                    metadata.get(
                        "skipped_optional",
                        [],
                    ),
            },
        )

    def close(
        self,
    ) -> None:
        return None
