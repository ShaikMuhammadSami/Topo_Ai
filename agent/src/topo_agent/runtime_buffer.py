from __future__ import annotations

import json
from pathlib import Path


class RuntimeBatchBuffer:
    def __init__(
        self,
        directory: Path,
        *,
        maximum_batches: int,
    ) -> None:
        self.directory = directory

        self.maximum_batches = max(
            maximum_batches,
            1,
        )

        self.directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    def pending(
        self,
    ) -> list[Path]:
        return sorted(
            self.directory.glob(
                "*.json"
            ),
            key=lambda item:
                item.name,
        )

    def size(
        self,
    ) -> int:
        return len(self.pending())

    def enqueue(
        self,
        batch: dict,
    ) -> Path:
        batch_id = str(
            batch["batch_id"]
        ).replace(
            ":",
            "-",
        )

        destination = (
            self.directory
            / f"{batch_id}.json"
        )

        temporary = destination.with_suffix(
            ".tmp"
        )

        temporary.write_text(
            json.dumps(
                batch,
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

    def _trim(
        self,
    ) -> None:
        values = self.pending()

        overflow = (
            len(values)
            - self.maximum_batches
        )

        for path in values[
            :max(overflow, 0)
        ]:
            path.unlink(
                missing_ok=True
            )