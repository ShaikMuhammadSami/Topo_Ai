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
    canonical_azure_identity,
)


KIND_MAP = {
    "azure_subscription":
        "AzureSubscription",

    "azure_resource_group":
        "AzureResourceGroup",

    "azure_virtual_network":
        "AzureVirtualNetwork",

    "azure_subnet":
        "AzureSubnet",

    "azure_route_table":
        "AzureRouteTable",

    "azure_network_security_group":
        "AzureNetworkSecurityGroup",

    "azure_network_interface":
        "AzureNetworkInterface",

    "azure_public_ip_address":
        "AzurePublicIPAddress",

    "azure_virtual_machine":
        "AzureVirtualMachine",

    (
        "azure_virtual_machine_"
        "scale_set"
    ): (
        "AzureVirtualMachineScaleSet"
    ),

    "azure_aks_cluster":
        "AzureAKSCluster",

    "azure_load_balancer":
        "AzureLoadBalancer",

    "azure_application_gateway":
        "AzureApplicationGateway",

    "azure_private_endpoint":
        "AzurePrivateEndpoint",

    "azure_sql_server":
        "AzureSQLServer",

    "azure_sql_database":
        "AzureSQLDatabase",

    (
        "azure_postgresql_"
        "flexible_server"
    ): (
        "AzurePostgreSQLFlexibleServer"
    ),

    "azure_app_service_plan":
        "AzureAppServicePlan",

    "azure_app_service":
        "AzureAppService",

    "azure_function_app":
        "AzureFunctionApp",
}


TYPE_MAP = {
    "azure_subscription": (
        "INFRASTRUCTURE",
        "BOUNDARY",
    ),

    "azure_resource_group": (
        "INFRASTRUCTURE",
        "BOUNDARY",
    ),

    "azure_virtual_network": (
        "NETWORK",
        "INFRASTRUCTURE",
    ),

    "azure_subnet": (
        "NETWORK",
        "INFRASTRUCTURE",
    ),

    "azure_route_table": (
        "NETWORK",
        "INFRASTRUCTURE",
    ),

    "azure_network_security_group": (
        "SECURITY",
        "NETWORK",
    ),

    "azure_network_interface": (
        "NETWORK",
        "INFRASTRUCTURE",
    ),

    "azure_public_ip_address": (
        "NETWORK",
        "ENDPOINT",
    ),

    "azure_virtual_machine": (
        "HOST",
        "COMPUTE",
    ),

    (
        "azure_virtual_machine_"
        "scale_set"
    ): (
        "HOST",
        "COMPUTE",
    ),

    "azure_aks_cluster": (
        "CLUSTER",
        "INFRASTRUCTURE",
    ),

    "azure_load_balancer": (
        "NETWORK",
        "SERVICE",
    ),

    "azure_application_gateway": (
        "NETWORK",
        "SERVICE",
    ),

    "azure_private_endpoint": (
        "NETWORK",
        "ENDPOINT",
    ),

    "azure_sql_server": (
        "DATABASE",
        "SERVICE",
    ),

    "azure_sql_database": (
        "DATABASE",
        "SERVICE",
    ),

    (
        "azure_postgresql_"
        "flexible_server"
    ): (
        "DATABASE",
        "SERVICE",
    ),

    "azure_app_service_plan": (
        "COMPUTE",
        "INFRASTRUCTURE",
    ),

    "azure_app_service": (
        "SERVICE",
        "WORKLOAD",
    ),

    "azure_function_app": (
        "FUNCTION",
        "WORKLOAD",
    ),
}


def _digest(
    value: str,
    length: int = 32,
) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:length]


def _normalise_id(
    value: Any,
) -> str:
    return str(
        value or ""
    ).strip().rstrip("/").lower()


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


def _azure_entity_id(
    resource_id: str,
) -> str:
    return canonical_azure_identity(
        subscription_id=None,
        resource_type="AzureResource",
        resource_id=resource_id,
    ).canonical_id


def _reference_ids(
    value: Any,
    target_keys: set[str],
) -> list[str]:
    results: list[str] = []

    def walk(
        item: Any,
        parent_key: str | None = None,
    ) -> None:
        if isinstance(item, dict):
            if (
                parent_key
                and parent_key.lower()
                in target_keys
            ):
                reference_id = item.get("id")

                if reference_id:
                    results.append(
                        _normalise_id(
                            reference_id
                        )
                    )

            for key, nested in item.items():
                walk(
                    nested,
                    str(key),
                )

        elif isinstance(item, list):
            for nested in item:
                walk(
                    nested,
                    parent_key,
                )

    walk(value)

    return sorted(set(results))


