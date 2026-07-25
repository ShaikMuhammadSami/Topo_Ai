from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class TetragonJsonTailer:
    def __init__(
        self,
        *,
        source_file: Path,
        checkpoint_file: Path,
    ) -> None:
        self.source_file = source_file
        self.checkpoint_file = (
            checkpoint_file
        )

        self.offset = 0
        self.inode: int | None = None

        self._load_checkpoint()

    def _load_checkpoint(
        self,
    ) -> None:
        if not self.checkpoint_file.exists():
            return

        try:
            value = json.loads(
                self.checkpoint_file.read_text(
                    encoding="utf-8"
                )
            )

        except (
            OSError,
            json.JSONDecodeError,
        ):
            return

        if not isinstance(value, dict):
            return

        if (
            value.get("source_file")
            != str(self.source_file)
        ):
            return

        self.offset = int(
            value.get("offset", 0)
        )

        inode_value = value.get(
            "inode"
        )

        self.inode = (
            int(inode_value)
            if inode_value is not None
            else None
        )

    def _save_checkpoint(
        self,
    ) -> None:
        self.checkpoint_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary = (
            self.checkpoint_file
            .with_suffix(".tmp")
        )

        temporary.write_text(
            json.dumps(
                {
                    "source_file":
                        str(
                            self.source_file
                        ),
                    "inode":
                        self.inode,
                    "offset":
                        self.offset,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        temporary.replace(
            self.checkpoint_file
        )

    def read_available(
        self,
        *,
        maximum_lines: int = 10000,
    ) -> tuple[
        list[dict[str, Any]],
        int,
    ]:
        if not self.source_file.exists():
            return [], 0

        stat = self.source_file.stat()

        current_inode = getattr(
            stat,
            "st_ino",
            None,
        )

        if (
            self.inode is not None
            and current_inode
            != self.inode
        ):
            self.offset = 0

        if stat.st_size < self.offset:
            self.offset = 0

        self.inode = current_inode

        events: list[
            dict[str, Any]
        ] = []

        malformed = 0

        with self.source_file.open(
            "r",
            encoding="utf-8",
            errors="replace",
        ) as stream:
            stream.seek(self.offset)

            while len(events) < maximum_lines:
                line_start = stream.tell()
                line = stream.readline()

                if not line:
                    break

                if not line.endswith("\n"):
                    stream.seek(line_start)
                    break

                stripped = line.strip()

                if not stripped:
                    continue

                try:
                    value = json.loads(
                        stripped
                    )

                except json.JSONDecodeError:
                    malformed += 1
                    continue

                if not isinstance(value, dict):
                    malformed += 1
                    continue

                events.append(value)

            self.offset = stream.tell()

        self._save_checkpoint()

        return events, malformed