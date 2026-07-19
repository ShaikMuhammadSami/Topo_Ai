from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from topo_cli.errors import (
    FileOperationFailure,
    InputValidationFailure,
    abort,
)
from topo_cli.output import (
    ColumnSpec,
    emit_json,
    render_data,
    render_records,
    OutputFormat,
)
from topo_cli.runtime import (
    api_call,
    collect_pages,
    get_runtime,
)


app = typer.Typer(
    help="List, inspect and capture snapshots.",
    no_args_is_help=True,
)


@app.command("list")
def list_snapshots(
    context: typer.Context,
    limit: int = typer.Option(
        20,
        min=1,
        max=1000,
    ),
    all_pages: bool = typer.Option(
        False,
        "--all",
        help="Retrieve every available page.",
    ),
    page_size: int = typer.Option(
       100,
       "--page-size",
       min=1,
       max=100,
    ),
    maximum_items: int | None = (
        typer.Option(
            None,
            "--max-items",
            min=1,
            help=(
               "Stop after this many records "
               "when using --all."
            ),
        )
    ),
) -> None:
    runtime = get_runtime(context)

    if all_pages:
     incidents = collect_pages(
         lambda offset, size:
             runtime.client.list_incidents(
                 limit=size,
                 offset=offset,
                ),
         page_size=page_size,
         maximum_items=maximum_items,
        )
    
    else:
        incidents = api_call(
         lambda:
             runtime.client.list_incidents(
                 limit=limit,
                 offset = 0,
                )
        )

    
    snapshots = api_call(
        lambda:
            runtime.client.list_snapshots(
                limit=limit
            )
    )

    if (
        runtime.output_format.value
        == "json"
    ):
        emit_json(snapshots)
        return

    render_records(
        snapshots,
        title="Topology Snapshots",
        columns=[
            ColumnSpec(
                "COLLECTED",
                (
                    "collected_at",
                    "created_at",
                ),
            ),
            ColumnSpec(
                "COLLECTOR",
                (
                    "collector_name",
                    "collector",
                ),
            ),
            ColumnSpec(
                "SCOPE",
                ("scope",),
                max_width=45,
            ),
            ColumnSpec(
                "ENTITIES",
                (
                    "entity_count",
                    "entities_count",
                ),
            ),
            ColumnSpec(
                "RELATIONSHIPS",
                (
                    "relationship_count",
                    "relationships_count",
                ),
            ),
            ColumnSpec(
                "SNAPSHOT ID",
                ("snapshot_id",),
                max_width=75,
            ),
        ],
    )


@app.command("get")
def get_snapshot(
    context: typer.Context,
    snapshot_id: str = typer.Argument(
        help="Topology snapshot ID.",
    ),
) -> None:
    runtime = get_runtime(context)

    snapshot = api_call(
        lambda:
            runtime.client.get_snapshot(
                snapshot_id
            )
    )

    if (
        runtime.output_format.value
        == "json"
    ):
        emit_json(snapshot)
        return

    summary = {
        "snapshot_id":
            snapshot.get("snapshot_id"),
        "schema_version":
            snapshot.get(
                "schema_version"
            ),
        "collected_at":
            snapshot.get(
                "collected_at"
            ),
        "collector_name":
            snapshot.get(
                "collector_name"
            ),
        "collector_version":
            snapshot.get(
                "collector_version"
            ),
        "scope":
            snapshot.get("scope"),
        "entity_count": len(
            snapshot.get(
                "entities",
                [],
            )
        ),
        "relationship_count": len(
            snapshot.get(
                "relationships",
                [],
            )
        ),
        "evidence_count": len(
            snapshot.get(
                "evidence",
                [],
            )
        ),
    }

    render_data(
        summary,
        output_format=(
            runtime.output_format
        ),
        title="Snapshot Detail",
    )


def _load_payload(
    path: Path,
) -> dict[str, Any]:
    try:
        content = path.read_text(
            encoding="utf-8"
        )

        value = json.loads(content)

    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise FileOperationFailure(
            "Unable to load snapshot "
            f"capture payload from {path}: "
            f"{exc}"
        ) from exc

    if not isinstance(value, dict):
        raise InputValidationFailure(
            "Snapshot capture payload "
            "must contain a JSON object."
        )

    return value


@app.command("capture")
def capture_snapshot(
    context: typer.Context,
    namespace: str | None = typer.Option(
        None,
        "--namespace",
        "-n",
        help="Kubernetes namespace.",
    ),
    cluster: str | None = typer.Option(
        None,
        "--cluster",
        help="Cluster name or context.",
    ),
    collector: str = typer.Option(
        "kubernetes",
        "--collector",
    ),
    payload_file: Path | None = typer.Option(
        None,
        "--payload",
        exists=True,
        dir_okay=False,
        readable=True,
        help=(
            "Send an exact JSON payload "
            "instead of the generated payload."
        ),
    ),
    endpoint: str | None = typer.Option(
        None,
        "--endpoint",
        help=(
            "Override the configured backend "
            "capture endpoint."
        ),
    ),
) -> None:
    runtime = get_runtime(context)

    try:
        if payload_file:
            payload = _load_payload(
                payload_file
            )

        else:
            scope: dict[str, Any] = {}

            if cluster:
                scope["cluster"] = cluster

            if namespace:
                scope["namespace"] = (
                    namespace
                )

            payload = {
                "collector_name":
                    collector,
                "scope": scope,
                "persist": True,
            }

    except (
        FileOperationFailure,
        InputValidationFailure,
    ) as exc:
        abort(exc)

        return

    result = api_call(
        lambda:
            runtime.client
            .capture_snapshot(
                payload,
                endpoint_override=endpoint,
            )
    )

    render_data(
        result,
        output_format=(
            runtime.output_format
        ),
        title="Captured Snapshot",
    )