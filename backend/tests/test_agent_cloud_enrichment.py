from types import SimpleNamespace

from app.models.agents import (
    AgentSnapshotSubmission,
)
from app.models.topology import (
    GraphSnapshot,
)
from app.services.agent_cloud_enrichment import (
    enrich_snapshot_with_aws,
)


def test_aws_vpc_and_subnet_relationship(
) -> None:
    snapshot = GraphSnapshot(
        schema_version="1.0",
        snapshot_id="test-snapshot",
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
                "test-submission"
            ),
            collected_at=(
                "2026-07-26T00:00:00+00:00"
            ),
            cluster_name="test",
            environment="test",
            namespace_scope=[],
            collector_version="test",
            inventory={
                "aws_accounts": [
                    {
                        "provider": "aws",
                        "account_id":
                            "123456789012",
                        "region": "global",
                        "resource_type":
                            "aws_account",
                        "resource_id":
                            "123456789012",
                        "name":
                            "123456789012",
                        "tags": {},
                        "subnet_ids": [],
                        "properties": {},
                    }
                ],
                "aws_regions": [
                    {
                        "provider": "aws",
                        "account_id":
                            "123456789012",
                        "region":
                            "us-east-1",
                        "resource_type":
                            "aws_region",
                        "resource_id":
                            "us-east-1",
                        "name":
                            "us-east-1",
                        "tags": {},
                        "subnet_ids": [],
                        "properties": {},
                    }
                ],
                "aws_vpcs": [
                    {
                        "provider": "aws",
                        "account_id":
                            "123456789012",
                        "region":
                            "us-east-1",
                        "resource_type":
                            "aws_vpc",
                        "resource_id":
                            "vpc-one",
                        "name": "vpc-one",
                        "vpc_id": "vpc-one",
                        "tags": {},
                        "subnet_ids": [],
                        "properties": {},
                    }
                ],
                "aws_subnets": [
                    {
                        "provider": "aws",
                        "account_id":
                            "123456789012",
                        "region":
                            "us-east-1",
                        "resource_type":
                            "aws_subnet",
                        "resource_id":
                            "subnet-one",
                        "name":
                            "subnet-one",
                        "vpc_id": "vpc-one",
                        "tags": {},
                        "subnet_ids": [
                            "subnet-one"
                        ],
                        "properties": {},
                    }
                ],
            },
            metadata={},
        )
    )

    result = enrich_snapshot_with_aws(
        snapshot=snapshot,
        agent=SimpleNamespace(
            agent_id="agent-one",
            environment="test",
        ),
        submission=submission,
    )

    assert any(
        entity.kind == "AWSVPC"
        for entity in result.entities
    )

    assert any(
        entity.kind == "AWSSubnet"
        for entity in result.entities
    )

    assert any(
        relationship
        .relationship_type.value
        == "contains"
        for relationship
        in result.relationships
    )

    for relationship in result.relationships:
        assert relationship.provenance is not None
        assert relationship.provenance.origin.value == "declared"
        assert relationship.confidence is None
        assert relationship.provenance.source_references
