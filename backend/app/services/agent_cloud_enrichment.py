from __future__ import annotations

import hashlib
from typing import Any

from app.db.models import (
    TopoAgentRecord,
)
from app.models.agents import (
    AgentSnapshotSubmission,
)
from app.models.topology import (
    Entity,
    EntityType,
    GraphSnapshot,
    Relationship,
    RelationshipType,
)
from app.services.canonical_identity import (
    canonical_aws_identity,
)


KIND_MAP = {
    "aws_account": "AWSAccount",
    "aws_region": "AWSRegion",
    "aws_vpc": "AWSVPC",
    "aws_subnet": "AWSSubnet",
    "aws_route_table":
        "AWSRouteTable",
    "aws_security_group":
        "AWSSecurityGroup",
    "aws_ec2_instance":
        "AWSEC2Instance",
    "aws_eks_cluster":
        "AWSEKSCluster",
    "aws_eks_nodegroup":
        "AWSEKSNodeGroup",
    "aws_load_balancer":
        "AWSLoadBalancer",
    "aws_target_group":
        "AWSTargetGroup",
    "aws_target_health":
        "AWSTarget",
    "aws_rds_instance":
        "AWSRDSInstance",
    "aws_lambda_function":
        "AWSLambdaFunction",
}


TYPE_MAP = {
    "aws_account": (
        "INFRASTRUCTURE",
        "BOUNDARY",
    ),
    "aws_region": (
        "INFRASTRUCTURE",
        "BOUNDARY",
    ),
    "aws_vpc": (
        "NETWORK",
        "INFRASTRUCTURE",
    ),
    "aws_subnet": (
        "NETWORK",
        "INFRASTRUCTURE",
    ),
    "aws_route_table": (
        "NETWORK",
        "INFRASTRUCTURE",
    ),
    "aws_security_group": (
        "SECURITY",
        "NETWORK",
    ),
    "aws_ec2_instance": (
        "HOST",
        "COMPUTE",
    ),
    "aws_eks_cluster": (
        "CLUSTER",
        "INFRASTRUCTURE",
    ),
    "aws_eks_nodegroup": (
        "COMPUTE",
        "INFRASTRUCTURE",
    ),
    "aws_load_balancer": (
        "NETWORK",
        "SERVICE",
    ),
    "aws_target_group": (
        "SERVICE",
        "NETWORK",
    ),
    "aws_target_health": (
        "ENDPOINT",
        "NETWORK",
    ),
    "aws_rds_instance": (
        "DATABASE",
        "SERVICE",
    ),
    "aws_lambda_function": (
        "FUNCTION",
        "COMPUTE",
    ),
}


def _digest(
    value: str,
    length: int = 32,
) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:length]


def _enum_member(
    enum_type: type,
    names: tuple[str, ...],
):
    for name in names:
        member = getattr(
            enum_type,
            name,
            None,
        )

        if member is not None:
            return member

    return next(iter(enum_type))


def _entity_type(
    names: tuple[str, ...],
):
    return _enum_member(
        EntityType,
        names + ("UNKNOWN",),
    )


def _relationship_type(
    name: str,
):
    return _enum_member(
        RelationshipType,
        (
            name,
            "UNKNOWN",
        ),
    )


def _entity_id(
    value: dict[str, Any],
) -> str:
    return canonical_aws_identity(
        account_id=str(value.get("account_id", "")),
        region=str(value.get("region", "")),
        resource_type=str(value.get("resource_type", "")),
        resource_id=str(value.get("resource_id", "")),
        arn=(
            str(value["arn"])
            if value.get("arn")
            else None
        ),
    ).canonical_id


