from __future__ import annotations

import typer

from topo_cli.output import (
    ColumnSpec,
    OutputFormat,
    emit_json,
    render_data,
    render_records,
)
from topo_cli.runtime import (
    api_call,
    get_runtime,
)


app = typer.Typer(
    help=(
        "Inspect snapshot-derived "
        "infrastructure changes."
    ),
    no_args_is_help=True,
)


@app.command("list")
def list_command(
    context: typer.Context,

    cluster_name: str | None = typer.Option(
        None,
        "--cluster",
        help="Filter by cluster.",
    ),

    namespace: str | None = typer.Option(
        None,
        "--namespace",
        help="Filter by namespace.",
    ),

    category: str | None = typer.Option(
        None,
        "--category",
        help=(
            "Filter by change category."
        ),
    ),

    importance: str | None = typer.Option(
        None,
        "--importance",
        help=(
            "Filter by importance."
        ),
    ),

    limit: int = typer.Option(
        200,
        "--limit",
        min=1,
        max=500,
    ),
) -> None:
    runtime = get_runtime(
        context
    )

    values = api_call(
        lambda:
            runtime.client.list_changes(
                cluster_name=(
                    cluster_name
                ),
                namespace=namespace,
                category=category,
                importance=importance,
                limit=limit,
            )
    )

    if (
        runtime.output_format
        == OutputFormat.JSON
    ):
        emit_json(values)

        return

    render_records(
        values,
        title="Snapshot Changes",
        columns=[
            ColumnSpec(
                "TIME",
                ("detected_at",),
            ),
            ColumnSpec(
                "TYPE",
                ("change_type",),
            ),
            ColumnSpec(
                "CATEGORY",
                ("category",),
            ),
            ColumnSpec(
                "IMPORTANCE",
                ("importance",),
            ),
            ColumnSpec(
                "ENTITY",
                ("entity_name",),
                max_width=35,
            ),
            ColumnSpec(
                "TITLE",
                ("title",),
                max_width=55,
            ),
            ColumnSpec(
                "CHANGE ID",
                ("change_id",),
                max_width=55,
            ),
        ],
    )


@app.command("get")
def get_command(
    context: typer.Context,

    change_id: str = typer.Argument(
        ...,
        help="Topo change ID.",
    ),
) -> None:
    runtime = get_runtime(
        context
    )

    result = api_call(
        lambda:
            runtime.client.get_change(
                change_id
            )
    )

    render_data(
        result,
        output_format=(
            runtime.output_format
        ),
        title="Snapshot Change",
    )


@app.command("from-diff")
def from_diff(
    context: typer.Context,

    from_snapshot_id: str = (
        typer.Argument(
            ...,
            help=(
                "Starting snapshot ID."
            ),
        )
    ),

    to_snapshot_id: str = (
        typer.Argument(
            ...,
            help=(
                "Ending snapshot ID."
            ),
        )
    ),
) -> None:
    runtime = get_runtime(
        context
    )

    result = api_call(
        lambda:
            runtime.client
            .create_changes_from_diff(
                from_snapshot_id=(
                    from_snapshot_id
                ),
                to_snapshot_id=(
                    to_snapshot_id
                ),
            )
    )

    render_data(
        result,
        output_format=(
            runtime.output_format
        ),
        title=(
            "Snapshot Change Detection"
        ),
    )