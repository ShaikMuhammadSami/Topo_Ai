from __future__ import annotations

import typer

from topo_cli.output import (
    ColumnSpec,
    OutputFormat,
    emit_json,
    render_data,
    render_records,
)
from topo_cli.runtime import api_call, get_runtime


app = typer.Typer(
    help=(
        "Create and inspect non-executing, "
        "approval-bound execution intents."
    ),
    no_args_is_help=True,
)


def _intent_fields(
    value: dict,
) -> dict[str, object]:
    target = value.get("target")
    contract = value.get(
        "future_execution_contract"
    )

    if not isinstance(target, dict):
        target = {}

    if not isinstance(contract, dict):
        contract = {}

    return {
        "Execution ID": value.get(
            "execution_id"
        ),
        "Incident": value.get("incident_id"),
        "Approval ID": value.get(
            "approval_id"
        ),
        "Action ID": value.get("action_id"),
        "Family": value.get("action_family"),
        "Status": value.get("status"),
        "Risk": value.get("risk"),
        "Policy Version": value.get(
            "policy_version"
        ),
        "Approval Fingerprint": value.get(
            "approval_evidence_fingerprint"
        ),
        "Idempotency Key": value.get(
            "idempotency_key"
        ),
        "Target Entities": target.get(
            "entity_ids",
            [],
        ),
        "Target Change": target.get(
            "change_event_id"
        ),
        "Created By": value.get("created_by"),
        "Created At": value.get("created_at"),
        "Claimed By": value.get("claimed_by"),
        "Claimed At": value.get("claimed_at"),
        "Claim Expires": value.get(
            "claim_expires_at"
        ),
        "Claim Generation": value.get(
            "claim_generation"
        ),
        "Attempt Count": value.get(
            "attempt_count"
        ),
        "Row Version": value.get("row_version"),
        "Approval Valid": value.get(
            "approval_currently_valid"
        ),
        "Currently Claimable": value.get(
            "currently_claimable"
        ),
        "Retryable": value.get("retryable"),
        "Cancellation Reason": value.get(
            "cancellation_reason"
        ),
        "Invalid Reason": value.get(
            "invalid_reason"
        ),
        "Execution Performed": value.get(
            "execution_performed"
        ),
        "Pre-execution Revalidation": (
            contract.get(
                "requires_pre_execution_revalidation"
            )
        ),
    }


def _render_detail(value: dict) -> None:
    render_data(
        _intent_fields(value),
        output_format=OutputFormat.TABLE,
        title="Execution Intent",
    )
    events = value.get("audit_events", [])

    if isinstance(events, list) and events:
        render_records(
            [
                event
                for event in events
                if isinstance(event, dict)
            ],
            title="Execution Intent Audit Ledger",
            columns=[
                ColumnSpec("#", ("sequence",)),
                ColumnSpec(
                    "WHEN",
                    ("occurred_at",),
                ),
                ColumnSpec(
                    "EVENT",
                    ("event_type",),
                ),
                ColumnSpec(
                    "FROM",
                    ("from_status",),
                ),
                ColumnSpec(
                    "TO",
                    ("to_status",),
                ),
                ColumnSpec(
                    "ACTOR",
                    ("actor_subject",),
                ),
                ColumnSpec(
                    "GENERATION",
                    ("claim_generation",),
                ),
                ColumnSpec(
                    "REASON",
                    ("reason",),
                    max_width=70,
                ),
            ],
        )


def _emit_detail(runtime, value: dict) -> None:
    if runtime.output_format == OutputFormat.JSON:
        emit_json(value)
        return

    _render_detail(value)


@app.command("list")
def list_intents(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
    status: str | None = typer.Option(
        None,
        "--status",
        help="Filter by execution-intent status.",
    ),
    approval_id: str | None = typer.Option(
        None,
        "--approval-id",
        help="Filter by exact approval ID.",
    ),
    action_id: str | None = typer.Option(
        None,
        "--action-id",
        help="Filter by exact action ID.",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        min=1,
        max=100,
    ),
    offset: int = typer.Option(
        0,
        "--offset",
        min=0,
    ),
) -> None:
    runtime = get_runtime(context)
    result = api_call(
        lambda: runtime.client.list_execution_intents(
            incident_id,
            status=status,
            approval_id=approval_id,
            action_id=action_id,
            limit=limit,
            offset=offset,
        )
    )

    if runtime.output_format == OutputFormat.JSON:
        emit_json(result)
        return

    render_records(
        result,
        title="Execution Intent History",
        columns=[
            ColumnSpec(
                "EXECUTION ID",
                ("execution_id",),
                max_width=48,
            ),
            ColumnSpec(
                "APPROVAL ID",
                ("approval_id",),
                max_width=42,
            ),
            ColumnSpec(
                "ACTION ID",
                ("action_id",),
                max_width=42,
            ),
            ColumnSpec("STATUS", ("status",)),
            ColumnSpec(
                "CLAIMABLE",
                ("currently_claimable",),
            ),
            ColumnSpec(
                "ATTEMPTS",
                ("attempt_count",),
            ),
            ColumnSpec(
                "CREATED BY",
                ("created_by",),
            ),
            ColumnSpec(
                "INVALID / CANCEL REASON",
                (
                    "invalid_reason",
                    "cancellation_reason",
                ),
                max_width=65,
            ),
        ],
    )


@app.command("get")
def get_intent(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
    execution_id: str = typer.Argument(
        help="Stable execution-intent ID.",
    ),
) -> None:
    runtime = get_runtime(context)
    result = api_call(
        lambda: runtime.client.get_execution_intent(
            incident_id,
            execution_id,
        )
    )
    _emit_detail(runtime, result)


@app.command("create")
def create_intent(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
    approval_id: str = typer.Argument(
        help="Currently valid approved 14G request ID.",
    ),
) -> None:
    runtime = get_runtime(context)
    result = api_call(
        lambda: runtime.client.create_execution_intent(
            incident_id,
            approval_id=approval_id,
        )
    )
    _emit_detail(runtime, result)


@app.command("cancel")
def cancel_intent(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
    execution_id: str = typer.Argument(
        help="Pending execution-intent ID.",
    ),
    reason: str = typer.Option(
        ...,
        "--reason",
        help="Required cancellation reason.",
    ),
) -> None:
    runtime = get_runtime(context)
    result = api_call(
        lambda: runtime.client.cancel_execution_intent(
            incident_id,
            execution_id,
            reason=reason,
        )
    )
    _emit_detail(runtime, result)
