from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import ctypes
from ctypes import POINTER, byref, c_void_p, wintypes
from dataclasses import (
    asdict,
    dataclass,
    field,
)
from pathlib import Path
from typing import Any
from uuid import uuid4


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
    change_watch_interval_seconds: int = 30

    change_watch_overlap_seconds: int = 60

    change_watch_kubernetes: bool = True

    change_watch_aws: bool = False

    change_watch_azure: bool = False

    change_watch_gcp: bool = False

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
            change_watch_interval_seconds=int(
                value.get(
                    "change_watch_interval_seconds",
                    30,
                )
            ),
            change_watch_overlap_seconds=int(
                value.get(
                    "change_watch_overlap_seconds",
                    60,
                )
            ),
            change_watch_kubernetes=bool(
                value.get(
                    "change_watch_kubernetes",
                    True,
                )
            ),
            change_watch_aws=bool(
                value.get(
                    "change_watch_aws",
                    False,
                )
            ),
            change_watch_azure=bool(
                value.get(
                    "change_watch_azure",
                    False,
                )
            ),
            change_watch_gcp=bool(
                value.get(
                    "change_watch_gcp",
                    False,
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

        self.change_watch_interval_seconds = (
            _integer(
                os.getenv(
                    "TOPO_CHANGE_WATCH_INTERVAL"
                ),
                self.change_watch_interval_seconds,
            )
        )
        self.change_watch_overlap_seconds = (
            _integer(
                os.getenv(
                    "TOPO_CHANGE_WATCH_OVERLAP"
                ),
                self.change_watch_overlap_seconds,
            )
        )
        self.change_watch_kubernetes = _boolean(
            os.getenv(
                "TOPO_CHANGE_WATCH_KUBERNETES"
            ),
            self.change_watch_kubernetes,
        )
        self.change_watch_aws = _boolean(
            os.getenv("TOPO_CHANGE_WATCH_AWS"),
            self.change_watch_aws,
        )
        self.change_watch_azure = _boolean(
            os.getenv("TOPO_CHANGE_WATCH_AZURE"),
            self.change_watch_azure,
        )
        self.change_watch_gcp = _boolean(
            os.getenv("TOPO_CHANGE_WATCH_GCP"),
            self.change_watch_gcp,
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
    payload = json.dumps({"agent_token": token}, indent=2).encode("utf-8")
    _secure_atomic_write(path, payload)
    return path


def _reject_unsafe_path(path: Path) -> None:
    candidate = path.absolute()
    existing = candidate if candidate.exists() else candidate.parent
    while True:
        try:
            info = existing.lstat()
        except FileNotFoundError:
            pass
        else:
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise OSError("Credential path contains a link or reparse point.")
        if existing.parent == existing:
            break
        existing = existing.parent
    if path.exists():
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise OSError("Credential destination is not a regular file.")


def _windows_current_sid() -> str:
    result = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    match = re.search(r"S-1(?:-\d+)+", result.stdout)
    if result.returncode != 0 or match is None:
        raise OSError("Unable to resolve the Windows agent identity.")
    return match.group(0)


def _windows_security_descriptor(path: Path) -> str:
    advapi32 = ctypes.windll.advapi32
    kernel32 = ctypes.windll.kernel32
    descriptor = c_void_p()
    advapi32.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
        POINTER(c_void_p), POINTER(c_void_p), POINTER(c_void_p), POINTER(c_void_p),
        POINTER(c_void_p),
    ]
    result = advapi32.GetNamedSecurityInfoW(
        str(path), 1, 0x00000004, None, None, None, None, byref(descriptor)
    )
    if result != 0 or not descriptor.value:
        raise OSError("Unable to read the Windows credential ACL.")
    output = wintypes.LPWSTR()
    length = wintypes.ULONG()
    try:
        advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
            c_void_p, wintypes.DWORD, wintypes.DWORD,
            POINTER(wintypes.LPWSTR), POINTER(wintypes.ULONG),
        ]
        if not advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            descriptor, 1, 0x00000004, byref(output), byref(length)
        ):
            raise OSError("Unable to inspect the Windows credential ACL.")
        return output.value or ""
    finally:
        if output:
            kernel32.LocalFree(output)
        kernel32.LocalFree(descriptor)


