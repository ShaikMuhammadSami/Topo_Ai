from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)
from typing import Any
from uuid import uuid4

from kubernetes import (
    client,
    config as kube_config,
)
from kubernetes.client.exceptions import (
    ApiException,
)

from topo_agent import __version__
from topo_agent.config import (
    AgentConfig,
)


def _utc_now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _labels(
    metadata: Any,
) -> dict[str, str]:
    values = getattr(
        metadata,
        "labels",
        None,
    ) or {}

    return {
        str(key): str(value)
        for key, value
        in values.items()
    }


def _owner(
    metadata: Any,
) -> tuple[
    str | None,
    str | None,
]:
    references = getattr(
        metadata,
        "owner_references",
        None,
    ) or []

    controller = next(
        (
            item
            for item in references
            if getattr(
                item,
                "controller",
                False,
            )
        ),
        references[0]
        if references
        else None,
    )

    if controller is None:
        return None, None

    return (
        getattr(
            controller,
            "uid",
            None,
        ),
        getattr(
            controller,
            "kind",
            None,
        ),
    )


def _pod_ready(
    pod: Any,
) -> bool:
    conditions = getattr(
        pod.status,
        "conditions",
        None,
    ) or []

    return any(
        condition.type == "Ready"
        and condition.status == "True"
        for condition in conditions
    )


