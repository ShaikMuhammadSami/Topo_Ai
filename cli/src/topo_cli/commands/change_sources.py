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
        "Manage inbound operational "
        "change sources."
    ),
    no_args_is_help=True,
)


def _create(
    context: typer.Context,
    *,
    name: str,
    source_type: str,
    secret_ref: str,
    config: dict,
    filters: dict | None = None,
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .create_change_source(
                {
                    "name": name,
                    "source_type":
                        source_type,
                    "secret_ref":
                        secret_ref,
                    "enabled": True,
                    "config": config,
                    "filters":
                        filters or {},
                }
            )
    )

    render_data(
        result,
        output_format=(
            runtime.output_format
        ),
        title="Change Source",
    )


@app.command("list")
def list_command(
    context: typer.Context,
) -> None:
    runtime = get_runtime(context)

    values = api_call(
        lambda:
            runtime.client
            .list_change_sources()
    )

    if (
        runtime.output_format
        == OutputFormat.JSON
    ):
        emit_json(values)
        return

    render_records(
        values,
        title="Change Sources",
        columns=[
            ColumnSpec(
                "TYPE",
                ("source_type",),
            ),
            ColumnSpec(
                "NAME",
                ("name",),
            ),
            ColumnSpec(
                "STATUS",
                ("status",),
            ),
            ColumnSpec(
                "DELIVERIES",
                ("delivery_count",),
            ),
            ColumnSpec(
                "FAILURES",
                ("failure_count",),
            ),
            ColumnSpec(
                "SOURCE ID",
                ("source_id",),
                max_width=55,
            ),
        ],
    )


@app.command("get")
def get_command(
    context: typer.Context,
    source_id: str,
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .get_change_source(
                source_id
            )
    )

    render_data(
        result,
        output_format=(
            runtime.output_format
        ),
        title="Change Source",
    )


@app.command("doctor")
def doctor(
    context: typer.Context,
    source_id: str,
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .doctor_change_source(
                source_id
            )
    )

    render_data(
        result,
        output_format=(
            runtime.output_format
        ),
        title="Change Source Doctor",
    )


@app.command("deliveries")
def deliveries(
    context: typer.Context,

    source_id: str | None = typer.Option(
        None,
        "--source",
    ),

    status: str | None = typer.Option(
        None,
        "--status",
    ),

    limit: int = typer.Option(
        200,
        "--limit",
        min=1,
        max=1000,
    ),
) -> None:
    runtime = get_runtime(context)

    values = api_call(
        lambda:
            runtime.client
            .list_change_source_deliveries(
                source_id=source_id,
                status=status,
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
        title="Change Source Deliveries",
        columns=[
            ColumnSpec(
                "TIME",
                ("received_at",),
            ),
            ColumnSpec(
                "STATUS",
                ("status",),
            ),
            ColumnSpec(
                "EVENT",
                ("event_type",),
            ),
            ColumnSpec(
                "SOURCE",
                ("source_id",),
                max_width=45,
            ),
            ColumnSpec(
                "DELIVERY",
                ("delivery_id",),
                max_width=45,
            ),
        ],
    )


@app.command("dead-letters")
def dead_letters(
    context: typer.Context,

    source_id: str | None = typer.Option(
        None,
        "--source",
    ),

    status: str | None = typer.Option(
        None,
        "--status",
    ),

    limit: int = typer.Option(
        200,
        "--limit",
        min=1,
        max=1000,
    ),
) -> None:
    runtime = get_runtime(context)

    values = api_call(
        lambda:
            runtime.client
            .list_change_source_dead_letters(
                source_id=source_id,
                status=status,
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
        title="Change Source Dead Letters",
        columns=[
            ColumnSpec(
                "STATUS",
                ("status",),
            ),
            ColumnSpec(
                "EVENT",
                ("event_type",),
            ),
            ColumnSpec(
                "ATTEMPTS",
                ("attempt_count",),
            ),
            ColumnSpec(
                "REASON",
                ("reason",),
                max_width=60,
            ),
            ColumnSpec(
                "ID",
                ("dead_letter_id",),
                max_width=45,
            ),
        ],
    )


@app.command("replay")
def replay(
    context: typer.Context,

    dead_letter_id: str,
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .replay_change_source_dead_letter(
                dead_letter_id
            )
    )

    render_data(
        result,
        output_format=(
            runtime.output_format
        ),
        title="Dead Letter Replay",
    )


@app.command("create-github")
def create_github(
    context: typer.Context,

    name: str = typer.Option(
        ...,
        "--name",
    ),

    secret_ref: str = typer.Option(
        ...,
        "--secret-ref",
    ),

    repository: str | None = typer.Option(
        None,
        "--repository",
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
) -> None:
    filters = {}

    if repository:
        filters["repositories"] = [
            repository
        ]

    _create(
        context,
        name=name,
        source_type="github",
        secret_ref=secret_ref,
        config={
            "environment":
                environment,
            "cluster_name":
                cluster_name,
            "namespace":
                namespace,
        },
        filters=filters,
    )


@app.command("create-gitlab")
def create_gitlab(
    context: typer.Context,

    name: str = typer.Option(
        ...,
        "--name",
    ),

    secret_ref: str = typer.Option(
        ...,
        "--secret-ref",
    ),

    auth_mode: str = typer.Option(
        "signing",
        "--auth-mode",
        help=(
            "signing or secret_token"
        ),
    ),

    environment: str | None = typer.Option(
        None,
        "--environment",
    ),
) -> None:
    if auth_mode not in {
        "signing",
        "secret_token",
    }:
        raise typer.BadParameter(
            "auth-mode must be "
            "signing or secret_token."
        )

    _create(
        context,
        name=name,
        source_type="gitlab",
        secret_ref=secret_ref,
        config={
            "auth_mode":
                auth_mode,
            "signature_max_age":
                300,
            "environment":
                environment,
        },
    )


@app.command("create-jenkins")
def create_jenkins(
    context: typer.Context,

    name: str = typer.Option(
        ...,
        "--name",
    ),

    secret_ref: str = typer.Option(
        ...,
        "--secret-ref",
    ),

    environment: str | None = typer.Option(
        None,
        "--environment",
    ),
) -> None:
    _create(
        context,
        name=name,
        source_type="jenkins",
        secret_ref=secret_ref,
        config={
            "environment":
                environment,
        },
    )


@app.command("create-azure-devops")
def create_azure_devops(
    context: typer.Context,

    name: str = typer.Option(
        ...,
        "--name",
    ),

    secret_ref: str = typer.Option(
        ...,
        "--secret-ref",
    ),

    username: str = typer.Option(
        "topo-webhook",
        "--username",
    ),

    environment: str | None = typer.Option(
        None,
        "--environment",
    ),
) -> None:
    _create(
        context,
        name=name,
        source_type="azure_devops",
        secret_ref=secret_ref,
        config={
            "username":
                username,
            "environment":
                environment,
        },
    )


@app.command("create-terraform-cloud")
def create_terraform_cloud(
    context: typer.Context,

    name: str = typer.Option(
        ...,
        "--name",
    ),

    secret_ref: str = typer.Option(
        ...,
        "--secret-ref",
    ),

    environment: str | None = typer.Option(
        None,
        "--environment",
    ),

    provider: str | None = typer.Option(
        None,
        "--provider",
    ),
) -> None:
    _create(
        context,
        name=name,
        source_type="terraform_cloud",
        secret_ref=secret_ref,
        config={
            "environment":
                environment,
            "provider":
                provider,
        },
    )