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
        "Request and audit evidence-bound human "
        "action approvals."
    ),
    no_args_is_help=True,
)


def _approval_fields(
    value: dict,
) -> dict[str, object]:
    snapshot = value.get(
        "readiness_snapshot"
    )
    target = value.get("target")

    if not isinstance(snapshot, dict):
        snapshot = {}

    if not isinstance(target, dict):
        target = {}

    return {
        "Approval ID": value.get(
            "approval_id"
        ),
        "Incident": value.get(
            "incident_id"
        ),
        "Action": (
            snapshot.get("action_title")
            or value.get("action_id")
        ),
        "Action ID": value.get("action_id"),
        "Family": value.get(
            "action_family"
        ),
        "Status": value.get("status"),
        "Risk": value.get("risk"),
        "Policy Version": value.get(
            "policy_version"
        ),
        "Evidence Fingerprint": value.get(
            "evidence_fingerprint"
        ),
        "Requested By": value.get(
            "requested_by"
        ),
        "Requested At": value.get(
            "requested_at"
        ),
        "Decided By": value.get(
            "decided_by"
        ),
        "Decided At": value.get(
            "decided_at"
        ),
        "Expires At": value.get(
            "expires_at"
        ),
        "Currently Valid": value.get(
            "currently_valid"
        ),
        "Target Entities": target.get(
            "entity_ids",
            [],
        ),
        "Target Change": target.get(
            "change_event_id"
        ),
        "Readiness at Request": value.get(
            "readiness_status_at_request"
        ),
        "Request Reason": value.get(
            "request_reason"
        ),
        "Decision Reason": value.get(
            "decision_reason"
        ),
        "Invalid Reason": value.get(
            "invalid_reason"
        ),
        "Revocation Reason": value.get(
            "revocation_reason"
        ),
        "Execution Performed": (
            (
                value.get(
                    "future_execution_contract"
                )
                or {}
            ).get("execution_performed")
            if isinstance(
                value.get(
                    "future_execution_contract"
                ),
                dict,
            )
            else None
        ),
    }


def _render_detail(
    value: dict,
) -> None:
    render_data(
        _approval_fields(value),
        output_format=OutputFormat.TABLE,
        title="Action Approval",
    )
    events = value.get("audit_events", [])

    if isinstance(events, list) and events:
        render_records(
            [
                event
                for event in events
                if isinstance(event, dict)
            ],
            title="Approval Audit Ledger",
            columns=[
                ColumnSpec(
                    "#",
                    ("sequence",),
                ),
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
                    "REASON",
                    ("reason",),
                    max_width=70,
                ),
            ],
        )


def _emit_detail(
    runtime,
    value: dict,
) -> None:
    if runtime.output_format == OutputFormat.JSON:
        emit_json(value)
        return

    _render_detail(value)


@app.command("list")
def list_approvals(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
    status: str | None = typer.Option(
        None,
        "--status",
        help="Filter by approval status.",
    ),
    action_id: str | None = typer.Option(
        None,
        "--action-id",
        help="Filter by exact response-plan action ID.",
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
        lambda:
            runtime.client
            .list_action_approvals(
                incident_id,
                status=status,
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
        title="Action Approval History",
        columns=[
            ColumnSpec(
                "APPROVAL ID",
                ("approval_id",),
                max_width=48,
            ),
            ColumnSpec(
                "ACTION ID",
                ("action_id",),
                max_width=45,
            ),
            ColumnSpec(
                "FAMILY",
                ("action_family",),
            ),
            ColumnSpec(
                "STATUS",
                ("status",),
            ),
            ColumnSpec(
                "VALID",
                ("currently_valid",),
            ),
            ColumnSpec(
                "REQUESTED BY",
                ("requested_by",),
            ),
            ColumnSpec(
                "DECIDED BY",
                ("decided_by",),
            ),
            ColumnSpec(
                "EXPIRES",
                ("expires_at",),
            ),
            ColumnSpec(
                "INVALID / REVOCATION REASON",
                (
                    "invalid_reason",
                    "revocation_reason",
                ),
                max_width=65,
            ),
        ],
    )


@app.command("get")
def get_approval(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
    approval_id: str = typer.Argument(
        help="Stable approval ID.",
    ),
) -> None:
    runtime = get_runtime(context)
    result = api_call(
        lambda:
            runtime.client.get_action_approval(
                incident_id,
                approval_id,
            )
    )
    _emit_detail(runtime, result)


@app.command("request")
def request_approval(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
    action_id: str = typer.Argument(
        help="Approval-ready 14F action ID.",
    ),
    reason: str | None = typer.Option(
        None,
        "--reason",
        help="Optional audit reason.",
    ),
) -> None:
    runtime = get_runtime(context)
    result = api_call(
        lambda:
            runtime.client
            .request_action_approval(
                incident_id,
                action_id=action_id,
                reason=reason,
            )
    )
    _emit_detail(runtime, result)


def _decision(
    context: typer.Context,
    *,
    incident_id: str,
    approval_id: str,
    decision: str,
    reason: str | None,
) -> None:
    runtime = get_runtime(context)
    result = api_call(
        lambda:
            runtime.client
            .decide_action_approval(
                incident_id,
                approval_id,
                decision=decision,
                reason=reason,
            )
    )
    _emit_detail(runtime, result)


@app.command("approve")
def approve(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
    approval_id: str = typer.Argument(
        help="Pending approval ID.",
    ),
    reason: str | None = typer.Option(
        None,
        "--reason",
        help="Optional decision reason.",
    ),
) -> None:
    _decision(
        context,
        incident_id=incident_id,
        approval_id=approval_id,
        decision="approve",
        reason=reason,
    )


@app.command("reject")
def reject(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
    approval_id: str = typer.Argument(
        help="Pending approval ID.",
    ),
    reason: str | None = typer.Option(
        None,
        "--reason",
        help="Optional decision reason.",
    ),
) -> None:
    _decision(
        context,
        incident_id=incident_id,
        approval_id=approval_id,
        decision="reject",
        reason=reason,
    )


@app.command("revoke")
def revoke(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
    approval_id: str = typer.Argument(
        help="Approved approval ID.",
    ),
    reason: str = typer.Option(
        ...,
        "--reason",
        help="Required revocation reason.",
    ),
) -> None:
    runtime = get_runtime(context)
    result = api_call(
        lambda:
            runtime.client
            .revoke_action_approval(
                incident_id,
                approval_id,
                reason=reason,
            )
    )
    _emit_detail(runtime, result)
