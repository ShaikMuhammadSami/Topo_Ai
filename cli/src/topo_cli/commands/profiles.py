from __future__ import annotations

import typer

from topo_cli.config import (
    DEFAULT_API_URL,
    Profile,
    config_file_path,
    save_config,
)
from topo_cli.security import validate_api_url
from topo_cli.errors import (
    ConfigurationError,
    InputValidationFailure,
    TopoCliError,
    abort,
)
from topo_cli.output import (
    ColumnSpec,
    emit_json,
    render_detail,
    render_records,
    OutputFormat,
)
from topo_cli.runtime import (
    get_runtime,
    api_call,
    collect_pages,
)


app = typer.Typer(
    help="Manage Topo API profiles.",
    no_args_is_help=True,
)


@app.command("list")
def list_profiles(
    context: typer.Context,
) -> None:
    runtime = get_runtime(context)

    values = [
        {
            "name": name,
            "active": (
                name
                == runtime.config
                .active_profile
            ),
            "api_url": profile.api_url,
            "token_env":
                profile.token_env,
            "verify_tls":
                profile.verify_tls,
            "timeout": profile.timeout,
            "snapshot_capture_path":
                profile
                .snapshot_capture_path,
        }
        for name, profile
        in sorted(
            runtime.config.profiles.items()
        )
    ]

    if (
        runtime.output_format.value
        == "json"
    ):
        emit_json(values)
        return

    render_records(
        values,
        title="Topo Profiles",
        columns=[
            ColumnSpec(
                "NAME",
                ("name",),
            ),
            ColumnSpec(
                "ACTIVE",
                ("active",),
            ),
            ColumnSpec(
                "API URL",
                ("api_url",),
            ),
            ColumnSpec(
                "TOKEN ENV",
                ("token_env",),
            ),
            ColumnSpec(
                "TLS",
                ("verify_tls",),
            ),
            ColumnSpec(
                "TIMEOUT",
                ("timeout",),
            ),
        ],
    )


@app.command("show")
def show_profile(
    context: typer.Context,
    name: str | None = typer.Argument(
        None,
        help=(
            "Profile name. Defaults to "
            "the active profile."
        ),
    ),
) -> None:
    runtime = get_runtime(context)

    profile_name = (
        name
        or runtime.config.active_profile
    )

    profile = runtime.config.profiles.get(
        profile_name
    )

    if profile is None:
        abort(
            ConfigurationError(
                f"Profile does not exist: "
                f"{profile_name}"
            )
        )

    value = {
        "name": profile_name,
        "active": (
            profile_name
            == runtime.config
            .active_profile
        ),
        "api_url": profile.api_url,
        "token_env": profile.token_env,
        "token_configured": bool(
            __import__("os").getenv(
                profile.token_env
            )
        ),
        "verify_tls":
            profile.verify_tls,
        "timeout": profile.timeout,
        "max_retries": profile.max_retries,
        "retry_backoff": profile.retry_backoff,
        "snapshot_capture_path":
            profile
            .snapshot_capture_path,
    }

    if (
        runtime.output_format.value
        == "json"
    ):
        emit_json(value)
        return

    render_detail(
        value,
        title=f"Profile: {profile_name}",
    )


@app.command("set")
def set_profile(
    context: typer.Context,
    name: str = typer.Argument(
        help="Profile name.",
    ),
    server: str | None = typer.Option(
        None,
        "--server",
        help="Topo AI API URL.",
    ),
    token_env: str | None = typer.Option(
        None,
        "--token-env",
        help=(
            "Environment variable containing "
            "the API token."
        ),
    ),
    timeout: float | None = typer.Option(
        None,
        "--timeout",
        min=1.0,
        help="Request timeout in seconds.",
    ),
    capture_path: str | None = typer.Option(
        None,
        "--capture-path",
        help=(
            "Backend snapshot-capture "
            "endpoint path."
        ),
    ),
    verify_tls: bool = typer.Option(
        False,
        "--verify-tls",
        help="Enable TLS verification.",
    ),
    max_retries: int | None = typer.Option(
      None,
      "--retries",
      min=0,
      help=(
          "Retry count for temporary "
          "failures."
        ),
    ),
    retry_backoff: float | None = (
     typer.Option(
         None,
         "--retry-backoff",
         min=0.0,
         help=(
             "Initial retry backoff "
             "in seconds."
            ),
        )
    ),
    insecure: bool = typer.Option(
        False,
        "--insecure",
        help="Disable TLS verification.",
    ),
) -> None:
    runtime = get_runtime(context)

    if verify_tls and insecure:
        abort(
            InputValidationFailure(
                "Use either --verify-tls "
                "or --insecure, not both."
            )
        )

    existing = (
        runtime.config.profiles.get(name)
        or Profile()
    )

    tls_value = existing.verify_tls

    if verify_tls:
        tls_value = True

    if insecure:
        tls_value = False

    try:
        api_url = validate_api_url(server or existing.api_url or DEFAULT_API_URL)
    except ValueError as exc:
        abort(
            InputValidationFailure(
                str(exc)
            )
        )

    runtime.config.profiles[name] = (
        Profile(
            api_url=api_url,
            token_env=(
                token_env
                or existing.token_env
            ),
            verify_tls=tls_value,
            timeout=(
                timeout
                if timeout is not None
                else existing.timeout
            ),
            snapshot_capture_path=(
                capture_path
                or existing
                .snapshot_capture_path
            ),
            max_retries=(
                max_retries if max_retries is not None else existing.max_retries
            ),
            retry_backoff=(
                retry_backoff if retry_backoff is not None else existing.retry_backoff
            ),
        )
    )

    try:
        path = save_config(
            runtime.config
        )

    except TopoCliError as exc:
        abort(exc)

    typer.echo(
        f"Profile '{name}' saved to "
        f"{path}"
    )


@app.command("use")
def use_profile(
    context: typer.Context,
    name: str = typer.Argument(
        help="Profile to activate.",
    ),
) -> None:
    runtime = get_runtime(context)

    if name not in runtime.config.profiles:
        abort(
            ConfigurationError(
                f"Profile does not exist: "
                f"{name}"
            )
        )

    runtime.config.active_profile = name

    try:
        save_config(runtime.config)

    except TopoCliError as exc:
        abort(exc)

    typer.echo(
        f"Active profile: {name}"
    )


@app.command("delete")
def delete_profile(
    context: typer.Context,
    name: str = typer.Argument(
        help="Profile to delete.",
    ),
) -> None:
    runtime = get_runtime(context)

    if name not in runtime.config.profiles:
        abort(
            ConfigurationError(
                f"Profile does not exist: "
                f"{name}"
            )
        )

    if len(runtime.config.profiles) == 1:
        abort(
            ConfigurationError(
                "The final profile cannot "
                "be deleted."
            )
        )

    del runtime.config.profiles[name]

    if (
        runtime.config.active_profile
        == name
    ):
        runtime.config.active_profile = (
            next(
                iter(
                    runtime.config.profiles
                )
            )
        )

    try:
        save_config(runtime.config)

    except TopoCliError as exc:
        abort(exc)

    typer.echo(
        f"Profile '{name}' deleted."
    )


@app.command("path")
def show_config_path() -> None:
    typer.echo(
        str(config_file_path())
    )
