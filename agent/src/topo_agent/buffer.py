from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4


class SnapshotBuffer:
    def __init__(
        self,
        directory: Path,
        *,
        max_items: int,
    ) -> None:
        self.directory = directory
        self.max_items = max(
            max_items,
            1,
        )

        self.directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    def size(self) -> int:
        return len(self.pending())

    def pending(
        self,
    ) -> list[Path]:
        return sorted(
            self.directory.glob(
                "*.json"
            ),
            key=lambda path:
                path.name,
        )

    def enqueue(
        self,
        payload: dict,
    ) -> Path:
        filename = (
            payload.get(
                "collected_at",
                "unknown",
            )
            .replace(":", "")
            .replace("+", "")
            + "-"
            + uuid4().hex
            + ".json"
        )

        destination = (
            self.directory
            / filename
        )

        temporary = (
            destination
            .with_suffix(".tmp")
        )

        temporary.write_text(
            json.dumps(
                payload,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        temporary.replace(
            destination
        )

        self._trim()

        return destination

    def load(
        self,
        path: Path,
    ) -> dict:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    def remove(
        self,
        path: Path,
    ) -> None:
        path.unlink(
            missing_ok=True
        )

    def _trim(self) -> None:
        items = self.pending()

        overflow = (
            len(items)
            - self.max_items
        )

        for path in items[
            :max(overflow, 0)
        ]:
            path.unlink(
                missing_ok=True
            )