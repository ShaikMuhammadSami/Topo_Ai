from topo_agent.aws_cache import (
    AwsInventoryCache,
)


def test_aws_inventory_cache(
    tmp_path,
) -> None:
    cache = AwsInventoryCache(
        tmp_path,
        ttl_seconds=300,
    )

    cache.save(
        account_id="123456789012",
        region="us-east-1",
        inventory={
            "aws_vpcs": [
                {
                    "resource_id":
                        "vpc-one",
                }
            ]
        },
    )

    value = cache.load(
        account_id="123456789012",
        region="us-east-1",
    )

    assert value is not None

    assert (
        value["inventory"]
        ["aws_vpcs"][0]
        ["resource_id"]
        == "vpc-one"
    )

    assert value["stale"] is False