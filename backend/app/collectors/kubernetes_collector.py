from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

from kubernetes import client, config
from kubernetes.config.config_exception import ConfigException

from app.models.topology import (
    Entity,
    EntityType,
    Evidence,
    EvidenceType,
    GraphSnapshot,
    Relationship,
    RelationshipType,
)


@dataclass(frozen=True)
class KubernetesConnection:
    cluster_name: str
    context_name: str
    authentication_mode: str


class KubernetesCollector:
    """
    Read Kubernetes objects and convert them into the canonical graph model.

    This collector performs only read operations.
    """

    def __init__(
        self,
        namespace: str | None = None,
        environment: str | None = None,
    ) -> None:
        self.namespace = namespace
        self.environment = (
            environment
            or os.getenv("TOPO_ENVIRONMENT")
            or "unknown"
        )

        self.connection = self._load_kubernetes_configuration()

        self.core_api = client.CoreV1Api()
        self.apps_api = client.AppsV1Api()
        self.version_api = client.VersionApi()

    def _load_kubernetes_configuration(
        self,
    ) -> KubernetesConnection:
        """
        Load local kubeconfig first.

        If no local kubeconfig exists, attempt in-cluster authentication.
        """
        kubeconfig_error: Exception | None = None

        try:
            contexts, current_context = (
                config.list_kube_config_contexts()
            )

            if current_context is None:
                raise ConfigException(
                    "No active Kubernetes context was found."
                )

            context_name = current_context["name"]
            cluster_name = current_context["context"]["cluster"]

            config.load_kube_config(
                context=context_name,
            )

            return KubernetesConnection(
                cluster_name=cluster_name,
                context_name=context_name,
                authentication_mode="kubeconfig",
            )

        except (
            ConfigException,
            FileNotFoundError,
            KeyError,
        ) as exc:
            kubeconfig_error = exc

        try:
            config.load_incluster_config()

            cluster_name = os.getenv(
                "TOPO_CLUSTER_NAME",
                os.getenv(
                    "KUBERNETES_SERVICE_HOST",
                    "in-cluster",
                ),
            )

            return KubernetesConnection(
                cluster_name=cluster_name,
                context_name="in-cluster",
                authentication_mode="service-account",
            )

        except ConfigException as in_cluster_error:
            raise RuntimeError(
                "Could not load Kubernetes access configuration. "
                "Verify that kubectl works or that the application "
                "is running with a Kubernetes service account."
            ) from (
                kubeconfig_error
                or in_cluster_error
            )

    @staticmethod
    def _safe_identifier(value: str) -> str:
        """
        Convert context names and cluster names into ID-safe values.
        """
        return re.sub(
            pattern=r"[^a-zA-Z0-9._-]+",
            repl="_",
            string=value,
        )

    def _cluster_id(self) -> str:
        cluster_name = self._safe_identifier(
            self.connection.cluster_name
        )

        return f"k8s:{cluster_name}:cluster"

    def _entity_id(
        self,
        kind: str,
        metadata: Any,
    ) -> str:
        """
        Prefer Kubernetes UID because it remains stable for the lifetime
        of the Kubernetes object.
        """
        cluster_name = self._safe_identifier(
            self.connection.cluster_name
        )

        fallback_identity = (
            f"{metadata.namespace or '_cluster'}:"
            f"{metadata.name}"
        )

        object_identity = str(
            metadata.uid
            or fallback_identity
        )

        return (
            f"k8s:{cluster_name}:"
            f"{kind.lower()}:{object_identity}"
        )

    @staticmethod
    def _relationship_id(
        source_entity_id: str,
        relationship_type: RelationshipType,
        target_entity_id: str,
    ) -> str:
        relationship_value = (
            f"{source_entity_id}|"
            f"{relationship_type.value}|"
            f"{target_entity_id}"
        )

        digest = sha256(
            relationship_value.encode("utf-8")
        ).hexdigest()[:20]

        return f"rel:{digest}"

    @staticmethod
    def _labels(metadata: Any) -> dict[str, str]:
        return {
            str(key): str(value)
            for key, value in (
                metadata.labels
                or {}
            ).items()
        }

    @staticmethod
    def _metadata_properties(
        metadata: Any,
    ) -> dict[str, Any]:
        creation_timestamp = None

        if metadata.creation_timestamp:
            creation_timestamp = (
                metadata.creation_timestamp.isoformat()
            )

        return {
            "namespace": metadata.namespace,
            "resource_version": metadata.resource_version,
            "creation_timestamp": creation_timestamp,
        }

    def connection_information(self) -> dict[str, Any]:
        version = self.version_api.get_code()

        return {
            "connected": True,
            "cluster_name": self.connection.cluster_name,
            "context_name": self.connection.context_name,
            "authentication_mode": (
                self.connection.authentication_mode
            ),
            "kubernetes_version": version.git_version,
            "namespace_filter": self.namespace,
        }

    def _list_namespaces(self) -> list[Any]:
        if self.namespace:
            namespace = self.core_api.read_namespace(
                name=self.namespace
            )

            return [namespace]

        return self.core_api.list_namespace().items

    def _list_deployments(self) -> list[Any]:
        if self.namespace:
            return self.apps_api.list_namespaced_deployment(
                namespace=self.namespace
            ).items

        return (
            self.apps_api
            .list_deployment_for_all_namespaces()
            .items
        )

    def _list_replica_sets(self) -> list[Any]:
        if self.namespace:
            return self.apps_api.list_namespaced_replica_set(
                namespace=self.namespace
            ).items

        return (
            self.apps_api
            .list_replica_set_for_all_namespaces()
            .items
        )

    def _list_pods(self) -> list[Any]:
        if self.namespace:
            return self.core_api.list_namespaced_pod(
                namespace=self.namespace
            ).items

        return (
            self.core_api
            .list_pod_for_all_namespaces()
            .items
        )

    def _list_services(self) -> list[Any]:
        if self.namespace:
            return self.core_api.list_namespaced_service(
                namespace=self.namespace
            ).items

        return (
            self.core_api
            .list_service_for_all_namespaces()
            .items
        )

    @staticmethod
    def _selector_matches(
        selector: dict[str, str],
        labels: dict[str, str],
    ) -> bool:
        if not selector:
            return False

        return all(
            labels.get(key) == value
            for key, value in selector.items()
        )

    def collect(self) -> GraphSnapshot:
        collected_at = datetime.now(timezone.utc)

        evidence_id = (
            f"evidence:kubernetes-discovery:{uuid4()}"
        )

        entities: list[Entity] = []
        relationships: list[Relationship] = []

        namespace_ids: dict[str, str] = {}
        deployment_ids_by_uid: dict[str, str] = {}
        replica_set_ids_by_uid: dict[str, str] = {}
        pod_entities_by_namespace: dict[
            str,
            list[tuple[Any, Entity]],
        ] = {}

        cluster_id = self._cluster_id()

        cluster_entity = Entity(
            id=cluster_id,
            entity_type=EntityType.ENVIRONMENT,
            kind="KubernetesCluster",
            name=self.connection.cluster_name,
            source_system="kubernetes",
            external_id=self.connection.context_name,
            environment=self.environment,
            observed_at=collected_at,
            confidence=1.0,
            labels={},
            properties={
                "context": self.connection.context_name,
                "authentication_mode": (
                    self.connection.authentication_mode
                ),
            },
        )

        entities.append(cluster_entity)

        namespaces = self._list_namespaces()
        deployments = self._list_deployments()
        replica_sets = self._list_replica_sets()
        pods = self._list_pods()
        services = self._list_services()

        def add_relationship(
            source_entity_id: str,
            target_entity_id: str,
            relationship_type: RelationshipType,
            confidence: float = 1.0,
            properties: dict[str, Any] | None = None,
        ) -> None:
            relationship = Relationship(
                id=self._relationship_id(
                    source_entity_id=source_entity_id,
                    relationship_type=relationship_type,
                    target_entity_id=target_entity_id,
                ),
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                relationship_type=relationship_type,
                source_system="kubernetes",
                observed_at=collected_at,
                confidence=confidence,
                directed=True,
                evidence_ids=[evidence_id],
                properties=properties or {},
            )

            relationships.append(relationship)

        for namespace in namespaces:
            namespace_id = self._entity_id(
                kind="namespace",
                metadata=namespace.metadata,
            )

            namespace_ids[
                namespace.metadata.name
            ] = namespace_id

            namespace_entity = Entity(
                id=namespace_id,
                entity_type=EntityType.ENVIRONMENT,
                kind="KubernetesNamespace",
                name=namespace.metadata.name,
                source_system="kubernetes",
                external_id=str(namespace.metadata.uid),
                environment=self.environment,
                observed_at=collected_at,
                confidence=1.0,
                labels=self._labels(namespace.metadata),
                properties={
                    **self._metadata_properties(
                        namespace.metadata
                    ),
                    "cluster": (
                        self.connection.cluster_name
                    ),
                    "phase": (
                        namespace.status.phase
                        if namespace.status
                        else None
                    ),
                },
            )

            entities.append(namespace_entity)

            add_relationship(
                source_entity_id=cluster_id,
                target_entity_id=namespace_id,
                relationship_type=(
                    RelationshipType.CONTAINS
                ),
            )

        for deployment in deployments:
            deployment_id = self._entity_id(
                kind="deployment",
                metadata=deployment.metadata,
            )

            deployment_ids_by_uid[
                str(deployment.metadata.uid)
            ] = deployment_id

            containers = [
                {
                    "name": container.name,
                    "image": container.image,
                }
                for container in (
                    deployment.spec.template.spec.containers
                    or []
                )
            ]

            match_labels = {}

            if (
                deployment.spec.selector
                and deployment.spec.selector.match_labels
            ):
                match_labels = dict(
                    deployment.spec.selector.match_labels
                )

            deployment_entity = Entity(
                id=deployment_id,
                entity_type=EntityType.WORKLOAD,
                kind="KubernetesDeployment",
                name=deployment.metadata.name,
                source_system="kubernetes",
                external_id=str(deployment.metadata.uid),
                environment=self.environment,
                observed_at=collected_at,
                confidence=1.0,
                labels=self._labels(
                    deployment.metadata
                ),
                properties={
                    **self._metadata_properties(
                        deployment.metadata
                    ),
                    "cluster": (
                        self.connection.cluster_name
                    ),
                    "desired_replicas": (
                        deployment.spec.replicas
                    ),
                    "ready_replicas": (
                        deployment.status.ready_replicas
                    ),
                    "available_replicas": (
                        deployment.status.available_replicas
                    ),
                    "updated_replicas": (
                        deployment.status.updated_replicas
                    ),
                    "selector": match_labels,
                    "containers": containers,
                },
            )

            entities.append(deployment_entity)

            namespace_id = namespace_ids.get(
                deployment.metadata.namespace
            )

            if namespace_id:
                add_relationship(
                    source_entity_id=namespace_id,
                    target_entity_id=deployment_id,
                    relationship_type=(
                        RelationshipType.CONTAINS
                    ),
                )

        for replica_set in replica_sets:
            replica_set_id = self._entity_id(
                kind="replicaset",
                metadata=replica_set.metadata,
            )

            replica_set_ids_by_uid[
                str(replica_set.metadata.uid)
            ] = replica_set_id

            replica_set_entity = Entity(
                id=replica_set_id,
                entity_type=EntityType.WORKLOAD,
                kind="KubernetesReplicaSet",
                name=replica_set.metadata.name,
                source_system="kubernetes",
                external_id=str(
                    replica_set.metadata.uid
                ),
                environment=self.environment,
                observed_at=collected_at,
                confidence=1.0,
                labels=self._labels(
                    replica_set.metadata
                ),
                properties={
                    **self._metadata_properties(
                        replica_set.metadata
                    ),
                    "cluster": (
                        self.connection.cluster_name
                    ),
                    "desired_replicas": (
                        replica_set.spec.replicas
                    ),
                    "ready_replicas": (
                        replica_set.status.ready_replicas
                    ),
                },
            )

            entities.append(replica_set_entity)

            namespace_id = namespace_ids.get(
                replica_set.metadata.namespace
            )

            if namespace_id:
                add_relationship(
                    source_entity_id=namespace_id,
                    target_entity_id=replica_set_id,
                    relationship_type=(
                        RelationshipType.CONTAINS
                    ),
                )

            for owner in (
                replica_set.metadata.owner_references
                or []
            ):
                if owner.kind != "Deployment":
                    continue

                deployment_id = (
                    deployment_ids_by_uid.get(
                        str(owner.uid)
                    )
                )

                if deployment_id:
                    add_relationship(
                        source_entity_id=deployment_id,
                        target_entity_id=replica_set_id,
                        relationship_type=(
                            RelationshipType.OWNS
                        ),
                    )

        for pod in pods:
            pod_id = self._entity_id(
                kind="pod",
                metadata=pod.metadata,
            )

            container_statuses = []

            for status in (
                pod.status.container_statuses
                or []
            ):
                container_statuses.append(
                    {
                        "name": status.name,
                        "image": status.image,
                        "ready": status.ready,
                        "restart_count": (
                            status.restart_count
                        ),
                    }
                )

            pod_entity = Entity(
                id=pod_id,
                entity_type=(
                    EntityType.RUNTIME_INSTANCE
                ),
                kind="KubernetesPod",
                name=pod.metadata.name,
                source_system="kubernetes",
                external_id=str(pod.metadata.uid),
                environment=self.environment,
                observed_at=collected_at,
                confidence=1.0,
                labels=self._labels(pod.metadata),
                properties={
                    **self._metadata_properties(
                        pod.metadata
                    ),
                    "cluster": (
                        self.connection.cluster_name
                    ),
                    "phase": pod.status.phase,
                    "pod_ip": pod.status.pod_ip,
                    "node_name": pod.spec.node_name,
                    "containers": container_statuses,
                    "total_restarts": sum(
                        item["restart_count"]
                        for item in container_statuses
                    ),
                },
            )

            entities.append(pod_entity)

            namespace_name = pod.metadata.namespace

            pod_entities_by_namespace.setdefault(
                namespace_name,
                [],
            ).append(
                (pod, pod_entity)
            )

            namespace_id = namespace_ids.get(
                namespace_name
            )

            if namespace_id:
                add_relationship(
                    source_entity_id=namespace_id,
                    target_entity_id=pod_id,
                    relationship_type=(
                        RelationshipType.CONTAINS
                    ),
                )

            for owner in (
                pod.metadata.owner_references
                or []
            ):
                if owner.kind != "ReplicaSet":
                    continue

                replica_set_id = (
                    replica_set_ids_by_uid.get(
                        str(owner.uid)
                    )
                )

                if replica_set_id:
                    add_relationship(
                        source_entity_id=replica_set_id,
                        target_entity_id=pod_id,
                        relationship_type=(
                            RelationshipType.RUNS
                        ),
                    )

        for service in services:
            service_id = self._entity_id(
                kind="service",
                metadata=service.metadata,
            )

            ports = [
                {
                    "name": port.name,
                    "port": port.port,
                    "protocol": port.protocol,
                    "target_port": (
                        str(port.target_port)
                        if port.target_port is not None
                        else None
                    ),
                }
                for port in (
                    service.spec.ports
                    or []
                )
            ]

            selector = {
                str(key): str(value)
                for key, value in (
                    service.spec.selector
                    or {}
                ).items()
            }

            service_entity = Entity(
                id=service_id,
                entity_type=EntityType.ENDPOINT,
                kind="KubernetesService",
                name=service.metadata.name,
                source_system="kubernetes",
                external_id=str(service.metadata.uid),
                environment=self.environment,
                observed_at=collected_at,
                confidence=1.0,
                labels=self._labels(service.metadata),
                properties={
                    **self._metadata_properties(
                        service.metadata
                    ),
                    "cluster": (
                        self.connection.cluster_name
                    ),
                    "service_type": (
                        service.spec.type
                    ),
                    "cluster_ip": (
                        service.spec.cluster_ip
                    ),
                    "selector": selector,
                    "ports": ports,
                },
            )

            entities.append(service_entity)

            namespace_name = service.metadata.namespace
            namespace_id = namespace_ids.get(
                namespace_name
            )

            if namespace_id:
                add_relationship(
                    source_entity_id=namespace_id,
                    target_entity_id=service_id,
                    relationship_type=(
                        RelationshipType.CONTAINS
                    ),
                )

            for pod, pod_entity in (
                pod_entities_by_namespace.get(
                    namespace_name,
                    [],
                )
            ):
                pod_labels = self._labels(
                    pod.metadata
                )

                if self._selector_matches(
                    selector=selector,
                    labels=pod_labels,
                ):
                    add_relationship(
                        source_entity_id=service_id,
                        target_entity_id=pod_entity.id,
                        relationship_type=(
                            RelationshipType.SELECTS
                        ),
                        properties={
                            "selector": selector,
                        },
                    )

        evidence = Evidence(
            id=evidence_id,
            evidence_type=EvidenceType.DISCOVERY,
            source_system="kubernetes",
            summary=(
                "Kubernetes resources and ownership "
                "relationships were collected from the "
                "Kubernetes API."
            ),
            observed_at=collected_at,
            related_entity_ids=[
                entity.id
                for entity in entities
            ],
            related_relationship_ids=[
                relationship.id
                for relationship in relationships
            ],
            payload={
                "cluster": (
                    self.connection.cluster_name
                ),
                "context": (
                    self.connection.context_name
                ),
                "namespace_filter": self.namespace,
                "counts": {
                    "namespaces": len(namespaces),
                    "deployments": len(deployments),
                    "replica_sets": len(replica_sets),
                    "pods": len(pods),
                    "services": len(services),
                },
            },
        )

        snapshot_id = (
            f"snapshot:kubernetes:"
            f"{self._safe_identifier(self.connection.cluster_name)}:"
            f"{collected_at.strftime('%Y%m%dT%H%M%SZ')}:"
            f"{str(uuid4())[:8]}"
        )

        return GraphSnapshot(
            schema_version="1.0",
            snapshot_id=snapshot_id,
            collected_at=collected_at,
            collector_name="kubernetes-collector",
            collector_version="0.1.0",
            scope={
                "platform": "kubernetes",
                "cluster": (
                    self.connection.cluster_name
                ),
                "context": (
                    self.connection.context_name
                ),
                "namespace": (
                    self.namespace
                    or "*"
                ),
                "environment": self.environment,
            },
            entities=entities,
            relationships=relationships,
            evidence=[evidence],
            metadata={
                "authentication_mode": (
                    self.connection.authentication_mode
                ),
                "counts": {
                    "entities": len(entities),
                    "relationships": len(
                        relationships
                    ),
                },
            },
        )