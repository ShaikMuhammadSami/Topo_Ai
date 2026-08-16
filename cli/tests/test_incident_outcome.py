from types import SimpleNamespace

import pytest

from topo_cli.client import TopoClient
import topo_cli.commands.incidents as incidents
from topo_cli.errors import ResourceNotFound
from topo_cli.output import OutputFormat


def _payload() -> dict:
    return {
        "outcome_id": "incident-outcome:1",
        "incident_id": "incident:1",
        "status": "resolved",
        "causal_analysis_id": (
            "causal-analysis:1"
        ),
        "response_plan_reference": (
            "response-plan:causal-analysis:1"
        ),
        "historical_topology_snapshot_id": (
            "snapshot:incident-time"
        ),
        "started_at": (
            "2026-08-16T10:00:00Z"
        ),
        "mitigated_at": (
            "2026-08-16T10:10:00Z"
        ),
        "resolved_at": (
            "2026-08-16T10:20:00Z"
        ),
        "time_to_mitigation_seconds": 600,
        "time_to_resolution_seconds": 1200,
        "original_root_cause": {
            "event_id": "event:commit",
            "entity_id": "entity:payments",
            "title": "Payment retry change",
            "source": "inferred",
            "evidence_ids": [
                "evidence:causal"
            ],
        },
        "final_root_cause": {
            "event_id": "event:commit",
            "entity_id": "entity:payments",
            "title": "Payment retry change",
            "source": "inferred",
            "evidence_ids": [
                "event:rollback"
            ],
        },
        "rca_verdict": "confirmed",
        "rca_confidence": 0.9,
        "resolution_summary": (
            "Rollback restored service."
        ),
        "actions_taken": [
            {
                "action_instance_id": (
                    "action:rollback"
                ),
                "response_plan_action_id": (
                    "plan:rollback"
                ),
                "change_event_id": (
                    "event:rollback"
                ),
                "action_type": (
                    "rollback_deployment"
                ),
                "title": (
                    "Rollback payments deployment"
                ),
                "actor": "payments-oncall",
                "source": "responder",
                "completed_at": (
                    "2026-08-16T10:09:00Z"
                ),
                "target_entity_ids": [
                    "entity:payments"
                ],
                "result": "successful",
                "effectiveness": "effective",
                "effectiveness_reason": (
                    "Recovery evidence aligned."
                ),
                "evidence_ids": [
                    "event:rollback"
                ],
            }
        ],
        "primary_resolution_action": {
            "action_instance_id": (
                "action:rollback"
            ),
            "title": (
                "Rollback payments deployment"
            ),
        },
        "response_plan_actions": [
            {
                "response_plan_action_id": (
                    "plan:rollback"
                ),
                "title": "Consider rollback",
                "category": (
                    "rollback_candidate"
                ),
                "follow_through": "followed",
                "effectiveness": "effective",
                "reason": (
                    "Durable action matched."
                ),
            }
        ],
        "recommendations_followed": [
            "plan:rollback"
        ],
        "recommendations_not_followed": [],
        "recommendations_unknown": [],
        "effective_action_ids": [
            "action:rollback"
        ],
        "ineffective_action_ids": [],
        "evidence_event_ids": [
            "event:commit",
            "event:rollback",
        ],
        "evidence_ids": [
            "evidence:causal",
            "event:rollback",
        ],
        "warnings": [],
    }


def test_client_requests_encoded_outcome_path() -> None:
    client = TopoClient.__new__(TopoClient)
    calls = []
    payload = _payload()

    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return payload

    client._request = request
    result = client.incident_outcome(
        "incident/1"
    )

    assert result is payload
    assert calls == [
        (
            "GET",
            (
                "/api/v1/incidents/"
                "incident%2F1/outcome"
            ),
            {},
        )
    ]


