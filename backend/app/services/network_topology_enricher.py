from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from kubernetes import client, config
from kubernetes.config.config_exception import (
    ConfigException,
)

from app.models.topology import (
    Entity,
    GraphSnapshot,
    Relationship,
)
from app.services.canonical_identity import (
    canonical_kubernetes_identity,
)


NETWORK_ANNOTATION_OUTBOUND = (
    "topo.ai/outbound-hosts"
)

NETWORK_ANNOTATION_DEPENDS_ON = (
    "topo.ai/depends-on"
)


def _scope_dict(
    snapshot: GraphSnapshot,
) -> dict[str, Any]:
    if isinstance(snapshot.scope, dict):
        return snapshot.scope

    if hasattr(snapshot.scope, "model_dump"):
        return snapshot.scope.model_dump()

    return {}


def _cluster_name(
    snapshot: GraphSnapshot,
) -> str:
    scope = _scope_dict(snapshot)

    return str(
        scope.get("cluster_name")
        or scope.get("cluster")
        or "unknown-cluster"
    )


def _namespace(
    entity: Entity,
) -> str | None:
    value = entity.properties.get(
        "namespace"
    )

    return (
        str(value)
        if value is not None
        else None
    )


def _hash(
    value: str,
    length: int = 24,
) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:length]


def _entity_id(
    cluster_name: str,
    kind: str,
    uid: str | None,
    namespace: str | None,
    name: str,
) -> str:
    return canonical_kubernetes_identity(
        cluster_name=cluster_name,
        kind=kind,
        name=name,
        namespace=namespace,
        uid=uid,
    ).canonical_id


def _relationship_id(
    source_id: str,
    target_id: str,
    relationship_type: str,
) -> str:
    value = "|".join(
        [
            source_id,
            relationship_type,
            target_id,
        ]
    )

    return f"relationship:{_hash(value, 32)}"


def _normalize_labels(
    values: dict | None,
) -> dict[str, str]:
    return {
        str(key): str(value)
        for key, value in (
            values or {}
        ).items()
    }


def _find_entity(
    entities: dict[str, Entity],
    kind: str,
    name: str,
    namespace: str | None,
) -> Entity | None:
    for entity in entities.values():
        if entity.kind != kind:
            continue

        if entity.name != name:
            continue

        if _namespace(entity) != namespace:
            continue

        return entity

    return None


def _make_entity(
    *,
    entity_id: str,
    entity_type: str,
    kind: str,
    name: str,
    source_system: str,
    external_id: str | None,
    observed_at: datetime,
    labels: dict[str, str],
    properties: dict[str, Any],
) -> Entity:
    identity = None
    if kind.startswith("Kubernetes"):
        cluster = properties.get("cluster")
        if cluster:
            identity = canonical_kubernetes_identity(
                cluster_name=str(cluster),
                kind=kind,
                name=name,
                namespace=(
                    str(properties["namespace"])
                    if properties.get("namespace")
                    else None
                ),
                uid=external_id,
            )
            entity_id = identity.canonical_id

    return Entity(
        id=entity_id,
        entity_type=entity_type,
        kind=kind,
        name=name,
        source_system=source_system,
        external_id=external_id,
        aliases=(
            identity.aliases
            if identity is not None
            else []
        ),
        identity_version=(
            identity.identity_version
            if identity is not None
            else "legacy"
        ),
        environment=None,
        observed_at=observed_at,
        confidence=1.0,
        labels=labels,
        properties=properties,
    )


def _add_relationship(
    relationships: dict[
        tuple[str, str, str],
        Relationship,
    ],
    *,
    source_id: str,
    target_id: str,
    relationship_type: str,
    observed_at: datetime,
    properties: dict[str, Any] | None = None,
) -> None:
    key = (
        source_id,
        target_id,
        relationship_type,
    )

    if key in relationships:
        return

    relationships[key] = Relationship(
        id=_relationship_id(
            source_id,
            target_id,
            relationship_type,
        ),
        source_entity_id=source_id,
        target_entity_id=target_id,
        relationship_type=relationship_type,
        source_system="kubernetes",
        observed_at=observed_at,
        confidence=1.0,
        directed=True,
        evidence_ids=[],
        properties=properties or {},
    )


def _load_kubernetes_config() -> None:
    try:
        config.load_incluster_config()
    except ConfigException:
        config.load_kube_config()


