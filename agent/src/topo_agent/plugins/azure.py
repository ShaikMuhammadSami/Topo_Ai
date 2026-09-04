from __future__ import annotations

import logging
import time
from datetime import (
    date,
    datetime,
)
from typing import Any

from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ServiceRequestError,
)
from azure.identity import (
    AzureCliCredential,
    CredentialUnavailableError,
    DefaultAzureCredential,
    ManagedIdentityCredential,
    WorkloadIdentityCredential,
)
from azure.mgmt.resourcegraph import (
    ResourceGraphClient,
)
from azure.mgmt.resourcegraph.models import (
    QueryRequest,
    QueryRequestOptions,
)
from azure.mgmt.subscription import (
    SubscriptionClient,
)

from topo_agent import __version__
from topo_agent.azure_cache import (
    AzureInventoryCache,
)
from topo_agent.config import (
    AgentConfig,
    agent_home,
)
from topo_agent.plugin import (
    PluginCollectionResult,
    PluginDiagnostic,
)
from topo_agent.security import safe_exception_message


LOGGER = logging.getLogger(
    "topo-agent.azure"
)


RESOURCE_TYPE_MAP = {
    (
        "microsoft.network/"
        "virtualnetworks"
    ): "azure_virtual_network",

    (
        "microsoft.network/"
        "virtualnetworks/subnets"
    ): "azure_subnet",

    (
        "microsoft.network/"
        "routetables"
    ): "azure_route_table",

    (
        "microsoft.network/"
        "networksecuritygroups"
    ): "azure_network_security_group",

    (
        "microsoft.network/"
        "networkinterfaces"
    ): "azure_network_interface",

    (
        "microsoft.network/"
        "publicipaddresses"
    ): "azure_public_ip_address",

    (
        "microsoft.compute/"
        "virtualmachines"
    ): "azure_virtual_machine",

    (
        "microsoft.compute/"
        "virtualmachinescalesets"
    ): "azure_virtual_machine_scale_set",

    (
        "microsoft.containerservice/"
        "managedclusters"
    ): "azure_aks_cluster",

    (
        "microsoft.network/"
        "loadbalancers"
    ): "azure_load_balancer",

    (
        "microsoft.network/"
        "applicationgateways"
    ): "azure_application_gateway",

    (
        "microsoft.network/"
        "privateendpoints"
    ): "azure_private_endpoint",

    (
        "microsoft.sql/servers"
    ): "azure_sql_server",

    (
        "microsoft.sql/"
        "servers/databases"
    ): "azure_sql_database",

    (
        "microsoft.dbforpostgresql/"
        "flexibleservers"
    ): (
        "azure_postgresql_"
        "flexible_server"
    ),

    (
        "microsoft.web/serverfarms"
    ): "azure_app_service_plan",

    (
        "microsoft.web/sites"
    ): "azure_app_service",
}


INVENTORY_KEYS = (
    "azure_subscriptions",
    "azure_resource_groups",
    "azure_virtual_networks",
    "azure_subnets",
    "azure_route_tables",
    "azure_network_security_groups",
    "azure_network_interfaces",
    "azure_public_ip_addresses",
    "azure_virtual_machines",
    "azure_virtual_machine_scale_sets",
    "azure_aks_clusters",
    "azure_load_balancers",
    "azure_application_gateways",
    "azure_private_endpoints",
    "azure_sql_servers",
    "azure_sql_databases",
    "azure_postgresql_flexible_servers",
    "azure_app_service_plans",
    "azure_app_services",
    "azure_function_apps",
)