def _parent_id(
    resource_id: str,
) -> str | None:
    normalized = resource_id.rstrip("/")

    if "/" not in normalized:
        return None

    return normalized.rsplit(
        "/",
        2,
    )[0]


def enrich_snapshot_with_azure(
    *,
    snapshot: GraphSnapshot,
    agent: TopoAgentRecord,
    submission:
        AgentSnapshotSubmission,
) -> GraphSnapshot:
    cloud_values: list[
        dict[str, Any]
    ] = []

    for values in (
        submission.inventory.values()
    ):
        if not isinstance(values, list):
            continue

        for value in values:
            if (
                isinstance(value, dict)
                and str(
                    value.get(
                        "provider",
                        "",
                    )
                ).lower()
                == "azure"
            ):
                cloud_values.append(value)

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
            relationship
            .source_entity_id,

            relationship
            .relationship_type.value,

            relationship
            .target_entity_id,
        )
        for relationship
        in relationships
    }

    azure_entity_by_resource_id: dict[
        str,
        str,
    ] = {}

    azure_values_by_entity: dict[
        str,
        dict[str, Any],
    ] = {}

    def add_relationship(
        source_id: str | None,
        target_id: str | None,
        relation_name: str,
        *,
        confidence: float = 1.0,
        properties:
            dict[str, Any] | None = None,
    ) -> None:
        if (
            not source_id
            or not target_id
            or source_id == target_id
        ):
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
                source_system="azure",
                observed_at=(
                    submission.collected_at
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

        if not resource_id:
            continue

        identity = canonical_azure_identity(
            subscription_id=(
                str(value["account_id"])
                if value.get("account_id")
                else None
            ),
            resource_type=resource_type,
            resource_id=resource_id,
        )
        entity_id = identity.canonical_id

        raw_properties = value.get(
            "properties",
            {},
        )

        properties = (
            raw_properties
            if isinstance(
                raw_properties,
                dict,
            )
            else {}
        )

        properties = {
            **properties,
            "provider": "azure",
            "account_id":
                value.get(
                    "account_id"
                ),
            "subscription_id":
                value.get(
                    "account_id"
                ),
            "region":
                value.get(
                    "region"
                ),
            "resource_group":
                value.get(
                    "resource_group"
                ),
            "resource_type":
                resource_type,
            "resource_id":
                resource_id,
            "status":
                value.get(
                    "status"
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
                    source_system="azure",
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
                        submission.collected_at
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
                    properties=properties,
                )
            )

            entity_ids.add(entity_id)

        normalized_id = (
            _normalise_id(
                resource_id
            )
        )

        azure_entity_by_resource_id[
            normalized_id
        ] = entity_id

        azure_values_by_entity[
            entity_id
        ] = value

    subscription_entities = {
        str(
            value.get(
                "account_id"
            )
        ).lower(): entity_id
        for entity_id, value
        in azure_values_by_entity.items()
        if value.get(
            "resource_type"
        )
        == "azure_subscription"
    }

    resource_group_entities: dict[
        tuple[str, str],
        str,
    ] = {}

    for entity_id, value in (
        azure_values_by_entity.items()
    ):
        if (
            value.get(
                "resource_type"
            )
            != "azure_resource_group"
        ):
            continue

        resource_group_entities[
            (
                str(
                    value.get(
                        "account_id"
                    )
                ).lower(),
                str(
                    value.get("name")
                    or value.get(
                        "resource_group"
                    )
                ).lower(),
            )
        ] = entity_id

    # Subscription and resource-group
    # containment.
    for entity_id, value in (
        azure_values_by_entity.items()
    ):
        resource_type = str(
            value.get(
                "resource_type",
                "",
            )
        )

        subscription_id = str(
            value.get(
                "account_id",
                "",
            )
        ).lower()

        resource_group = str(
            value.get(
                "resource_group",
                "",
            )
        ).lower()

        if (
            resource_type
            == "azure_resource_group"
        ):
            add_relationship(
                subscription_entities.get(
                    subscription_id
                ),
                entity_id,
                "CONTAINS",
            )

        elif (
            resource_type
            != "azure_subscription"
            and resource_group
        ):
            add_relationship(
                resource_group_entities.get(
                    (
                        subscription_id,
                        resource_group,
                    )
                ),
                entity_id,
                "CONTAINS",
            )

    # Resource-specific Azure
    # relationships.
    for entity_id, value in (
        azure_values_by_entity.items()
    ):
        resource_type = str(
            value.get(
                "resource_type",
                "",
            )
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

        resource_id = str(
            value.get(
                "resource_id",
                "",
            )
        )

        if (
            resource_type
            == "azure_subnet"
        ):
            virtual_network_id = (
                properties.get(
                    "parent_virtual_network_id"
                )
            )

            add_relationship(
                azure_entity_by_resource_id
                .get(
                    _normalise_id(
                        virtual_network_id
                    )
                ),
                entity_id,
                "CONTAINS",
            )

            nsg_ids = _reference_ids(
                properties,
                {
                    "networksecuritygroup",
                },
            )

            for nsg_id in nsg_ids:
                add_relationship(
                    azure_entity_by_resource_id
                    .get(nsg_id),
                    entity_id,
                    "PROTECTS",
                )

            route_table_ids = (
                _reference_ids(
                    properties,
                    {
                        "routetable",
                    },
                )
            )

            for route_table_id in (
                route_table_ids
            ):
                add_relationship(
                    entity_id,
                    azure_entity_by_resource_id
                    .get(
                        route_table_id
                    ),
                    "ATTACHED_TO",
                )

        subnet_ids = _reference_ids(
            properties,
            {
                "subnet",
                "subnets",
            },
        )

        for subnet_id in subnet_ids:
            add_relationship(
                entity_id,
                azure_entity_by_resource_id
                .get(subnet_id),
                "ATTACHED_TO",
            )

        nsg_ids = _reference_ids(
            properties,
            {
                "networksecuritygroup",
            },
        )

        for nsg_id in nsg_ids:
            add_relationship(
                azure_entity_by_resource_id
                .get(nsg_id),
                entity_id,
                "PROTECTS",
            )

        if (
            resource_type
            == "azure_virtual_machine"
        ):
            nic_ids = _reference_ids(
                properties,
                {
                    "networkinterfaces",
                    "networkinterface",
                },
            )

            for nic_id in nic_ids:
                add_relationship(
                    entity_id,
                    azure_entity_by_resource_id
                    .get(nic_id),
                    "ATTACHED_TO",
                )

        if (
            resource_type
            == "azure_sql_database"
        ):
            parent = _parent_id(
                resource_id
            )

            add_relationship(
                azure_entity_by_resource_id
                .get(
                    _normalise_id(
                        parent
                    )
                ),
                entity_id,
                "CONTAINS",
            )

        if resource_type in {
            "azure_app_service",
            "azure_function_app",
        }:
            plan_id = properties.get(
                "serverFarmId"
            )

            add_relationship(
                azure_entity_by_resource_id
                .get(
                    _normalise_id(
                        plan_id
                    )
                ),
                entity_id,
                "CONTAINS",
            )

        if (
            resource_type
            == "azure_private_endpoint"
        ):
            connections = properties.get(
                "privateLinkServiceConnections",
                [],
            )

            if isinstance(
                connections,
                list,
            ):
                for connection in (
                    connections
                ):
                    if not isinstance(
                        connection,
                        dict,
                    ):
                        continue

                    connection_properties = (
                        connection.get(
                            "properties",
                            {},
                        )
                    )

                    if not isinstance(
                        connection_properties,
                        dict,
                    ):
                        continue

                    target_id = (
                        connection_properties
                        .get(
                            "privateLinkServiceId"
                        )
                    )

                    add_relationship(
                        entity_id,
                        azure_entity_by_resource_id
                        .get(
                            _normalise_id(
                                target_id
                            )
                        ),
                        "ROUTES_TO",
                    )

    # AKS to Kubernetes cluster
    # correlation.
    aks_clusters = {
        str(
            value.get("name")
            or ""
        ).lower(): entity_id
        for entity_id, value
        in azure_values_by_entity.items()
        if value.get(
            "resource_type"
        )
        == "azure_aks_cluster"
    }

    vm_entities_by_name = {
        str(
            value.get("name")
            or ""
        ).lower(): entity_id
        for entity_id, value
        in azure_values_by_entity.items()
        if value.get(
            "resource_type"
        )
        == "azure_virtual_machine"
    }

    vmss_entities_by_name = {
        str(
            value.get("name")
            or ""
        ).lower(): entity_id
        for entity_id, value
        in azure_values_by_entity.items()
        if value.get(
            "resource_type"
        )
        == (
            "azure_virtual_machine_"
            "scale_set"
        )
    }

    # Public IP and load-balancer
    # endpoint correlation.
    public_ip_values: dict[
        str,
        str,
    ] = {}

    for entity_id, value in (
        azure_values_by_entity.items()
    ):
        if (
            value.get(
                "resource_type"
            )
            != "azure_public_ip_address"
        ):
            continue

        properties = value.get(
            "properties",
            {},
        )

        if not isinstance(
            properties,
            dict,
        ):
            continue

        ip_address = properties.get(
            "ipAddress"
        )

        dns_settings = properties.get(
            "dnsSettings",
            {},
        )

        fqdn = (
            dns_settings.get("fqdn")
            if isinstance(
                dns_settings,
                dict,
            )
            else None
        )

        if ip_address:
            public_ip_values[
                str(ip_address).lower()
            ] = entity_id

        if fqdn:
            public_ip_values[
                str(fqdn).lower()
            ] = entity_id

    frontend_owner_by_endpoint: dict[
        str,
        str,
    ] = {}

    for entity_id, value in (
        azure_values_by_entity.items()
    ):
        if value.get(
            "resource_type"
        ) not in {
            "azure_load_balancer",
            "azure_application_gateway",
        }:
            continue

        properties = value.get(
            "properties",
            {},
        )

        if not isinstance(
            properties,
            dict,
        ):
            continue

        frontend_values = (
            properties.get(
                "frontendIPConfigurations",
                [],
            )
        )

        if not isinstance(
            frontend_values,
            list,
        ):
            continue

        for frontend in frontend_values:
            if not isinstance(
                frontend,
                dict,
            ):
                continue

            frontend_properties = (
                frontend.get(
                    "properties",
                    {},
                )
            )

            if not isinstance(
                frontend_properties,
                dict,
            ):
                continue

            private_ip = (
                frontend_properties.get(
                    "privateIPAddress"
                )
            )

            if private_ip:
                frontend_owner_by_endpoint[
                    str(
                        private_ip
                    ).lower()
                ] = entity_id

            public_ip = (
                frontend_properties.get(
                    "publicIPAddress",
                    {},
                )
            )

            if isinstance(
                public_ip,
                dict,
            ):
                public_ip_id = (
                    public_ip.get("id")
                )

                public_ip_entity = (
                    azure_entity_by_resource_id
                    .get(
                        _normalise_id(
                            public_ip_id
                        )
                    )
                )

                if public_ip_entity:
                    add_relationship(
                        entity_id,
                        public_ip_entity,
                        "EXPOSES",
                    )

                for endpoint, (
                    public_entity_id
                ) in (
                    public_ip_values.items()
                ):
                    if (
                        public_entity_id
                        == public_ip_entity
                    ):
                        frontend_owner_by_endpoint[
                            endpoint
                        ] = entity_id

    for entity in entities:
        if (
            entity.kind
            == "KubernetesCluster"
        ):
            add_relationship(
                aks_clusters.get(
                    entity.name.lower()
                ),
                entity.id,
                "RUNS",
                confidence=0.99,
            )

        elif (
            entity.kind
            == "KubernetesNode"
        ):
            provider_id = (
                _normalise_id(
                    entity.properties.get(
                        "provider_id"
                    )
                )
            )

            if not provider_id:
                continue

            parts = [
                part
                for part in (
                    provider_id.split("/")
                )
                if part
            ]

            lower_parts = [
                part.lower()
                for part in parts
            ]

            if (
                "virtualmachinescalesets"
                in lower_parts
            ):
                index = lower_parts.index(
                    "virtualmachinescalesets"
                )

                if (
                    index + 1
                    < len(parts)
                ):
                    vmss_name = parts[
                        index + 1
                    ].lower()

                    add_relationship(
                        vmss_entities_by_name
                        .get(vmss_name),
                        entity.id,
                        "RUNS",
                        confidence=0.99,
                    )

            elif (
                "virtualmachines"
                in lower_parts
            ):
                index = lower_parts.index(
                    "virtualmachines"
                )

                if (
                    index + 1
                    < len(parts)
                ):
                    vm_name = parts[
                        index + 1
                    ].lower()

                    add_relationship(
                        vm_entities_by_name
                        .get(vm_name),
                        entity.id,
                        "RUNS",
                        confidence=0.99,
                    )

        elif (
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

                for endpoint in (
                    ingress.get("ip"),
                    ingress.get(
                        "hostname"
                    ),
                ):
                    if not endpoint:
                        continue

                    add_relationship(
                        frontend_owner_by_endpoint
                        .get(
                            str(
                                endpoint
                            ).lower()
                        ),
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
                "azure_cloud_discovery": {
                    "resource_count":
                        len(
                            azure_values_by_entity
                        ),
                    "subscription_count":
                        len(
                            subscription_entities
                        ),
                    "agent_id":
                        agent.agent_id,
                },
            },
        }
    )
