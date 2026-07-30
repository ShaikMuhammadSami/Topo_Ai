from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


class AwsInventoryCache:
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
        account_id: str,
        region: str,
    ) -> Path:
        identity = (
            f"{account_id}|{region}"
        )

        digest = hashlib.sha256(
            identity.encode("utf-8")
        ).hexdigest()[:24]

        return (
            self.directory
            / f"aws-{digest}.json"
        )

    def load(
        self,
        *,
        account_id: str,
        region: str,
        allow_stale: bool = False,
    ) -> dict[str, Any] | None:
        path = self._path(
            account_id,
            region,
        )

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

        age = time.time() - written_at

        if (
            not allow_stale
            and age > self.ttl_seconds
        ):
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
            "age_seconds": age,
            "stale":
                age > self.ttl_seconds,
        }

    def save(
        self,
        *,
        account_id: str,
        region: str,
        inventory:
            dict[str, list[dict]],
    ) -> Path:
        path = self._path(
            account_id,
            region,
        )

        temporary = path.with_suffix(
            ".tmp"
        )

        temporary.write_text(
            json.dumps(
                {
                    "written_at_epoch":
                        time.time(),
                    "account_id":
                        account_id,
                    "region": region,
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