from __future__ import annotations

import os

import typer
import sys  
from topo_cli import __version__
from topo_cli.client import TopoClient
from topo_cli.commands import (
    blast_radius,
    copilot,
    explanations,
    incidents,
    investigations,
    profiles,
    reports,
    snapshots,
)
from topo_cli.config import (
    config_file_path,
    delete_profile_token,
    load_config,
    profile_token,
    resolve_profile,
    store_profile_token,
    token_source,
)
from topo_cli.errors import (
    TopoCliError,
    InputValidationFailure,
    abort,
)
from topo_cli.output import (
    OutputFormat,
    emit_json,
    render_detail,
    configure_output,
    emit_notice,
    render_data,
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
app.add_typer(
    copilot.app,
    name="copilot",
)

app.add_typer(
    investigations.app,
    name="investigations",
)

app.add_typer(
    reports.app,
    name="reports",
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
    max_retries: int | None = typer.Option(
     None,
     "--retries",
     min=0,
     envvar="TOPO_MAX_RETRIES",
     help="Retry count for temporary failures.",
    ),
    retry_backoff: float | None = typer.Option(
     None,
     "--retry-backoff",
     min=0.0,
     envvar="TOPO_RETRY_BACKOFF",
     help="Initial retry backoff in seconds.",
    ),
    quiet: bool = typer.Option(
     False,
     "--quiet",
     "-q",
     envvar="TOPO_QUIET",
     help=(
         "Suppress non-data confirmation "
         "messages."
        ),
    ),
    no_color: bool = typer.Option(
     False,
     "--no-color",
     envvar="NO_COLOR",
     help="Disable colorized output.",
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
    if max_retries is not None:
     resolved_profile.max_retries = (
         max_retries
        )

    if retry_backoff is not None:
     resolved_profile.retry_backoff = (
         retry_backoff
        )
    # token = (
    #     os.getenv("TOPO_API_TOKEN")
    #     or profile_token(
    #         resolved_profile
    #     )
    # )
    configure_output(
     quiet=quiet,
     no_color=no_color,
    )
    token = profile_token(
     resolved_profile,
     profile_name,
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
        max_retries=(
            resolved_profile.max_retries
        ),
        retry_backoff=(
            resolved_profile.retry_backoff
        ),
    )
    context.call_on_close(
     client.close
    )
    context.obj = RuntimeContext(
        config=config,
        profile_name=profile_name,
        profile=resolved_profile,
        output_format=output,
        client=client,
        quiet=quiet,
        no_color=no_color,
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

@app.command("login")
def login_command(
    context: typer.Context,
    token_stdin: bool = typer.Option(
        False,
        "--token-stdin",
        help=(
            "Read the token from standard "
            "input instead of prompting."
        ),
    ),
) -> None:
    runtime = get_runtime(context)

    if token_stdin:
        token = sys.stdin.read().strip()
    else:
        token = typer.prompt(
            "Topo API token",
            hide_input=True,
            confirmation_prompt=False,
        ).strip()

    if not token:
        abort(
            InputValidationFailure(
                "API token cannot be empty."
            )
        )

    candidate = TopoClient(
        api_url=runtime.profile.api_url,
        token=token,
        timeout=runtime.profile.timeout,
        verify_tls=(
            runtime.profile.verify_tls
        ),
        snapshot_capture_path=(
            runtime.profile
            .snapshot_capture_path
        ),
        max_retries=(
            runtime.profile.max_retries
        ),
        retry_backoff=(
            runtime.profile.retry_backoff
        ),
    )

    try:
        principal = api_call(
            candidate.whoami
        )

    finally:
        candidate.close()

    try:
        store_profile_token(
            runtime.profile_name,
            token,
        )

    except TopoCliError as exc:
        abort(exc)
        return
    
    identity = (
     principal.get("display_name")
     or principal.get("subject")
     or "unknown"
    )

    emit_notice(
     f"Authenticated as {identity} "
     f"for profile "
     f"'{runtime.profile_name}'."
    )

@app.command("logout")
def logout_command(
    context: typer.Context,
) -> None:
    runtime = get_runtime(context)

    try:
        removed = delete_profile_token(
            runtime.profile_name
        )

    except TopoCliError as exc:
        abort(exc)
        return

    if removed:
        emit_notice(
            f"Stored token removed for "
            f"profile "
            f"'{runtime.profile_name}'."
        )
    else:
        emit_notice(
            "No keyring token was stored "
            f"for profile "
            f"'{runtime.profile_name}'."
        )

@app.command("whoami")
def whoami_command(
    context: typer.Context,
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        runtime.client.whoami
    )

    render_data(
        result,
        output_format=(
            runtime.output_format
        ),
        title="Topo Identity",
    )

@app.command("doctor")
def doctor_command(
    context: typer.Context,
) -> None:
    runtime = get_runtime(context)

    result: dict[str, object] = {
        "profile":
            runtime.profile_name,
        "api_url":
            runtime.profile.api_url,
        "config_file":
            str(config_file_path()),
        "token_source":
            token_source(
                runtime.profile,
                runtime.profile_name,
            ),
        "verify_tls":
            runtime.profile.verify_tls,
        "timeout":
            runtime.profile.timeout,
        "max_retries":
            runtime.profile.max_retries,
        "retry_backoff":
            runtime.profile.retry_backoff,
        "health":
            "unknown",
        "authentication":
            "unknown",
        "identity":
            None,
    }

    failure_code: int | None = None

    try:
        health = runtime.client.health()

        result["health"] = "available"
        result["service"] = health.get(
            "service"
        )
        result["version"] = health.get(
            "version"
        )

    except TopoCliError as exc:
        result["health"] = "failed"
        result["health_error"] = (
            exc.message
        )
        failure_code = exc.exit_code

    try:
        identity = (
            runtime.client.whoami()
        )

        result["authentication"] = (
            "valid"
        )
        result["identity"] = (
            identity.get("subject")
        )
        result["roles"] = (
            identity.get("roles")
        )

    except TopoCliError as exc:
        result["authentication"] = (
            "failed"
        )
        result["authentication_error"] = (
            exc.message
        )

        if failure_code is None:
            failure_code = exc.exit_code

    render_data(
        result,
        output_format=(
            runtime.output_format
        ),
        title="Topo CLI Diagnostics",
    )

    if failure_code is not None:
        raise typer.Exit(
            code=failure_code
        )