from __future__ import annotations

import json
from pathlib import Path

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
        "Inspect unified operational "
        "change events."
    ),
    no_args_is_help=True,
)


@app.command("list")
def list_command(
    context: typer.Context,

    source: str | None = typer.Option(
        None,
        "--source",
    ),

    kind: str | None = typer.Option(
        None,
        "--kind",
    ),

    environment: str | None = typer.Option(
        None,
        "--environment",
    ),

    cluster_name: str | None = typer.Option(
        None,
        "--cluster",
    ),

    namespace: str | None = typer.Option(
        None,
        "--namespace",
    ),

    minimum_risk_score: int = (
        typer.Option(
            0,
            "--minimum-risk",
            min=0,
            max=100,
        )
    ),

    limit: int = typer.Option(
        100,
        "--limit",
        min=1,
        max=5000,
    ),
) -> None:
    runtime = get_runtime(
        context
    )

    values = api_call(
        lambda:
            runtime.client
            .list_change_events(
                source=source,
                kind=kind,
                environment=(
                    environment
                ),
                cluster_name=(
                    cluster_name
                ),
                namespace=namespace,
                minimum_risk_score=(
                    minimum_risk_score
                ),
                limit=limit,
                offset=0,
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
        title="Change Events",
        columns=[
            ColumnSpec(
                "TIME",
                ("occurred_at",),
            ),
            ColumnSpec(
                "SOURCE",
                ("source",),
            ),
            ColumnSpec(
                "KIND",
                ("kind",),
            ),
            ColumnSpec(
                "RISK",
                ("risk_score",),
            ),
            ColumnSpec(
                "TITLE",
                ("title",),
                max_width=55,
            ),
            ColumnSpec(
                "EVENT ID",
                ("event_id",),
                max_width=55,
            ),
        ],
    )


@app.command("get")
def get_command(
    context: typer.Context,

    event_id: str = typer.Argument(
        ...,
    ),
) -> None:
    runtime = get_runtime(
        context
    )

    result = api_call(
        lambda:
            runtime.client
            .get_change_event(
                event_id
            )
    )

    render_data(
        result,
        output_format=(
            runtime.output_format
        ),
        title="Change Event",
    )


@app.command("ingest")
def ingest(
    context: typer.Context,

    file: Path = typer.Option(
        ...,
        "--file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
) -> None:
    runtime = get_runtime(
        context
    )

    try:
        payload = json.loads(
            file.read_text(
                encoding="utf-8"
            )
        )

    except json.JSONDecodeError as exc:
        raise typer.BadParameter(
            (
                "Invalid JSON file: "
                f"{exc}"
            )
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise typer.BadParameter(
            "Change event input must "
            "contain one JSON object."
        )

    result = api_call(
        lambda:
            runtime.client
            .ingest_change_event(
                payload
            )
    )

    render_data(
        result,
        output_format=(
            runtime.output_format
        ),
        title=(
            "Change Event Ingestion"
        ),
    )


@app.command("correlate")
def correlate(
    context: typer.Context,

    event_id: str = typer.Argument(
        ...,
    ),

    snapshot_id: str | None = typer.Option(
        None,
        "--snapshot",
    ),
) -> None:
    runtime = get_runtime(
        context
    )

    result = api_call(
        lambda:
            runtime.client
            .correlate_change_event(
                event_id=event_id,
                snapshot_id=(
                    snapshot_id
                ),
            )
    )

    render_data(
        result,
        output_format=(
            runtime.output_format
        ),
        title=(
            "Change Event Correlation"
        ),
    )