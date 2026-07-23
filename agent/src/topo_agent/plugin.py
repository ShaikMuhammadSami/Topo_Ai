from __future__ import annotations

from dataclasses import (
    asdict,
    dataclass,
    field,
)
from typing import Any, Protocol


Inventory = dict[
    str,
    list[dict[str, Any]],
]


@dataclass
class PluginDiagnostic:
    name: str
    status: str

    message: str | None = None

    capabilities: list[str] = field(
        default_factory=list
    )

    details: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PluginCollectionResult:
    plugin_name: str
    status: str

    inventory: Inventory = field(
        default_factory=dict
    )

    capabilities: list[str] = field(
        default_factory=list
    )

    errors: list[str] = field(
        default_factory=list
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    duration_ms: float = 0.0

    def to_metadata(
        self,
    ) -> dict[str, Any]:
        return {
            "name": self.plugin_name,
            "status": self.status,
            "duration_ms":
                self.duration_ms,
            "capabilities":
                self.capabilities,
            "errors": self.errors,
            "inventory_counts": {
                key: len(values)
                for key, values
                in self.inventory.items()
            },
            **self.metadata,
        }


class CollectorPlugin(Protocol):
    name: str
    version: str
    capabilities: tuple[str, ...]

    def doctor(
        self,
    ) -> PluginDiagnostic:
        ...

    def collect(
        self,
    ) -> PluginCollectionResult:
        ...

    def close(
        self,
    ) -> None:
        ...