from topo_agent.azure_cache import (
    AzureInventoryCache,
)


def test_azure_inventory_cache(
    tmp_path,
) -> None:
    cache = AzureInventoryCache(
        tmp_path,
        ttl_seconds=300,
    )

    cache.save(
        scope_key=(
            "subscription-one|eastus2"
        ),
        inventory={
            "azure_virtual_networks": [
                {
                    "resource_id":
                        "/subscriptions/"
                        "subscription-one/"
                        "resourceGroups/rg-one/"
                        "providers/"
                        "Microsoft.Network/"
                        "virtualNetworks/"
                        "vnet-one",
                }
            ]
        },
    )

    value = cache.load(
        scope_key=(
            "subscription-one|eastus2"
        )
    )

    assert value is not None

    assert (
        value["inventory"]
        ["azure_virtual_networks"]
        [0]["resource_id"]
        .endswith("vnet-one")
    )

    assert value["stale"] is False