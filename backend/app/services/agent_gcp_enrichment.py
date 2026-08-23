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
    RelationshipConfidenceSemantics,
    RelationshipOrigin,
    RelationshipType,
)
from app.services.canonical_identity import (
    canonical_gcp_identity,
)
from app.services.relationship_provenance import (
    relationship_provenance,
    source_reference,
)


KIND_MAP = {
    "gcp_organization":
        "GCPOrganization",

    "gcp_folder":
        "GCPFolder",

    "gcp_project":
        "GCPProject",

    "gcp_network":
        "GCPVPCNetwork",

    "gcp_subnetwork":
        "GCPSubnetwork",

    "gcp_firewall_rule":
        "GCPFirewallRule",

    "gcp_route":
        "GCPRoute",

    "gcp_address":
        "GCPIPAddress",

    "gcp_compute_instance":
        "GCPComputeInstance",

    "gcp_instance_group_manager":
        "GCPManagedInstanceGroup",

    "gcp_gke_cluster":
        "GCPGKECluster",

    "gcp_gke_node_pool":
        "GCPGKENodePool",

    "gcp_forwarding_rule":
        "GCPForwardingRule",

    "gcp_backend_service":
        "GCPBackendService",

    "gcp_health_check":
        "GCPHealthCheck",

    "gcp_cloud_sql_instance":
        "GCPCloudSQLInstance",

    "gcp_cloud_run_service":
        "GCPCloudRunService",

    "gcp_cloud_function":
        "GCPCloudFunction",

    "gcp_pubsub_topic":
        "GCPPubSubTopic",

    "gcp_pubsub_subscription":
        "GCPPubSubSubscription",
}


TYPE_MAP = {
    "gcp_organization": (
        "INFRASTRUCTURE",
        "BOUNDARY",
    ),
    "gcp_folder": (
        "INFRASTRUCTURE",
        "BOUNDARY",
    ),
    "gcp_project": (
        "INFRASTRUCTURE",
        "BOUNDARY",
    ),
    "gcp_network": (
        "NETWORK",
        "INFRASTRUCTURE",
    ),
    "gcp_subnetwork": (
        "NETWORK",
        "INFRASTRUCTURE",
    ),
    "gcp_firewall_rule": (
        "SECURITY",
        "NETWORK",
    ),
    "gcp_route": (
        "NETWORK",
        "INFRASTRUCTURE",
    ),
    "gcp_address": (
        "NETWORK",
        "ENDPOINT",
    ),
    "gcp_compute_instance": (
        "HOST",
        "COMPUTE",
    ),
    "gcp_instance_group_manager": (
        "COMPUTE",
        "INFRASTRUCTURE",
    ),
    "gcp_gke_cluster": (
        "CLUSTER",
        "INFRASTRUCTURE",
    ),
    "gcp_gke_node_pool": (
        "COMPUTE",
        "INFRASTRUCTURE",
    ),
    "gcp_forwarding_rule": (
        "NETWORK",
        "SERVICE",
    ),
    "gcp_backend_service": (
        "SERVICE",
        "NETWORK",
    ),
    "gcp_health_check": (
        "ENDPOINT",
        "NETWORK",
    ),
    "gcp_cloud_sql_instance": (
        "DATABASE",
        "SERVICE",
    ),
    "gcp_cloud_run_service": (
        "SERVICE",
        "WORKLOAD",
    ),
    "gcp_cloud_function": (
        "FUNCTION",
        "WORKLOAD",
    ),
    "gcp_pubsub_topic": (
        "SERVICE",
        "MESSAGING",
    ),
    "gcp_pubsub_subscription": (
        "SERVICE",
        "MESSAGING",
    ),
}


def _digest(
    value: str,
    length: int = 32,
) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:length]


def _normalise(
    value: Any,
) -> str:
    return (
        str(value or "")
        .strip()
        .rstrip("/")
        .lower()
    )


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
    resource_id: str,
) -> str:
    return canonical_gcp_identity(
        project_id=None,
        resource_type="GCPResource",
        resource_id=resource_id,
    ).canonical_id


def _references(
    value: Any,
    keys: set[str],
) -> list[str]:
    results: list[str] = []

    def walk(
        item: Any,
    ) -> None:
        if isinstance(item, dict):
            for key, nested in item.items():
                lowered = str(key).lower()

                if (
                    lowered in keys
                    and isinstance(
                        nested,
                        str,
                    )
                    and nested
                ):
                    results.append(
                        _normalise(nested)
                    )

                walk(nested)

        elif isinstance(item, list):
            for nested in item:
                walk(nested)

    walk(value)

    return sorted(set(results))


