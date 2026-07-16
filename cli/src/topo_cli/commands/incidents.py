from __future__ import annotations

import typer

from topo_cli.commands.blast_radius import (
    display_blast_radius,
)
from topo_cli.commands.explanations import (
    generate_and_display,
)
from topo_cli.output import (
    ColumnSpec,
    emit_json,
    render_data,
    render_records,
)
from topo_cli.runtime import (
    api_call,
    get_runtime,
)


app = typer.Typer(
    help="List and inspect incidents.",
    no_args_is_help=True,
)


def _contains(
    value: object,
    query: str,
) -> bool:
    return (
        query.lower()
        in str(value).lower()
    )


@app.command("list")
def list_incidents(
    context: typer.Context,
    limit: int = typer.Option(
        50,
        min=1,
        max=1000,
    ),
    status: str | None = typer.Option(
        None,
        "--status",
        help="Filter by incident status.",
    ),
    severity: str | None = typer.Option(
        None,
        "--severity",
        help="Filter by severity.",
    ),
    search: str | None = typer.Option(
        None,
        "--search",
        "-s",
        help=(
            "Search incident ID, title, "
            "summary or entity."
        ),
    ),
) -> None:
    runtime = get_runtime(context)

    incidents = api_call(
        lambda:
            runtime.client.list_incidents(
                limit=limit
            )
    )

    if status:
        incidents = [
            incident
            for incident in incidents
            if _contains(
                incident.get("status"),
                status,
            )
        ]

    if severity:
        incidents = [
            incident
            for incident in incidents
            if _contains(
                incident.get("severity"),
                severity,
            )
        ]

    if search:
        incidents = [
            incident
            for incident in incidents
            if any(
                _contains(
                    incident.get(field),
                    search,
                )
                for field in (
                    "incident_id",
                    "title",
                    "summary",
                    "affected_object_name",
                    "affected_entity_id",
                )
            )
        ]

    if (
        runtime.output_format.value
        == "json"
    ):
        emit_json(incidents)
        return

    render_records(
        incidents,
        title="Topo Incidents",
        columns=[
            ColumnSpec(
                "SEVERITY",
                ("severity",),
            ),
            ColumnSpec(
                "STATUS",
                ("status",),
            ),
            ColumnSpec(
                "TITLE",
                (
                    "title",
                    "summary",
                ),
                max_width=50,
            ),
            ColumnSpec(
                "AFFECTED ENTITY",
                (
                    "affected_object_name",
                    "affected_entity_name",
                    "affected_entity_id",
                ),
                max_width=45,
            ),
            ColumnSpec(
                "LAST OBSERVED",
                (
                    "last_observed_at",
                    "updated_at",
                ),
            ),
            ColumnSpec(
                "INCIDENT ID",
                ("incident_id",),
                max_width=70,
            ),
        ],
    )


@app.command("get")
def get_incident(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
) -> None:
    runtime = get_runtime(context)

    incident = api_call(
        lambda:
            runtime.client.get_incident(
                incident_id
            )
    )

    render_data(
        incident,
        output_format=(
            runtime.output_format
        ),
        title="Incident Detail",
    )


@app.command("blast-radius")
def incident_blast_radius(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
) -> None:
    display_blast_radius(
        context,
        incident_id,
    )


@app.command("explain")
def explain_incident(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
    provider: str = typer.Option(
        "auto",
        "--provider",
    ),
    force_regenerate: bool = typer.Option(
        False,
        "--force",
    ),
) -> None:
    generate_and_display(
        context,
        incident_id=incident_id,
        provider=provider,
        force_regenerate=(
            force_regenerate
        ),
    )