INVENTORY_KEY_MAP = {
    "azure_subscription":
        "azure_subscriptions",

    "azure_resource_group":
        "azure_resource_groups",

    "azure_virtual_network":
        "azure_virtual_networks",

    "azure_subnet":
        "azure_subnets",

    "azure_route_table":
        "azure_route_tables",

    "azure_network_security_group":
        "azure_network_security_groups",

    "azure_network_interface":
        "azure_network_interfaces",

    "azure_public_ip_address":
        "azure_public_ip_addresses",

    "azure_virtual_machine":
        "azure_virtual_machines",

    "azure_virtual_machine_scale_set":
        "azure_virtual_machine_scale_sets",

    "azure_aks_cluster":
        "azure_aks_clusters",

    "azure_load_balancer":
        "azure_load_balancers",

    "azure_application_gateway":
        "azure_application_gateways",

    "azure_private_endpoint":
        "azure_private_endpoints",

    "azure_sql_server":
        "azure_sql_servers",

    "azure_sql_database":
        "azure_sql_databases",

    (
        "azure_postgresql_"
        "flexible_server"
    ): (
        "azure_postgresql_"
        "flexible_servers"
    ),

    "azure_app_service_plan":
        "azure_app_service_plans",

    "azure_app_service":
        "azure_app_services",

    "azure_function_app":
        "azure_function_apps",
}


QUERY_GROUPS = {
    "resource-groups": (
        """
resourcecontainers
| where type =~
    'microsoft.resources/subscriptions/resourcegroups'
| project
    id,
    name,
    type=tolower(type),
    subscriptionId,
    resourceGroup=name,
    location,
    tags,
    kind='',
    sku='',
    properties=pack_all()
| order by id asc
"""
    ),

    "network": (
        """
resources
| where type in~ (
    'microsoft.network/virtualnetworks',
    'microsoft.network/routetables',
    'microsoft.network/networksecuritygroups',
    'microsoft.network/networkinterfaces',
    'microsoft.network/publicipaddresses',
    'microsoft.network/loadbalancers',
    'microsoft.network/applicationgateways',
    'microsoft.network/privateendpoints'
)
| project
    id,
    name,
    type=tolower(type),
    subscriptionId,
    resourceGroup,
    location,
    tags,
    kind,
    sku,
    properties
| order by id asc
"""
    ),

    "compute": (
        """
resources
| where type in~ (
    'microsoft.compute/virtualmachines',
    'microsoft.compute/virtualmachinescalesets'
)
| project
    id,
    name,
    type=tolower(type),
    subscriptionId,
    resourceGroup,
    location,
    tags,
    kind,
    sku,
    properties
| order by id asc
"""
    ),

    "containers": (
        """
resources
| where type =~
    'microsoft.containerservice/managedclusters'
| project
    id,
    name,
    type=tolower(type),
    subscriptionId,
    resourceGroup,
    location,
    tags,
    kind,
    sku,
    properties
| order by id asc
"""
    ),

    "data": (
        """
resources
| where type in~ (
    'microsoft.sql/servers',
    'microsoft.sql/servers/databases',
    'microsoft.dbforpostgresql/flexibleservers'
)
| project
    id,
    name,
    type=tolower(type),
    subscriptionId,
    resourceGroup,
    location,
    tags,
    kind,
    sku,
    properties
| order by id asc
"""
    ),

    "apps": (
        """
resources
| where type in~ (
    'microsoft.web/serverfarms',
    'microsoft.web/sites'
)
| project
    id,
    name,
    type=tolower(type),
    subscriptionId,
    resourceGroup,
    location,
    tags,
    kind,
    sku,
    properties
| order by id asc
"""
    ),
}


def _empty_inventory(
) -> dict[str, list[dict]]:
    return {
        key: []
        for key in INVENTORY_KEYS
    }


def _json_value(
    value: Any,
) -> Any:
    if isinstance(
        value,
        (datetime, date),
    ):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            str(key): _json_value(item)
            for key, item
            in value.items()
        }

    if isinstance(value, list):
        return [
            _json_value(item)
            for item in value
        ]

    return value


def _tags(
    value: Any,
) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}

    return {
        str(key): str(item)
        for key, item
        in value.items()
    }


def _chunks(
    values: list[str],
    size: int,
) -> list[list[str]]:
    return [
        values[index:index + size]
        for index
        in range(
            0,
            len(values),
            size,
        )
    ]


