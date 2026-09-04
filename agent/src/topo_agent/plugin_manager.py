from __future__ import annotations

import logging
import time
from datetime import (
    datetime,
    timezone,
)
from typing import Any
from uuid import uuid4

from topo_agent import __version__
from topo_agent.plugin import (
    CollectorPlugin,
    PluginCollectionResult,
    PluginDiagnostic,
)
from topo_agent.security import safe_exception_message


LOGGER = logging.getLogger(
    "topo-agent.plugins"
)


def _utc_now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


class PluginManager:
    def __init__(
        self,
        *,
        plugins:
            list[CollectorPlugin],
        cluster_name: str,
        environment: str | None,
        namespace_scope: list[str],
    ) -> None:
        self.plugins = plugins

        self.cluster_name = (
            cluster_name
        )

        self.environment = environment

        self.namespace_scope = (
            namespace_scope
        )

        self.last_results: dict[
            str,
            dict[str, Any],
        ] = {}

    def plugin_names(
        self,
    ) -> list[str]:
        return [
            plugin.name
            for plugin in self.plugins
        ]

    def capabilities(
        self,
    ) -> list[str]:
        values: set[str] = set()

        for plugin in self.plugins:
            values.update(
                plugin.capabilities
            )

        return sorted(values)

    def diagnostics(
        self,
    ) -> list[PluginDiagnostic]:
        results: list[
            PluginDiagnostic
        ] = []

        for plugin in self.plugins:
            try:
                result = plugin.doctor()

            except Exception as exc:
                result = PluginDiagnostic(
                    name=plugin.name,
                    status="failed",
                    message=safe_exception_message(exc, "Plugin diagnostics failed"),
                    capabilities=list(
                        plugin.capabilities
                    ),
                )

            results.append(result)

        return results

    @staticmethod
    def _merge_inventory(
        destination: dict[
            str,
            list[dict[str, Any]],
        ],
        source: dict[
            str,
            list[dict[str, Any]],
        ],
    ) -> None:
        for key, values in source.items():
            destination.setdefault(
                key,
                [],
            )

            destination[key].extend(
                values
            )

    def collect(
        self,
    ) -> dict[str, Any]:
        inventory: dict[
            str,
            list[dict[str, Any]],
        ] = {}

        plugin_metadata: list[
            dict[str, Any]
        ] = []

        successful_plugins = 0
        failed_plugins = 0

        for plugin in self.plugins:
            started = (
                time.perf_counter()
            )

            try:
                result = plugin.collect()

                result.duration_ms = round(
                    (
                        time.perf_counter()
                        - started
                    )
                    * 1000,
                    2,
                )

            except Exception as exc:
                result = (
                    PluginCollectionResult(
                        plugin_name=(
                            plugin.name
                        ),
                        status="failed",
                        capabilities=list(
                            plugin
                            .capabilities
                        ),
                        errors=[safe_exception_message(exc, "Plugin collection failed")],
                        duration_ms=round(
                            (
                                time
                                .perf_counter()
                                - started
                            )
                            * 1000,
                            2,
                        ),
                    )
                )

                LOGGER.exception(
                    "Plugin %s failed.",
                    plugin.name,
                )

            self.last_results[
                plugin.name
            ] = result.to_metadata()

            plugin_metadata.append(
                result.to_metadata()
            )

            if result.status in {
                "success",
                "partial",
            }:
                successful_plugins += 1

                self._merge_inventory(
                    inventory,
                    result.inventory,
                )

            else:
                failed_plugins += 1

        overall_status = (
            "success"
            if failed_plugins == 0
            else (
                "partial"
                if successful_plugins > 0
                else "failed"
            )
        )

        return {
            "submission_id": (
                "agent-submission:"
                + uuid4().hex
            ),
            "collected_at":
                _utc_now_iso(),
            "cluster_name":
                self.cluster_name,
            "environment":
                self.environment,
            "namespace_scope":
                self.namespace_scope,
            "collector_version":
                __version__,
            "inventory": inventory,
            "metadata": {
                "collection_status":
                    overall_status,
                "plugin_count":
                    len(self.plugins),
                "successful_plugin_count":
                    successful_plugins,
                "failed_plugin_count":
                    failed_plugins,
                "plugins":
                    plugin_metadata,
            },
        }

    def status_snapshot(
        self,
    ) -> list[dict[str, Any]]:
        values: list[
            dict[str, Any]
        ] = []

        for plugin in self.plugins:
            status = self.last_results.get(
                plugin.name
            )

            if status:
                values.append(status)
            else:
                values.append(
                    {
                        "name":
                            plugin.name,
                        "status":
                            "not_collected",
                        "capabilities":
                            list(
                                plugin
                                .capabilities
                            ),
                        "errors": [],
                        "inventory_counts":
                            {},
                    }
                )

        return values

    def close(
        self,
    ) -> None:
        for plugin in self.plugins:
            try:
                plugin.close()

            except Exception:
                LOGGER.exception(
                    "Unable to close "
                    "plugin %s.",
                    plugin.name,
                )
