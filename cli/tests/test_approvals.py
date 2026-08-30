from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from topo_cli.client import TopoClient
import topo_cli.commands.approvals as approvals
from topo_cli.errors import (
    AuthorizationFailure,
)
from topo_cli.output import OutputFormat


def _payload(
    *,
    status: str = "pending",
    currently_valid: bool = False,
    invalid_reason: str | None = None,
) -> dict:
    return {
        "approval_id": "approval:1",
        "incident_id": "incident:1",
        "action_id": "action:rollback",
        "action_family": "rollback",
        "status": status,
        "risk": "high",
        "requires_human_approval": True,
        "policy_version": "14f-v1",
        "readiness_status_at_request": (
            "ready_for_human_approval"
        ),
        "evidence_fingerprint": "a" * 64,
        "target": {
            "entity_ids": ["entity:payments"],
            "change_event_id": "event:deploy",
            "uniquely_identified": True,
        },
        "readiness_snapshot": {
            "action_title": (
                "Consider rollback deployment"
            ),
        },
        "request_reason": "Prepare rollback.",
        "requested_by": "requester-user",
        "requested_by_display_name": (
            "Requester User"
        ),
        "requested_by_roles": ["operator"],
        "requested_at": (
            "2026-08-16T12:00:00+00:00"
        ),
        "decided_by": (
            "approver-user"
            if status != "pending"
            else None
        ),
        "decided_at": (
            "2026-08-16T12:01:00+00:00"
            if status != "pending"
            else None
        ),
        "decision_reason": None,
        "expires_at": (
            "2026-08-16T12:30:00+00:00"
        ),
        "revocation_reason": None,
        "currently_valid": currently_valid,
        "invalid_reason": invalid_reason,
        "future_execution_contract": {
            "approval_reference_valid": (
                currently_valid
            ),
            "execution_performed": False,
        },
        "audit_events": [
            {
                "event_id": "approval-event:1",
                "event_type": "requested",
                "from_status": None,
                "to_status": "pending",
                "actor_subject": "requester-user",
                "reason": "Prepare rollback.",
                "occurred_at": (
                    "2026-08-16T12:00:00+00:00"
                ),
            }
        ],
    }


def _runtime(
    client,
    output_format=OutputFormat.JSON,
):
    return SimpleNamespace(
        output_format=output_format,
        client=client,
    )


def test_client_request_path_is_encoded_and_body_is_minimal(
) -> None:
    client = TopoClient.__new__(TopoClient)
    calls = []
    payload = _payload()
    client._request = (
        lambda method, path, **kwargs: (
            calls.append(
                (method, path, kwargs)
            )
            or payload
        )
    )

    result = client.request_action_approval(
        "incident/1",
        action_id="action/rollback",
        reason="Prepare rollback.",
    )

    assert result is payload
    assert calls == [
        (
            "POST",
            (
                "/api/v1/incidents/incident%2F1/"
                "approvals"
            ),
            {
                "json_body": {
                    "action_id": "action/rollback",
                    "reason": "Prepare rollback.",
                }
            },
        )
    ]
    assert "target" not in calls[0][2][
        "json_body"
    ]
    assert "approved_by" not in calls[0][2][
        "json_body"
    ]


def test_client_lists_bounded_filtered_history(
) -> None:
    client = TopoClient.__new__(TopoClient)
    calls = []
    payload = [_payload()]
    client._request = (
        lambda method, path, **kwargs: (
            calls.append(
                (method, path, kwargs)
            )
            or payload
        )
    )

    result = client.list_action_approvals(
        "incident/1",
        status="pending",
        action_id="action:rollback",
        limit=25,
        offset=5,
    )

    assert result == payload
    assert calls[0][0:2] == (
        "GET",
        "/api/v1/incidents/incident%2F1/approvals",
    )
    assert calls[0][2]["params"] == {
        "status": "pending",
        "action_id": "action:rollback",
        "limit": 25,
        "offset": 5,
    }


def test_client_get_encodes_incident_and_approval_ids(
) -> None:
    client = TopoClient.__new__(TopoClient)
    calls = []
    payload = _payload()
    client._request = (
        lambda method, path, **kwargs: (
            calls.append((method, path))
            or payload
        )
    )

    client.get_action_approval(
        "incident/1",
        "approval/1",
    )

    assert calls == [
        (
            "GET",
            (
                "/api/v1/incidents/incident%2F1/"
                "approvals/approval%2F1"
            ),
        )
    ]


