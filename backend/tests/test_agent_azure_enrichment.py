from types import SimpleNamespace

from app.models.agents import (
    AgentSnapshotSubmission,
)
from app.models.topology import (
    GraphSnapshot,
)
from app.services.agent_azure_enrichment import (
    enrich_snapshot_with_azure,
)


def test_azure_vnet_contains_subnet(
) -> None:
    subscription_id = (
        "00000000-0000-0000-"
        "0000-000000000001"
    )

    vnet_id = (
        "/subscriptions/"
        f"{subscription_id}/"
        "resourceGroups/rg-test/"
        "providers/Microsoft.Network/"
        "virtualNetworks/vnet-test"
    )

    subnet_id = (
        f"{vnet_id}/"
        "subnets/subnet-test"
    )

    snapshot = GraphSnapshot(
        schema_version="1.0",
        snapshot_id="snapshot-test",
        collected_at=(
            "2026-07-26T00:00:00+00:00"
        ),
        collector_name="test",
        collector_version="test",
        scope={},
        entities=[],
        relationships=[],
        evidence=[],
        metadata={},
    )

    submission = (
        AgentSnapshotSubmission(
            submission_id=(
                "submission-test"
            ),
            collected_at=(
                "2026-07-26T00:00:00+00:00"
            ),
            cluster_name="test",
            environment="test",
            namespace_scope=[],
            collector_version="test",
            inventory={
                "azure_subscriptions": [
                    {
                        "provider": "azure",
                        "account_id":
                            subscription_id,
                        "region": "global",
                        "resource_group":
                            None,
                        "resource_type":
                            "azure_subscription",
                        "resource_id":
                            subscription_id,
                        "name":
                            "Test Subscription",
                        "arn":
                            (
                                "/subscriptions/"
                                + subscription_id
                            ),
                        "status":
                            "Enabled",
                        "tags": {},
                        "vpc_id": None,
                        "subnet_ids": [],
                        "properties": {},
                    }
                ],
                "azure_virtual_networks": [
                    {
                        "provider": "azure",
                        "account_id":
                            subscription_id,
                        "region": "eastus2",
                        "resource_group":
                            "rg-test",
                        "resource_type":
                            (
                                "azure_"
                                "virtual_network"
                            ),
                        "resource_id":
                            vnet_id,
                        "name":
                            "vnet-test",
                        "arn": vnet_id,
                        "status":
                            "Succeeded",
                        "tags": {},
                        "vpc_id": None,
                        "subnet_ids": [],
                        "properties": {},
                    }
                ],
                "azure_subnets": [
                    {
                        "provider": "azure",
                        "account_id":
                            subscription_id,
                        "region": "eastus2",
                        "resource_group":
                            "rg-test",
                        "resource_type":
                            "azure_subnet",
                        "resource_id":
                            subnet_id,
                        "name":
                            "subnet-test",
                        "arn": subnet_id,
                        "status":
                            "Succeeded",
                        "tags": {},
                        "vpc_id": None,
                        "subnet_ids": [],
                        "properties": {
                            (
                                "parent_"
                                "virtual_network_id"
                            ): vnet_id,
                        },
                    }
                ],
            },
            metadata={},
        )
    )

    result = enrich_snapshot_with_azure(
        snapshot=snapshot,
        agent=SimpleNamespace(
            agent_id="agent-test",
            environment="test",
        ),
        submission=submission,
    )

    assert any(
        entity.kind
        == "AzureVirtualNetwork"
        for entity in result.entities
    )

    assert any(
        entity.kind
        == "AzureSubnet"
        for entity in result.entities
    )

    assert any(
        relationship
        .relationship_type.name
        == "CONTAINS"
        for relationship
        in result.relationships
    )