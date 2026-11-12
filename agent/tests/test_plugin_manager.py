from topo_agent.plugin import (
    PluginCollectionResult,
    PluginDiagnostic,
)
from topo_agent.plugin_manager import (
    PluginManager,
)


class SuccessfulPlugin:
    name = "success"
    version = "1.0"

    capabilities = (
        "test.success",
    )

    def doctor(
        self,
    ) -> PluginDiagnostic:
        return PluginDiagnostic(
            name=self.name,
            status="available",
        )

    def collect(
        self,
    ) -> PluginCollectionResult:
        return PluginCollectionResult(
            plugin_name=self.name,
            status="success",
            inventory={
                "items": [
                    {
                        "id": "one",
                    }
                ]
            },
            capabilities=list(
                self.capabilities
            ),
        )

    def close(
        self,
    ) -> None:
        return None


class FailedPlugin:
    name = "failed"
    version = "1.0"

    capabilities = (
        "test.failed",
    )

    def doctor(
        self,
    ) -> PluginDiagnostic:
        return PluginDiagnostic(
            name=self.name,
            status="failed",
        )

    def collect(
        self,
    ) -> PluginCollectionResult:
        raise RuntimeError(
            "Plugin failure"
        )

    def close(
        self,
    ) -> None:
        return None


def test_partial_collection_does_not_merge_incomplete_plugin_inventory(
) -> None:
    manager = PluginManager(
        plugins=[
            SuccessfulPlugin(),
            FailedPlugin(),
        ],
        cluster_name="test",
        environment="test",
        namespace_scope=[],
    )

    result = manager.collect()

    assert (
        result["metadata"]
        ["collection_status"]
        == "partial"
    )

    assert result["inventory"]["items"][0]["id"] == "one"

    assert (
        result["metadata"]
        ["successful_plugin_count"]
        == 1
    )

    assert (
        result["metadata"]
        ["failed_plugin_count"]
        == 1
    )


class PartialPlugin(SuccessfulPlugin):
    name = "partial"

    def collect(
        self,
    ) -> PluginCollectionResult:
        return PluginCollectionResult(
            plugin_name=self.name,
            status="partial",
            inventory={
                "kubernetes_items": [
                    {"id": "must-not-merge"}
                ]
            },
            errors=["replicasets: HTTP 403"],
            metadata={
                "collection_failures": [
                    {
                        "resource": "replicasets",
                        "status_code": 403,
                        "category": "authorization",
                    }
                ]
            },
        )


def test_successful_plugin_cannot_hide_partial_kubernetes_plugin(
) -> None:
    manager = PluginManager(
        plugins=[
            SuccessfulPlugin(),
            PartialPlugin(),
        ],
        cluster_name="test",
        environment="test",
        namespace_scope=[],
    )

    result = manager.collect()

    assert result["metadata"]["collection_status"] == "partial"
    assert "kubernetes_items" not in result["inventory"]
    assert result["inventory"]["items"] == [{"id": "one"}]
