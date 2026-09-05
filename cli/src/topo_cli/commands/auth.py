from __future__ import annotations

import typer

from topo_cli.errors import InputValidationFailure, abort
from topo_cli.output import ColumnSpec, OutputFormat, emit_json, render_records
from topo_cli.runtime import api_call, get_runtime


app = typer.Typer(
    help="Manage Topo authentication credentials.",
    no_args_is_help=True,
)
credentials_app = typer.Typer(
    help="Create, list, and revoke named API credentials.",
    no_args_is_help=True,
)
app.add_typer(credentials_app, name="credentials")


@credentials_app.command("create")
def create_credential(
    context: typer.Context,
    name: str = typer.Option(..., "--name", help="Operator-visible name."),
    caller_type: str = typer.Option(
        "human_api",
        "--caller-type",
        help="human_api or service_api.",
    ),
    subject: str | None = typer.Option(
        None,
        "--subject",
        help="Explicit legacy-local subject when provisioning a new identity.",
    ),
    principal_id: str | None = typer.Option(
        None,
        "--principal-id",
        help="Existing durable human or service principal ID.",
    ),
    display_name: str | None = typer.Option(None, "--display-name"),
    role: list[str] | None = typer.Option(None, "--role"),
    expires_in_days: int = typer.Option(
        30,
        "--expires-in-days",
        min=1,
        max=90,
    ),
    output_token_stdout: bool = typer.Option(
        False,
        "--output-token-stdout",
        help="Acknowledge and print the one-time raw credential to stdout.",
    ),
) -> None:
    if not output_token_stdout:
        abort(
            InputValidationFailure(
                "Credential creation requires --output-token-stdout so the "
                "one-time secret has an explicit destination."
            )
        )
    if caller_type not in {"human_api", "service_api"}:
        abort(
            InputValidationFailure(
                "--caller-type must be human_api or service_api."
            )
        )
    if subject is None and principal_id is None:
        abort(
            InputValidationFailure(
                "Credential creation requires --principal-id or explicit --subject."
            )
        )

    runtime = get_runtime(context)
    result = api_call(
        lambda: runtime.client.create_api_credential(
            name=name,
            caller_type=caller_type,
            subject=subject,
            principal_id=principal_id,
            display_name=display_name,
            roles=list(role or []),
            expires_in_days=expires_in_days,
        )
    )
    raw_secret = result.get("api_credential")
    if not isinstance(raw_secret, str) or not raw_secret:
        abort(InputValidationFailure("API did not return a one-time credential."))
    typer.echo(raw_secret)
    typer.echo(
        f"Created {result.get('credential_id', 'API credential')}. "
        "The secret is shown once and was not stored by the CLI.",
        err=True,
    )


@credentials_app.command("list")
def list_credentials(
    context: typer.Context,
    limit: int = typer.Option(100, "--limit", min=1, max=1000),
) -> None:
    runtime = get_runtime(context)
    values = api_call(
        lambda: runtime.client.list_api_credentials(limit=limit, offset=0)
    )
    if runtime.output_format is OutputFormat.JSON:
        emit_json(values)
        return
    render_records(
        values,
        title="Topo API Credentials",
        columns=[
            ColumnSpec("NAME", ("name",)),
            ColumnSpec("TYPE", ("caller_type",)),
            ColumnSpec("PRINCIPAL ID", ("principal_id",), max_width=60),
            ColumnSpec("SUBJECT", ("subject",)),
            ColumnSpec("ROLES", ("roles",)),
            ColumnSpec("EXPIRES", ("expires_at",)),
            ColumnSpec("REVOKED", ("revoked_at",)),
            ColumnSpec("LAST USED", ("last_used_at",)),
            ColumnSpec("CREDENTIAL ID", ("credential_id",), max_width=60),
        ],
    )


@credentials_app.command("revoke")
def revoke_credential(
    context: typer.Context,
    credential_id: str = typer.Argument(..., help="Credential ID to revoke."),
) -> None:
    runtime = get_runtime(context)
    result = api_call(
        lambda: runtime.client.revoke_api_credential(credential_id)
    )
    if runtime.output_format is OutputFormat.JSON:
        emit_json(result)
        return
    render_records(
        [result],
        title="Revoked Topo API Credential",
        columns=[
            ColumnSpec("NAME", ("name",)),
            ColumnSpec("CREDENTIAL ID", ("credential_id",), max_width=60),
            ColumnSpec("REVOKED", ("revoked_at",)),
            ColumnSpec("REVOKED BY", ("revoked_by_subject",)),
        ],
    )
