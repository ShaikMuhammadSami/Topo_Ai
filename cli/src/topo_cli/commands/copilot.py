from __future__ import annotations

import typer

from topo_cli.errors import (
    InputValidationFailure,
    abort,
)
from topo_cli.output import (
    ColumnSpec,
    OutputFormat,
    console,
    emit_json,
    render_detail,
    render_records,
)
from topo_cli.runtime import (
    api_call,
    get_runtime,
)


app = typer.Typer(
    help=(
        "Ask evidence-grounded questions "
        "about incidents."
    ),
    no_args_is_help=True,
)


VALID_PROVIDERS = {
    "auto",
    "groq",
    "deterministic",
}


def _validate_provider(
    provider: str,
) -> str:
    value = provider.strip().lower()

    if value not in VALID_PROVIDERS:
        abort(
            InputValidationFailure(
                "Provider must be one of: "
                "auto, groq, deterministic."
            )
        )

    return value


def _latest_session(
    context: typer.Context,
    incident_id: str,
) -> dict | None:
    runtime = get_runtime(context)

    sessions = api_call(
        lambda:
            runtime.client
            .list_copilot_sessions(
                incident_id=incident_id,
                limit=50,
            )
    )

    active = next(
        (
            item
            for item in sessions
            if item.get("status")
            == "active"
        ),
        None,
    )

    return active or (
        sessions[0]
        if sessions
        else None
    )


def _display_session(
    context: typer.Context,
    value: dict,
) -> None:
    runtime = get_runtime(context)

    if (
        runtime.output_format
        == OutputFormat.JSON
    ):
        emit_json(value)
        return

    render_detail(
        {
            "session_id":
                value.get("session_id"),
            "incident_id":
                value.get("incident_id"),
            "title":
                value.get("title"),
            "provider":
                value.get("provider"),
            "model_name":
                value.get("model_name"),
            "status":
                value.get("status"),
            "message_count":
                value.get(
                    "message_count"
                ),
            "created_at":
                value.get("created_at"),
            "updated_at":
                value.get("updated_at"),
        },
        title="Incident Copilot Session",
    )

    messages = value.get(
        "messages",
        [],
    )

    if isinstance(messages, list):
        render_records(
            [
                item
                for item in messages
                if isinstance(item, dict)
            ],
            title="Copilot Conversation",
            columns=[
                ColumnSpec(
                    "TIME",
                    ("created_at",),
                ),
                ColumnSpec(
                    "ROLE",
                    ("role",),
                ),
                ColumnSpec(
                    "PROVIDER",
                    ("provider",),
                ),
                ColumnSpec(
                    "STATUS",
                    ("answer_status",),
                ),
                ColumnSpec(
                    "CONFIDENCE",
                    ("confidence",),
                ),
                ColumnSpec(
                    "MESSAGE",
                    ("content",),
                    max_width=100,
                ),
                ColumnSpec(
                    "EVIDENCE",
                    ("evidence_ids",),
                    max_width=80,
                ),
            ],
        )


def _display_answer(
    context: typer.Context,
    value: dict,
) -> None:
    runtime = get_runtime(context)

    if (
        runtime.output_format
        == OutputFormat.JSON
    ):
        emit_json(value)
        return

    assistant = value.get(
        "assistant_message",
        {},
    )

    if not isinstance(assistant, dict):
        emit_json(value)
        return

    render_detail(
        {
            "session_id":
                value.get("session_id"),
            "provider":
                assistant.get("provider"),
            "answer_status":
                assistant.get(
                    "answer_status"
                ),
            "confidence":
                assistant.get("confidence"),
            "created_at":
                assistant.get("created_at"),
            "evidence_ids":
                assistant.get(
                    "evidence_ids"
                ),
        },
        title="Copilot Answer",
    )

    console.print()
    console.print(
        assistant.get(
            "content",
            "",
        )
    )

    warning = assistant.get(
        "warning"
    )

    if warning:
        console.print()
        console.print(
            f"[yellow]{warning}[/yellow]"
        )


@app.command("new")
def new_session(
    context: typer.Context,
    incident_id: str = typer.Argument(
        ...,
        help="Stable incident ID.",
    ),
    title: str | None = typer.Option(
        None,
        "--title",
        help="Optional session title.",
    ),
    provider: str = typer.Option(
        "auto",
        "--provider",
        help=(
            "auto, groq, or "
            "deterministic"
        ),
    ),
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .create_copilot_session(
                incident_id=incident_id,
                title=title,
                provider=(
                    _validate_provider(
                        provider
                    )
                ),
            )
    )

    _display_session(
        context,
        result,
    )


