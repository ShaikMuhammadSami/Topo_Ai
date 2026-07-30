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

@app.command("plugins")
def plugins(
    context: typer.Context,
    agent_id: str = typer.Argument(
        ...,
    ),
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .get_agent_plugins(
                agent_id
            )
    )

    if (
        runtime.output_format
        == OutputFormat.JSON
    ):
        emit_json(result)
        return

    values = result.get(
        "plugins",
        [],
    )

    render_records(
        [
            item
            for item in values
            if isinstance(item, dict)
        ],
        title=(
            "Agent Plugin Status"
        ),
        columns=[
            ColumnSpec(
                "PLUGIN",
                ("name",),
            ),
            ColumnSpec(
                "STATUS",
                ("status",),
            ),
            ColumnSpec(
                "DURATION MS",
                ("duration_ms",),
            ),
            ColumnSpec(
                "INVENTORY",
                ("inventory_counts",),
                max_width=70,
            ),
            ColumnSpec(
                "ERRORS",
                ("errors",),
                max_width=80,
            ),
        ],
    )

@app.command("sensors")
def sensors(
    context: typer.Context,
    agent_id: str = typer.Argument(
        ...,
        help="Topo Agent ID.",
    ),
) -> None:
    runtime = get_runtime(context)

    values = api_call(
        lambda:
            runtime.client
            .list_agent_sensors(
                agent_id
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
        title="Runtime Sensors",
        columns=[
            ColumnSpec(
                "STATUS",
                ("status",),
            ),
            ColumnSpec(
                "NODE",
                ("node_name",),
            ),
            ColumnSpec(
                "SOURCE",
                ("source",),
            ),
            ColumnSpec(
                "VERSION",
                ("version",),
            ),
            ColumnSpec(
                "EVENTS",
                (
                    "processed_event_count",
                ),
            ),
            ColumnSpec(
                "DROPPED",
                (
                    "dropped_event_count",
                ),
            ),
            ColumnSpec(
                "PARSER ERRORS",
                (
                    "parser_error_count",
                ),
            ),
            ColumnSpec(
                "BUFFERED",
                (
                    "buffered_batch_count",
                ),
            ),
            ColumnSpec(
                "LAST HEARTBEAT",
                (
                    "last_heartbeat_at",
                ),
            ),
            ColumnSpec(
                "SENSOR ID",
                ("sensor_id",),
                max_width=60,
            ),
        ],
    )


@app.command("runtime-dependencies")
def runtime_dependencies(
    context: typer.Context,
    agent_id: str = typer.Argument(
        ...,
        help="Topo Agent ID.",
    ),
    window_minutes: int = typer.Option(
        15,
        "--window-minutes",
        min=1,
        max=10080,
    ),
    limit: int = typer.Option(
        1000,
        "--limit",
        min=1,
        max=5000,
    ),
    all_pages: bool = typer.Option(
        False,
        "--all",
    ),
    page_size: int = typer.Option(
        500,
        "--page-size",
        min=1,
        max=5000,
    ),
) -> None:
    runtime = get_runtime(context)

    if all_pages:
        values = collect_pages(
            lambda offset, size:
                runtime.client
                .list_agent_runtime_dependencies(
                    agent_id=agent_id,
                    window_minutes=(
                        window_minutes
                    ),
                    limit=size,
                    offset=offset,
                ),
            page_size=page_size,
        )

    else:
        values = api_call(
            lambda:
                runtime.client
                .list_agent_runtime_dependencies(
                    agent_id=agent_id,
                    window_minutes=(
                        window_minutes
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
        title=(
            "eBPF Runtime Dependencies"
        ),
        columns=[
            ColumnSpec(
                "NAMESPACE",
                (
                    "source_namespace",
                ),
            ),
            ColumnSpec(
                "POD",
                ("source_pod_name",),
                max_width=35,
            ),
            ColumnSpec(
                "BINARY",
                ("source_binary",),
                max_width=45,
            ),
            ColumnSpec(
                "DESTINATION",
                (
                    "destination_name",
                    "destination_address",
                ),
                max_width=45,
            ),
            ColumnSpec(
                "PORT",
                (
                    "destination_port",
                ),
            ),
            ColumnSpec(
                "PROTOCOL",
                ("protocol",),
            ),
            ColumnSpec(
                "DIRECTION",
                ("direction",),
            ),
            ColumnSpec(
                "COUNT",
                (
                    "observation_count",
                ),
            ),
            ColumnSpec(
                "FAILURES",
                ("failure_count",),
            ),
            ColumnSpec(
                "LAST SEEN",
                ("last_seen_at",),
            ),
        ],
    )

@app.command("cloud-status")
def cloud_status(
    context: typer.Context,
    agent_id: str = typer.Argument(
        ...,
        help="Topo Agent ID.",
    ),
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .get_agent_cloud_status(
                agent_id
            )
    )

    render_data(
        result,
        output_format=(
            runtime.output_format
        ),
        title="Agent Cloud Status",
    )