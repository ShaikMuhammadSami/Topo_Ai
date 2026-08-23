from types import SimpleNamespace

from app.models.agents import (
    AgentSnapshotSubmission,
)
from app.models.topology import (
    GraphSnapshot,
)
from app.services.agent_gcp_enrichment import (
    enrich_snapshot_with_gcp,
)


def test_gcp_network_contains_subnetwork(
) -> None:
    network_id = (
        "projects/project-one/"
        "global/networks/network-one"
    )

    subnetwork_id = (
        "projects/project-one/"
        "regions/us-central1/"
        "subnetworks/subnet-one"
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
                "gcp_projects": [
                    {
                        "provider": "gcp",
                        "account_id":
                            "project-one",
                        "region": "global",
                        "resource_group":
                            None,
                        "resource_type":
                            "gcp_project",
                        "resource_id":
                            "projects/123456",
                        "name":
                            "Project One",
                        "arn":
                            "projects/123456",
                        "status": "ACTIVE",
                        "tags": {},
                        "vpc_id": None,
                        "subnet_ids": [],
                        "properties": {
                            "project_id":
                                "project-one",
                            "parent":
                                "folders/123",
                        },
                    }
                ],
                "gcp_networks": [
                    {
                        "provider": "gcp",
                        "account_id":
                            "project-one",
                        "region": "global",
                        "resource_group":
                            None,
                        "resource_type":
                            "gcp_network",
                        "resource_id":
                            network_id,
                        "name":
                            "network-one",
                        "arn": network_id,
                        "status": None,
                        "tags": {},
                        "vpc_id": None,
                        "subnet_ids": [],
                        "properties": {},
                    }
                ],
                "gcp_subnetworks": [
                    {
                        "provider": "gcp",
                        "account_id":
                            "project-one",
                        "region":
                            "us-central1",
                        "resource_group":
                            None,
                        "resource_type":
                            "gcp_subnetwork",
                        "resource_id":
                            subnetwork_id,
                        "name":
                            "subnet-one",
                        "arn":
                            subnetwork_id,
                        "status": None,
                        "tags": {},
                        "vpc_id":
                            network_id,
                        "subnet_ids": [
                            subnetwork_id
                        ],
                        "properties": {},
                    }
                ],
            },
            metadata={},
        )
    )

    result = enrich_snapshot_with_gcp(
        snapshot=snapshot,
        agent=SimpleNamespace(
            agent_id="agent-test",
            environment="test",
        ),
        submission=submission,
    )

    assert any(
        entity.kind
        == "GCPVPCNetwork"
        for entity in result.entities
    )

    assert any(
        entity.kind
        == "GCPSubnetwork"
        for entity in result.entities
    )

    assert any(
        relationship
        .relationship_type.name
        == "CONTAINS"
        for relationship
        in result.relationships
    )

    for relationship in result.relationships:
        assert relationship.provenance is not None
        assert relationship.provenance.origin.value == "declared"
        assert relationship.confidence is None
        assert relationship.provenance.source_references
