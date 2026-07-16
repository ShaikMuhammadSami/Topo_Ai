from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

import typer
from rich.console import Console
from rich.table import Table


console = Console()


class OutputFormat(str, Enum):
    TABLE = "table"
    JSON = "json"


@dataclass(frozen=True)
class ColumnSpec:
    header: str

    paths: tuple[str, ...]

    max_width: int | None = None


def emit_json(
    value: Any,
) -> None:
    """
    Plain JSON is intentionally emitted without
    Rich styling so it remains pipeline-safe.
    """

    typer.echo(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            default=str,
        )
    )


def _path_value(
    value: dict[str, Any],
    path: str,
) -> Any:
    current: Any = value

    for segment in path.split("."):
        if not isinstance(current, dict):
            return None

        current = current.get(segment)

    return current


def first_value(
    value: dict[str, Any],
    paths: tuple[str, ...],
) -> Any:
    for path in paths:
        result = _path_value(
            value,
            path,
        )

        if result is not None:
            return result

    return None


def format_value(
    value: Any,
    *,
    max_width: int | None = None,
) -> str:
    if value is None:
        result = "-"

    elif isinstance(value, bool):
        result = (
            "true"
            if value
            else "false"
        )

    elif isinstance(
        value,
        (dict, list),
    ):
        result = json.dumps(
            value,
            sort_keys=True,
            default=str,
        )

    else:
        result = str(value)

    if (
        max_width is not None
        and len(result) > max_width
    ):
        return (
            result[: max_width - 1]
            + "…"
        )

    return result


def render_records(
    records: list[dict[str, Any]],
    *,
    columns: list[ColumnSpec],
    title: str,
) -> None:
    table = Table(
        title=title,
        show_lines=False,
        expand=True,
    )

    for column in columns:
        table.add_column(
            column.header,
            overflow="fold",
        )

    for record in records:
        table.add_row(
            *[
                format_value(
                    first_value(
                        record,
                        column.paths,
                    ),
                    max_width=(
                        column.max_width
                    ),
                )
                for column in columns
            ]
        )

    console.print(table)


def render_detail(
    value: dict[str, Any],
    *,
    title: str,
) -> None:
    table = Table(
        title=title,
        show_header=True,
        expand=True,
    )

    table.add_column(
        "Field",
        style="bold",
        width=28,
    )

    table.add_column(
        "Value",
        overflow="fold",
    )

    for key, item in value.items():
        table.add_row(
            str(key),
            format_value(item),
        )

    console.print(table)


def render_data(
    value: Any,
    *,
    output_format: OutputFormat,
    title: str,
) -> None:
    if (
        output_format
        == OutputFormat.JSON
    ):
        emit_json(value)
        return

    if isinstance(value, dict):
        render_detail(
            value,
            title=title,
        )
        return

    if isinstance(value, list):
        records = [
            item
            for item in value
            if isinstance(item, dict)
        ]

        if not records:
            console.print(
                "[dim]No records found.[/dim]"
            )
            return

        keys = list(records[0])[:8]

        render_records(
            records,
            columns=[
                ColumnSpec(
                    header=key,
                    paths=(key,),
                    max_width=60,
                )
                for key in keys
            ],
            title=title,
        )
        return

    console.print(value)