def enrich_snapshot_with_gcp(
    *,
    snapshot: GraphSnapshot,
    agent: TopoAgentRecord,
    submission:
        AgentSnapshotSubmission,
) -> GraphSnapshot:
    gcp_values: list[
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
                == "gcp"
            ):
                gcp_values.append(value)

    if not gcp_values:
        return snapshot

    entities = list(snapshot.entities)

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

    entity_by_resource_id: dict[
        str,
        str,
    ] = {}

    values_by_entity: dict[
        str,
        dict[str, Any],
    ] = {}

    existing_native_references = {
        entity.id: entity.external_id
        for entity in entities
        if entity.external_id
    }

    def add_relationship(
        source_id: str | None,
        target_id: str | None,
        relation_name: str,
        *,
        confidence: float | None = None,
        properties:
            dict[str, Any] | None = None,
        origin: RelationshipOrigin = RelationshipOrigin.DECLARED,
        source_references: list[Any] | None = None,
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

        references = list(source_references or [])

        for role, relationship_entity_id in (
            ("subject", source_id),
            ("object", target_id),
        ):
            value = values_by_entity.get(
                relationship_entity_id,
                {},
            )
            native_id = (
                value.get("resource_id")
                or value.get("id")
                or existing_native_references.get(
                    relationship_entity_id
                )
            )
            references.append(
                source_reference(
                    reference_type="source_native_entity",
                    reference=native_id,
                    source_system=(
                        "gcp" if value else "topology"
                    ),
                    attributes={"role": role},
                )
            )

        relationships.append(
            Relationship(
                id=(
                    "relationship:"
                    + _digest(
                        "|".join(key),
                        length=24,
                    )
                ),
                source_entity_id=source_id,
                target_entity_id=target_id,
                relationship_type=relation,
                source_system="gcp",
                observed_at=(
                    submission.collected_at
                ),
                confidence=confidence,
                confidence_semantics=(
                    RelationshipConfidenceSemantics.HEURISTIC_SCORE
                    if confidence is not None
                    else None
                ),
                directed=True,
                evidence_ids=[],
                provenance=relationship_provenance(
                    predicate=relation,
                    origin=origin,
                    source_component=(
                        "backend.app.services.agent_gcp_enrichment"
                    ),
                    source_references=references,
                    linker_version="gcp-inventory-linker:v1",
                ),
                properties=(
                    properties or {}
                ),
            )
        )

    for value in gcp_values:
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

        identity = canonical_gcp_identity(
            project_id=(
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
            "provider": "gcp",
            "project_id":
                value.get(
                    "account_id"
                ),
            "account_id":
                value.get(
                    "account_id"
                ),
            "region":
                value.get(
                    "region"
                ),
            "resource_type":
                resource_type,
            "resource_id":
                resource_id,
            "status":
                value.get(
                    "status"
                ),
            "network":
                value.get(
                    "vpc_id"
                ),
            "subnetworks":
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
                    source_system="gcp",
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

        normalized = _normalise(
            resource_id
        )

        entity_by_resource_id[
            normalized
        ] = entity_id

        # Also index common final resource
        # names for API references that use
        # different URL formats.
        entity_by_resource_id[
            normalized.split("/")[-1]
        ] = entity_id

        values_by_entity[
            entity_id
        ] = value

    project_entities: dict[
        str,
        str,
    ] = {}

    folder_entities: dict[
        str,
        str,
    ] = {}

    organization_entities: dict[
        str,
        str,
    ] = {}

    for entity_id, value in (
        values_by_entity.items()
    ):
        resource_type = value.get(
            "resource_type"
        )

        resource_id = _normalise(
            value.get(
                "resource_id"
            )
        )

        if resource_type == "gcp_project":
            project_id = str(
                value.get(
                    "account_id"
                )
                or value.get(
                    "properties",
                    {},
                ).get(
                    "project_id"
                )
                or ""
            ).lower()

            project_entities[
                project_id
            ] = entity_id

        elif resource_type == "gcp_folder":
            folder_entities[
                resource_id
            ] = entity_id

        elif (
            resource_type
            == "gcp_organization"
        ):
            organization_entities[
                resource_id
            ] = entity_id

    # Hierarchy relationships.
    for entity_id, value in (
        values_by_entity.items()
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

        parent = _normalise(
            properties.get("parent")
        )

        if resource_type == "gcp_folder":
            parent_entity = (
                folder_entities.get(
                    parent
                )
                or organization_entities.get(
                    parent
                )
            )

            add_relationship(
                parent_entity,
                entity_id,
                "CONTAINS",
            )

        elif resource_type == "gcp_project":
            parent_entity = (
                folder_entities.get(
                    parent
                )
                or organization_entities.get(
                    parent
                )
            )

            add_relationship(
                parent_entity,
                entity_id,
                "CONTAINS",
            )

        elif resource_type not in {
            "gcp_organization",
            "gcp_folder",
        }:
            project_id = str(
                value.get(
                    "account_id",
                    "",
                )
            ).lower()

            add_relationship(
                project_entities.get(
                    project_id
                ),
                entity_id,
                "CONTAINS",
            )

    # Provider-specific references.
    for entity_id, value in (
        values_by_entity.items()
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

        network = _normalise(
            value.get("vpc_id")
        )

        network_entity = (
            entity_by_resource_id.get(
                network
            )
            or entity_by_resource_id.get(
                network.split("/")[-1]
            )
        )

        if (
            resource_type
            == "gcp_subnetwork"
        ):
            add_relationship(
                network_entity,
                entity_id,
                "CONTAINS",
            )

        elif (
            resource_type
            == "gcp_firewall_rule"
        ):
            add_relationship(
                entity_id,
                network_entity,
                "PROTECTS",
            )

        elif resource_type == "gcp_route":
            add_relationship(
                entity_id,
                network_entity,
                "ATTACHED_TO",
            )

        elif network_entity:
            add_relationship(
                entity_id,
                network_entity,
                "ATTACHED_TO",
            )

        for subnetwork in (
            value.get(
                "subnet_ids",
                [],
            )
            or []
        ):
            normalized_subnetwork = (
                _normalise(subnetwork)
            )

            add_relationship(
                entity_id,
                (
                    entity_by_resource_id
                    .get(
                        normalized_subnetwork
                    )
                    or entity_by_resource_id
                    .get(
                        normalized_subnetwork
                        .split("/")[-1]
                    )
                ),
                "ATTACHED_TO",
            )

        if (
            resource_type
            == "gcp_gke_node_pool"
        ):
            cluster_id = _normalise(
                properties.get(
                    "cluster_id"
                )
            )

            add_relationship(
                entity_by_resource_id.get(
                    cluster_id
                ),
                entity_id,
                "CONTAINS",
            )

        if (
            resource_type
            == "gcp_forwarding_rule"
        ):
            targets = _references(
                properties,
                {
                    "backend_service",
                    "backendservice",
                    "target",
                },
            )

            for target in targets:
                add_relationship(
                    entity_id,
                    (
                        entity_by_resource_id
                        .get(target)
                        or entity_by_resource_id
                        .get(
                            target.split(
                                "/"
                            )[-1]
                        )
                    ),
                    "ROUTES_TO",
                )

        if (
            resource_type
            == "gcp_backend_service"
        ):
            groups = _references(
                properties,
                {
                    "group",
                    "instance_group",
                },
            )

            for group in groups:
                add_relationship(
                    entity_id,
                    (
                        entity_by_resource_id
                        .get(group)
                        or entity_by_resource_id
                        .get(
                            group.split(
                                "/"
                            )[-1]
                        )
                    ),
                    "ROUTES_TO",
                )

            health_checks = _references(
                properties,
                {
                    "health_checks",
                    "healthcheck",
                    "health_check",
                },
            )

            for health_check in (
                health_checks
            ):
                add_relationship(
                    entity_id,
                    (
                        entity_by_resource_id
                        .get(health_check)
                        or entity_by_resource_id
                        .get(
                            health_check
                            .split("/")[-1]
                        )
                    ),
                    "ATTACHED_TO",
                )

        if (
            resource_type
            == "gcp_pubsub_subscription"
        ):
            topics = _references(
                properties,
                {"topic"},
            )

            for topic in topics:
                add_relationship(
                    (
                        entity_by_resource_id
                        .get(topic)
                        or entity_by_resource_id
                        .get(
                            topic.split("/")[-1]
                        )
                    ),
                    entity_id,
                    "ROUTES_TO",
                )

    # Kubernetes correlations.
    gke_clusters = {
        (
            str(
                value.get("name")
                or ""
            ).lower(),
            str(
                value.get(
                    "account_id"
                )
                or ""
            ).lower(),
        ): entity_id
        for entity_id, value
        in values_by_entity.items()
        if value.get(
            "resource_type"
        )
        == "gcp_gke_cluster"
    }

    node_pools = {
        (
            str(
                value.get(
                    "properties",
                    {},
                ).get(
                    "cluster_name"
                )
                or ""
            ).lower(),
            str(
                value.get("name")
                or ""
            ).lower(),
        ): entity_id
        for entity_id, value
        in values_by_entity.items()
        if value.get(
            "resource_type"
        )
        == "gcp_gke_node_pool"
    }

    compute_instances = {
        (
            str(
                value.get(
                    "account_id"
                )
                or ""
            ).lower(),
            str(
                value.get("name")
                or ""
            ).lower(),
        ): entity_id
        for entity_id, value
        in values_by_entity.items()
        if value.get(
            "resource_type"
        )
        == "gcp_compute_instance"
    }

    forwarding_rule_by_ip: dict[
        str,
        str,
    ] = {}

    for entity_id, value in (
        values_by_entity.items()
    ):
        if (
            value.get(
                "resource_type"
            )
            != "gcp_forwarding_rule"
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

        ip_address = (
            properties.get(
                "ip_address"
            )
            or properties.get(
                "IPAddress"
            )
        )

        if ip_address:
            forwarding_rule_by_ip[
                str(ip_address).lower()
            ] = entity_id

    for entity in entities:
        if (
            entity.kind
            == "KubernetesCluster"
        ):
            # Prefer exact name. A project
            # match is used when available.
            matches = [
                cloud_entity
                for (
                    cluster_name,
                    _project_id,
                ), cloud_entity
                in gke_clusters.items()
                if cluster_name
                == entity.name.lower()
            ]

            if len(matches) == 1:
                add_relationship(
                    matches[0],
                    entity.id,
                    "RUNS",
                    confidence=0.99,
                    origin=RelationshipOrigin.INFERRED,
                )

        elif (
            entity.kind
            == "KubernetesNode"
        ):
            provider_id = str(
                entity.properties.get(
                    "provider_id",
                    "",
                )
            )

            if provider_id.startswith(
                "gce://"
            ):
                parts = provider_id[
                    len("gce://"):
                ].split("/")

                if len(parts) >= 3:
                    project_id = (
                        parts[0].lower()
                    )

                    instance_name = (
                        parts[-1].lower()
                    )

                    add_relationship(
                        compute_instances.get(
                            (
                                project_id,
                                instance_name,
                            )
                        ),
                        entity.id,
                        "RUNS",
                        confidence=0.99,
                        origin=RelationshipOrigin.INFERRED,
                    )

            node_pool_name = (
                entity.labels.get(
                    (
                        "cloud.google.com/"
                        "gke-nodepool"
                    )
                )
            )

            cluster_name = (
                entity.labels.get(
                    (
                        "cluster-name"
                    )
                )
                or snapshot.scope.get(
                    "cluster"
                )
            )

            if (
                node_pool_name
                and cluster_name
            ):
                add_relationship(
                    node_pools.get(
                        (
                            str(
                                cluster_name
                            ).lower(),
                            str(
                                node_pool_name
                            ).lower(),
                        )
                    ),
                    entity.id,
                    "RUNS",
                    confidence=0.98,
                    origin=RelationshipOrigin.INFERRED,
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
                        forwarding_rule_by_ip
                        .get(
                            str(
                                endpoint
                            ).lower()
                        ),
                        entity.id,
                        "ROUTES_TO",
                        confidence=0.99,
                        origin=RelationshipOrigin.INFERRED,
                    )

    return snapshot.model_copy(
        update={
            "entities": entities,
            "relationships":
                relationships,
            "metadata": {
                **snapshot.metadata,
                "gcp_cloud_discovery": {
                    "resource_count":
                        len(
                            values_by_entity
                        ),
                    "project_count":
                        len(
                            project_entities
                        ),
                    "agent_id":
                        agent.agent_id,
                },
            },
        }
    )