def _extract_ingress_backends(
    ingress: Any,
) -> list[dict[str, Any]]:
    backends: list[
        dict[str, Any]
    ] = []

    default_backend = (
        ingress.spec.default_backend
    )

    if (
        default_backend
        and default_backend.service
    ):
        backends.append(
            {
                "host": None,
                "path": "/",
                "service_name": (
                    default_backend
                    .service.name
                ),
                "service_port": (
                    default_backend
                    .service.port.number
                    or default_backend
                    .service.port.name
                ),
            }
        )

    for rule in ingress.spec.rules or []:
        if not rule.http:
            continue

        for path in (
            rule.http.paths or []
        ):
            if not path.backend.service:
                continue

            backends.append(
                {
                    "host": rule.host,
                    "path": (
                        path.path or "/"
                    ),
                    "service_name": (
                        path.backend
                        .service.name
                    ),
                    "service_port": (
                        path.backend
                        .service.port.number
                        or path.backend
                        .service.port.name
                    ),
                }
            )

    return backends


def _parse_dependency_values(
    value: str | None,
) -> list[str]:
    if not value:
        return []

    return [
        item.strip()
        for item in value.split(",")
        if item.strip()
    ]


def _external_host(
    value: str,
) -> tuple[str, int | None]:
    parsed_value = value

    if "://" not in parsed_value:
        parsed_value = (
            f"//{parsed_value}"
        )

    parsed = urlparse(parsed_value)

    host = (
        parsed.hostname
        or value.split("/")[0]
    )

    try:
        port = parsed.port
    except ValueError:
        port = None

    return host.lower(), port


