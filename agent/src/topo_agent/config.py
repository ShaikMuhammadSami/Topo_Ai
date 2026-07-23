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