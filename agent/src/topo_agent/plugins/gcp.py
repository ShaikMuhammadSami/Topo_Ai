from __future__ import annotations

import logging
from typing import Any

import google.auth
from google.api_core.exceptions import (
    Forbidden,
    GoogleAPICallError,
    NotFound,
    PermissionDenied,
    RetryError,
    ServiceUnavailable,
    TooManyRequests,
)
from google.api_core.retry import (
    Retry,
    if_transient_error,
)
from google.auth import (
    impersonated_credentials,
)
from google.cloud import (
    asset_v1,
    compute_v1,
    container_v1,
    resourcemanager_v3,
)
from google.protobuf.json_format import (
    MessageToDict,
)

from topo_agent import __version__
from topo_agent.config import (
    AgentConfig,
    agent_home,
)
from topo_agent.gcp_cache import (
    GcpInventoryCache,
)
from topo_agent.plugin import (
    PluginCollectionResult,
    PluginDiagnostic,
)


LOGGER = logging.getLogger(
    "topo-agent.gcp"
)


INVENTORY_KEYS = (
    "gcp_organizations",
    "gcp_folders",
    "gcp_projects",
    "gcp_networks",
    "gcp_subnetworks",
    "gcp_firewall_rules",
    "gcp_routes",
    "gcp_addresses",
    "gcp_compute_instances",
    "gcp_instance_group_managers",
    "gcp_gke_clusters",
    "gcp_gke_node_pools",
    "gcp_forwarding_rules",
    "gcp_backend_services",
    "gcp_health_checks",
    "gcp_cloud_sql_instances",
    "gcp_cloud_run_services",
    "gcp_cloud_functions",
    "gcp_pubsub_topics",
    "gcp_pubsub_subscriptions",
)


ASSET_TYPE_GROUPS = {
    "load-balancing": [
        (
            "compute.googleapis.com/"
            "BackendService"
        ),
        (
            "compute.googleapis.com/"
            "HealthCheck"
        ),
    ],

    "sql": [
        (
            "sqladmin.googleapis.com/"
            "Instance"
        ),
    ],

    "run": [
        "run.googleapis.com/Service",
    ],

    "functions": [
        (
            "cloudfunctions.googleapis.com/"
            "CloudFunction"
        ),
        (
            "cloudfunctions.googleapis.com/"
            "Function"
        ),
    ],

    "pubsub": [
        "pubsub.googleapis.com/Topic",
        (
            "pubsub.googleapis.com/"
            "Subscription"
        ),
    ],
}


ASSET_RESOURCE_TYPES = {
    (
        "compute.googleapis.com/"
        "BackendService"
    ): "gcp_backend_service",

    (
        "compute.googleapis.com/"
        "HealthCheck"
    ): "gcp_health_check",

    (
        "sqladmin.googleapis.com/"
        "Instance"
    ): "gcp_cloud_sql_instance",

    "run.googleapis.com/Service":
        "gcp_cloud_run_service",

    (
        "cloudfunctions.googleapis.com/"
        "CloudFunction"
    ): "gcp_cloud_function",

    (
        "cloudfunctions.googleapis.com/"
        "Function"
    ): "gcp_cloud_function",

    "pubsub.googleapis.com/Topic":
        "gcp_pubsub_topic",

    (
        "pubsub.googleapis.com/"
        "Subscription"
    ): "gcp_pubsub_subscription",
}


ASSET_INVENTORY_KEYS = {
    "gcp_backend_service":
        "gcp_backend_services",

    "gcp_health_check":
        "gcp_health_checks",

    "gcp_cloud_sql_instance":
        "gcp_cloud_sql_instances",

    "gcp_cloud_run_service":
        "gcp_cloud_run_services",

    "gcp_cloud_function":
        "gcp_cloud_functions",

    "gcp_pubsub_topic":
        "gcp_pubsub_topics",

    "gcp_pubsub_subscription":
        "gcp_pubsub_subscriptions",
}


def _empty_inventory(
) -> dict[str, list[dict]]:
    return {
        key: []
        for key in INVENTORY_KEYS
    }


def _message_dict(
    value: Any,
) -> dict[str, Any]:
    converter = getattr(
        type(value),
        "to_dict",
        None,
    )

    if callable(converter):
        result = converter(value)

        if isinstance(result, dict):
            return result

    protobuf = getattr(
        value,
        "_pb",
        None,
    )

    if protobuf is not None:
        result = MessageToDict(
            protobuf,
            preserving_proto_field_name=True,
        )

        if isinstance(result, dict):
            return result

    return {}


def _last_segment(
    value: str | None,
) -> str:
    if not value:
        return ""

    return (
        str(value)
        .rstrip("/")
        .split("/")[-1]
    )


