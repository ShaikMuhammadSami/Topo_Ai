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
    collect_pages,
    get_runtime,
)


app = typer.Typer(
    help=(
        "Manage Topo infrastructure agents."
    ),
    no_args_is_help=True,
)


@app.command("create-token")
def create_token(
    context: typer.Context,
    label: str | None = typer.Option(
        None,
        "--label",
    ),
    expires_in_minutes: int = typer.Option(
        30,
        "--expires-in-minutes",
        min=1,
        max=10080,
    ),
    max_uses: int = typer.Option(
        1,
        "--max-uses",
        min=1,
        max=100,
    ),
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .create_agent_enrollment_token(
                label=label,
                expires_in_minutes=(
                    expires_in_minutes
                ),
                max_uses=max_uses,
            )
    )

    render_data(
        result,
        output_format=(
            runtime.output_format
        ),
        title=(
            "Agent Enrollment Token"
        ),
    )


@app.command("list")
def list_agent_records(
    context: typer.Context,
    limit: int = typer.Option(
        100,
        "--limit",
        min=1,
        max=1000,
    ),
    all_pages: bool = typer.Option(
        False,
        "--all",
    ),
    page_size: int = typer.Option(
        100,
        "--page-size",
        min=1,
        max=1000,
    ),
) -> None:
    runtime = get_runtime(context)

    if all_pages:
        values = collect_pages(
            lambda offset, size:
                runtime.client
                .list_agents(
                    limit=size,
                    offset=offset,
                ),
            page_size=page_size,
        )

    else:
        values = api_call(
            lambda:
                runtime.client
                .list_agents(
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
        title="Topo Agents",
        columns=[
            ColumnSpec(
                "STATUS",
                ("status",),
            ),
            ColumnSpec(
                "NAME",
                ("name",),
            ),
            ColumnSpec(
                "CLUSTER",
                ("cluster_name",),
            ),
            ColumnSpec(
                "ENVIRONMENT",
                ("environment",),
            ),
            ColumnSpec(
                "VERSION",
                ("version",),
            ),
            ColumnSpec(
                "LAST HEARTBEAT",
                ("last_heartbeat_at",),
            ),
            ColumnSpec(
                "LAST SNAPSHOT",
                ("last_snapshot_at",),
            ),
            ColumnSpec(
                "BUFFERED",
                (
                    "buffered_item_count",
                ),
            ),
            ColumnSpec(
                "AGENT ID",
                ("agent_id",),
                max_width=60,
            ),
        ],
    )


@app.command("get")
def get_agent(
    context: typer.Context,
    agent_id: str = typer.Argument(
        ...,
    ),
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client.get_agent(
                agent_id
            )
    )

    render_data(
        result,
        output_format=(
            runtime.output_format
        ),
        title="Topo Agent",
    )


@app.command("health")
def health(
    context: typer.Context,
    agent_id: str = typer.Argument(
        ...,
    ),
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .get_agent_health(
                agent_id
            )
    )

    render_data(
        result,
        output_format=(
            runtime.output_format
        ),
        title="Agent Health",
    )


@app.command("revoke")
def revoke(
    context: typer.Context,
    agent_id: str = typer.Argument(
        ...,
    ),
    confirm: bool = typer.Option(
        False,
        "--yes",
        "-y",
    ),
) -> None:
    if not confirm:
        approved = typer.confirm(
            "Revoke this agent?"
        )

        if not approved:
            raise typer.Abort()

    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client.revoke_agent(
                agent_id
            )
    )

    render_data(
        result,
        output_format=(
            runtime.output_format
        ),
        title="Revoked Agent",
    )