def _validate_windows_acl(path: Path, current_sid: str) -> None:
    descriptor = _windows_security_descriptor(path)
    dacl = descriptor[descriptor.find("D:"):] if "D:" in descriptor else descriptor
    if not dacl.startswith("D:P"):
        raise OSError("Windows credential ACL inheritance is not protected.")
    allowed = {current_sid, "SY", "BA", "S-1-5-18", "S-1-5-32-544"}
    trustees = re.findall(r"\([^)]*;;;([^)]+)\)", dacl)
    if current_sid not in trustees or not trustees or any(item not in allowed for item in trustees):
        raise OSError("Windows credential ACL grants an unauthorized principal.")


_WINDOWS_SDDL_TRUSTEE_SIDS = {
    "WD": "S-1-1-0",       # Everyone
    "CO": "S-1-3-0",       # Creator Owner
    "OW": "S-1-3-4",       # Owner Rights
    "AN": "S-1-5-7",       # Anonymous
    "AU": "S-1-5-11",      # Authenticated Users
    "IU": "S-1-5-4",       # Interactive Users
    "SU": "S-1-5-6",       # Service
    "LS": "S-1-5-19",      # Local Service
    "NS": "S-1-5-20",      # Network Service
    "BU": "S-1-5-32-545",  # Builtin Users
    "BG": "S-1-5-32-546",  # Builtin Guests
    "PU": "S-1-5-32-547",  # Power Users
}


def _remove_unapproved_windows_aces(path: Path, current_sid: str) -> None:
    descriptor = _windows_security_descriptor(path)
    dacl = descriptor[descriptor.find("D:"):] if "D:" in descriptor else descriptor
    allowed = {current_sid, "SY", "BA", "S-1-5-18", "S-1-5-32-544"}
    trustees = set(re.findall(r"\([^)]*;;;([^)]+)\)", dacl))
    for trustee in sorted(trustees - allowed):
        sid = _WINDOWS_SDDL_TRUSTEE_SIDS.get(trustee, trustee)
        if not sid.startswith("S-1-"):
            continue
        principal = f"*{sid}"
        for removal in ("/remove:g", "/remove:d"):
            subprocess.run(
                ["icacls", str(path), removal, principal],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
            )


def _secure_windows_file(path: Path) -> None:
    sid = _windows_current_sid()
    result = subprocess.run(
        [
            "icacls", str(path), "/inheritance:r", "/grant:r",
            f"*{sid}:(F)", "*S-1-5-18:(F)", "*S-1-5-32-544:(F)",
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=15,
    )
    if result.returncode != 0:
        raise OSError("Unable to apply the Windows credential ACL.")
    # /grant:r replaces grants for the named principals but Windows can retain
    # unrelated explicit ACEs from a pre-created file. Remove those identities
    # before proving the final exact protected DACL.
    _remove_unapproved_windows_aces(path, sid)
    _validate_windows_acl(path, sid)


def _secure_atomic_write(path: Path, payload: bytes) -> None:
    _reject_unsafe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _reject_unsafe_path(path)
    if os.name == "posix":
        path.parent.chmod(path.parent.stat().st_mode & ~0o077)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, flags, 0o600)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise OSError("Credential temporary file is not regular.")
        if os.name == "posix" and before.st_mode & 0o077:
            raise OSError("Credential temporary file mode is not restrictive.")
        if os.name == "nt":
            os.close(descriptor)
            descriptor = None
            _secure_windows_file(temporary)
            descriptor = os.open(temporary, os.O_WRONLY | getattr(os, "O_BINARY", 0))
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        if os.name == "nt":
            _validate_windows_acl(temporary, _windows_current_sid())
        os.replace(temporary, path)
        if os.name == "posix":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        _validate_agent_credential_file(path)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _validate_agent_credential_file(path: Path) -> None:
    _reject_unsafe_path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise OSError("Credential file is not regular.")
    if os.name == "posix" and info.st_mode & 0o077:
        raise OSError("Credential file mode is not restrictive.")
    if os.name == "nt":
        _validate_windows_acl(path, _windows_current_sid())


def preflight_agent_token_storage() -> None:
    """Prove secure persistence capability without handling a real token."""
    path = credentials_path()
    probe = path.with_name(f".{path.name}.{uuid4().hex}.preflight")
    try:
        _secure_atomic_write(probe, b"{}")
    finally:
        probe.unlink(missing_ok=True)


def load_agent_token() -> str | None:
    environment_token = os.getenv(
        "TOPO_AGENT_TOKEN"
    )

    if environment_token:
        return environment_token

    path = credentials_path()

    if not path.exists():
        return None

    _validate_agent_credential_file(path)

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