def _normalise_reference(
    value: Any,
) -> str:
    return (
        str(value or "")
        .strip()
        .rstrip("/")
        .lower()
    )


def _location(
    value: str | None,
) -> str:
    if not value:
        return "global"

    result = _last_segment(value)

    return result.lower() or "global"


def _labels(
    value: Any,
) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}

    return {
        str(key): str(item)
        for key, item in value.items()
    }


def _reference_values(
    value: Any,
    keys: set[str],
) -> list[str]:
    results: list[str] = []

    def walk(
        item: Any,
        parent_key: str | None = None,
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
                        nested
                    )

                walk(
                    nested,
                    lowered,
                )

        elif isinstance(item, list):
            for nested in item:
                walk(
                    nested,
                    parent_key,
                )

    walk(value)

    return sorted(set(results))


def _resource(
    *,
    project_id: str,
    location: str,
    resource_type: str,
    resource_id: str,
    name: str,
    status: str | None = None,
    labels: dict[str, str] | None = None,
    network: str | None = None,
    subnetworks:
        list[str] | None = None,
    properties:
        dict[str, Any] | None = None,
    resource_group:
        str | None = None,
) -> dict[str, Any]:
    return {
        "provider": "gcp",
        "account_id": project_id,
        "region": location,
        "resource_group":
            resource_group,
        "resource_type":
            resource_type,
        "resource_id":
            resource_id,
        "name": name,
        "arn": resource_id,
        "status": status,
        "tags": labels or {},
        "vpc_id": network,
        "subnet_ids":
            subnetworks or [],
        "properties":
            properties or {},
    }


def _merge(
    destination:
        dict[str, list[dict]],
    source:
        dict[str, list[dict]],
) -> None:
    for key, values in source.items():
        destination.setdefault(
            key,
            [],
        )

        destination[key].extend(
            values
        )


class GcpCredentialFactory:
    SCOPES = [
        (
            "https://www.googleapis.com/"
            "auth/cloud-platform"
        )
    ]

    def __init__(
        self,
        config: AgentConfig,
    ) -> None:
        self.config = config

    def build(
        self,
    ):
        credentials, detected_project = (
            google.auth.default(
                scopes=self.SCOPES,
                quota_project_id=(
                    self.config
                    .gcp_quota_project
                ),
            )
        )

        target = (
            self.config
            .gcp_impersonate_service_account
        )

        if target:
            credentials = (
                impersonated_credentials
                .Credentials(
                    source_credentials=(
                        credentials
                    ),
                    target_principal=target,
                    target_scopes=(
                        self.SCOPES
                    ),
                    lifetime=3600,
                )
            )

        return credentials, detected_project


