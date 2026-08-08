from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


class AzureInventoryCache:
    def __init__(
        self,
        directory: Path,
        *,
        ttl_seconds: int,
    ) -> None:
        self.directory = directory
        self.ttl_seconds = max(
            ttl_seconds,
            0,
        )

        self.directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    def _path(
        self,
        scope_key: str,
    ) -> Path:
        digest = hashlib.sha256(
            scope_key.encode("utf-8")
        ).hexdigest()[:24]

        return (
            self.directory
            / f"azure-{digest}.json"
        )

    def load(
        self,
        *,
        scope_key: str,
        allow_stale: bool = False,
    ) -> dict[str, Any] | None:
        path = self._path(scope_key)

        if not path.exists():
            return None

        try:
            value = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

        except (
            OSError,
            json.JSONDecodeError,
        ):
            return None

        if not isinstance(value, dict):
            return None

        written_at = float(
            value.get(
                "written_at_epoch",
                0,
            )
        )

        age_seconds = (
            time.time() - written_at
        )

        stale = (
            age_seconds
            > self.ttl_seconds
        )

        if stale and not allow_stale:
            return None

        inventory = value.get(
            "inventory"
        )

        if not isinstance(
            inventory,
            dict,
        ):
            return None

        return {
            "inventory": inventory,
            "age_seconds":
                age_seconds,
            "stale": stale,
        }

    def save(
        self,
        *,
        scope_key: str,
        inventory:
            dict[str, list[dict]],
    ) -> Path:
        path = self._path(scope_key)

        temporary = path.with_suffix(
            ".tmp"
        )

        temporary.write_text(
            json.dumps(
                {
                    "written_at_epoch":
                        time.time(),
                    "scope_key":
                        scope_key,
                    "inventory":
                        inventory,
                },
                sort_keys=True,
                default=str,
            ),
            encoding="utf-8",
        )

        temporary.replace(path)

        return path