def enrich_snapshot_with_aws(
    *,
    snapshot: GraphSnapshot,
    agent: TopoAgentRecord,
    submission:
        AgentSnapshotSubmission,
) -> GraphSnapshot:
    inventory = submission.inventory

    cloud_values: list[
        dict[str, Any]
    ] = []

    for values in inventory.values():
        if not isinstance(values, list):
            continue

        for value in values:
            if (
                isinstance(value, dict)
                and value.get(
                    "provider"
                )
                == "aws"
            ):
                cloud_values.append(
                    value
                )

    if not cloud_values:
        return snapshot

    entities = list(
        snapshot.entities
    )

    relationships = list(
        snapshot.relationships
    )

    entity_ids = {
        entity.id
        for entity in entities
    }

    relationship_keys = {
        (
            item.source_entity_id,
            item.relationship_type.value,
            item.target_entity_id,
        )
        for item in relationships
    }

    resource_entity: dict[
        tuple[str, str, str],
        str,
    ] = {}

    resource_entity_by_id: dict[
        str,
        str,
    ] = {}

    resource_entity_by_arn: dict[
        str,
        str,
    ] = {}

    resource_values: dict[
        str,
        dict[str, Any],
    ] = {}

    def add_relationship(
        source_id: str | None,
        target_id: str | None,
        relation_name: str,
        properties:
            dict[str, Any] | None = None,
        confidence: float = 1.0,
    ) -> None:
        if not source_id or not target_id:
            return

        relation = _relationship_type(
            relation_name
        )

        key = (
            source_id,
            relation.value,
            target_id,
        )

        if key in relationship_keys:
            return

        relationship_keys.add(key)

        relationships.append(
            Relationship(
                id=(
                    "relationship:"
                    + _digest(
                        "|".join(key),
                        length=24,
                    )
                ),
                source_entity_id=(
                    source_id
                ),
                target_entity_id=(
                    target_id
                ),
                relationship_type=(
                    relation
                ),
                source_system="aws",
                observed_at=(
                    submission
                    .collected_at
                ),
                confidence=confidence,
                directed=True,
                evidence_ids=[],
                properties=(
                    properties or {}
                ),
            )
        )

    for value in cloud_values:
        resource_type = str(
            value.get(
                "resource_type",
                "",
            )
        )

        if resource_type not in KIND_MAP:
            continue

        resource_id = str(
            value.get(
                "resource_id",
                "",
            )
        )

        account_id = str(
            value.get(
                "account_id",
                "",
            )
        )

        region = str(
            value.get(
                "region",
                "global",
            )
        )

        if not resource_id:
            continue

        identity = canonical_aws_identity(
            account_id=account_id,
            region=region,
            resource_type=resource_type,
            resource_id=resource_id,
            arn=(
                str(value["arn"])
                if value.get("arn")
                else None
            ),
        )
        entity_id = identity.canonical_id

        properties = {
            **(
                value.get(
                    "properties",
                    {},
                )
                if isinstance(
                    value.get(
                        "properties"
                    ),
                    dict,
                )
                else {}
            ),
            "provider": "aws",
            "account_id":
                account_id,
            "region": region,
            "resource_type":
                resource_type,
            "resource_id":
                resource_id,
            "arn": value.get("arn"),
            "status":
                value.get("status"),
            "vpc_id":
                value.get("vpc_id"),
            "subnet_ids":
                value.get(
                    "subnet_ids",
                    [],
                ),
        }

        if entity_id not in entity_ids:
            entities.append(
                Entity(
                    id=entity_id,
                    entity_type=(
                        _entity_type(
                            TYPE_MAP[
                                resource_type
                            ]
                        )
                    ),
                    kind=KIND_MAP[
                        resource_type
                    ],
                    name=str(
                        value.get("name")
                        or resource_id
                    ),
                    source_system="aws",
                    external_id=(
                        identity.source_native_id
                    ),
                    aliases=identity.aliases,
                    identity_version=(
                        identity.identity_version
                    ),
                    environment=(
                        agent.environment
                    ),
                    observed_at=(
                        submission
                        .collected_at
                    ),
                    confidence=1.0,
                    labels={
                        str(key):
                            str(item)
                        for key, item
                        in (
                            value.get(
                                "tags",
                                {},
                            )
                            if isinstance(
                                value.get(
                                    "tags"
                                ),
                                dict,
                            )
                            else {}
                        ).items()
                    },
                    properties=(
                        properties
                    ),
                )
            )

            entity_ids.add(
                entity_id
            )

        resource_entity[
            (
                resource_type,
                region,
                resource_id,
            )
        ] = entity_id

        resource_entity_by_id[
            resource_id
        ] = entity_id

        arn = value.get("arn")

        if arn:
            resource_entity_by_arn[
                str(arn)
            ] = entity_id

        resource_values[
            entity_id
        ] = value

    account_entities = {
        str(
            value.get(
                "account_id"
            )
        ): entity_id
        for entity_id, value
        in resource_values.items()
        if value.get(
            "resource_type"
        )
        == "aws_account"
    }

    region_entities = {
        (
            str(
                value.get(
                    "account_id"
                )
            ),
            str(
                value.get(
                    "region"
                )
            ),
        ): entity_id
        for entity_id, value
        in resource_values.items()
        if value.get(
            "resource_type"
        )
        == "aws_region"
    }

    for entity_id, value in (
        resource_values.items()
    ):
        resource_type = value.get(
            "resource_type"
        )

        account_id = str(
            value.get(
                "account_id"
            )
        )

        region = str(
            value.get(
                "region",
                "global",
            )
        )

        if resource_type == "aws_region":
            add_relationship(
                account_entities.get(
                    account_id
                ),
                entity_id,
                "CONTAINS",
            )

        elif resource_type != "aws_account":
            add_relationship(
                region_entities.get(
                    (
                        account_id,
                        region,
                    )
                ),
                entity_id,
                "CONTAINS",
            )

        vpc_id = value.get(
            "vpc_id"
        )

        if vpc_id:
            add_relationship(
                resource_entity_by_id.get(
                    str(vpc_id)
                ),
                entity_id,
                "CONTAINS"
                if resource_type
                in {
                    "aws_subnet",
                    "aws_route_table",
                    "aws_security_group",
                }
                else "ATTACHED_TO",
            )

        for subnet_id in (
            value.get(
                "subnet_ids",
                [],
            )
            or []
        ):
            add_relationship(
                entity_id,
                resource_entity_by_id.get(
                    str(subnet_id)
                ),
                "ATTACHED_TO",
            )

        properties = value.get(
            "properties",
            {},
        )

        if not isinstance(
            properties,
            dict,
        ):
            properties = {}

        for security_group_id in (
            properties.get(
                "security_group_ids",
                [],
            )
            or []
        ):
            add_relationship(
                entity_id,
                resource_entity_by_id.get(
                    str(
                        security_group_id
                    )
                ),
                "PROTECTS",
            )

        if (
            resource_type
            == "aws_eks_nodegroup"
        ):
            cluster_name = (
                properties.get(
                    "cluster_name"
                )
            )

            add_relationship(
                resource_entity.get(
                    (
                        "aws_eks_cluster",
                        region,
                        str(
                            cluster_name
                        ),
                    )
                ),
                entity_id,
                "CONTAINS",
            )

        if (
            resource_type
            == "aws_target_group"
        ):
            for load_balancer_arn in (
                properties.get(
                    "load_balancer_arns",
                    [],
                )
                or []
            ):
                add_relationship(
                    resource_entity_by_arn
                    .get(
                        str(
                            load_balancer_arn
                        )
                    ),
                    entity_id,
                    "ROUTES_TO",
                )

        if (
            resource_type
            == "aws_target_health"
        ):
            target_group_arn = (
                properties.get(
                    "target_group_arn"
                )
            )

            target_id = properties.get(
                "target_id"
            )

            target_entity = (
                resource_entity_by_id.get(
                    str(target_id)
                )
            )

            if target_entity is None:
                target_entity = entity_id

            add_relationship(
                resource_entity_by_arn.get(
                    str(
                        target_group_arn
                    )
                ),
                target_entity,
                "ROUTES_TO",
                properties={
                    "health_status":
                        value.get(
                            "status"
                        ),
                    "target_port":
                        properties.get(
                            "target_port"
                        ),
                },
            )

    aws_instances = {
        str(
            entity.properties.get(
                "resource_id"
            )
        ): entity.id
        for entity in entities
        if entity.kind
        == "AWSEC2Instance"
    }

    aws_clusters = {
        entity.name: entity.id
        for entity in entities
        if entity.kind
        == "AWSEKSCluster"
    }

    aws_load_balancers = {
        str(
            entity.properties.get(
                "dns_name",
                "",
            )
        ).lower(): entity.id
        for entity in entities
        if (
            entity.kind
            == "AWSLoadBalancer"
            and entity.properties.get(
                "dns_name"
            )
        )
    }

    for entity in entities:
        if entity.kind == "KubernetesNode":
            provider_id = str(
                entity.properties.get(
                    "provider_id",
                    "",
                )
            )

            instance_id = (
                provider_id
                .rstrip("/")
                .split("/")[-1]
            )

            if instance_id.startswith(
                "i-"
            ):
                add_relationship(
                    aws_instances.get(
                        instance_id
                    ),
                    entity.id,
                    "RUNS",
                    confidence=0.99,
                )

        if (
            entity.kind
            == "KubernetesCluster"
        ):
            add_relationship(
                aws_clusters.get(
                    entity.name
                ),
                entity.id,
                "RUNS",
                confidence=0.99,
            )

        if (
            entity.kind
            == "KubernetesService"
        ):
            ingress_values = (
                entity.properties.get(
                    "load_balancer_ingress",
                    [],
                )
            )

            if not isinstance(
                ingress_values,
                list,
            ):
                continue

            for ingress in ingress_values:
                if not isinstance(
                    ingress,
                    dict,
                ):
                    continue

                hostname = str(
                    ingress.get(
                        "hostname",
                        "",
                    )
                ).lower()

                load_balancer_id = (
                    aws_load_balancers.get(
                        hostname
                    )
                )

                add_relationship(
                    load_balancer_id,
                    entity.id,
                    "ROUTES_TO",
                    confidence=0.99,
                )

    return snapshot.model_copy(
        update={
            "entities": entities,
            "relationships":
                relationships,
            "metadata": {
                **snapshot.metadata,
                "cloud_discovery": {
                    "provider": "aws",
                    "resource_count":
                        len(
                            resource_values
                        ),
                    "agent_id":
                        agent.agent_id,
                },
            },
        }
    )
