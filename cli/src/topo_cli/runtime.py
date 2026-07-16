from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypeVar

import typer

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