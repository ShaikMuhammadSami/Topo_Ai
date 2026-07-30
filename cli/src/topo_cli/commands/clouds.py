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
        "Inspect cloud accounts, "
        "resources and topology."
    ),
    no_args_is_help=True,
)


@app.command("accounts")
def accounts(
    context: typer.Context,
    provider: str | None = typer.Option(
        "aws",
        "--provider",
    ),
) -> None:
    runtime = get_runtime(context)

    values = api_call(
        lambda:
            runtime.client
            .list_cloud_accounts(
                provider=provider
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
        title="Cloud Accounts",
        columns=[
            ColumnSpec(
                "PROVIDER",
                ("provider",),
            ),
            ColumnSpec(
                "ACCOUNT",
                ("account_number",),
            ),
            ColumnSpec(
                "NAME",
                ("display_name",),
            ),
            ColumnSpec(
                "PRINCIPAL",
                ("principal_arn",),
                max_width=65,
            ),
            ColumnSpec(
                "LAST SEEN",
                ("last_seen_at",),
            ),
        ],
    )


@app.command("resources")
def resources(
    context: typer.Context,
    provider: str | None = typer.Option(
        "aws",
        "--provider",
    ),
    account_id: str | None = typer.Option(
        None,
        "--account",
    ),
    region: str | None = typer.Option(
        None,
        "--region",
    ),
    resource_type:
        str | None = typer.Option(
            None,
            "--type",
        ),
    tag_key: str | None = typer.Option(
        None,
        "--tag-key",
    ),
    tag_value:
        str | None = typer.Option(
            None,
            "--tag-value",
        ),
    limit: int = typer.Option(
        500,
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

    def fetch(
        offset: int,
        size: int,
    ):
        return (
            runtime.client
            .list_cloud_resources(
                provider=provider,
                account_id=account_id,
                region=region,
                resource_type=(
                    resource_type
                ),
                tag_key=tag_key,
                tag_value=tag_value,
                limit=size,
                offset=offset,
            )
        )

    if all_pages:
        values = collect_pages(
            fetch,
            page_size=page_size,
        )

    else:
        values = api_call(
            lambda: fetch(
                0,
                limit,
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
        title="Cloud Resources",
        columns=[
            ColumnSpec(
                "TYPE",
                ("resource_type",),
            ),
            ColumnSpec(
                "NAME",
                ("name",),
                max_width=40,
            ),
            ColumnSpec(
                "STATUS",
                ("status",),
            ),
            ColumnSpec(
                "REGION",
                ("region",),
            ),
            ColumnSpec(
                "VPC",
                ("vpc_id",),
            ),
            ColumnSpec(
                "RESOURCE ID",
                ("resource_id",),
                max_width=60,
            ),
            ColumnSpec(
                "OBSERVED",
                ("observed_at",),
            ),
        ],
    )


@app.command("topology")
def topology(
    context: typer.Context,
    provider: str = typer.Option(
        "aws",
        "--provider",
    ),
    account_id: str | None = typer.Option(
        None,
        "--account",
    ),
    region: str | None = typer.Option(
        None,
        "--region",
    ),
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .get_cloud_topology(
                provider=provider,
                account_id=account_id,
                region=region,
            )
    )

    if (
        runtime.output_format
        == OutputFormat.JSON
    ):
        emit_json(result)
        return

    summary = {
        "snapshot_id":
            result.get(
                "snapshot_id"
            ),
        "provider":
            result.get(
                "provider"
            ),
        "account_id":
            result.get(
                "account_id"
            ),
        "region":
            result.get(
                "region"
            ),
        "entity_count": len(
            result.get(
                "entities",
                [],
            )
        ),
        "relationship_count": len(
            result.get(
                "relationships",
                [],
            )
        ),
    }

    render_data(
        summary,
        output_format=(
            runtime.output_format
        ),
        title="Cloud Topology",
    )