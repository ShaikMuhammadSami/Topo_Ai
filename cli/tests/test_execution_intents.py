from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from topo_cli.client import TopoClient
import topo_cli.commands.execution_intents as commands
from topo_cli.errors import AuthenticationFailure
from topo_cli.output import OutputFormat


def _payload(
    *,
    status: str = "pending",
    claimable: bool = True,
    invalid_reason: str | None = None,
) -> dict:
    return {
        "execution_id": "execution-intent:1",
        "incident_id": "incident:1",
        "approval_id": "approval:1",
        "action_id": "action:rollback",
        "action_family": "rollback",
        "status": status,
        "approval_evidence_fingerprint": "a" * 64,
        "policy_version": "14f-v1",
        "target": {
            "entity_ids": ["entity:payments"],
            "change_event_id": "event:deploy",
            "uniquely_identified": True,
        },
        "risk": "high",
        "idempotency_key": "b" * 64,
        "execution_snapshot": {
            "requires_pre_execution_revalidation": True,
        },
        "created_by": "operator:creator",
        "created_by_display_name": "Creator",
        "created_by_roles": ["operator"],
        "created_at": "2026-08-16T13:00:00+00:00",
        "claimed_by": None,
        "claimed_by_display_name": None,
        "claimed_at": None,
        "claim_expires_at": None,
        "claim_generation": 0,
        "attempt_count": 0,
        "row_version": 1,
        "updated_at": "2026-08-16T13:00:00+00:00",
        "approval_currently_valid": claimable,
        "currently_claimable": claimable,
        "retryable": claimable,
        "invalid_reason": invalid_reason,
        "cancellation_reason": (
            invalid_reason
            if status == "cancelled"
            else None
        ),
        "execution_performed": False,
        "future_execution_contract": {
            "intent_reference_valid": claimable,
            "requires_pre_execution_revalidation": True,
            "execution_performed": False,
        },
        "audit_events": [
            {
                "sequence": 1,
                "occurred_at": "2026-08-16T13:00:00+00:00",
                "event_type": "created",
                "from_status": None,
                "to_status": "pending",
                "actor_subject": "operator:creator",
                "claim_generation": 0,
                "reason": "Created.",
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


def test_client_create_path_is_encoded_and_body_is_minimal(
) -> None:
    client = TopoClient.__new__(TopoClient)
    calls = []
    payload = _payload()
    client._request = (
        lambda method, path, **kwargs: (
            calls.append((method, path, kwargs))
            or payload
        )
    )

    result = client.create_execution_intent(
        "incident/1",
        approval_id="approval/1",
    )

    assert result is payload
    assert calls == [
        (
            "POST",
            (
                "/api/v1/incidents/incident%2F1/"
                "execution-intents"
            ),
            {"json_body": {"approval_id": "approval/1"}},
        )
    ]
    assert "target" not in calls[0][2]["json_body"]
    assert "status" not in calls[0][2]["json_body"]


def test_client_lists_bounded_filtered_intents() -> None:
    client = TopoClient.__new__(TopoClient)
    calls = []
    payload = [_payload()]
    client._request = (
        lambda method, path, **kwargs: (
            calls.append((method, path, kwargs))
            or payload
        )
    )

    result = client.list_execution_intents(
        "incident/1",
        status="pending",
        approval_id="approval:1",
        action_id="action:rollback",
        limit=25,
        offset=5,
    )

    assert result == payload
    assert calls[0][0:2] == (
        "GET",
        (
            "/api/v1/incidents/incident%2F1/"
            "execution-intents"
        ),
    )
    assert calls[0][2]["params"] == {
        "status": "pending",
        "approval_id": "approval:1",
        "action_id": "action:rollback",
        "limit": 25,
        "offset": 5,
    }


def test_client_get_encodes_both_identifiers() -> None:
    client = TopoClient.__new__(TopoClient)
    calls = []
    client._request = (
        lambda method, path, **kwargs: (
            calls.append((method, path))
            or _payload()
        )
    )

    client.get_execution_intent(
        "incident/1",
        "execution-intent/1",
    )

    assert calls == [
        (
            "GET",
            (
                "/api/v1/incidents/incident%2F1/"
                "execution-intents/execution-intent%2F1"
            ),
        )
    ]


def test_client_cancel_path_and_reason() -> None:
    client = TopoClient.__new__(TopoClient)
    calls = []
    client._request = (
        lambda method, path, **kwargs: (
            calls.append((method, path, kwargs))
            or _payload(status="cancelled", claimable=False)
        )
    )

    client.cancel_execution_intent(
        "incident/1",
        "execution-intent/1",
        reason="Stop before processing.",
    )

    assert calls[0][1].endswith(
        "/execution-intent%2F1/cancel"
    )
    assert calls[0][2]["json_body"] == {
        "reason": "Stop before processing."
    }


def test_json_create_preserves_complete_backend_response(
    monkeypatch,
) -> None:
    payload = _payload()
    emitted = []
    client = SimpleNamespace(
        create_execution_intent=(
            lambda *args, **kwargs: payload
        )
    )
    monkeypatch.setattr(
        commands,
        "get_runtime",
        lambda context: _runtime(client),
    )
    monkeypatch.setattr(
        commands,
        "api_call",
        lambda operation: operation(),
    )
    monkeypatch.setattr(
        commands,
        "emit_json",
        emitted.append,
    )

    commands.create_intent(
        context=object(),
        incident_id="incident:1",
        approval_id="approval:1",
    )

    assert emitted == [payload]


def test_human_output_shows_transaction_and_audit_fields(
    monkeypatch,
) -> None:
    payload = _payload(
        status="invalidated",
        claimable=False,
        invalid_reason="Source approval was revoked.",
    )
    details = []
    ledgers = []
    client = SimpleNamespace(
        get_execution_intent=(
            lambda *args, **kwargs: payload
        )
    )
    monkeypatch.setattr(
        commands,
        "get_runtime",
        lambda context: _runtime(
            client,
            OutputFormat.TABLE,
        ),
    )
    monkeypatch.setattr(
        commands,
        "api_call",
        lambda operation: operation(),
    )
    monkeypatch.setattr(
        commands,
        "render_data",
        lambda value, **kwargs: details.append(value),
    )
    monkeypatch.setattr(
        commands,
        "render_records",
        lambda value, **kwargs: ledgers.append(
            (kwargs["title"], value)
        ),
    )

    commands.get_intent(
        context=object(),
        incident_id="incident:1",
        execution_id="execution-intent:1",
    )

    fields = details[0]
    assert fields["Status"] == "invalidated"
    assert fields["Currently Claimable"] is False
    assert fields["Invalid Reason"] == (
        "Source approval was revoked."
    )
    assert fields["Execution Performed"] is False
    assert fields["Pre-execution Revalidation"] is True
    assert ledgers[0][0] == "Execution Intent Audit Ledger"


def test_list_human_output_shows_claimability(
    monkeypatch,
) -> None:
    payload = [_payload()]
    rendered = []
    client = SimpleNamespace(
        list_execution_intents=(
            lambda *args, **kwargs: payload
        )
    )
    monkeypatch.setattr(
        commands,
        "get_runtime",
        lambda context: _runtime(
            client,
            OutputFormat.TABLE,
        ),
    )
    monkeypatch.setattr(
        commands,
        "api_call",
        lambda operation: operation(),
    )
    monkeypatch.setattr(
        commands,
        "render_records",
        lambda value, **kwargs: rendered.append(value),
    )

    commands.list_intents(
        context=object(),
        incident_id="incident:1",
        status=None,
        approval_id=None,
        action_id=None,
        limit=50,
        offset=0,
    )

    assert rendered == [payload]


def test_cli_exposes_no_worker_claim_or_execute_command() -> None:
    command_names = {
        command.name
        for command in commands.app.registered_commands
    }

    assert command_names == {
        "list",
        "get",
        "create",
        "cancel",
    }
    assert "claim" not in command_names
    assert "execute" not in command_names


def test_authorization_error_maps_to_authentication_failure(
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
            "http://topo.test/execution-intents",
        ),
    )

    with pytest.raises(AuthenticationFailure):
        client._raise_for_status(response)
