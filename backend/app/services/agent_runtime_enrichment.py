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
    RelationshipOrigin,
    RelationshipType,
)
from app.services.relationship_provenance import (
    relationship_provenance,
    source_reference,
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
    *names: str,
):
    return _enum_member(
        EntityType,
        tuple(names)
        + ("UNKNOWN",),
    )


def _relationship_type(
    *names: str,
):
    return _enum_member(
        RelationshipType,
        tuple(names)
        + ("UNKNOWN",),
    )


def _digest(
    value: str,
    length: int = 24,
) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:length]


def _relationship_id(
    source_id: str,
    relationship: str,
    target_id: str,
) -> str:
    return (
        "relationship:"
        + _digest(
            f"{source_id}|"
            f"{relationship}|"
            f"{target_id}"
        )
    )


def enrich_runtime_inventory(
    *,
    snapshot: GraphSnapshot,
    agent: TopoAgentRecord,
    submission: AgentSnapshotSubmission,
) -> GraphSnapshot:
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

    native_references = {
        entity.id: entity.external_id
        for entity in entities
        if entity.external_id
    }

    relationship_keys = {
        (
            item.source_entity_id,
            item.relationship_type.value,
            item.target_entity_id,
        )
        for item in relationships
    }

    observed_at = (
        submission.collected_at
    )

    inventory = submission.inventory

    processes_by_pid: dict[
        int,
        str,
    ] = {}

    hosts_by_name: dict[
        str,
        str,
    ] = {}

    docker_networks: dict[
        str,
        str,
    ] = {}

    docker_containers: dict[
        str,
        str,
    ] = {}

    pod_by_container_id: dict[
        str,
        str,
    ] = {}

    for entity in entities:
        if (
            entity.kind
            != "KubernetesPod"
        ):
            continue

        values = entity.properties.get(
            "container_ids",
            [],
        )

        if not isinstance(values, list):
            continue

        for container_id in values:
            normalized = str(
                container_id
            )

            pod_by_container_id[
                normalized
            ] = entity.id

            pod_by_container_id[
                normalized[:12]
            ] = entity.id

    def add_entity(
        *,
        entity_id: str,
        kind: str,
        name: str,
        entity_types:
            tuple[str, ...],
        external_id:
            str | None = None,
        labels:
            dict[str, str] | None = None,
        properties:
            dict[str, Any] | None = None,
    ) -> str:
        if external_id:
            native_references[entity_id] = external_id

        if entity_id in entity_ids:
            return entity_id

        entities.append(
            Entity(
                id=entity_id,
                entity_type=_entity_type(
                    *entity_types
                ),
                kind=kind,
                name=name,
                source_system=(
                    "topo-agent"
                ),
                external_id=external_id,
                environment=(
                    submission.environment
                ),
                observed_at=observed_at,
                confidence=1.0,
                labels=labels or {},
                properties=(
                    properties or {}
                ),
            )
        )

        entity_ids.add(entity_id)

        return entity_id

    def add_relationship(
        *,
        source_id: str,
        target_id: str,
        relation_name: str,
        properties:
            dict[str, Any] | None = None,
        source_references: list[Any] | None = None,
    ) -> None:
        relation = (
            _relationship_type(
                relation_name
            )
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
                id=_relationship_id(
                    source_id,
                    relation.value,
                    target_id,
                ),
                source_entity_id=source_id,
                target_entity_id=target_id,
                relationship_type=relation,
                source_system=(
                    "topo-agent"
                ),
                observed_at=observed_at,
                directed=True,
                evidence_ids=[],
                provenance=relationship_provenance(
                    predicate=relation,
                    origin=RelationshipOrigin.OBSERVED,
                    source_component=(
                        "backend.app.services.agent_runtime_enrichment"
                    ),
                    source_references=[
                        source_reference(
                            reference_type="runtime_entity_native_id",
                            reference=native_references.get(source_id),
                            source_system="topo-agent",
                            attributes={"role": "subject"},
                        ),
                        source_reference(
                            reference_type="runtime_entity_native_id",
                            reference=native_references.get(target_id),
                            source_system="topo-agent",
                            attributes={"role": "object"},
                        ),
                        *(source_references or []),
                    ],
                    linker_version="runtime-inventory-linker:v1",
                ),
                properties=(
                    properties or {}
                ),
            )
        )

    for host in inventory.get(
        "hosts",
        [],
    ):
        host_name = str(
            host.get("name")
            or host.get("id")
            or "unknown-host"
        )

        host_id = (
            "host:"
            + _digest(
                host_name
            )
        )

        add_entity(
            entity_id=host_id,
            kind="Host",
            name=host_name,
            entity_types=(
                "HOST",
                "COMPUTE",
            ),
            external_id=str(
                host.get("id")
                or host_name
            ),
            properties=host,
        )

        hosts_by_name[
            host_name
        ] = host_id

    default_host_id = next(
        iter(
            hosts_by_name.values()
        ),
        None,
    )

    for process in inventory.get(
        "processes",
        [],
    ):
        pid_value = process.get(
            "pid"
        )

        if pid_value is None:
            continue

        pid = int(pid_value)

        host_name = str(
            process.get(
                "host_id"
            )
            or "unknown-host"
        )

        process_name = str(
            process.get("name")
            or f"pid-{pid}"
        )

        process_id = (
            "process:"
            + _digest(
                f"{host_name}|{pid}|"
                f"{process.get('create_time')}"
            )
        )

        add_entity(
            entity_id=process_id,
            kind="Process",
            name=process_name,
            entity_types=(
                "PROCESS",
                "WORKLOAD",
                "COMPUTE",
            ),
            external_id=str(pid),
            properties=process,
        )

        processes_by_pid[
            pid
        ] = process_id

        host_id = (
            hosts_by_name.get(
                host_name
            )
            or default_host_id
        )

        if host_id:
            add_relationship(
                source_id=host_id,
                target_id=process_id,
                relation_name=(
                    "CONTAINS"
                ),
            )

    for service in inventory.get(
        "system_services",
        [],
    ):
        service_name = str(
            service.get("name")
            or "unknown-service"
        )

        service_id = (
            "system-service:"
            + _digest(service_name)
        )

        add_entity(
            entity_id=service_id,
            kind="SystemService",
            name=service_name,
            entity_types=(
                "SERVICE",
                "WORKLOAD",
            ),
            properties=service,
        )

        if default_host_id:
            add_relationship(
                source_id=default_host_id,
                target_id=service_id,
                relation_name=(
                    "CONTAINS"
                ),
            )

    for network in inventory.get(
        "docker_networks",
        [],
    ):
        network_external_id = str(
            network.get("id")
            or network.get("name")
            or "unknown"
        )

        network_name = str(
            network.get("name")
            or network_external_id
        )

        network_id = (
            "docker-network:"
            + _digest(
                network_external_id
            )
        )

        add_entity(
            entity_id=network_id,
            kind="DockerNetwork",
            name=network_name,
            entity_types=(
                "NETWORK",
                "INFRASTRUCTURE",
            ),
            external_id=(
                network_external_id
            ),
            labels=network.get(
                "labels",
                {},
            ),
            properties=network,
        )

        docker_networks[
            network_external_id
        ] = network_id

        docker_networks[
            network_name
        ] = network_id

    for container in inventory.get(
        "docker_containers",
        [],
    ):
        container_external_id = str(
            container.get("id")
            or container.get(
                "short_id"
            )
            or container.get(
                "name"
            )
        )

        container_name = str(
            container.get("name")
            or container_external_id
        )

        container_id = (
            "container:"
            + _digest(
                container_external_id
            )
        )

        add_entity(
            entity_id=container_id,
            kind="Container",
            name=container_name,
            entity_types=(
                "CONTAINER",
                "WORKLOAD",
                "COMPUTE",
            ),
            external_id=(
                container_external_id
            ),
            labels=container.get(
                "labels",
                {},
            ),
            properties=container,
        )

        docker_containers[
            container_external_id
        ] = container_id

        docker_containers[
            container_external_id[:12]
        ] = container_id

        pid_value = container.get(
            "pid"
        )

        if pid_value:
            process_id = (
                processes_by_pid.get(
                    int(pid_value)
                )
            )

            if process_id:
                add_relationship(
                    source_id=container_id,
                    target_id=process_id,
                    relation_name="RUNS",
                )

        if default_host_id:
            add_relationship(
                source_id=default_host_id,
                target_id=container_id,
                relation_name=(
                    "CONTAINS"
                ),
            )

        pod_id = (
            pod_by_container_id.get(
                container_external_id
            )
            or pod_by_container_id.get(
                container_external_id[
                    :12
                ]
            )
        )

        if pod_id:
            add_relationship(
                source_id=pod_id,
                target_id=container_id,
                relation_name="RUNS",
            )

        for network in container.get(
            "networks",
            [],
        ):
            network_id_value = (
                network.get(
                    "network_id"
                )
            )

            network_name = (
                network.get("name")
            )

            network_entity_id = (
                docker_networks.get(
                    str(
                        network_id_value
                    )
                )
                or docker_networks.get(
                    str(network_name)
                )
            )

            if network_entity_id:
                add_relationship(
                    source_id=container_id,
                    target_id=(
                        network_entity_id
                    ),
                    relation_name=(
                        "ATTACHED_TO"
                    ),
                )

    for port in inventory.get(
        "listening_ports",
        [],
    ):
        address = str(
            port.get("address")
            or "0.0.0.0"
        )

        port_number = port.get(
            "port"
        )

        protocol = str(
            port.get("protocol")
            or "tcp"
        )

        port_id = (
            "network-port:"
            + _digest(
                f"{address}|"
                f"{port_number}|"
                f"{protocol}"
            )
        )

        add_entity(
            entity_id=port_id,
            kind="ListeningPort",
            name=(
                f"{protocol}://"
                f"{address}:{port_number}"
            ),
            entity_types=(
                "NETWORK",
                "ENDPOINT",
            ),
            properties=port,
        )

        pid_value = port.get("pid")

        process_id = (
            processes_by_pid.get(
                int(pid_value)
            )
            if pid_value
            else None
        )

        if process_id:
            add_relationship(
                source_id=process_id,
                target_id=port_id,
                relation_name="EXPOSES",
            )
        elif default_host_id:
            add_relationship(
                source_id=default_host_id,
                target_id=port_id,
                relation_name="EXPOSES",
            )

    for connection in inventory.get(
        "network_connections",
        [],
    ):
        remote_address = str(
            connection.get(
                "remote_address"
            )
            or "unknown"
        )

        remote_port = connection.get(
            "remote_port"
        )

        protocol = str(
            connection.get(
                "protocol"
            )
            or "tcp"
        )

        endpoint_id = (
            "remote-endpoint:"
            + _digest(
                f"{protocol}|"
                f"{remote_address}|"
                f"{remote_port}"
            )
        )

        add_entity(
            entity_id=endpoint_id,
            kind="NetworkEndpoint",
            name=(
                f"{protocol}://"
                f"{remote_address}:"
                f"{remote_port}"
            ),
            entity_types=(
                "NETWORK",
                "ENDPOINT",
                "EXTERNAL",
            ),
            external_id=(
                f"{remote_address}:"
                f"{remote_port}"
            ),
            properties={
                "address":
                    remote_address,
                "port":
                    remote_port,
                "protocol":
                    protocol,
            },
        )

        pid_value = connection.get(
            "pid"
        )

        source_id = (
            processes_by_pid.get(
                int(pid_value)
            )
            if pid_value
            else None
        )

        if source_id is None:
            source_id = default_host_id

        if source_id:
            add_relationship(
                source_id=source_id,
                target_id=endpoint_id,
                relation_name="CALLS",
                properties={
                    "local_address":
                        connection.get(
                            "local_address"
                        ),
                    "local_port":
                        connection.get(
                            "local_port"
                        ),
                    "status":
                        connection.get(
                            "status"
                        ),
                    "protocol":
                        protocol,
                },
            )

    return snapshot.model_copy(
        update={
            "entities": entities,
            "relationships":
                relationships,
            "metadata": {
                **snapshot.metadata,
                "runtime_enrichment": {
                    "host_count":
                        len(
                            inventory.get(
                                "hosts",
                                [],
                            )
                        ),
                    "process_count":
                        len(
                            inventory.get(
                                "processes",
                                [],
                            )
                        ),
                    "container_count":
                        len(
                            inventory.get(
                                "docker_containers",
                                [],
                            )
                        ),
                    "network_connection_count":
                        len(
                            inventory.get(
                                "network_connections",
                                [],
                            )
                        ),
                },
            },
        }
    )