class KubernetesCollector:
    def __init__(
        self,
        config: AgentConfig,
    ) -> None:
        self.config = config

        try:
            kube_config.load_incluster_config()

            self.access_mode = (
                "in-cluster"
            )

        except Exception:
            kube_config.load_kube_config(
                context=(
                    config.kube_context
                )
            )

            self.access_mode = (
                "kubeconfig"
            )

        self.core = (
            client.CoreV1Api()
        )

        self.apps = (
            client.AppsV1Api()
        )

        self.networking = (
            client
            .NetworkingV1Api()
        )

        self.discovery = (
            client
            .DiscoveryV1Api()
        )

    def _list_for_namespaces(
        self,
        all_namespaces_call,
        namespaced_call,
    ) -> list[Any]:
        if not self.config.namespaces:
            return list(
                all_namespaces_call().items
            )

        results: list[Any] = []

        for namespace in (
            self.config.namespaces
        ):
            results.extend(
                namespaced_call(
                    namespace
                ).items
            )

        return results

    def doctor(
        self,
    ) -> dict[str, Any]:
        namespaces = (
            self.core.list_namespace(
                limit=1
            )
        )

        return {
            "kubernetes_access":
                "available",
            "access_mode":
                self.access_mode,
            "cluster_name":
                self.config.cluster_name,
            "namespace_scope":
                self.config.namespaces,
            "probe_count":
                len(namespaces.items),
        }

    def collect(
        self,
    ) -> dict[str, Any]:
        errors: list[str] = []

        inventory: dict[
            str,
            list[dict[str, Any]],
        ] = {
            "namespaces": [],
            "nodes": [],
            "deployments": [],
            "replicasets": [],
            "pods": [],
            "services": [],
            "ingresses": [],
            "endpoint_slices": [],
        }

        try:
            namespaces = (
                self.core
                .list_namespace()
                .items
            )

            for namespace in namespaces:
                if (
                    self.config.namespaces
                    and namespace
                    .metadata
                    .name
                    not in self
                    .config.namespaces
                ):
                    continue

                inventory[
                    "namespaces"
                ].append(
                    {
                        "uid":
                            namespace
                            .metadata.uid,
                        "name":
                            namespace
                            .metadata.name,
                        "labels":
                            _labels(
                                namespace
                                .metadata
                            ),
                        "phase":
                            getattr(
                                namespace
                                .status,
                                "phase",
                                None,
                            ),
                    }
                )

        except ApiException as exc:
            errors.append(
                "namespaces: "
                f"{exc.status} {exc.reason}"
            )

        try:
            nodes = (
                self.core
                .list_node()
                .items
            )

            for node in nodes:
                conditions = [
                    {
                        "type":
                            item.type,
                        "status":
                            item.status,
                    }
                    for item in (
                        node
                        .status
                        .conditions
                        or []
                    )
                ]

                inventory[
                    "nodes"
                ].append(
                    {
                        "uid":
                            node
                            .metadata.uid,
                        "name":
                            node
                            .metadata.name,
                        "labels":
                            _labels(
                                node.metadata
                            ),
                        "addresses": [
                            {
                                "type":
                                    item.type,
                                "address":
                                    item.address,
                            }
                            for item in (
                                node
                                .status
                                .addresses
                                or []
                            )
                        ],
                        "conditions":
                            conditions,
                    }
                )

        except ApiException as exc:
            errors.append(
                "nodes: "
                f"{exc.status} {exc.reason}"
            )

        deployments = (
            self._list_for_namespaces(
                self.apps
                .list_deployment_for_all_namespaces,
                self.apps
                .list_namespaced_deployment,
            )
        )

        for deployment in deployments:
            containers = (
                deployment
                .spec
                .template
                .spec
                .containers
                or []
            )

            inventory[
                "deployments"
            ].append(
                {
                    "uid":
                        deployment
                        .metadata.uid,
                    "name":
                        deployment
                        .metadata.name,
                    "namespace":
                        deployment
                        .metadata.namespace,
                    "labels":
                        _labels(
                            deployment
                            .metadata
                        ),
                    "selector":
                        (
                            deployment
                            .spec
                            .selector
                            .match_labels
                            or {}
                        ),
                    "replicas":
                        deployment
                        .spec.replicas,
                    "available_replicas":
                        deployment
                        .status
                        .available_replicas,
                    "images": [
                        item.image
                        for item in containers
                    ],
                }
            )

        replicasets = (
            self._list_for_namespaces(
                self.apps
                .list_replica_set_for_all_namespaces,
                self.apps
                .list_namespaced_replica_set,
            )
        )

        for replica_set in replicasets:
            owner_uid, owner_kind = (
                _owner(
                    replica_set.metadata
                )
            )

            inventory[
                "replicasets"
            ].append(
                {
                    "uid":
                        replica_set
                        .metadata.uid,
                    "name":
                        replica_set
                        .metadata.name,
                    "namespace":
                        replica_set
                        .metadata.namespace,
                    "labels":
                        _labels(
                            replica_set
                            .metadata
                        ),
                    "owner_uid":
                        owner_uid,
                    "owner_kind":
                        owner_kind,
                    "selector":
                        (
                            replica_set
                            .spec
                            .selector
                            .match_labels
                            or {}
                        ),
                    "replicas":
                        replica_set
                        .status.replicas,
                    "ready_replicas":
                        replica_set
                        .status
                        .ready_replicas,
                }
            )

        pods = self._list_for_namespaces(
            self.core
            .list_pod_for_all_namespaces,
            self.core
            .list_namespaced_pod,
        )

        for pod in pods:
            owner_uid, owner_kind = (
                _owner(pod.metadata)
            )

            statuses = (
                pod
                .status
                .container_statuses
                or []
            )
            container_ids = []

            for item in statuses:
               container_id = getattr(
                  item,
                  "container_id",
                  None,
                )

            if not container_id:
               continue

            normalized = str(
              container_id
            )

            if "://" in normalized:
              normalized = normalized.split(
                 "://",
                 1,
                )[1]

            container_ids.append(
              normalized
            )


            inventory["pods"].append(
                {
                    "uid":
                        pod.metadata.uid,
                    "name":
                        pod.metadata.name,
                    "namespace":
                        pod
                        .metadata
                        .namespace,
                    "labels":
                        _labels(
                            pod.metadata
                        ),
                    "owner_uid":
                        owner_uid,
                    "owner_kind":
                        owner_kind,
                    "node_name":
                        pod
                        .spec
                        .node_name,
                    "phase":
                        pod.status.phase,
                    "ready":
                        _pod_ready(pod),
                    "restart_count":
                        sum(
                            item
                            .restart_count
                            for item
                            in statuses
                        ),
                    "images": [
                        item.image
                        for item in (
                            pod
                            .spec
                            .containers
                            or []
                        )
                    ],
                    "container_ids":
                        container_ids,
                    "pod_ip":
                        pod.status.pod_ip,
                }
            )

        services = (
            self._list_for_namespaces(
                self.core
                .list_service_for_all_namespaces,
                self.core
                .list_namespaced_service,
            )
        )

        for service in services:
            inventory[
                "services"
            ].append(
                {
                    "uid":
                        service
                        .metadata.uid,
                    "name":
                        service
                        .metadata.name,
                    "namespace":
                        service
                        .metadata.namespace,
                    "labels":
                        _labels(
                            service
                            .metadata
                        ),
                    "selector":
                        service
                        .spec.selector
                        or {},
                    "type":
                        service
                        .spec.type,
                    "cluster_ip":
                        service
                        .spec.cluster_ip,
                    "ports": [
                        {
                            "name":
                                port.name,
                            "port":
                                port.port,
                            "protocol":
                                port.protocol,
                            "target_port":
                                str(
                                    port
                                    .target_port
                                ),
                        }
                        for port in (
                            service
                            .spec.ports
                            or []
                        )
                    ],
                }
            )

        ingresses = (
            self._list_for_namespaces(
                self.networking
                .list_ingress_for_all_namespaces,
                self.networking
                .list_namespaced_ingress,
            )
        )

        for ingress in ingresses:
            backends: list[
                dict[str, Any]
            ] = []

            for rule in (
                ingress.spec.rules
                or []
            ):
                if (
                    rule.http is None
                ):
                    continue

                for path in (
                    rule.http.paths
                    or []
                ):
                    service_backend = (
                        path.backend.service
                    )

                    if (
                        service_backend
                        is None
                    ):
                        continue

                    backends.append(
                        {
                            "host":
                                rule.host,
                            "path":
                                path.path,
                            "service_name":
                                service_backend
                                .name,
                            "port":
                                (
                                    service_backend
                                    .port.name
                                    or service_backend
                                    .port.number
                                ),
                        }
                    )

            inventory[
                "ingresses"
            ].append(
                {
                    "uid":
                        ingress
                        .metadata.uid,
                    "name":
                        ingress
                        .metadata.name,
                    "namespace":
                        ingress
                        .metadata.namespace,
                    "labels":
                        _labels(
                            ingress
                            .metadata
                        ),
                    "backends":
                        backends,
                }
            )

        endpoint_slices = (
            self._list_for_namespaces(
                self.discovery
                .list_endpoint_slice_for_all_namespaces,
                self.discovery
                .list_namespaced_endpoint_slice,
            )
        )

        for endpoint_slice in endpoint_slices:
            service_name = (
                (
                    endpoint_slice
                    .metadata
                    .labels
                    or {}
                ).get(
                    "kubernetes.io/"
                    "service-name"
                )
            )

            endpoints = []

            for endpoint in (
                endpoint_slice
                .endpoints
                or []
            ):
                target_ref = (
                    endpoint.target_ref
                )

                endpoints.append(
                    {
                        "target_uid":
                            (
                                target_ref.uid
                                if target_ref
                                else None
                            ),
                        "target_name":
                            (
                                target_ref.name
                                if target_ref
                                else None
                            ),
                        "addresses":
                            endpoint.addresses
                            or [],
                        "ready":
                            (
                                endpoint
                                .conditions
                                .ready
                                if endpoint
                                .conditions
                                else None
                            ),
                    }
                )

            inventory[
                "endpoint_slices"
            ].append(
                {
                    "uid":
                        endpoint_slice
                        .metadata.uid,
                    "name":
                        endpoint_slice
                        .metadata.name,
                    "namespace":
                        endpoint_slice
                        .metadata.namespace,
                    "labels":
                        _labels(
                            endpoint_slice
                            .metadata
                        ),
                    "service_name":
                        service_name,
                    "endpoints":
                        endpoints,
                }
            )

        return {
            "submission_id": (
                "agent-submission:"
                + uuid4().hex
            ),
            "collected_at":
                _utc_now_iso(),
            "cluster_name":
                self.config
                .cluster_name,
            "environment":
                self.config
                .environment,
            "namespace_scope":
                self.config
                .namespaces,
            "collector_version":
                __version__,
            "inventory":
                inventory,
            "metadata": {
                "access_mode":
                    self.access_mode,
                "collection_errors":
                    errors,
            },
        }