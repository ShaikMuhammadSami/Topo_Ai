from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ChangeWatchState:
    def __init__(
        self,
        path: Path,
    ) -> None:
        self.path = path

        self.values: dict[
            str,
            Any,
        ] = {}

        self.load()

    def load(
        self,
    ) -> None:
        if not self.path.exists():
            return

        try:
            value = json.loads(
                self.path.read_text(
                    encoding="utf-8"
                )
            )

        except Exception:
            return

        if isinstance(value, dict):
            self.values = value

    def get(
        self,
        key: str,
        default=None,
    ):
        return self.values.get(
            key,
            default,
        )

    def set(
        self,
        key: str,
        value: Any,
    ) -> None:
        self.values[key] = value

    def save(
        self,
    ) -> None:
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary = (
            self.path.with_suffix(
                ".tmp"
            )
        )

        temporary.write_text(
            json.dumps(
                self.values,
                indent=2,
                sort_keys=True,
                default=str,
            ),
            encoding="utf-8",
        )

        temporary.replace(
            self.path
        )