@app.command("sessions")
def list_sessions(
    context: typer.Context,
    incident_id: str = typer.Argument(
        ...,
        help="Stable incident ID.",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        min=1,
        max=100,
    ),
    all_pages: bool = typer.Option(
        False,
        "--all",
        help="Retrieve every available page.",
    ),
    page_size: int = typer.Option(
       100,
       "--page-size",
       min=1,
       max=100,
    ),
    maximum_items: int | None = (
        typer.Option(
            None,
            "--max-items",
            min=1,
            help=(
               "Stop after this many records "
               "when using --all."
            ),
        )
    ),

) -> None:
    runtime = get_runtime(context)
    if all_pages:
     incidents = collect_pages(
         lambda offset, size:
             runtime.client.list_incidents(
                 limit=size,
                 offset=offset,
                ),
         page_size=page_size,
         maximum_items=maximum_items,
        )
    
    else:
        incidents = api_call(
         lambda:
             runtime.client.list_incidents(
                 limit=limit,
                 offset = 0,
                )
        )
    
    values = api_call(
        lambda:
            runtime.client
            .list_copilot_sessions(
                incident_id=incident_id,
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
        title="Copilot Sessions",
        columns=[
            ColumnSpec(
                "UPDATED",
                ("updated_at",),
            ),
            ColumnSpec(
                "STATUS",
                ("status",),
            ),
            ColumnSpec(
                "PROVIDER",
                ("provider",),
            ),
            ColumnSpec(
                "MODEL",
                ("model_name",),
            ),
            ColumnSpec(
                "MESSAGES",
                ("message_count",),
            ),
            ColumnSpec(
                "TITLE",
                ("title",),
                max_width=55,
            ),
            ColumnSpec(
                "SESSION ID",
                ("session_id",),
                max_width=65,
            ),
        ],
    )


@app.command("get")
def get_session(
    context: typer.Context,
    incident_id: str = typer.Argument(
        ...,
        help="Stable incident ID.",
    ),
    session_id: str = typer.Argument(
        ...,
        help="Copilot session ID.",
    ),
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .get_copilot_session(
                incident_id=incident_id,
                session_id=session_id,
            )
    )

    _display_session(
        context,
        result,
    )


@app.command("history")
def session_history(
    context: typer.Context,
    incident_id: str = typer.Argument(
        ...,
        help="Stable incident ID.",
    ),
    session_id: str | None = typer.Option(
        None,
        "--session-id",
        help=(
            "Session ID. Defaults to the "
            "most recently updated session."
        ),
    ),
) -> None:
    runtime = get_runtime(context)

    selected_id = session_id

    if selected_id is None:
        latest = _latest_session(
            context,
            incident_id,
        )

        if latest is None:
            console.print(
                "[dim]No Copilot sessions "
                "were found.[/dim]"
            )
            return

        selected_id = str(
            latest["session_id"]
        )

    result = api_call(
        lambda:
            runtime.client
            .get_copilot_session(
                incident_id=incident_id,
                session_id=selected_id,
            )
    )

    _display_session(
        context,
        result,
    )


@app.command("ask")
def ask_question(
    context: typer.Context,
    incident_id: str = typer.Argument(
        ...,
        help="Stable incident ID.",
    ),
    question: str = typer.Argument(
        ...,
        help="Question for Topo Copilot.",
    ),
    session_id: str | None = typer.Option(
        None,
        "--session-id",
        help=(
            "Existing session ID. When "
            "omitted, the latest active "
            "session is used."
        ),
    ),
    provider: str = typer.Option(
        "auto",
        "--provider",
        help=(
            "Provider used when a new "
            "session must be created."
        ),
    ),
    new_session: bool = typer.Option(
        False,
        "--new",
        help=(
            "Create a new Copilot session "
            "before asking."
        ),
    ),
) -> None:
    runtime = get_runtime(context)

    if not question.strip():
        abort(
            InputValidationFailure(
                "Question cannot be empty."
            )
        )

    selected_id = session_id

    if (
        selected_id is None
        and not new_session
    ):
        latest = _latest_session(
            context,
            incident_id,
        )

        if latest is not None:
            selected_id = str(
                latest["session_id"]
            )

    if selected_id is None:
        created = api_call(
            lambda:
                runtime.client
                .create_copilot_session(
                    incident_id=incident_id,
                    title=None,
                    provider=(
                        _validate_provider(
                            provider
                        )
                    ),
                )
        )

        selected_id = str(
            created["session_id"]
        )

    result = api_call(
        lambda:
            runtime.client
            .send_copilot_message(
                incident_id=incident_id,
                session_id=selected_id,
                question=question.strip(),
            )
    )

    _display_answer(
        context,
        result,
    )