def _resource_group_from_id(
    resource_id: str,
) -> str | None:
    parts = [
        part
        for part in resource_id.split("/")
        if part
    ]

    for index, part in enumerate(
        parts
    ):
        if (
            part.lower()
            == "resourcegroups"
            and index + 1 < len(parts)
        ):
            return parts[index + 1]

    return None


def _collect_reference_ids(
    value: Any,
    *,
    key_names: set[str],
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
                in key_names
            ):
                reference_id = item.get("id")

                if reference_id:
                    results.append(
                        str(reference_id)
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

    return sorted(
        set(results)
    )


def _resource_type(
    *,
    azure_type: str,
    kind: str,
) -> str | None:
    resource_type = (
        RESOURCE_TYPE_MAP.get(
            azure_type.lower()
        )
    )

    if (
        resource_type
        == "azure_app_service"
        and "functionapp"
        in kind.lower()
    ):
        return "azure_function_app"

    return resource_type


class AzureCredentialFactory:
    def __init__(
        self,
        config: AgentConfig,
    ) -> None:
        self.config = config

    def build(
        self,
    ):
        mode = (
            self.config.azure_auth_mode
            .strip()
            .lower()
        )

        if mode == "cli":
            return AzureCliCredential(
                tenant_id=(
                    self.config
                    .azure_tenant_id
                )
            )

        if mode == "managed_identity":
            return (
                ManagedIdentityCredential(
                    client_id=(
                        self.config
                        .azure_client_id
                    )
                )
            )

        if mode == "workload_identity":
            required = {
                "azure_tenant_id":
                    self.config
                    .azure_tenant_id,

                "azure_client_id":
                    self.config
                    .azure_client_id,

                (
                    "azure_federated_"
                    "token_file"
                ): (
                    self.config
                    .azure_federated_token_file
                ),
            }

            missing = [
                name
                for name, value
                in required.items()
                if not value
            ]

            if missing:
                raise ValueError(
                    "Azure workload identity "
                    "configuration is missing: "
                    + ", ".join(missing)
                )

            return WorkloadIdentityCredential(
                tenant_id=(
                    self.config
                    .azure_tenant_id
                ),
                client_id=(
                    self.config
                    .azure_client_id
                ),
                token_file_path=(
                    self.config
                    .azure_federated_token_file
                ),
            )

        if mode != "default":
            raise ValueError(
                "Unsupported Azure "
                "authentication mode: "
                f"{mode}"
            )

        return DefaultAzureCredential(
            exclude_interactive_browser_credential=True,
            managed_identity_client_id=(
                self.config.azure_client_id
            ),
        )


class AzurePlugin:
    name = "azure"
    version = __version__

    capabilities = (
        "azure.identity",
        "azure.subscriptions",
        "azure.resource_groups",
        "azure.resource_graph",
        "azure.network",
        "azure.compute",
        "azure.aks",
        "azure.load_balancing",
        "azure.private_endpoints",
        "azure.sql",
        "azure.postgresql",
        "azure.app_service",
        "azure.functions",
        "azure.tags",
    )

    def __init__(
        self,
        config: AgentConfig,
    ) -> None:
        self.config = config

        self.credential = (
            AzureCredentialFactory(
                config
            ).build()
        )

        self.subscription_client = (
            SubscriptionClient(
                self.credential
            )
        )

        self.resource_graph = (
            ResourceGraphClient(
                self.credential
            )
        )

        self.cache = AzureInventoryCache(
            (
                agent_home()
                / "cache"
                / "azure"
            ),
            ttl_seconds=(
                config
                .azure_cache_ttl_seconds
            ),
        )

    def close(
        self,
    ) -> None:
        for value in (
            self.resource_graph,
            self.subscription_client,
            self.credential,
        ):
            close_method = getattr(
                value,
                "close",
                None,
            )

            if callable(close_method):
                try:
                    close_method()
                except Exception:
                    LOGGER.debug(
                        "Unable to close Azure "
                        "SDK client.",
                        exc_info=True,
                    )

    def _retry(
        self,
        operation,
    ):
        attempts = max(
            self.config
            .azure_api_max_attempts,
            1,
        )

        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                return operation()

            except (
                ServiceRequestError,
                HttpResponseError,
            ) as exc:
                last_error = exc

                response = getattr(
                    exc,
                    "response",
                    None,
                )

                status_code = (
                    getattr(
                        exc,
                        "status_code",
                        None,
                    )
                    or getattr(
                        response,
                        "status_code",
                        None,
                    )
                )

                retryable = (
                    status_code is None
                    or status_code in {
                        408,
                        429,
                        500,
                        502,
                        503,
                        504,
                    }
                )

                if (
                    not retryable
                    or attempt
                    >= attempts - 1
                ):
                    raise

                time.sleep(
                    1.0 * (2 ** attempt)
                )

        if last_error:
            raise last_error

        raise RuntimeError(
            "Azure retry operation ended "
            "without a result."
        )

    def _subscriptions(
        self,
    ) -> list[dict[str, Any]]:
        configured = [
            value.strip()
            for value in (
                self.config
                .azure_subscription_ids
            )
            if value.strip()
        ]

        subscriptions: list[
            dict[str, Any]
        ] = []

        if configured:
            for subscription_id in (
                configured
            ):
                display_name = (
                    subscription_id
                )

                state = "unknown"

                try:
                    value = self._retry(
                        lambda:
                            self
                            .subscription_client
                            .subscriptions
                            .get(
                                subscription_id
                            )
                    )

                    display_name = str(
                        getattr(
                            value,
                            "display_name",
                            subscription_id,
                        )
                        or subscription_id
                    )

                    state = str(
                        getattr(
                            value,
                            "state",
                            "unknown",
                        )
                    )

                except HttpResponseError:
                    LOGGER.warning(
                        "Unable to read Azure "
                        "subscription metadata "
                        "for %s. The configured "
                        "subscription ID will "
                        "still be queried.",
                        subscription_id,
                    )

                subscriptions.append(
                    {
                        "subscription_id":
                            subscription_id,
                        "display_name":
                            display_name,
                        "state": state,
                    }
                )

            return subscriptions

        values = self._retry(
            lambda: list(
                self
                .subscription_client
                .subscriptions
                .list()
            )
        )

        for value in values:
            subscription_id = getattr(
                value,
                "subscription_id",
                None,
            )

            if not subscription_id:
                continue

            subscriptions.append(
                {
                    "subscription_id":
                        str(subscription_id),

                    "display_name": str(
                        getattr(
                            value,
                            "display_name",
                            subscription_id,
                        )
                        or subscription_id
                    ),

                    "state": str(
                        getattr(
                            value,
                            "state",
                            "unknown",
                        )
                    ),
                }
            )

        return subscriptions

    def _query_rows(
        self,
        *,
        subscription_ids: list[str],
        query: str,
    ) -> list[dict[str, Any]]:
        rows: list[
            dict[str, Any]
        ] = []

        # Keep each Resource Graph scope
        # reasonably bounded.
        for subscription_batch in (
            _chunks(
                subscription_ids,
                200,
            )
        ):
            skip_token: (
                str | None
            ) = None

            while True:
                options = (
                    QueryRequestOptions(
                        result_format=(
                            "objectArray"
                        ),
                        top=max(
                            min(
                                self.config
                                .azure_query_page_size,
                                1000,
                            ),
                            1,
                        ),
                        skip_token=skip_token,
                    )
                )

                request = QueryRequest(
                    subscriptions=(
                        subscription_batch
                    ),
                    query=query,
                    options=options,
                )

                response = self._retry(
                    lambda:
                        self
                        .resource_graph
                        .resources(request)
                )

                data = getattr(
                    response,
                    "data",
                    [],
                )

                if isinstance(data, list):
                    rows.extend(
                        item
                        for item in data
                        if isinstance(
                            item,
                            dict,
                        )
                    )

                skip_token = getattr(
                    response,
                    "skip_token",
                    None,
                )

                if not skip_token:
                    break

        return rows

    def _row_in_scope(
        self,
        row: dict[str, Any],
    ) -> bool:
        location = str(
            row.get("location")
            or "global"
        ).lower()

        resource_group = str(
            row.get("resourceGroup")
            or _resource_group_from_id(
                str(
                    row.get("id")
                    or ""
                )
            )
            or ""
        ).lower()

        if (
            self.config.azure_locations
            and location not in (
                self.config.azure_locations
            )
            and location != "global"
        ):
            return False

        if (
            self.config
            .azure_resource_groups
            and resource_group not in (
                self.config
                .azure_resource_groups
            )
        ):
            return False

        return True

    def _base_resource(
        self,
        *,
        subscription_id: str,
        location: str,
        resource_group: str | None,
        resource_type: str,
        resource_id: str,
        name: str,
        azure_type: str,
        tags: dict[str, str],
        properties:
            dict[str, Any],
        kind: str | None = None,
        sku: Any = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        subnet_ids = (
            _collect_reference_ids(
                properties,
                key_names={
                    "subnet",
                    "subnets",
                },
            )
        )

        return {
            "provider": "azure",
            "account_id":
                subscription_id,
            "region":
                location or "global",
            "resource_group":
                resource_group,
            "resource_type":
                resource_type,
            "resource_id":
                resource_id,
            "name": name,
            "arn": resource_id,
            "status": status,
            "tags": tags,
            "vpc_id": None,
            "subnet_ids":
                subnet_ids,
            "properties": {
                **properties,
                "azure_type":
                    azure_type,
                "resource_group":
                    resource_group,
                "kind": kind,
                "sku":
                    _json_value(sku),
            },
        }

    def _normalise_row(
        self,
        row: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not self._row_in_scope(row):
            return []

        resource_id = str(
            row.get("id")
            or ""
        )

        azure_type = str(
            row.get("type")
            or ""
        ).lower()

        kind = str(
            row.get("kind")
            or ""
        )

        subscription_id = str(
            row.get("subscriptionId")
            or ""
        )

        resource_group = str(
            row.get("resourceGroup")
            or _resource_group_from_id(
                resource_id
            )
            or ""
        )

        location = str(
            row.get("location")
            or "global"
        ).lower()

        name = str(
            row.get("name")
            or resource_id
        )

        properties = row.get(
            "properties"
        )

        if not isinstance(
            properties,
            dict,
        ):
            properties = {}

        tags = _tags(
            row.get("tags")
        )

        if (
            azure_type
            == (
                "microsoft.resources/"
                "subscriptions/resourcegroups"
            )
        ):
            return [
                self._base_resource(
                    subscription_id=(
                        subscription_id
                    ),
                    location=location,
                    resource_group=(
                        resource_group
                    ),
                    resource_type=(
                        "azure_resource_group"
                    ),
                    resource_id=(
                        resource_id
                    ),
                    name=name,
                    azure_type=azure_type,
                    tags=tags,
                    properties=properties,
                )
            ]

        resource_type = _resource_type(
            azure_type=azure_type,
            kind=kind,
        )

        if resource_type is None:
            return []

        status = (
            properties.get(
                "provisioningState"
            )
            or properties.get("state")
        )

        result = [
            self._base_resource(
                subscription_id=(
                    subscription_id
                ),
                location=location,
                resource_group=(
                    resource_group
                ),
                resource_type=(
                    resource_type
                ),
                resource_id=(
                    resource_id
                ),
                name=name,
                azure_type=azure_type,
                tags=tags,
                properties=properties,
                kind=kind,
                sku=row.get("sku"),
                status=(
                    str(status)
                    if status is not None
                    else None
                ),
            )
        ]

        # Resource Graph commonly returns
        # subnets embedded under a VNet.
        if (
            resource_type
            == "azure_virtual_network"
        ):
            subnets = properties.get(
                "subnets",
                [],
            )

            if isinstance(subnets, list):
                for subnet in subnets:
                    if not isinstance(
                        subnet,
                        dict,
                    ):
                        continue

                    subnet_properties = (
                        subnet.get(
                            "properties"
                        )
                    )

                    if not isinstance(
                        subnet_properties,
                        dict,
                    ):
                        subnet_properties = {}

                    subnet_name = str(
                        subnet.get("name")
                        or "unknown-subnet"
                    )

                    subnet_id = str(
                        subnet.get("id")
                        or (
                            f"{resource_id}/"
                            f"subnets/"
                            f"{subnet_name}"
                        )
                    )

                    result.append(
                        self._base_resource(
                            subscription_id=(
                                subscription_id
                            ),
                            location=location,
                            resource_group=(
                                resource_group
                            ),
                            resource_type=(
                                "azure_subnet"
                            ),
                            resource_id=(
                                subnet_id
                            ),
                            name=subnet_name,
                            azure_type=(
                                "microsoft.network/"
                                "virtualnetworks/"
                                "subnets"
                            ),
                            tags={},
                            properties={
                                **subnet_properties,
                                (
                                    "parent_"
                                    "virtual_network_id"
                                ): resource_id,
                            },
                            status=str(
                                subnet_properties.get(
                                    "provisioningState",
                                    "",
                                )
                            )
                            or None,
                        )
                    )

        return result

    def _scope_key(
        self,
        subscription_ids: list[str],
    ) -> str:
        return "|".join(
            [
                ",".join(
                    sorted(
                        subscription_ids
                    )
                ),
                ",".join(
                    sorted(
                        self.config
                        .azure_locations
                    )
                ),
                ",".join(
                    sorted(
                        self.config
                        .azure_resource_groups
                    )
                ),
            ]
        )

    def doctor(
        self,
    ) -> PluginDiagnostic:
        try:
            self.credential.get_token(
                (
                    "https://management."
                    "azure.com/.default"
                )
            )

            subscriptions = (
                self._subscriptions()
            )

        except (
            ClientAuthenticationError,
            CredentialUnavailableError,
            HttpResponseError,
            ServiceRequestError,
            ValueError,
        ) as exc:
            return PluginDiagnostic(
                name=self.name,
                status="failed",
                message=safe_exception_message(exc, "Azure discovery failed"),
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
                "auth_mode":
                    self.config
                    .azure_auth_mode,

                "tenant_id":
                    self.config
                    .azure_tenant_id,

                "client_id":
                    self.config
                    .azure_client_id,

                "subscription_count":
                    len(subscriptions),

                "subscriptions": [
                    {
                        "subscription_id":
                            item[
                                "subscription_id"
                            ],
                        "display_name":
                            item[
                                "display_name"
                            ],
                        "state":
                            item["state"],
                    }
                    for item in subscriptions
                ],

                "locations":
                    self.config
                    .azure_locations,

                "resource_groups":
                    self.config
                    .azure_resource_groups,
            },
        )

    def collect(
        self,
    ) -> PluginCollectionResult:
        subscriptions = (
            self._subscriptions()
        )

        subscription_ids = [
            item["subscription_id"]
            for item in subscriptions
        ]

        if not subscription_ids:
            return PluginCollectionResult(
                plugin_name=self.name,
                status="failed",
                capabilities=list(
                    self.capabilities
                ),
                errors=[
                    "No Azure subscriptions "
                    "are available."
                ],
            )

        inventory = _empty_inventory()

        for subscription in subscriptions:
            subscription_id = (
                subscription[
                    "subscription_id"
                ]
            )

            inventory[
                "azure_subscriptions"
            ].append(
                {
                    "provider": "azure",
                    "account_id":
                        subscription_id,
                    "region": "global",
                    "resource_group": None,
                    "resource_type":
                        "azure_subscription",
                    "resource_id":
                        subscription_id,
                    "name":
                        subscription[
                            "display_name"
                        ],
                    "arn": (
                        "/subscriptions/"
                        f"{subscription_id}"
                    ),
                    "status":
                        subscription[
                            "state"
                        ],
                    "tags": {},
                    "vpc_id": None,
                    "subnet_ids": [],
                    "properties": {
                        "tenant_id":
                            self.config
                            .azure_tenant_id,
                        "auth_mode":
                            self.config
                            .azure_auth_mode,
                    },
                }
            )

        scope_key = self._scope_key(
            subscription_ids
        )

        cached = self.cache.load(
            scope_key=scope_key
        )

        if cached is not None:
            cached_inventory = (
                cached["inventory"]
            )

            # Keep current subscription
            # metadata, but reuse cached
            # resources.
            for key, values in (
                cached_inventory.items()
            ):
                if (
                    key
                    == "azure_subscriptions"
                ):
                    continue

                inventory.setdefault(
                    key,
                    [],
                )

                inventory[key].extend(
                    values
                )

            return PluginCollectionResult(
                plugin_name=self.name,
                status="success",
                inventory=inventory,
                capabilities=list(
                    self.capabilities
                ),
                metadata={
                    "provider": "azure",
                    "auth_mode":
                        self.config
                        .azure_auth_mode,
                    "tenant_id":
                        self.config
                        .azure_tenant_id,
                    "subscription_ids":
                        subscription_ids,
                    "locations":
                        self.config
                        .azure_locations,
                    "resource_count":
                        sum(
                            len(values)
                            for key, values
                            in inventory.items()
                            if key
                            != (
                                "azure_"
                                "subscriptions"
                            )
                        ),
                    "cache_used": True,
                    "cache_age_seconds":
                        cached[
                            "age_seconds"
                        ],
                },
            )

        errors: list[str] = []
        successful_queries = 0

        seen_resource_ids: set[
            str
        ] = set()

        for (
            query_name,
            query,
        ) in QUERY_GROUPS.items():
            try:
                rows = self._query_rows(
                    subscription_ids=(
                        subscription_ids
                    ),
                    query=query,
                )

                successful_queries += 1

            except (
                ClientAuthenticationError,
                HttpResponseError,
                ServiceRequestError,
            ) as exc:
                errors.append(
                    safe_exception_message(
                        exc,
                        f"Azure Resource Graph query failed for {query_name}",
                    )
                )

                LOGGER.warning(
                    "Azure Resource Graph "
                    "query failed for %s: %s",
                    query_name,
                    type(exc).__name__,
                )

                continue

            for row in rows:
                for value in (
                    self._normalise_row(
                        row
                    )
                ):
                    resource_id = str(
                        value.get(
                            "resource_id"
                        )
                        or ""
                    ).lower()

                    if (
                        not resource_id
                        or resource_id
                        in seen_resource_ids
                    ):
                        continue

                    seen_resource_ids.add(
                        resource_id
                    )

                    inventory_key = (
                        INVENTORY_KEY_MAP.get(
                            str(
                                value.get(
                                    "resource_type"
                                )
                            )
                        )
                    )

                    if not inventory_key:
                        continue

                    inventory[
                        inventory_key
                    ].append(value)

        if successful_queries:
            self.cache.save(
                scope_key=scope_key,
                inventory=inventory,
            )

        elif errors:
            stale = self.cache.load(
                scope_key=scope_key,
                allow_stale=True,
            )

            if stale is not None:
                errors.append(
                    "Using stale Azure "
                    "inventory cache."
                )

                inventory = (
                    stale["inventory"]
                )

                successful_queries = 1

        resource_count = sum(
            len(values)
            for key, values
            in inventory.items()
            if key
            != "azure_subscriptions"
        )

        status = (
            "success"
            if not errors
            else (
                "partial"
                if successful_queries
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
                "provider": "azure",
                "auth_mode":
                    self.config
                    .azure_auth_mode,
                "tenant_id":
                    self.config
                    .azure_tenant_id,
                "subscription_ids":
                    subscription_ids,
                "locations":
                    self.config
                    .azure_locations,
                "resource_groups":
                    self.config
                    .azure_resource_groups,
                "query_count":
                    len(QUERY_GROUPS),
                "successful_query_count":
                    successful_queries,
                "resource_count":
                    resource_count,
                "cache_used": False,
            },
        )