def enrich_kubernetes_network_topology(
    snapshot: GraphSnapshot,
) -> GraphSnapshot:
    """
    Add network entities and relationships to an
    existing Kubernetes topology snapshot.
    """

    _load_kubernetes_config()

    core_api = client.CoreV1Api()
    networking_api = (
        client.NetworkingV1Api()
    )
    discovery_api = (
        client.DiscoveryV1Api()
    )

    scope = _scope_dict(snapshot)

    namespace = (
        scope.get("namespace")
        or scope.get("kubernetes_namespace")
    )

    if not namespace:
        raise ValueError(
            "Network discovery requires a "
            "namespace-scoped snapshot."
        )

    namespace = str(namespace)
    cluster_name = _cluster_name(
        snapshot
    )

    observed_at = snapshot.collected_at

    entities = {
        entity.id: entity
        for entity in snapshot.entities
    }

    relationships = {
        (
            relationship.source_entity_id,
            relationship.target_entity_id,
            relationship
            .relationship_type.value,
        ): relationship
        for relationship
        in snapshot.relationships
    }

    errors: list[str] = []

    try:
        services = (
            core_api
            .list_namespaced_service(
                namespace=namespace
            )
            .items
        )
    except Exception as exc:
        services = []
        errors.append(
            "Service discovery failed: "
            f"{type(exc).__name__}: {exc}"
        )

    try:
        pods = (
            core_api
            .list_namespaced_pod(
                namespace=namespace
            )
            .items
        )
    except Exception as exc:
        pods = []
        errors.append(
            "Pod discovery failed: "
            f"{type(exc).__name__}: {exc}"
        )

    try:
        ingresses = (
            networking_api
            .list_namespaced_ingress(
                namespace=namespace
            )
            .items
        )
    except Exception as exc:
        ingresses = []
        errors.append(
            "Ingress discovery failed: "
            f"{type(exc).__name__}: {exc}"
        )

    try:
        endpoint_slices = (
            discovery_api
            .list_namespaced_endpoint_slice(
                namespace=namespace
            )
            .items
        )
    except Exception as exc:
        endpoint_slices = []
        errors.append(
            "EndpointSlice discovery failed: "
            f"{type(exc).__name__}: {exc}"
        )

    service_entities: dict[
        tuple[str, str],
        Entity,
    ] = {}

    pod_entities_by_uid: dict[
        str,
        Entity,
    ] = {}

    pod_entities_by_name: dict[
        tuple[str, str],
        Entity,
    ] = {}

    for pod in pods:
        pod_entity = _find_entity(
            entities,
            "KubernetesPod",
            pod.metadata.name,
            namespace,
        )

        if pod_entity is None:
            continue

        pod_entities_by_name[
            (
                namespace,
                pod.metadata.name,
            )
        ] = pod_entity

        if pod.metadata.uid:
            pod_entities_by_uid[
                str(pod.metadata.uid)
            ] = pod_entity

    # Services and Service → Pod selector edges.
    for service in services:
        service_name = (
            service.metadata.name
        )

        service_uid = (
            str(service.metadata.uid)
            if service.metadata.uid
            else None
        )

        selector = {
            str(key): str(value)
            for key, value in (
                service.spec.selector
                or {}
            ).items()
        }

        properties = {
            "cluster": cluster_name,
            "namespace": namespace,
            "service_type": (
                service.spec.type
            ),
            "cluster_ip": (
                service.spec.cluster_ip
            ),
            "external_name": (
                service.spec.external_name
            ),
            "selector": selector,
            "ports": [
                {
                    "name": port.name,
                    "port": port.port,
                    "protocol": (
                        port.protocol
                    ),
                    "target_port": str(
                        port.target_port
                    ),
                }
                for port in (
                    service.spec.ports
                    or []
                )
            ],
        }

        existing = _find_entity(
            entities,
            "KubernetesService",
            service_name,
            namespace,
        )

        if existing:
            service_entity = (
                existing.model_copy(
                    update={
                        "labels":
                            _normalize_labels(
                                service
                                .metadata.labels
                            ),
                        "properties": {
                            **existing.properties,
                            **properties,
                        },
                    }
                )
            )
        else:
            service_entity = _make_entity(
                entity_id=_entity_id(
                    cluster_name,
                    "service",
                    service_uid,
                    namespace,
                    service_name,
                ),
                entity_type="endpoint",
                kind="KubernetesService",
                name=service_name,
                source_system="kubernetes",
                external_id=service_uid,
                observed_at=observed_at,
                labels=_normalize_labels(
                    service.metadata.labels
                ),
                properties=properties,
            )

        entities[
            service_entity.id
        ] = service_entity

        service_entities[
            (
                namespace,
                service_name,
            )
        ] = service_entity

        if selector:
            for pod in pods:
                pod_labels = (
                    pod.metadata.labels
                    or {}
                )

                selected = all(
                    str(
                        pod_labels.get(key)
                    )
                    == value
                    for key, value
                    in selector.items()
                )

                if not selected:
                    continue

                pod_entity = (
                    pod_entities_by_name.get(
                        (
                            namespace,
                            pod.metadata.name,
                        )
                    )
                )

                if not pod_entity:
                    continue

                _add_relationship(
                    relationships,
                    source_id=(
                        service_entity.id
                    ),
                    target_id=(
                        pod_entity.id
                    ),
                    relationship_type=(
                        "selects"
                    ),
                    observed_at=(
                        observed_at
                    ),
                    properties={
                        "selector": selector,
                    },
                )

        if (
            service.spec.type
            == "ExternalName"
            and service.spec.external_name
        ):
            host = (
                service.spec
                .external_name
                .lower()
            )

            dns_entity_id = (
                f"dns:{_hash(host, 32)}"
            )

            dns_entity = _make_entity(
                entity_id=dns_entity_id,
                entity_type="endpoint",
                kind="DNSName",
                name=host,
                source_system="kubernetes",
                external_id=host,
                observed_at=observed_at,
                labels={},
                properties={
                    "hostname": host,
                    "resolution_status":
                        "not_checked",
                    "external": True,
                },
            )

            entities[
                dns_entity.id
            ] = dns_entity

            _add_relationship(
                relationships,
                source_id=(
                    service_entity.id
                ),
                target_id=dns_entity.id,
                relationship_type=(
                    "resolves_to"
                ),
                observed_at=observed_at,
            )

    # Ingress → Service routes.
    for ingress in ingresses:
        ingress_name = (
            ingress.metadata.name
        )

        ingress_uid = (
            str(ingress.metadata.uid)
            if ingress.metadata.uid
            else None
        )

        backends = (
            _extract_ingress_backends(
                ingress
            )
        )

        existing = _find_entity(
            entities,
            "KubernetesIngress",
            ingress_name,
            namespace,
        )

        ingress_properties = {
            "cluster": cluster_name,
            "namespace": namespace,
            "ingress_class_name": (
                ingress.spec
                .ingress_class_name
            ),
            "backends": backends,
            "tls_hosts": [
                host
                for item in (
                    ingress.spec.tls or []
                )
                for host in (
                    item.hosts or []
                )
            ],
        }

        if existing:
            ingress_entity = (
                existing.model_copy(
                    update={
                        "labels":
                            _normalize_labels(
                                ingress
                                .metadata.labels
                            ),
                        "properties": {
                            **existing.properties,
                            **ingress_properties,
                        },
                    }
                )
            )
        else:
            ingress_entity = _make_entity(
                entity_id=_entity_id(
                    cluster_name,
                    "ingress",
                    ingress_uid,
                    namespace,
                    ingress_name,
                ),
                entity_type="endpoint",
                kind="KubernetesIngress",
                name=ingress_name,
                source_system="kubernetes",
                external_id=ingress_uid,
                observed_at=observed_at,
                labels=_normalize_labels(
                    ingress.metadata.labels
                ),
                properties=(
                    ingress_properties
                ),
            )

        entities[
            ingress_entity.id
        ] = ingress_entity

        for backend in backends:
            service_entity = (
                service_entities.get(
                    (
                        namespace,
                        backend[
                            "service_name"
                        ],
                    )
                )
            )

            if not service_entity:
                continue

            _add_relationship(
                relationships,
                source_id=(
                    ingress_entity.id
                ),
                target_id=(
                    service_entity.id
                ),
                relationship_type=(
                    "routes_to"
                ),
                observed_at=observed_at,
                properties={
                    "host": backend["host"],
                    "path": backend["path"],
                    "service_port": (
                        backend[
                            "service_port"
                        ]
                    ),
                },
            )

    # Service → EndpointSlice → Pod/IP.
    for endpoint_slice in endpoint_slices:
        slice_name = (
            endpoint_slice.metadata.name
        )

        slice_uid = (
            str(
                endpoint_slice
                .metadata.uid
            )
            if endpoint_slice.metadata.uid
            else None
        )

        labels = (
            endpoint_slice.metadata.labels
            or {}
        )

        service_name = labels.get(
            "kubernetes.io/service-name"
        )

        ready_count = 0
        total_count = 0

        for endpoint in (
            endpoint_slice.endpoints
            or []
        ):
            total_count += 1

            if (
                endpoint.conditions
                and endpoint.conditions.ready
            ):
                ready_count += 1

        slice_entity = _make_entity(
            entity_id=_entity_id(
                cluster_name,
                "endpointslice",
                slice_uid,
                namespace,
                slice_name,
            ),
            entity_type="network",
            kind="KubernetesEndpointSlice",
            name=slice_name,
            source_system="kubernetes",
            external_id=slice_uid,
            observed_at=observed_at,
            labels=_normalize_labels(
                labels
            ),
            properties={
                "cluster": cluster_name,
                "namespace": namespace,
                "service_name":
                    service_name,
                "address_type":
                    endpoint_slice
                    .address_type,
                "ready_endpoint_count":
                    ready_count,
                "total_endpoint_count":
                    total_count,
                "ports": [
                    {
                        "name": port.name,
                        "port": port.port,
                        "protocol":
                            port.protocol,
                    }
                    for port in (
                        endpoint_slice.ports
                        or []
                    )
                ],
            },
        )

        entities[
            slice_entity.id
        ] = slice_entity

        service_entity = (
            service_entities.get(
                (
                    namespace,
                    service_name,
                )
            )
            if service_name
            else None
        )

        if service_entity:
            _add_relationship(
                relationships,
                source_id=(
                    service_entity.id
                ),
                target_id=(
                    slice_entity.id
                ),
                relationship_type=(
                    "exposes"
                ),
                observed_at=observed_at,
            )

        for endpoint in (
            endpoint_slice.endpoints
            or []
        ):
            target_ref = (
                endpoint.target_ref
            )

            pod_entity = None

            if (
                target_ref
                and target_ref.uid
            ):
                pod_entity = (
                    pod_entities_by_uid.get(
                        str(
                            target_ref.uid
                        )
                    )
                )

            if pod_entity:
                _add_relationship(
                    relationships,
                    source_id=(
                        slice_entity.id
                    ),
                    target_id=(
                        pod_entity.id
                    ),
                    relationship_type=(
                        "routes_to"
                    ),
                    observed_at=(
                        observed_at
                    ),
                    properties={
                        "ready": bool(
                            endpoint.conditions
                            and endpoint
                            .conditions.ready
                        ),
                        "addresses": list(
                            endpoint.addresses
                            or []
                        ),
                    },
                )

                continue

            for address in (
                endpoint.addresses or []
            ):
                endpoint_id = (
                    "network:endpoint:"
                    f"{_hash(address, 32)}"
                )

                address_entity = (
                    _make_entity(
                        entity_id=endpoint_id,
                        entity_type="network",
                        kind=(
                            "NetworkEndpoint"
                        ),
                        name=address,
                        source_system=(
                            "kubernetes"
                        ),
                        external_id=address,
                        observed_at=(
                            observed_at
                        ),
                        labels={},
                        properties={
                            "address":
                                address,
                            "namespace":
                                namespace,
                            "ready": bool(
                                endpoint
                                .conditions
                                and endpoint
                                .conditions.ready
                            ),
                        },
                    )
                )

                entities[
                    address_entity.id
                ] = address_entity

                _add_relationship(
                    relationships,
                    source_id=(
                        slice_entity.id
                    ),
                    target_id=(
                        address_entity.id
                    ),
                    relationship_type=(
                        "routes_to"
                    ),
                    observed_at=(
                        observed_at
                    ),
                )

    # Declared application dependencies from
    # Pod annotations.
    for pod in pods:
        annotations = (
            pod.metadata.annotations
            or {}
        )

        pod_entity = (
            pod_entities_by_name.get(
                (
                    namespace,
                    pod.metadata.name,
                )
            )
        )

        if not pod_entity:
            continue

        outbound_hosts = (
            _parse_dependency_values(
                annotations.get(
                    NETWORK_ANNOTATION_OUTBOUND
                )
            )
        )

        for outbound_value in (
            outbound_hosts
        ):
            host, port = _external_host(
                outbound_value
            )

            external_id = (
                "external:endpoint:"
                f"{_hash(host, 32)}"
            )

            external_entity = (
                _make_entity(
                    entity_id=external_id,
                    entity_type="endpoint",
                    kind="ExternalEndpoint",
                    name=host,
                    source_system=(
                        "kubernetes-annotation"
                    ),
                    external_id=host,
                    observed_at=observed_at,
                    labels={},
                    properties={
                        "hostname": host,
                        "port": port,
                        "external": True,
                        "resolution_status":
                            "not_checked",
                    },
                )
            )

            entities[
                external_entity.id
            ] = external_entity

            _add_relationship(
                relationships,
                source_id=pod_entity.id,
                target_id=(
                    external_entity.id
                ),
                relationship_type="calls",
                observed_at=observed_at,
                properties={
                    "declared_by":
                        NETWORK_ANNOTATION_OUTBOUND,
                    "port": port,
                },
            )

        dependencies = (
            _parse_dependency_values(
                annotations.get(
                    NETWORK_ANNOTATION_DEPENDS_ON
                )
            )
        )

        for dependency in dependencies:
            if "/" in dependency:
                (
                    dependency_namespace,
                    dependency_name,
                ) = dependency.split(
                    "/",
                    1,
                )
            else:
                dependency_namespace = (
                    namespace
                )
                dependency_name = (
                    dependency
                )

            target_service = (
                service_entities.get(
                    (
                        dependency_namespace,
                        dependency_name,
                    )
                )
            )

            if target_service:
                _add_relationship(
                    relationships,
                    source_id=pod_entity.id,
                    target_id=(
                        target_service.id
                    ),
                    relationship_type=(
                        "depends_on"
                    ),
                    observed_at=(
                        observed_at
                    ),
                    properties={
                        "declared_by":
                            NETWORK_ANNOTATION_DEPENDS_ON,
                    },
                )

    metadata = dict(
        snapshot.metadata or {}
    )

    metadata[
        "network_discovery"
    ] = {
        "service_count": len(
            services
        ),
        "ingress_count": len(
            ingresses
        ),
        "endpoint_slice_count": len(
            endpoint_slices
        ),
        "errors": errors,
    }

    return snapshot.model_copy(
        update={
            "entities": list(
                entities.values()
            ),
            "relationships": list(
                relationships.values()
            ),
            "metadata": metadata,
        }
    )
