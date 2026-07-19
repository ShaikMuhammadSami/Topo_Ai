from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypeVar

import typer
import json
from collections.abc import Callable
from typing import Any
from topo_cli.client import TopoClient
from topo_cli.config import (
    Profile,
    TopoConfig,
)
from topo_cli.errors import (
    ConfigurationError,
    TopoCliError,
    abort,
)
from topo_cli.output import OutputFormat


ResultType = TypeVar("ResultType")


@dataclass
class RuntimeContext:
    config: TopoConfig

    profile_name: str
    profile: Profile

    output_format: OutputFormat

    client: TopoClient
    quiet: bool = False
    no_color: bool = False


def get_runtime(
    context: typer.Context,
) -> RuntimeContext:
    runtime = context.obj

    if not isinstance(
        runtime,
        RuntimeContext,
    ):
        raise ConfigurationError(
            "Topo CLI runtime context "
            "was not initialized."
        )

    return runtime


def api_call(
    operation: Callable[
        [],
        ResultType,
    ],
) -> ResultType:
    try:
        return operation()

    except TopoCliError as exc:
        abort(exc)

        raise

def collect_pages(
    fetch_page: Callable[
        [int, int],
        list[dict[str, Any]],
    ],
    *,
    page_size: int = 100,
    maximum_items: int | None = None,
) -> list[dict[str, Any]]:
    offset = 0

    results: list[
        dict[str, Any]
    ] = []

    seen_pages: set[str] = set()

    while True:
        page = api_call(
            lambda:
                fetch_page(
                    offset,
                    page_size,
                )
        )

        if not page:
            break

        signature = json.dumps(
            page,
            sort_keys=True,
            default=str,
        )

        if signature in seen_pages:
            raise ConfigurationError(
                "The API returned the same "
                "pagination page repeatedly. "
                "Confirm that the backend "
                "supports the offset parameter."
            )

        seen_pages.add(signature)

        results.extend(page)

        if (
            maximum_items is not None
            and len(results)
            >= maximum_items
        ):
            return results[
                :maximum_items
            ]

        if len(page) < page_size:
            break

        offset += len(page)

    return results