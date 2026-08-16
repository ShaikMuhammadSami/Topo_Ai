from __future__ import annotations

from pathlib import Path

import typer

from topo_cli.errors import (
    FileOperationFailure,
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
    collect_pages,
    get_runtime,
)


app = typer.Typer(
    help=(
        "Generate, review and export "
        "post-incident reports."
    ),
    no_args_is_help=True,
)


VALID_PROVIDERS = {
    "auto",
    "openai",
    "groq",
    "deterministic",
}


VALID_REPORT_STATUSES = {
    "draft",
    "in_review",
    "approved",
    "rejected",
}


VALID_ACTION_STATUSES = {
    "open",
    "in_progress",
    "completed",
    "cancelled",
}


VALID_EXPORT_FORMATS = {
    "markdown",
    "json",
}


def _validate_provider(
    value: str,
) -> str:
    normalized = value.lower().strip()

    if normalized not in VALID_PROVIDERS:
        abort(
            InputValidationFailure(
                "Provider must be one of: "
                "auto, openai, groq, "
                "deterministic."
            )
        )

    return normalized


def _display_report(
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
            "report_id":
                value.get("report_id"),
            "incident_id":
                value.get("incident_id"),
            "version":
                value.get("version"),
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
            "action_items":
                value.get(
                    "action_item_count"
                ),
            "completed_actions":
                value.get(
                    "completed_action_item_count"
                ),
            "reviewer":
                value.get("reviewer_name"),
            "reviewed_at":
                value.get("reviewed_at"),
            "approved_at":
                value.get("approved_at"),
            "created_at":
                value.get("created_at"),
        },
        title="Post-Incident Report",
    )

    sections = {
        "executive_summary":
            value.get(
                "executive_summary"
            ),
        "root_cause":
            value.get("root_cause"),
        "business_impact":
            value.get(
                "business_impact"
            ),
        "technical_impact":
            value.get(
                "technical_impact"
            ),
        "remediation_summary":
            value.get(
                "remediation_summary"
            ),
        "recovery_validation":
            value.get(
                "recovery_validation"
            ),
        "evidence_gaps":
            value.get(
                "evidence_gaps"
            ),
    }

    render_detail(
        sections,
        title="Report Summary",
    )

    actions = value.get(
        "action_items",
        [],
    )

    if isinstance(actions, list):
        render_records(
            [
                item
                for item in actions
                if isinstance(item, dict)
            ],
            title="Corrective Actions",
            columns=[
                ColumnSpec(
                    "ACTION",
                    ("sequence",),
                ),
                ColumnSpec(
                    "PRIORITY",
                    ("priority",),
                ),
                ColumnSpec(
                    "STATUS",
                    ("status",),
                ),
                ColumnSpec(
                    "TITLE",
                    ("title",),
                    max_width=55,
                ),
                ColumnSpec(
                    "OWNER TEAM",
                    ("owner_team",),
                ),
                ColumnSpec(
                    "DUE DATE",
                    ("due_date",),
                ),
                ColumnSpec(
                    "ACTION ID",
                    ("action_item_id",),
                    max_width=55,
                ),
            ],
        )


@app.command("generate")
def generate_report(
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
        help="Generate a new report version.",
    ),
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .generate_post_incident_report(
                incident_id=incident_id,
                provider=(
                    _validate_provider(
                        provider
                    )
                ),
                force_regenerate=(
                    force_regenerate
                ),
            )
    )

    _display_report(
        context,
        result,
    )


@app.command("list")
def list_reports(
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
            .list_post_incident_reports(
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
        title="Post-Incident Reports",
        columns=[
            ColumnSpec(
                "VERSION",
                ("version",),
            ),
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
                "ACTIONS",
                ("action_item_count",),
            ),
            ColumnSpec(
                "COMPLETED",
                (
                    "completed_action_item_count",
                ),
            ),
            ColumnSpec(
                "REPORT ID",
                ("report_id",),
                max_width=65,
            ),
        ],
    )


@app.command("get")
def get_report(
    context: typer.Context,
    incident_id: str = typer.Argument(
        ...,
        help="Stable incident ID.",
    ),
    report_id: str = typer.Argument(
        ...,
        help="Post-incident report ID.",
    ),
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .get_post_incident_report(
                incident_id=incident_id,
                report_id=report_id,
            )
    )

    _display_report(
        context,
        result,
    )


@app.command("review")
def review_report(
    context: typer.Context,
    incident_id: str = typer.Argument(
        ...,
        help="Stable incident ID.",
    ),
    report_id: str = typer.Argument(
        ...,
        help="Post-incident report ID.",
    ),
    status: str = typer.Option(
        "in_review",
        "--status",
        help=(
            "draft, in_review, approved, "
            "or rejected"
        ),
    ),
    reviewer: str | None = typer.Option(
        None,
        "--reviewer",
    ),
    notes: str | None = typer.Option(
        None,
        "--notes",
    ),
) -> None:
    normalized_status = (
        status.lower().strip()
    )

    if (
        normalized_status
        not in VALID_REPORT_STATUSES
    ):
        abort(
            InputValidationFailure(
                "Invalid report status."
            )
        )

    if (
        normalized_status == "approved"
        and not reviewer
    ):
        abort(
            InputValidationFailure(
                "Approval requires "
                "--reviewer."
            )
        )

    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .update_post_incident_report(
                incident_id=incident_id,
                report_id=report_id,
                status=normalized_status,
                reviewer_name=reviewer,
                review_notes=notes,
            )
    )

    _display_report(
        context,
        result,
    )


