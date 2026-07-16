from __future__ import annotations

import typer

from topo_cli.output import (
    ColumnSpec,
    emit_json,
    render_detail,
    render_records,
)
from topo_cli.runtime import (
    api_call,
    get_runtime,
)


app = typer.Typer(
    help="Inspect incident blast radius.",
    no_args_is_help=True,
)


def display_blast_radius(
    context: typer.Context,
    incident_id: str,
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client.blast_radius(
                incident_id
            )
    )

    if (
        runtime.output_format.value
        == "json"
    ):
        emit_json(result)
        return

    summary = {
        "incident_id":
            result.get(
                "incident_id",
                incident_id,
            ),
        "root_entity_id":
            result.get(
                "root_entity_id"
            ),
        "root_entity_name":
            result.get(
                "root_entity_name"
            ),
        "affected_entity_count":
            result.get(
                "affected_entity_count"
            ),
        "direct_impact_count":
            result.get(
                "direct_impact_count"
            ),
        "indirect_impact_count":
            result.get(
                "indirect_impact_count"
            ),
        "potential_impact_count":
            result.get(
                "potential_impact_count"
            ),
    }

    render_detail(
        summary,
        title="Blast Radius Summary",
    )

    affected_entities = result.get(
        "affected_entities",
        [],
    )

    if isinstance(
        affected_entities,
        list,
    ) and affected_entities:
        render_records(
            [
                item
                for item in affected_entities
                if isinstance(item, dict)
            ],
            title="Affected Entities",
            columns=[
                ColumnSpec(
                    "DISTANCE",
                    ("distance",),
                ),
                ColumnSpec(
                    "IMPACT",
                    ("impact",),
                ),
                ColumnSpec(
                    "KIND",
                    (
                        "entity_kind",
                        "kind",
                    ),
                ),
                ColumnSpec(
                    "NAME",
                    (
                        "entity_name",
                        "name",
                    ),
                ),
                ColumnSpec(
                    "ENTITY ID",
                    ("entity_id",),
                    max_width=60,
                ),
            ],
        )


@app.command("get")
def get_blast_radius(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
) -> None:
    display_blast_radius(
        context,
        incident_id,
    )