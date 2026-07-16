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

from topo_cli.errors import (
    ConfigurationError,
    FileOperationFailure,
)


DEFAULT_PROFILE_NAME = "local"
DEFAULT_API_URL = "http://127.0.0.1:8000"

DEFAULT_CAPTURE_PATH = (
    "/api/v1/snapshots/capture"
)


@dataclass
class Profile:
    api_url: str = DEFAULT_API_URL

    token_env: str = "TOPO_API_TOKEN"

    verify_tls: bool = True

    timeout: float = 30.0

    snapshot_capture_path: str = (
        DEFAULT_CAPTURE_PATH
    )

    @classmethod
    def from_dict(
        cls,
        value: dict[str, Any],
    ) -> "Profile":
        return cls(
            api_url=str(
                value.get(
                    "api_url",
                    DEFAULT_API_URL,
                )
            ).rstrip("/"),
            token_env=str(
                value.get(
                    "token_env",
                    "TOPO_API_TOKEN",
                )
            ),
            verify_tls=bool(
                value.get(
                    "verify_tls",
                    True,
                )
            ),
            timeout=float(
                value.get(
                    "timeout",
                    30.0,
                )
            ),
            snapshot_capture_path=str(
                value.get(
                    "snapshot_capture_path",
                    DEFAULT_CAPTURE_PATH,
                )
            ),
        )


@dataclass
class TopoConfig:
    active_profile: str = (
        DEFAULT_PROFILE_NAME
    )

    profiles: dict[str, Profile] = field(
        default_factory=lambda: {
            DEFAULT_PROFILE_NAME: Profile()
        }
    )

    @classmethod
    def from_dict(
        cls,
        value: dict[str, Any],
    ) -> "TopoConfig":
        profile_values = value.get(
            "profiles",
            {},
        )

        profiles = {
            str(name): Profile.from_dict(
                profile_data
            )
            for name, profile_data
            in profile_values.items()
            if isinstance(
                profile_data,
                dict,
            )
        }

        if not profiles:
            profiles = {
                DEFAULT_PROFILE_NAME:
                    Profile()
            }

        active_profile = str(
            value.get(
                "active_profile",
                DEFAULT_PROFILE_NAME,
            )
        )

        if active_profile not in profiles:
            active_profile = next(
                iter(profiles)
            )

        return cls(
            active_profile=active_profile,
            profiles=profiles,
        )


def config_file_path() -> Path:
    override = os.getenv(
        "TOPO_CONFIG_FILE"
    )

    if override:
        return Path(
            override
        ).expanduser()

    if os.name == "nt":
        base = Path(
            os.getenv(
                "APPDATA",
                Path.home(),
            )
        )

        return (
            base
            / "TopoAI"
            / "config.json"
        )

    xdg_config_home = os.getenv(
        "XDG_CONFIG_HOME"
    )

    if xdg_config_home:
        return (
            Path(xdg_config_home)
            / "topo-ai"
            / "config.json"
        )

    return (
        Path.home()
        / ".config"
        / "topo-ai"
        / "config.json"
    )


def load_config() -> TopoConfig:
    path = config_file_path()

    if not path.exists():
        return TopoConfig()

    try:
        content = path.read_text(
            encoding="utf-8"
        )

        value = json.loads(content)

    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise ConfigurationError(
            "Unable to load Topo CLI "
            f"configuration from {path}: "
            f"{exc}"
        ) from exc

    if not isinstance(value, dict):
        raise ConfigurationError(
            "Topo CLI configuration must "
            "contain a JSON object."
        )

    return TopoConfig.from_dict(value)


def save_config(
    config: TopoConfig,
) -> Path:
    path = config_file_path()

    try:
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
                    "active_profile":
                        config.active_profile,
                    "profiles": {
                        name: asdict(profile)
                        for name, profile
                        in config.profiles.items()
                    },
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        temporary.replace(path)

    except OSError as exc:
        raise FileOperationFailure(
            "Unable to save Topo CLI "
            f"configuration to {path}: "
            f"{exc}"
        ) from exc

    return path


def resolve_profile(
    config: TopoConfig,
    requested_name: str | None,
) -> tuple[str, Profile]:
    name = (
        requested_name
        or os.getenv("TOPO_PROFILE")
        or config.active_profile
    )

    profile = config.profiles.get(name)

    if profile is None:
        available = ", ".join(
            sorted(config.profiles)
        )

        raise ConfigurationError(
            f"Profile '{name}' does not exist. "
            f"Available profiles: {available}"
        )

    return name, Profile(
        api_url=profile.api_url,
        token_env=profile.token_env,
        verify_tls=profile.verify_tls,
        timeout=profile.timeout,
        snapshot_capture_path=(
            profile.snapshot_capture_path
        ),
    )


def profile_token(
    profile: Profile,
) -> str | None:
    return os.getenv(
        profile.token_env
    )