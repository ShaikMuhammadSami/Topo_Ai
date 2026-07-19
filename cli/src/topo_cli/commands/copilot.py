from __future__ import annotations

import typer

from topo_cli.errors import (
    InputValidationFailure,
    abort,
)
from topo_cli.output import (
    ColumnSpec,
    OutputFormat,
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
        "Generate and track incident "
        "investigation plans."
    ),
    no_args_is_help=True,
)


VALID_PROVIDERS = {
    "auto",
    "groq",
    "deterministic",
}


VALID_STEP_STATUSES = {
    "pending",
    "in_progress",
    "completed",
    "skipped",
    "blocked",
}


def _provider(
    value: str,
) -> str:
    normalized = value.lower().strip()

    if normalized not in VALID_PROVIDERS:
        abort(
            InputValidationFailure(
                "Provider must be one of: "
                "auto, groq, deterministic."
            )
        )

    return normalized


def _display_plan(
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
            "plan_id":
                value.get("plan_id"),
            "incident_id":
                value.get("incident_id"),
            "title":
                value.get("title"),
            "status":
                value.get("status"),
            "provider":
                value.get("provider"),
            "model_name":
                value.get("model_name"),
            "confidence":
                value.get(
                    "overall_confidence"
                ),
            "step_count":
                value.get("step_count"),
            "completed":
                value.get(
                    "completed_step_count"
                ),
            "blocked":
                value.get(
                    "blocked_step_count"
                ),
            "evidence_count":
                value.get(
                    "evidence_count"
                ),
            "created_at":
                value.get("created_at"),
            "updated_at":
                value.get("updated_at"),
        },
        title="Investigation Plan",
    )

    steps = value.get(
        "steps",
        [],
    )

    if isinstance(steps, list):
        render_records(
            [
                item
                for item in steps
                if isinstance(item, dict)
            ],
            title="Investigation Steps",
            columns=[
                ColumnSpec(
                    "STEP",
                    ("sequence",),
                ),
                ColumnSpec(
                    "STATUS",
                    ("status",),
                ),
                ColumnSpec(
                    "TITLE",
                    ("title",),
                    max_width=48,
                ),
                ColumnSpec(
                    "TARGET",
                    ("target",),
                    max_width=40,
                ),
                ColumnSpec(
                    "TYPE",
                    ("command_type",),
                ),
                ColumnSpec(
                    "COMMAND",
                    ("command",),
                    max_width=80,
                ),
                ColumnSpec(
                    "FINDING",
                    ("finding",),
                    max_width=55,
                ),
                ColumnSpec(
                    "STEP ID",
                    ("step_id",),
                    max_width=55,
                ),
            ],
        )


@app.command("generate")
def generate_plan(
    context: typer.Context,
    incident_id: str = typer.Argument(
        ...,
        help="Stable incident ID.",
    ),
    provider: str = typer.Option(
        "auto",
        "--provider",
    ),
    force_regenerate: bool = typer.Option(
        False,
        "--force",
        help="Generate a new plan.",
    ),
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .generate_investigation_plan(
                incident_id=incident_id,
                provider=_provider(
                    provider
                ),
                force_regenerate=(
                    force_regenerate
                ),
            )
    )

    _display_plan(
        context,
        result,
    )


@app.command("list")
def list_plans(
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
) -> None:
    runtime = get_runtime(context)

    values = api_call(
        lambda:
            runtime.client
            .list_investigation_plans(
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
        title="Investigation Plans",
        columns=[
            ColumnSpec(
                "CREATED",
                ("created_at",),
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
                "CONFIDENCE",
                ("overall_confidence",),
            ),
            ColumnSpec(
                "COMPLETE",
                (
                    "completed_step_count",
                ),
            ),
            ColumnSpec(
                "TOTAL",
                ("step_count",),
            ),
            ColumnSpec(
                "TITLE",
                ("title",),
                max_width=55,
            ),
            ColumnSpec(
                "PLAN ID",
                ("plan_id",),
                max_width=65,
            ),
        ],
    )


@app.command("get")
def get_plan(
    context: typer.Context,
    incident_id: str = typer.Argument(
        ...,
        help="Stable incident ID.",
    ),
    plan_id: str = typer.Argument(
        ...,
        help="Investigation plan ID.",
    ),
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .get_investigation_plan(
                incident_id=incident_id,
                plan_id=plan_id,
            )
    )

    _display_plan(
        context,
        result,
    )


@app.command("update-step")
def update_step(
    context: typer.Context,
    incident_id: str = typer.Argument(
        ...,
        help="Stable incident ID.",
    ),
    plan_id: str = typer.Argument(
        ...,
        help="Investigation plan ID.",
    ),
    step_id: str = typer.Argument(
        ...,
        help="Investigation step ID.",
    ),
    status: str | None = typer.Option(
        None,
        "--status",
        help=(
            "pending, in_progress, "
            "completed, skipped, or blocked"
        ),
    ),
    finding: str | None = typer.Option(
        None,
        "--finding",
        help="Observed investigation result.",
    ),
    notes: str | None = typer.Option(
        None,
        "--notes",
        help="Responder notes.",
    ),
) -> None:
    if (
        status is None
        and finding is None
        and notes is None
    ):
        abort(
            InputValidationFailure(
                "Provide --status, --finding, "
                "or --notes."
            )
        )

    normalized_status = None

    if status is not None:
        normalized_status = (
            status.lower().strip()
        )

        if (
            normalized_status
            not in VALID_STEP_STATUSES
        ):
            abort(
                InputValidationFailure(
                    "Invalid investigation-step "
                    "status."
                )
            )

    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .update_investigation_step(
                incident_id=incident_id,
                plan_id=plan_id,
                step_id=step_id,
                status=normalized_status,
                finding=finding,
                responder_notes=notes,
            )
    )

    _display_plan(
        context,
        result,
    )