@app.command("approve")
def approve_report(
    context: typer.Context,
    incident_id: str = typer.Argument(
        ...,
        help="Stable incident ID.",
    ),
    report_id: str = typer.Argument(
        ...,
        help="Post-incident report ID.",
    ),
    reviewer: str = typer.Option(
        ...,
        "--reviewer",
        help="Approving reviewer.",
    ),
    notes: str | None = typer.Option(
        None,
        "--notes",
    ),
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .update_post_incident_report(
                incident_id=incident_id,
                report_id=report_id,
                status="approved",
                reviewer_name=reviewer,
                review_notes=notes,
            )
    )

    _display_report(
        context,
        result,
    )


@app.command("reject")
def reject_report(
    context: typer.Context,
    incident_id: str = typer.Argument(
        ...,
        help="Stable incident ID.",
    ),
    report_id: str = typer.Argument(
        ...,
        help="Post-incident report ID.",
    ),
    reviewer: str = typer.Option(
        ...,
        "--reviewer",
    ),
    notes: str = typer.Option(
        ...,
        "--notes",
        help="Rejection reason.",
    ),
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .update_post_incident_report(
                incident_id=incident_id,
                report_id=report_id,
                status="rejected",
                reviewer_name=reviewer,
                review_notes=notes,
            )
    )

    _display_report(
        context,
        result,
    )


@app.command("update-action")
def update_action(
    context: typer.Context,
    incident_id: str = typer.Argument(
        ...,
        help="Stable incident ID.",
    ),
    report_id: str = typer.Argument(
        ...,
        help="Post-incident report ID.",
    ),
    action_item_id: str = typer.Argument(
        ...,
        help="Corrective-action ID.",
    ),
    status: str | None = typer.Option(
        None,
        "--status",
        help=(
            "open, in_progress, completed, "
            "or cancelled"
        ),
    ),
    owner_team: str | None = typer.Option(
        None,
        "--owner-team",
    ),
    owner_contact: str | None = typer.Option(
        None,
        "--owner-contact",
    ),
    due_date: str | None = typer.Option(
        None,
        "--due-date",
        help="Due date such as YYYY-MM-DD.",
    ),
    notes: str | None = typer.Option(
        None,
        "--notes",
    ),
) -> None:
    if all(
        value is None
        for value in (
            status,
            owner_team,
            owner_contact,
            due_date,
            notes,
        )
    ):
        abort(
            InputValidationFailure(
                "Provide at least one action "
                "field to update."
            )
        )

    normalized_status = None

    if status is not None:
        normalized_status = (
            status.lower().strip()
        )

        if (
            normalized_status
            not in VALID_ACTION_STATUSES
        ):
            abort(
                InputValidationFailure(
                    "Invalid corrective-action "
                    "status."
                )
            )

    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .update_report_action(
                incident_id=incident_id,
                report_id=report_id,
                action_item_id=(
                    action_item_id
                ),
                status=normalized_status,
                owner_team=owner_team,
                owner_contact=(
                    owner_contact
                ),
                due_date=due_date,
                notes=notes,
            )
    )

    _display_report(
        context,
        result,
    )


@app.command("export")
def export_report(
    context: typer.Context,
    incident_id: str = typer.Argument(
        ...,
        help="Stable incident ID.",
    ),
    report_id: str = typer.Argument(
        ...,
        help="Post-incident report ID.",
    ),
    export_format: str = typer.Option(
        "markdown",
        "--format",
        help="markdown or json",
    ),
    output_file: Path | None = typer.Option(
        None,
        "--file",
        "-f",
        dir_okay=False,
        help="Destination file.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help=(
            "Overwrite an existing file."
        ),
    ),
) -> None:
    normalized_format = (
        export_format.lower().strip()
    )

    if (
        normalized_format
        not in VALID_EXPORT_FORMATS
    ):
        abort(
            InputValidationFailure(
                "Export format must be "
                "markdown or json."
            )
        )

    runtime = get_runtime(context)

    content, suggested_name = api_call(
        lambda:
            runtime.client
            .export_post_incident_report(
                incident_id=incident_id,
                report_id=report_id,
                export_format=(
                    normalized_format
                ),
            )
    )

    destination = (
        output_file
        or Path(suggested_name)
    )

    if (
        destination.exists()
        and not overwrite
    ):
        abort(
            FileOperationFailure(
                f"File already exists: "
                f"{destination}. Use "
                "--overwrite to replace it."
            )
        )

    try:
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        destination.write_bytes(
            content
        )

    except OSError as exc:
        abort(
            FileOperationFailure(
                "Unable to save report to "
                f"{destination}: {exc}"
            )
        )

    typer.echo(
        f"Report exported to "
        f"{destination.resolve()}"
    )
