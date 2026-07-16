from __future__ import annotations

import os

import typer

from topo_cli import __version__
from topo_cli.client import TopoClient
from topo_cli.commands import (
    blast_radius,
    explanations,
    incidents,
    profiles,
    snapshots,
)
from topo_cli.config import (
    load_config,
    profile_token,
    resolve_profile,
)
from topo_cli.errors import (
    TopoCliError,
    abort,
)
from topo_cli.output import (
    OutputFormat,
    emit_json,
    render_detail,
)
from topo_cli.runtime import (
    RuntimeContext,
    api_call,
    get_runtime,
)


app = typer.Typer(
    name="topo",
    help=(
        "Topo AI infrastructure "
        "intelligence command line."
    ),
    no_args_is_help=True,
    add_completion=True,
)


app.add_typer(
    profiles.app,
    name="profiles",
)

app.add_typer(
    incidents.app,
    name="incidents",
)

app.add_typer(
    snapshots.app,
    name="snapshots",
)

app.add_typer(
    blast_radius.app,
    name="blast-radius",
)

app.add_typer(
    explanations.app,
    name="explanations",
)


@app.callback()
def initialize(
    context: typer.Context,
    profile: str | None = typer.Option(
        None,
        "--profile",
        "-p",
        help="Named Topo API profile.",
    ),
    server: str | None = typer.Option(
        None,
        "--server",
        envvar="TOPO_API_URL",
        help=(
            "Override the profile API URL."
        ),
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.TABLE,
        "--output",
        "-o",
        envvar="TOPO_OUTPUT",
        help="table or json",
    ),
    timeout: float | None = typer.Option(
        None,
        "--timeout",
        min=1.0,
        envvar="TOPO_TIMEOUT",
        help=(
            "Override request timeout."
        ),
    ),
    insecure: bool = typer.Option(
        False,
        "--insecure",
        help=(
            "Disable TLS verification for "
            "this command."
        ),
    ),
) -> None:
    try:
        config = load_config()

        (
            profile_name,
            resolved_profile,
        ) = resolve_profile(
            config,
            profile,
        )

    except TopoCliError as exc:
        abort(exc)
        return

    if server:
        resolved_profile.api_url = (
            server.rstrip("/")
        )

    if timeout is not None:
        resolved_profile.timeout = timeout

    if insecure:
        resolved_profile.verify_tls = (
            False
        )

    token = (
        os.getenv("TOPO_API_TOKEN")
        or profile_token(
            resolved_profile
        )
    )

    client = TopoClient(
        api_url=(
            resolved_profile.api_url
        ),
        token=token,
        timeout=(
            resolved_profile.timeout
        ),
        verify_tls=(
            resolved_profile.verify_tls
        ),
        snapshot_capture_path=(
            resolved_profile
            .snapshot_capture_path
        ),
    )

    context.obj = RuntimeContext(
        config=config,
        profile_name=profile_name,
        profile=resolved_profile,
        output_format=output,
        client=client,
    )


@app.command("version")
def version_command() -> None:
    typer.echo(
        f"topo {__version__}"
    )


@app.command("health")
def health_command(
    context: typer.Context,
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        runtime.client.health
    )

    if (
        runtime.output_format
        == OutputFormat.JSON
    ):
        emit_json(result)
        return

    render_detail(
        result,
        title="Topo AI Connection",
    )