def test_outcome_json_preserves_complete_response(
    monkeypatch,
) -> None:
    payload = _payload()
    emitted = []
    runtime = SimpleNamespace(
        output_format=OutputFormat.JSON,
        client=SimpleNamespace(
            incident_outcome=(
                lambda incident_id: payload
            )
        ),
    )
    monkeypatch.setattr(
        incidents,
        "get_runtime",
        lambda context: runtime,
    )
    monkeypatch.setattr(
        incidents,
        "api_call",
        lambda operation: operation(),
    )
    monkeypatch.setattr(
        incidents,
        "emit_json",
        emitted.append,
    )

    incidents.incident_outcome(
        context=object(),
        incident_id="incident:1",
    )

    assert emitted == [payload]


def test_outcome_human_output_has_required_sections(
    monkeypatch,
) -> None:
    payload = _payload()
    details = []
    records = []
    runtime = SimpleNamespace(
        output_format=OutputFormat.TABLE,
        client=SimpleNamespace(
            incident_outcome=(
                lambda incident_id: payload
            )
        ),
    )
    monkeypatch.setattr(
        incidents,
        "get_runtime",
        lambda context: runtime,
    )
    monkeypatch.setattr(
        incidents,
        "api_call",
        lambda operation: operation(),
    )
    monkeypatch.setattr(
        incidents,
        "render_data",
        lambda value, **kwargs: details.append(
            (kwargs["title"], value)
        ),
    )
    monkeypatch.setattr(
        incidents,
        "render_records",
        lambda value, **kwargs: records.append(
            (kwargs["title"], value)
        ),
    )

    incidents.incident_outcome(
        context=object(),
        incident_id="incident:1",
    )

    summary = details[0][1]
    sections = {
        title: values
        for title, values in records
    }

    assert summary["RCA Verdict"] == (
        "confirmed"
    )
    assert summary[
        "Primary Resolution Action"
    ] == "Rollback payments deployment"
    assert summary[
        "Time to Mitigation (seconds)"
    ] == 600
    assert "Actions Taken" in sections
    assert (
        "Response Plan Follow-through"
        in sections
    )


def test_partial_inconclusive_outcome_renders(
    monkeypatch,
) -> None:
    payload = _payload()
    payload.update(
        {
            "status": "investigating",
            "mitigated_at": None,
            "resolved_at": None,
            "time_to_mitigation_seconds": None,
            "time_to_resolution_seconds": None,
            "final_root_cause": None,
            "rca_verdict": "inconclusive",
            "primary_resolution_action": None,
            "actions_taken": [],
            "warnings": [
                "No responder actions recorded."
            ],
        }
    )
    details = []
    runtime = SimpleNamespace(
        output_format=OutputFormat.TABLE,
        client=SimpleNamespace(
            incident_outcome=(
                lambda incident_id: payload
            )
        ),
    )
    monkeypatch.setattr(
        incidents,
        "get_runtime",
        lambda context: runtime,
    )
    monkeypatch.setattr(
        incidents,
        "api_call",
        lambda operation: operation(),
    )
    monkeypatch.setattr(
        incidents,
        "render_data",
        lambda value, **kwargs: details.append(
            value
        ),
    )
    monkeypatch.setattr(
        incidents,
        "render_records",
        lambda *args, **kwargs: None,
    )

    incidents.incident_outcome(
        context=object(),
        incident_id="incident:1",
    )

    assert details[0]["Outcome Status"] == (
        "investigating"
    )
    assert details[0]["RCA Verdict"] == (
        "inconclusive"
    )
    assert details[0]["Warnings"] == [
        "No responder actions recorded."
    ]


def test_outcome_uses_normal_cli_error_handling(
    monkeypatch,
) -> None:
    runtime = SimpleNamespace(
        output_format=OutputFormat.TABLE,
        client=SimpleNamespace(
            incident_outcome=(
                lambda incident_id: {}
            )
        ),
    )
    monkeypatch.setattr(
        incidents,
        "get_runtime",
        lambda context: runtime,
    )

    def fail(operation):
        raise ResourceNotFound(
            "Outcome not found."
        )

    monkeypatch.setattr(
        incidents,
        "api_call",
        fail,
    )

    with pytest.raises(ResourceNotFound):
        incidents.incident_outcome(
            context=object(),
            incident_id="incident:missing",
        )