@pytest.mark.parametrize(
    "decision",
    ["approve", "reject"],
)
def test_client_decision_paths(
    decision,
) -> None:
    client = TopoClient.__new__(TopoClient)
    calls = []
    payload = _payload(status="approved")
    client._request = (
        lambda method, path, **kwargs: (
            calls.append(
                (method, path, kwargs)
            )
            or payload
        )
    )

    client.decide_action_approval(
        "incident/1",
        "approval/1",
        decision=decision,
        reason="Human decision.",
    )

    assert calls == [
        (
            "POST",
            (
                "/api/v1/incidents/incident%2F1/"
                "approvals/approval%2F1/"
                f"{decision}"
            ),
            {
                "json_body": {
                    "reason": "Human decision."
                }
            },
        )
    ]


def test_client_revoke_path_and_reason(
) -> None:
    client = TopoClient.__new__(TopoClient)
    calls = []
    payload = _payload(status="revoked")
    client._request = (
        lambda method, path, **kwargs: (
            calls.append(
                (method, path, kwargs)
            )
            or payload
        )
    )

    client.revoke_action_approval(
        "incident/1",
        "approval/1",
        reason="Conditions changed.",
    )

    assert calls[0][1].endswith(
        "/approval%2F1/revoke"
    )
    assert calls[0][2]["json_body"] == {
        "reason": "Conditions changed."
    }


def test_json_command_preserves_complete_backend_response(
    monkeypatch,
) -> None:
    payload = _payload()
    emitted = []
    client = SimpleNamespace(
        request_action_approval=(
            lambda *args, **kwargs: payload
        )
    )
    monkeypatch.setattr(
        approvals,
        "get_runtime",
        lambda context: _runtime(client),
    )
    monkeypatch.setattr(
        approvals,
        "api_call",
        lambda operation: operation(),
    )
    monkeypatch.setattr(
        approvals,
        "emit_json",
        emitted.append,
    )

    approvals.request_approval(
        context=object(),
        incident_id="incident:1",
        action_id="action:rollback",
        reason="Prepare rollback.",
    )

    assert emitted == [payload]


def test_human_output_renders_stale_approval_and_audit(
    monkeypatch,
) -> None:
    payload = _payload(
        status="invalidated",
        invalid_reason=(
            "The action target changed."
        ),
    )
    details = []
    records = []
    client = SimpleNamespace(
        get_action_approval=(
            lambda *args, **kwargs: payload
        )
    )
    monkeypatch.setattr(
        approvals,
        "get_runtime",
        lambda context: _runtime(
            client,
            OutputFormat.TABLE,
        ),
    )
    monkeypatch.setattr(
        approvals,
        "api_call",
        lambda operation: operation(),
    )
    monkeypatch.setattr(
        approvals,
        "render_data",
        lambda value, **kwargs: details.append(
            (kwargs["title"], value)
        ),
    )
    monkeypatch.setattr(
        approvals,
        "render_records",
        lambda value, **kwargs: records.append(
            (kwargs["title"], value)
        ),
    )

    approvals.get_approval(
        context=object(),
        incident_id="incident:1",
        approval_id="approval:1",
    )

    fields = details[0][1]
    assert fields["Status"] == "invalidated"
    assert fields["Currently Valid"] is False
    assert fields["Invalid Reason"] == (
        "The action target changed."
    )
    assert fields["Execution Performed"] is False
    assert records[0][0] == (
        "Approval Audit Ledger"
    )


def test_list_human_output_shows_current_validity(
    monkeypatch,
) -> None:
    payload = [
        _payload(
            status="approved",
            currently_valid=True,
        )
    ]
    records = []
    client = SimpleNamespace(
        list_action_approvals=(
            lambda *args, **kwargs: payload
        )
    )
    monkeypatch.setattr(
        approvals,
        "get_runtime",
        lambda context: _runtime(
            client,
            OutputFormat.TABLE,
        ),
    )
    monkeypatch.setattr(
        approvals,
        "api_call",
        lambda operation: operation(),
    )
    monkeypatch.setattr(
        approvals,
        "render_records",
        lambda value, **kwargs: records.append(
            value
        ),
    )

    approvals.list_approvals(
        context=object(),
        incident_id="incident:1",
        status=None,
        action_id=None,
        limit=50,
        offset=0,
    )

    assert records == [payload]


def test_authorization_error_maps_to_cli_authorization_failure(
) -> None:
    client = TopoClient.__new__(TopoClient)
    response = httpx.Response(
        403,
        json={
            "detail": (
                "The admin or operator role is required."
            )
        },
        request=httpx.Request(
            "POST",
            "http://topo.test/approvals",
        ),
    )

    with pytest.raises(AuthorizationFailure):
        client._raise_for_status(response)
