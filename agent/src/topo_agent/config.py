from __future__ import annotations

import json
import os
from dataclasses import (
    asdict,
    dataclass,
    field,
)
from pathlib import Path
from typing import Any


def _boolean(
    value: str | None,
    default: bool,
) -> bool:
    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

def _comma_values(
    value: str | None,
) -> list[str]:
    if not value:
        return []

    return [
        item.strip()
        for item in value.split(",")
        if item.strip()
    ]

def _integer(
    value: str | None,
    default: int,
) -> int:
    if value is None:
        return default

    try:
        return int(value)

    except ValueError:
        return default


def _namespaces(
    value: str | None,
) -> list[str]:
    if not value:
        return []

    return [
        item.strip()
        for item in value.split(",")
        if item.strip()
    ]

def _plugins(
    value: str | None,
) -> list[str]:
    if not value:
        return []

    return [
        item.strip().lower()
        for item in value.split(",")
        if item.strip()
    ]

def agent_home() -> Path:
    override = os.getenv(
        "TOPO_AGENT_HOME"
    )

    if override:
        return Path(
            override
        ).expanduser()

    if os.name == "nt":
        return (
            Path(
                os.getenv(
                    "LOCALAPPDATA",
                    Path.home(),
                )
            )
            / "TopoAI"
            / "Agent"
        )

    return (
        Path.home()
        / ".local"
        / "share"
        / "topo-agent"
    )


def config_path() -> Path:
    override = os.getenv(
        "TOPO_AGENT_CONFIG_FILE"
    )

    if override:
        return Path(
            override
        ).expanduser()

    return (
        agent_home()
        / "config.json"
    )


def credentials_path() -> Path:
    override = os.getenv(
        "TOPO_AGENT_CREDENTIALS_FILE"
    )

    if override:
        return Path(
            override
        ).expanduser()

    return (
        agent_home()
        / "credentials.json"
    )


def buffer_directory() -> Path:
    override = os.getenv(
        "TOPO_AGENT_BUFFER_DIR"
    )

    if override:
        return Path(
            override
        ).expanduser()

    return (
        agent_home()
        / "buffer"
    )