class GcpPlugin:
    name = "gcp"
    version = __version__

    capabilities = (
        "gcp.identity",
        "gcp.organizations",
        "gcp.folders",
        "gcp.projects",
        "gcp.vpc",
        "gcp.subnetworks",
        "gcp.firewalls",
        "gcp.routes",
        "gcp.compute",
        "gcp.instance_groups",
        "gcp.gke",
        "gcp.load_balancing",
        "gcp.cloud_sql",
        "gcp.cloud_run",
        "gcp.functions",
        "gcp.pubsub",
        "gcp.labels",
    )

    def __init__(
        self,
        config: AgentConfig,
    ) -> None:
        self.config = config

        (
            self.credentials,
            self.detected_project,
        ) = GcpCredentialFactory(
            config
        ).build()

        self.retry = Retry(
            predicate=if_transient_error,
            initial=1.0,
            maximum=10.0,
            multiplier=2.0,
            deadline=max(
                config
                .gcp_api_max_attempts
                * 15,
                30,
            ),
        )

        self.projects_client = (
            resourcemanager_v3
            .ProjectsClient(
                credentials=(
                    self.credentials
                )
            )
        )

        self.folders_client = (
            resourcemanager_v3
            .FoldersClient(
                credentials=(
                    self.credentials
                )
            )
        )

        self.organizations_client = (
            resourcemanager_v3
            .OrganizationsClient(
                credentials=(
                    self.credentials
                )
            )
        )

        self.asset_client = (
            asset_v1.AssetServiceClient(
                credentials=(
                    self.credentials
                )
            )
        )

        self.networks_client = (
            compute_v1.NetworksClient(
                credentials=(
                    self.credentials
                )
            )
        )

        self.subnetworks_client = (
            compute_v1
            .SubnetworksClient(
                credentials=(
                    self.credentials
                )
            )
        )

        self.firewalls_client = (
            compute_v1.FirewallsClient(
                credentials=(
                    self.credentials
                )
            )
        )

        self.routes_client = (
            compute_v1.RoutesClient(
                credentials=(
                    self.credentials
                )
            )
        )

        self.instances_client = (
            compute_v1.InstancesClient(
                credentials=(
                    self.credentials
                )
            )
        )

        self.instance_group_managers_client = (
            compute_v1
            .InstanceGroupManagersClient(
                credentials=(
                    self.credentials
                )
            )
        )

        self.addresses_client = (
            compute_v1.AddressesClient(
                credentials=(
                    self.credentials
                )
            )
        )

        self.forwarding_rules_client = (
            compute_v1
            .ForwardingRulesClient(
                credentials=(
                    self.credentials
                )
            )
        )

        self.gke_client = (
            container_v1
            .ClusterManagerClient(
                credentials=(
                    self.credentials
                )
            )
        )

        self.cache = GcpInventoryCache(
            (
                agent_home()
                / "cache"
                / "gcp"
            ),
            ttl_seconds=(
                config
                .gcp_cache_ttl_seconds
            ),
        )

    def close(
        self,
    ) -> None:
        clients = (
            self.projects_client,
            self.folders_client,
            self.organizations_client,
            self.asset_client,
            self.networks_client,
            self.subnetworks_client,
            self.firewalls_client,
            self.routes_client,
            self.instances_client,
            (
                self
                .instance_group_managers_client
            ),
            self.addresses_client,
            self.forwarding_rules_client,
            self.gke_client,
        )

        for client in clients:
            close_method = getattr(
                client,
                "close",
                None,
            )

            if callable(close_method):
                try:
                    close_method()

                except Exception:
                    LOGGER.debug(
                        "Unable to close GCP "
                        "SDK client.",
                        exc_info=True,
                    )

    def _project_ids(
        self,
    ) -> list[str]:
        configured = [
            value.strip()
            for value in (
                self.config
                .gcp_project_ids
            )
            if value.strip()
        ]

        if configured:
            return sorted(set(configured))

        if (
            not self.config
            .gcp_discover_projects
        ):
            if self.detected_project:
                return [
                    str(
                        self.detected_project
                    )
                ]

            return []

        projects = (
            self.projects_client
            .search_projects(
                request={
                    "query":
                        "state:ACTIVE",
                },
                retry=self.retry,
            )
        )

        results: list[str] = []

        for project in projects:
            project_id = getattr(
                project,
                "project_id",
                None,
            )

            if project_id:
                results.append(
                    str(project_id)
                )

        return sorted(set(results))

    def _project_metadata(
        self,
        project_id: str,
    ) -> dict[str, Any]:
        project = (
            self.projects_client
            .get_project(
                request={
                    "name":
                        f"projects/{project_id}"
                },
                retry=self.retry,
            )
        )

        project_name = str(
            getattr(
                project,
                "name",
                "",
            )
        )

        project_number = (
            _last_segment(project_name)
        )

        state = getattr(
            project,
            "state",
            None,
        )

        state_name = getattr(
            state,
            "name",
            None,
        )

        return {
            "project_id": str(
                getattr(
                    project,
                    "project_id",
                    project_id,
                )
                or project_id
            ),
            "project_number":
                project_number,
            "display_name": str(
                getattr(
                    project,
                    "display_name",
                    project_id,
                )
                or project_id
            ),
            "parent": str(
                getattr(
                    project,
                    "parent",
                    "",
                )
                or ""
            ),
            "state": (
                str(state_name)
                if state_name
                else str(state)
            ),
            "labels": _labels(
                getattr(
                    project,
                    "labels",
                    {},
                )
            ),
        }

    def _hierarchy_inventory(
        self,
        *,
        project:
            dict[str, Any],
    ) -> dict[str, list[dict]]:
        result = _empty_inventory()

        project_id = project[
            "project_id"
        ]

        project_resource_id = (
            f"projects/"
            f"{project['project_number']}"
            if project.get(
                "project_number"
            )
            else f"projects/{project_id}"
        )

        result[
            "gcp_projects"
        ].append(
            _resource(
                project_id=project_id,
                location="global",
                resource_type=(
                    "gcp_project"
                ),
                resource_id=(
                    project_resource_id
                ),
                name=project[
                    "display_name"
                ],
                status=project[
                    "state"
                ],
                labels=project[
                    "labels"
                ],
                properties={
                    "project_id":
                        project_id,
                    "project_number":
                        project.get(
                            "project_number"
                        ),
                    "parent":
                        project.get(
                            "parent"
                        ),
                },
            )
        )

        if not self.config.gcp_include_hierarchy:
            return result

        parent = str(
            project.get("parent")
            or ""
        )

        visited: set[str] = set()

        while (
            parent
            and parent not in visited
        ):
            visited.add(parent)

            if parent.startswith(
                "folders/"
            ):
                folder = (
                    self.folders_client
                    .get_folder(
                        request={
                            "name": parent
                        },
                        retry=self.retry,
                    )
                )

                folder_name = str(
                    getattr(
                        folder,
                        "name",
                        parent,
                    )
                )

                folder_parent = str(
                    getattr(
                        folder,
                        "parent",
                        "",
                    )
                    or ""
                )

                result[
                    "gcp_folders"
                ].append(
                    _resource(
                        project_id=project_id,
                        location="global",
                        resource_type=(
                            "gcp_folder"
                        ),
                        resource_id=(
                            folder_name
                        ),
                        name=str(
                            getattr(
                                folder,
                                "display_name",
                                folder_name,
                            )
                        ),
                        status=str(
                            getattr(
                                getattr(
                                    folder,
                                    "state",
                                    None,
                                ),
                                "name",
                                getattr(
                                    folder,
                                    "state",
                                    "",
                                ),
                            )
                        ),
                        properties={
                            "parent":
                                folder_parent,
                        },
                    )
                )

                parent = folder_parent
                continue

            if parent.startswith(
                "organizations/"
            ):
                organization = (
                    self
                    .organizations_client
                    .get_organization(
                        request={
                            "name": parent
                        },
                        retry=self.retry,
                    )
                )

                organization_name = (
                    str(
                        getattr(
                            organization,
                            "name",
                            parent,
                        )
                    )
                )

                result[
                    "gcp_organizations"
                ].append(
                    _resource(
                        project_id=project_id,
                        location="global",
                        resource_type=(
                            "gcp_organization"
                        ),
                        resource_id=(
                            organization_name
                        ),
                        name=str(
                            getattr(
                                organization,
                                "display_name",
                                organization_name,
                            )
                        ),
                        status=str(
                            getattr(
                                getattr(
                                    organization,
                                    "state",
                                    None,
                                ),
                                "name",
                                getattr(
                                    organization,
                                    "state",
                                    "",
                                ),
                            )
                        ),
                        properties={},
                    )
                )

            break

        return result

    def _location_allowed(
        self,
        location: str,
    ) -> bool:
        allowed = (
            self.config.gcp_locations
        )

        if not allowed:
            return True

        value = location.lower()

        if value == "global":
            return True

        if value in allowed:
            return True

        # A zone such as us-central1-a
        # is accepted when us-central1 is
        # configured.
        return any(
            value.startswith(
                f"{region}-"
            )
            for region in allowed
        )

    @staticmethod
    def _aggregated_items(
        pager,
        attribute_name: str,
    ):
        for (
            scope,
            scoped_values,
        ) in pager:
            values = getattr(
                scoped_values,
                attribute_name,
                None,
            )

            if not values:
                continue

            for value in values:
                yield scope, value

    def _compute_inventory(
        self,
        project_id: str,
    ) -> dict[str, list[dict]]:
        result = _empty_inventory()

        for network in (
            self.networks_client.list(
                project=project_id,
                retry=self.retry,
            )
        ):
            data = _message_dict(
                network
            )

            resource_id = str(
                data.get("self_link")
                or (
                    f"projects/{project_id}/"
                    f"global/networks/"
                    f"{data.get('name')}"
                )
            )

            result[
                "gcp_networks"
            ].append(
                _resource(
                    project_id=project_id,
                    location="global",
                    resource_type=(
                        "gcp_network"
                    ),
                    resource_id=(
                        resource_id
                    ),
                    name=str(
                        data.get("name")
                        or resource_id
                    ),
                    labels=_labels(
                        data.get("labels")
                    ),
                    properties=data,
                )
            )

        subnetworks = (
            self.subnetworks_client
            .aggregated_list(
                project=project_id,
                retry=self.retry,
            )
        )

        for scope, subnetwork in (
            self._aggregated_items(
                subnetworks,
                "subnetworks",
            )
        ):
            data = _message_dict(
                subnetwork
            )

            location = _location(
                data.get("region")
                or scope
            )

            if not self._location_allowed(
                location
            ):
                continue

            resource_id = str(
                data.get("self_link")
                or (
                    f"projects/{project_id}/"
                    f"regions/{location}/"
                    f"subnetworks/"
                    f"{data.get('name')}"
                )
            )

            network = data.get(
                "network"
            )

            result[
                "gcp_subnetworks"
            ].append(
                _resource(
                    project_id=project_id,
                    location=location,
                    resource_type=(
                        "gcp_subnetwork"
                    ),
                    resource_id=(
                        resource_id
                    ),
                    name=str(
                        data.get("name")
                        or resource_id
                    ),
                    network=(
                        str(network)
                        if network
                        else None
                    ),
                    subnetworks=[
                        resource_id
                    ],
                    properties=data,
                )
            )

        for firewall in (
            self.firewalls_client.list(
                project=project_id,
                retry=self.retry,
            )
        ):
            data = _message_dict(
                firewall
            )

            resource_id = str(
                data.get("self_link")
                or (
                    f"projects/{project_id}/"
                    f"global/firewalls/"
                    f"{data.get('name')}"
                )
            )

            result[
                "gcp_firewall_rules"
            ].append(
                _resource(
                    project_id=project_id,
                    location="global",
                    resource_type=(
                        "gcp_firewall_rule"
                    ),
                    resource_id=(
                        resource_id
                    ),
                    name=str(
                        data.get("name")
                        or resource_id
                    ),
                    status=(
                        "disabled"
                        if data.get(
                            "disabled"
                        )
                        else "enabled"
                    ),
                    network=data.get(
                        "network"
                    ),
                    properties=data,
                )
            )

        for route in (
            self.routes_client.list(
                project=project_id,
                retry=self.retry,
            )
        ):
            data = _message_dict(route)

            resource_id = str(
                data.get("self_link")
                or (
                    f"projects/{project_id}/"
                    f"global/routes/"
                    f"{data.get('name')}"
                )
            )

            result[
                "gcp_routes"
            ].append(
                _resource(
                    project_id=project_id,
                    location="global",
                    resource_type=(
                        "gcp_route"
                    ),
                    resource_id=(
                        resource_id
                    ),
                    name=str(
                        data.get("name")
                        or resource_id
                    ),
                    network=data.get(
                        "network"
                    ),
                    properties=data,
                )
            )

        instances = (
            self.instances_client
            .aggregated_list(
                project=project_id,
                retry=self.retry,
            )
        )

        for scope, instance in (
            self._aggregated_items(
                instances,
                "instances",
            )
        ):
            data = _message_dict(instance)

            location = _location(
                data.get("zone")
                or scope
            )

            if not self._location_allowed(
                location
            ):
                continue

            resource_id = str(
                data.get("self_link")
                or (
                    f"projects/{project_id}/"
                    f"zones/{location}/"
                    f"instances/"
                    f"{data.get('name')}"
                )
            )

            interfaces = data.get(
                "network_interfaces",
                [],
            )

            networks: list[str] = []
            subnetworks: list[str] = []

            if isinstance(
                interfaces,
                list,
            ):
                for interface in interfaces:
                    if not isinstance(
                        interface,
                        dict,
                    ):
                        continue

                    network = interface.get(
                        "network"
                    )

                    subnetwork = (
                        interface.get(
                            "subnetwork"
                        )
                    )

                    if network:
                        networks.append(
                            str(network)
                        )

                    if subnetwork:
                        subnetworks.append(
                            str(subnetwork)
                        )

            result[
                "gcp_compute_instances"
            ].append(
                _resource(
                    project_id=project_id,
                    location=location,
                    resource_type=(
                        "gcp_compute_instance"
                    ),
                    resource_id=(
                        resource_id
                    ),
                    name=str(
                        data.get("name")
                        or resource_id
                    ),
                    status=data.get(
                        "status"
                    ),
                    labels=_labels(
                        data.get("labels")
                    ),
                    network=(
                        networks[0]
                        if networks
                        else None
                    ),
                    subnetworks=(
                        subnetworks
                    ),
                    properties={
                        **data,
                        "networks":
                            networks,
                        "subnetworks":
                            subnetworks,
                    },
                )
            )

        managers = (
            self
            .instance_group_managers_client
            .aggregated_list(
                project=project_id,
                retry=self.retry,
            )
        )

        for scope, manager in (
            self._aggregated_items(
                managers,
                (
                    "instance_group_managers"
                ),
            )
        ):
            data = _message_dict(manager)

            location = _location(
                data.get("zone")
                or data.get("region")
                or scope
            )

            if not self._location_allowed(
                location
            ):
                continue

            resource_id = str(
                data.get("self_link")
                or (
                    f"projects/{project_id}/"
                    f"locations/{location}/"
                    f"instanceGroupManagers/"
                    f"{data.get('name')}"
                )
            )

            result[
                "gcp_instance_group_managers"
            ].append(
                _resource(
                    project_id=project_id,
                    location=location,
                    resource_type=(
                        "gcp_instance_group_manager"
                    ),
                    resource_id=(
                        resource_id
                    ),
                    name=str(
                        data.get("name")
                        or resource_id
                    ),
                    status=data.get(
                        "status"
                    ),
                    properties=data,
                )
            )

        addresses = (
            self.addresses_client
            .aggregated_list(
                project=project_id,
                retry=self.retry,
            )
        )

        for scope, address in (
            self._aggregated_items(
                addresses,
                "addresses",
            )
        ):
            data = _message_dict(address)

            location = _location(
                data.get("region")
                or scope
            )

            if not self._location_allowed(
                location
            ):
                continue

            resource_id = str(
                data.get("self_link")
                or (
                    f"projects/{project_id}/"
                    f"locations/{location}/"
                    f"addresses/"
                    f"{data.get('name')}"
                )
            )

            result[
                "gcp_addresses"
            ].append(
                _resource(
                    project_id=project_id,
                    location=location,
                    resource_type=(
                        "gcp_address"
                    ),
                    resource_id=(
                        resource_id
                    ),
                    name=str(
                        data.get("name")
                        or resource_id
                    ),
                    status=data.get(
                        "status"
                    ),
                    network=data.get(
                        "network"
                    ),
                    subnetworks=[
                        str(
                            data.get(
                                "subnetwork"
                            )
                        )
                    ]
                    if data.get(
                        "subnetwork"
                    )
                    else [],
                    properties=data,
                )
            )

        forwarding_rules = (
            self.forwarding_rules_client
            .aggregated_list(
                project=project_id,
                retry=self.retry,
            )
        )

        for scope, rule in (
            self._aggregated_items(
                forwarding_rules,
                "forwarding_rules",
            )
        ):
            data = _message_dict(rule)

            location = _location(
                data.get("region")
                or scope
            )

            if not self._location_allowed(
                location
            ):
                continue

            resource_id = str(
                data.get("self_link")
                or (
                    f"projects/{project_id}/"
                    f"locations/{location}/"
                    f"forwardingRules/"
                    f"{data.get('name')}"
                )
            )

            result[
                "gcp_forwarding_rules"
            ].append(
                _resource(
                    project_id=project_id,
                    location=location,
                    resource_type=(
                        "gcp_forwarding_rule"
                    ),
                    resource_id=(
                        resource_id
                    ),
                    name=str(
                        data.get("name")
                        or resource_id
                    ),
                    status=data.get(
                        "status"
                    ),
                    network=data.get(
                        "network"
                    ),
                    subnetworks=[
                        str(
                            data.get(
                                "subnetwork"
                            )
                        )
                    ]
                    if data.get(
                        "subnetwork"
                    )
                    else [],
                    properties=data,
                )
            )

        return result

    def _gke_inventory(
        self,
        project_id: str,
    ) -> dict[str, list[dict]]:
        result = _empty_inventory()

        response = (
            self.gke_client
            .list_clusters(
                request={
                    "parent": (
                        f"projects/{project_id}/"
                        "locations/-"
                    )
                },
                retry=self.retry,
            )
        )

        clusters = getattr(
            response,
            "clusters",
            [],
        ) or []

        for cluster in clusters:
            data = _message_dict(cluster)

            location = str(
                data.get("location")
                or data.get("zone")
                or "global"
            ).lower()

            if not self._location_allowed(
                location
            ):
                continue

            cluster_name = str(
                data.get("name")
                or "unknown-cluster"
            )

            resource_id = (
                "//container.googleapis.com/"
                f"projects/{project_id}/"
                f"locations/{location}/"
                f"clusters/{cluster_name}"
            )

            labels = _labels(
                data.get(
                    "resource_labels"
                )
            )

            result[
                "gcp_gke_clusters"
            ].append(
                _resource(
                    project_id=project_id,
                    location=location,
                    resource_type=(
                        "gcp_gke_cluster"
                    ),
                    resource_id=(
                        resource_id
                    ),
                    name=cluster_name,
                    status=str(
                        data.get("status")
                        or ""
                    ),
                    labels=labels,
                    network=data.get(
                        "network"
                    ),
                    subnetworks=[
                        str(
                            data.get(
                                "subnetwork"
                            )
                        )
                    ]
                    if data.get(
                        "subnetwork"
                    )
                    else [],
                    properties={
                        **data,
                        "cluster_name":
                            cluster_name,
                    },
                )
            )

            node_pools = data.get(
                "node_pools",
                [],
            )

            if not isinstance(
                node_pools,
                list,
            ):
                continue

            for node_pool in node_pools:
                if not isinstance(
                    node_pool,
                    dict,
                ):
                    continue

                node_pool_name = str(
                    node_pool.get("name")
                    or "unknown-node-pool"
                )

                node_pool_id = (
                    f"{resource_id}/"
                    f"nodePools/"
                    f"{node_pool_name}"
                )

                node_config = (
                    node_pool.get(
                        "config",
                        {},
                    )
                )

                if not isinstance(
                    node_config,
                    dict,
                ):
                    node_config = {}

                result[
                    "gcp_gke_node_pools"
                ].append(
                    _resource(
                        project_id=(
                            project_id
                        ),
                        location=location,
                        resource_type=(
                            "gcp_gke_node_pool"
                        ),
                        resource_id=(
                            node_pool_id
                        ),
                        name=(
                            node_pool_name
                        ),
                        status=str(
                            node_pool.get(
                                "status"
                            )
                            or ""
                        ),
                        labels=_labels(
                            node_config.get(
                                "labels"
                            )
                        ),
                        properties={
                            **node_pool,
                            "cluster_name":
                                cluster_name,
                            "cluster_id":
                                resource_id,
                        },
                    )
                )

        return result

    def _asset_inventory(
        self,
        project_id: str,
    ) -> tuple[
        dict[str, list[dict]],
        list[str],
    ]:
        result = _empty_inventory()

        errors: list[str] = []

        scope = f"projects/{project_id}"

        for (
            group_name,
            asset_types,
        ) in ASSET_TYPE_GROUPS.items():
            try:
                values = (
                    self.asset_client
                    .search_all_resources(
                        request={
                            "scope": scope,
                            "asset_types":
                                asset_types,
                            "page_size": max(
                                min(
                                    self.config
                                    .gcp_asset_page_size,
                                    500,
                                ),
                                1,
                            ),
                        },
                        retry=self.retry,
                    )
                )

                for value in values:
                    data = _message_dict(
                        value
                    )

                    asset_type = str(
                        data.get(
                            "asset_type"
                        )
                        or ""
                    )

                    resource_type = (
                        ASSET_RESOURCE_TYPES
                        .get(asset_type)
                    )

                    inventory_key = (
                        ASSET_INVENTORY_KEYS
                        .get(
                            resource_type
                            or ""
                        )
                    )

                    if (
                        not resource_type
                        or not inventory_key
                    ):
                        continue

                    location = _location(
                        data.get(
                            "location"
                        )
                    )

                    if (
                        not self
                        ._location_allowed(
                            location
                        )
                    ):
                        continue

                    resource_id = str(
                        data.get("name")
                        or ""
                    )

                    if not resource_id:
                        continue

                    properties = {
                        **data,
                        "asset_type":
                            asset_type,
                    }

                    network_refs = (
                        _reference_values(
                            properties,
                            {
                                "network",
                                "network_uri",
                                "networkuri",
                            },
                        )
                    )

                    subnet_refs = (
                        _reference_values(
                            properties,
                            {
                                "subnetwork",
                                "subnet",
                                "subnetwork_uri",
                            },
                        )
                    )

                    result[
                        inventory_key
                    ].append(
                        _resource(
                            project_id=(
                                project_id
                            ),
                            location=location,
                            resource_type=(
                                resource_type
                            ),
                            resource_id=(
                                resource_id
                            ),
                            name=str(
                                data.get(
                                    "display_name"
                                )
                                or _last_segment(
                                    resource_id
                                )
                            ),
                            status=str(
                                data.get(
                                    "state"
                                )
                                or ""
                            )
                            or None,
                            labels=_labels(
                                data.get(
                                    "labels"
                                )
                            ),
                            network=(
                                network_refs[0]
                                if network_refs
                                else None
                            ),
                            subnetworks=(
                                subnet_refs
                            ),
                            properties=(
                                properties
                            ),
                            resource_group=(
                                data.get(
                                    (
                                        "parent_"
                                        "full_resource_name"
                                    )
                                )
                            ),
                        )
                    )

            except (
                GoogleAPICallError,
                RetryError,
            ) as exc:
                errors.append(
                    f"{group_name}: {exc}"
                )

                LOGGER.warning(
                    "GCP Cloud Asset query "
                    "failed for %s/%s: %s",
                    project_id,
                    group_name,
                    exc,
                )

        return result, errors

    def _collect_project(
        self,
        project_id: str,
    ) -> tuple[
        dict[str, list[dict]],
        list[str],
    ]:
        cached = self.cache.load(
            project_id=project_id
        )

        if cached is not None:
            inventory = cached[
                "inventory"
            ]

            inventory.setdefault(
                "gcp_projects",
                [],
            )

            return inventory, []

        inventory = _empty_inventory()

        errors: list[str] = []

        successful_collectors = 0

        try:
            project = (
                self._project_metadata(
                    project_id
                )
            )

            hierarchy = (
                self._hierarchy_inventory(
                    project=project
                )
            )

            _merge(
                inventory,
                hierarchy,
            )

            successful_collectors += 1

        except (
            GoogleAPICallError,
            RetryError,
        ) as exc:
            errors.append(
                f"{project_id}/hierarchy: "
                f"{exc}"
            )

        collectors = (
            (
                "compute",
                self._compute_inventory,
            ),
            (
                "gke",
                self._gke_inventory,
            ),
        )

        for name, collector in collectors:
            try:
                collected = collector(
                    project_id
                )

                _merge(
                    inventory,
                    collected,
                )

                successful_collectors += 1

            except (
                GoogleAPICallError,
                RetryError,
            ) as exc:
                errors.append(
                    f"{project_id}/{name}: "
                    f"{exc}"
                )

                LOGGER.warning(
                    "GCP collection failed "
                    "for %s/%s: %s",
                    project_id,
                    name,
                    exc,
                )

        assets, asset_errors = (
            self._asset_inventory(
                project_id
            )
        )

        _merge(inventory, assets)

        errors.extend(asset_errors)

        if any(
            values
            for values in assets.values()
        ):
            successful_collectors += 1

        if successful_collectors:
            self.cache.save(
                project_id=project_id,
                inventory=inventory,
            )

            return inventory, errors

        stale = self.cache.load(
            project_id=project_id,
            allow_stale=True,
        )

        if stale is not None:
            errors.append(
                f"{project_id}: using stale "
                "GCP inventory cache"
            )

            return (
                stale["inventory"],
                errors,
            )

        return inventory, errors

    def doctor(
        self,
    ) -> PluginDiagnostic:
        try:
            project_ids = (
                self._project_ids()
            )

            if not project_ids:
                raise ValueError(
                    "No GCP projects are "
                    "configured or detected."
                )

            project = (
                self._project_metadata(
                    project_ids[0]
                )
            )

        except (
            GoogleAPICallError,
            RetryError,
            ValueError,
        ) as exc:
            return PluginDiagnostic(
                name=self.name,
                status="failed",
                message=str(exc),
                capabilities=list(
                    self.capabilities
                ),
            )

        return PluginDiagnostic(
            name=self.name,
            status="available",
            capabilities=list(
                self.capabilities
            ),
            details={
                "detected_project":
                    self.detected_project,
                "project_ids":
                    project_ids,
                "project_probe":
                    project,
                "locations":
                    self.config
                    .gcp_locations,
                "impersonation":
                    bool(
                        self.config
                        .gcp_impersonate_service_account
                    ),
                "credential_method":
                    (
                        "application-default-"
                        "credentials"
                    ),
            },
        )

    def collect(
        self,
    ) -> PluginCollectionResult:
        try:
            project_ids = (
                self._project_ids()
            )

        except (
            GoogleAPICallError,
            RetryError,
        ) as exc:
            return PluginCollectionResult(
                plugin_name=self.name,
                status="failed",
                capabilities=list(
                    self.capabilities
                ),
                errors=[str(exc)],
            )

        if not project_ids:
            return PluginCollectionResult(
                plugin_name=self.name,
                status="failed",
                capabilities=list(
                    self.capabilities
                ),
                errors=[
                    "No GCP projects are "
                    "configured or detected."
                ],
            )

        inventory = _empty_inventory()

        errors: list[str] = []

        successful_projects = 0

        project_status: list[
            dict[str, Any]
        ] = []

        for project_id in project_ids:
            project_inventory, (
                project_errors
            ) = self._collect_project(
                project_id
            )

            _merge(
                inventory,
                project_inventory,
            )

            errors.extend(
                project_errors
            )

            has_resources = any(
                values
                for values in (
                    project_inventory
                    .values()
                )
            )

            if has_resources:
                successful_projects += 1

            project_status.append(
                {
                    "project_id":
                        project_id,
                    "status": (
                        "partial"
                        if project_errors
                        else "success"
                    ),
                    "errors":
                        project_errors,
                }
            )

        resource_count = sum(
            len(values)
            for key, values
            in inventory.items()
            if key != "gcp_projects"
        )

        status = (
            "success"
            if not errors
            else (
                "partial"
                if successful_projects
                else "failed"
            )
        )

        return PluginCollectionResult(
            plugin_name=self.name,
            status=status,
            inventory=inventory,
            capabilities=list(
                self.capabilities
            ),
            errors=errors,
            metadata={
                "provider": "gcp",
                "project_ids":
                    project_ids,
                "account_ids":
                    project_ids,
                "locations":
                    self.config
                    .gcp_locations,
                "resource_count":
                    resource_count,
                "successful_project_count":
                    successful_projects,
                "project_status":
                    project_status,
                "impersonation":
                    bool(
                        self.config
                        .gcp_impersonate_service_account
                    ),
            },
        )