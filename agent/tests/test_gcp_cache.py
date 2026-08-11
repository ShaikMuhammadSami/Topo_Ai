from topo_agent.gcp_cache import (
    GcpInventoryCache,
)


def test_gcp_inventory_cache(
    tmp_path,
) -> None:
    cache = GcpInventoryCache(
        tmp_path,
        ttl_seconds=300,
    )

    cache.save(
        project_id="project-one",
        inventory={
            "gcp_networks": [
                {
                    "resource_id":
                        (
                            "projects/"
                            "project-one/"
                            "global/networks/"
                            "network-one"
                        ),
                }
            ]
        },
    )

    value = cache.load(
        project_id="project-one"
    )

    assert value is not None

    assert (
        value["inventory"]
        ["gcp_networks"][0]
        ["resource_id"]
        .endswith("network-one")
    )

    assert value["stale"] is False