@dataclass
class AgentConfig:
    backend_url: str = (
        "http://127.0.0.1:8000"
    )

    agent_id: str | None = None

    name: str = "topo-agent"

    cluster_name: str = (
        "docker-desktop"
    )

    environment: str | None = None

    namespaces: list[str] = field(
        default_factory=list
    )

    enabled_plugins: list[str] = field(
     default_factory=lambda: [
         "kubernetes",
        ]
    )

    docker_base_url: str | None = None

    collect_process_username: bool = False

    network_include_loopback: bool = False

    network_include_listening: bool = True

    network_include_established: bool = True

    kube_context: str | None = None

    verify_tls: bool = True

    timeout_seconds: int = 60

    heartbeat_interval_seconds: int = 30

    collection_interval_seconds: int = 300

    max_retries: int = 3

    retry_backoff_seconds: float = 1.0

    max_buffer_items: int = 100
    aws_profile: str | None = None

    aws_role_arn: str | None = None

    aws_external_id: str | None = None

    aws_role_session_name: str = (
     "topo-agent-discovery"
    )

    aws_regions: list[str] = field(
     default_factory=list
    )

    aws_discover_regions: bool = False

    aws_cache_ttl_seconds: int = 300

    aws_api_max_attempts: int = 5

    azure_auth_mode: str = "default"

    azure_tenant_id: str | None = None

    azure_client_id: str | None = None

    azure_federated_token_file: str | None = None

    azure_subscription_ids: list[str] = field(
     default_factory=list
    )

    azure_locations: list[str] = field(
     default_factory=list
    )

    azure_resource_groups: list[str] = field(
     default_factory=list
    )

    azure_cache_ttl_seconds: int = 300

    azure_query_page_size: int = 1000

    azure_api_max_attempts: int = 5
    gcp_project_ids: list[str] = field(
     default_factory=list
    )

    gcp_organization_ids: list[str] = field(
     default_factory=list
    )

    gcp_folder_ids: list[str] = field(
     default_factory=list
    )

    gcp_locations: list[str] = field(
     default_factory=list
    )

    gcp_discover_projects: bool = False

    gcp_include_hierarchy: bool = True

    gcp_impersonate_service_account: (
     str | None
    ) = None

    gcp_quota_project: str | None = None

    gcp_cache_ttl_seconds: int = 300

    gcp_asset_page_size: int = 500

    gcp_api_max_attempts: int = 5

    @classmethod
    def from_dict(
        cls,
        value: dict[str, Any],
    ) -> "AgentConfig":
        return cls(
            backend_url=str(
                value.get(
                    "backend_url",
                    "http://127.0.0.1:8000",
                )
            ).rstrip("/"),
            agent_id=value.get(
                "agent_id"
            ),
            name=str(
                value.get(
                    "name",
                    "topo-agent",
                )
            ),
            cluster_name=str(
                value.get(
                    "cluster_name",
                    "docker-desktop",
                )
            ),
            environment=value.get(
                "environment"
            ),
            namespaces=[
                str(item)
                for item in value.get(
                    "namespaces",
                    [],
                )
            ],
            enabled_plugins=[
             str(item).lower()
             for item in value.get(
                 "enabled_plugins",
                 ["kubernetes"],
                )
            ],
            docker_base_url=value.get(
              "docker_base_url"
            ),
            collect_process_username=bool(
             value.get(
                 "collect_process_username",
                 False,
                )
            ),
            network_include_loopback=bool(
             value.get(
                 "network_include_loopback",
                 False,
                )
            ),
            network_include_listening=bool(
             value.get(
                  "network_include_listening",
                   True,
                )
            ),
            network_include_established=bool(
             value.get(
                 "network_include_established",
                 True,
                )
            ),
            kube_context=value.get(
                "kube_context"
            ),
            verify_tls=bool(
                value.get(
                    "verify_tls",
                    True,
                )
            ),
            timeout_seconds=int(
                value.get(
                    "timeout_seconds",
                    60,
                )
            ),
            heartbeat_interval_seconds=int(
                value.get(
                    "heartbeat_interval_seconds",
                    30,
                )
            ),
            collection_interval_seconds=int(
                value.get(
                    "collection_interval_seconds",
                    300,
                )
            ),
            max_retries=int(
                value.get(
                    "max_retries",
                    3,
                )
            ),
            retry_backoff_seconds=float(
                value.get(
                    "retry_backoff_seconds",
                    1.0,
                )
            ),
            max_buffer_items=int(
                value.get(
                    "max_buffer_items",
                    100,
                )
            ),
            aws_profile=value.get(
             "aws_profile"
            ),
            aws_role_arn=value.get(
             "aws_role_arn"
            ),
            aws_external_id=value.get(
             "aws_external_id"
            ),
            aws_role_session_name=str(
             value.get(
                 "aws_role_session_name",
                 "topo-agent-discovery",
                )
            ),
            aws_regions=[
             str(item)
             for item in value.get(
                 "aws_regions",
                  [],
                )
            ],
            aws_discover_regions=bool(
                value.get(
                 "aws_discover_regions",
                 False,
                )
            ),
            aws_cache_ttl_seconds=int(
             value.get(
                 "aws_cache_ttl_seconds",
                  300,
                )
            ),
            aws_api_max_attempts=int(
               value.get(
                 "aws_api_max_attempts",
                 5,
                )
            ),
            azure_auth_mode=str(
             value.get(
                 "azure_auth_mode",
                 "default",
                )
            ).lower(),
            azure_tenant_id=value.get(
             "azure_tenant_id"
            ),
            azure_client_id=value.get(
             "azure_client_id"
            ),
            azure_federated_token_file=value.get(
             "azure_federated_token_file"
            ),
            azure_subscription_ids=[
             str(item)
             for item in value.get(
                 "azure_subscription_ids",
                 [],
                )
            ],
            azure_locations=[
             str(item).lower()
             for item in value.get(
                 "azure_locations",
                 [],
                )
            ],
            azure_resource_groups=[
             str(item).lower()
             for item in value.get(
                 "azure_resource_groups",
                 [],
                )
            ],
            azure_cache_ttl_seconds=int(
             value.get(
                 "azure_cache_ttl_seconds",
                 300,
                )
            ),
            azure_query_page_size=int(
             value.get(
                 "azure_query_page_size",
                 1000,
                )
            ),
            azure_api_max_attempts=int(
             value.get(
                 "azure_api_max_attempts",
                 5,
                )
            ),
            gcp_project_ids=[
             str(item)
             for item in value.get(
                 "gcp_project_ids",
                 [],
                )
            ],
            gcp_organization_ids=[
             str(item)
             for item in value.get(
                 "gcp_organization_ids",
                 [],
                )
            ],
            gcp_folder_ids=[
             str(item)
             for item in value.get(
                 "gcp_folder_ids",
                 [],
                )
            ],
            gcp_locations=[
             str(item).lower()
             for item in value.get(
                 "gcp_locations",
                 [],
                )
            ],
            gcp_discover_projects=bool(
                value.get(
                    "gcp_discover_projects",
                    False,
                )
            ),

            gcp_include_hierarchy=bool(
             value.get(
                 "gcp_include_hierarchy",
                 True,
                )
            ),
            gcp_impersonate_service_account=(
             value.get(
                  "gcp_impersonate_service_account"
                )
            ),
            gcp_quota_project=value.get(
             "gcp_quota_project"
            ),
            gcp_cache_ttl_seconds=int(
             value.get(
                 "gcp_cache_ttl_seconds",
                 300,
                )
            ),
            gcp_asset_page_size=int(
             value.get(
                 "gcp_asset_page_size",
                 500,
                )
            ),
            gcp_api_max_attempts=int(
             value.get(
                   "gcp_api_max_attempts",
                    5,
                )
            ),
        )

    def apply_environment(
        self,
    ) -> "AgentConfig":
        self.backend_url = os.getenv(
            "TOPO_BACKEND_URL",
            self.backend_url,
        ).rstrip("/")

        self.agent_id = os.getenv(
            "TOPO_AGENT_ID",
            self.agent_id,
        )

        self.name = os.getenv(
            "TOPO_AGENT_NAME",
            self.name,
        )

        self.cluster_name = os.getenv(
            "TOPO_CLUSTER_NAME",
            self.cluster_name,
        )

        self.environment = os.getenv(
            "TOPO_ENVIRONMENT",
            self.environment,
        )

        namespace_value = os.getenv(
            "TOPO_NAMESPACES"
        )

        if namespace_value is not None:
            self.namespaces = _namespaces(
                namespace_value
            )

        self.kube_context = os.getenv(
            "TOPO_KUBE_CONTEXT",
            self.kube_context,
        )

        self.verify_tls = _boolean(
            os.getenv(
                "TOPO_VERIFY_TLS"
            ),
            self.verify_tls,
        )

        self.timeout_seconds = _integer(
            os.getenv(
                "TOPO_AGENT_TIMEOUT"
            ),
            self.timeout_seconds,
        )

        self.heartbeat_interval_seconds = (
            _integer(
                os.getenv(
                    "TOPO_HEARTBEAT_INTERVAL"
                ),
                self
                .heartbeat_interval_seconds,
            )
        )

        self.collection_interval_seconds = (
            _integer(
                os.getenv(
                    "TOPO_COLLECTION_INTERVAL"
                ),
                self
                .collection_interval_seconds,
            )
        )
        plugin_value = os.getenv(
          "TOPO_ENABLED_PLUGINS"
        )

        if plugin_value is not None:
           self.enabled_plugins = _plugins(
              plugin_value
            )

        self.docker_base_url = os.getenv(
           "TOPO_DOCKER_BASE_URL",
            self.docker_base_url,
        )

        self.collect_process_username = (
          _boolean(
             os.getenv(
                 "TOPO_COLLECT_PROCESS_USERNAME"
                ),
             self.collect_process_username,
            )
        )

        self.network_include_loopback = (
          _boolean(
              os.getenv(
                 "TOPO_NETWORK_INCLUDE_LOOPBACK"
                ),
              self.network_include_loopback,
           )
        ) 

        self.network_include_listening = (
          _boolean(
              os.getenv(
                 "TOPO_NETWORK_INCLUDE_LISTENING"
                ),
              self.network_include_listening,
            )
        )

        self.network_include_established = (
         _boolean(
             os.getenv(
                 "TOPO_NETWORK_INCLUDE_ESTABLISHED"
                ),
             self.network_include_established,
            )
        )
        self.aws_profile = os.getenv(
         "TOPO_AWS_PROFILE",
         self.aws_profile,
        )

        self.aws_role_arn = os.getenv(
         "TOPO_AWS_ROLE_ARN",
         self.aws_role_arn,
        )

        self.aws_external_id = os.getenv(
         "TOPO_AWS_EXTERNAL_ID",
         self.aws_external_id,
        )

        self.aws_role_session_name = os.getenv(
         "TOPO_AWS_ROLE_SESSION_NAME",
         self.aws_role_session_name,
        )

        regions_value = os.getenv(
         "TOPO_AWS_REGIONS"
        )

        if regions_value is not None:
         self.aws_regions = _comma_values(
             regions_value
            )

        self.aws_discover_regions = _boolean(
         os.getenv(
             "TOPO_AWS_DISCOVER_REGIONS"
            ),
         self.aws_discover_regions,
        )

        self.aws_cache_ttl_seconds = _integer(
         os.getenv(
             "TOPO_AWS_CACHE_TTL"
            ),
         self.aws_cache_ttl_seconds,
        )

        self.aws_api_max_attempts = _integer(
          os.getenv(
             "TOPO_AWS_API_MAX_ATTEMPTS"
            ),
          self.aws_api_max_attempts,
        )

        self.azure_auth_mode = os.getenv(
         "TOPO_AZURE_AUTH_MODE",
         self.azure_auth_mode,
        ).strip().lower()

        self.azure_tenant_id = os.getenv(
         "TOPO_AZURE_TENANT_ID",
         self.azure_tenant_id,
        )

        self.azure_client_id = os.getenv(
          "TOPO_AZURE_CLIENT_ID",
          self.azure_client_id,
        )

        self.azure_federated_token_file = (
         os.getenv(
             "TOPO_AZURE_FEDERATED_TOKEN_FILE",
             self.azure_federated_token_file,
            )
        )

        subscription_value = os.getenv(
         "TOPO_AZURE_SUBSCRIPTIONS"
        )

        if subscription_value is not None:
         self.azure_subscription_ids = (
             _comma_values(
                 subscription_value
                )
            )

        location_value = os.getenv(
         "TOPO_AZURE_LOCATIONS"
        )

        if location_value is not None:
         self.azure_locations = [
             item.lower()
             for item in _comma_values(
                 location_value
                )
            ]

        resource_group_value = os.getenv(
         "TOPO_AZURE_RESOURCE_GROUPS"
        )

        if resource_group_value is not None:
         self.azure_resource_groups = [
              item.lower()
              for item in _comma_values(
                  resource_group_value
                )
            ]

        self.azure_cache_ttl_seconds = (
         _integer(
             os.getenv(
                 "TOPO_AZURE_CACHE_TTL"
                ),
             self.azure_cache_ttl_seconds,
            )
        )

        self.azure_query_page_size = (
         _integer(
             os.getenv(
                 "TOPO_AZURE_QUERY_PAGE_SIZE"
                ),
             self.azure_query_page_size,
            )
        )

        self.azure_api_max_attempts = (
         _integer(
             os.getenv(
                 "TOPO_AZURE_API_MAX_ATTEMPTS"
                ),
             self.azure_api_max_attempts,
            )
        )
        
        project_value = os.getenv(
          "TOPO_GCP_PROJECTS"
        )

        if project_value is not None:
         self.gcp_project_ids = (
             _comma_values(project_value)
            )

        organization_value = os.getenv(
         "TOPO_GCP_ORGANIZATIONS"
        )

        if organization_value is not None:
         self.gcp_organization_ids = (
              _comma_values(
                 organization_value
                )
            )

        folder_value = os.getenv(
           "TOPO_GCP_FOLDERS"
        )

        if folder_value is not None:
         self.gcp_folder_ids = (
             _comma_values(folder_value)
            )

        location_value = os.getenv(
         "TOPO_GCP_LOCATIONS"
        )

        if location_value is not None:
         self.gcp_locations = [
             item.lower()
             for item in _comma_values(
                 location_value
                )
            ]

        self.gcp_discover_projects = (
         _boolean(
             os.getenv(
                 "TOPO_GCP_DISCOVER_PROJECTS"
                ),
             self.gcp_discover_projects,
            )
        )

        self.gcp_include_hierarchy = (
         _boolean(
              os.getenv(
                 "TOPO_GCP_INCLUDE_HIERARCHY"
                ),
              self.gcp_include_hierarchy,
            )
        )

        self.gcp_impersonate_service_account = (
          os.getenv(
             (
                 "TOPO_GCP_IMPERSONATE_"
                 "SERVICE_ACCOUNT"
                ),
             self
             .gcp_impersonate_service_account,
            )
        )

        self.gcp_quota_project = os.getenv(
         "TOPO_GCP_QUOTA_PROJECT",
         self.gcp_quota_project,
        )

        self.gcp_cache_ttl_seconds = (
         _integer(
             os.getenv(
                 "TOPO_GCP_CACHE_TTL"
                ),
             self.gcp_cache_ttl_seconds,
            )
        )

        self.gcp_asset_page_size = (
         _integer(
             os.getenv(
                 "TOPO_GCP_ASSET_PAGE_SIZE"
                ),
             self.gcp_asset_page_size,
            )
        )

        self.gcp_api_max_attempts = (
         _integer(
             os.getenv(
                 "TOPO_GCP_API_MAX_ATTEMPTS"
                ),
             self.gcp_api_max_attempts,
            )
        )

        return self


def load_config() -> AgentConfig:
    path = config_path()

    if not path.exists():
        return (
            AgentConfig()
            .apply_environment()
        )

    value = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(value, dict):
        raise ValueError(
            "Agent configuration must "
            "contain a JSON object."
        )

    return (
        AgentConfig.from_dict(value)
        .apply_environment()
    )


def save_config(
    config: AgentConfig,
) -> Path:
    path = config_path()

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        ".tmp"
    )

    temporary.write_text(
        json.dumps(
            asdict(config),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    temporary.replace(path)

    return path


def store_agent_token(
    token: str,
) -> Path:
    path = credentials_path()

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        ".tmp"
    )

    temporary.write_text(
        json.dumps(
            {
                "agent_token": token,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary.replace(path)

    if os.name != "nt":
        path.chmod(0o600)

    return path


def load_agent_token() -> str | None:
    environment_token = os.getenv(
        "TOPO_AGENT_TOKEN"
    )

    if environment_token:
        return environment_token

    path = credentials_path()

    if not path.exists():
        return None

    value = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    token = value.get(
        "agent_token"
    )

    return (
        str(token)
        if token
        else None
    )