from __future__ import annotations

from types import SimpleNamespace

from topo_cli.client import TopoClient
import topo_cli.commands.incidents as incidents
from topo_cli.output import OutputFormat


def _payload() -> dict:
    return {
        "incident_id": "incident:1",
        "causal_analysis_id": "analysis:1",
        "response_plan_reference": (
            "response-plan:analysis:1"
        ),
        "policy_version": "14f-v1",
        "overall_execution_posture": (
            "validation_required"
        ),
        "response_intelligence": {
            "incident_id": "incident:1",
            "actions": [],
        },
        "actions": [
            {
                "action_id": "action:inspect",
                "baseline_rank": 1,
                "title": "Inspect deployment evidence",
                "action_family": "investigate",
                "risk": "low",
                "mutation": False,
                "readiness_status": (
                    "read_only_safe"
                ),
                "current_evidence_strength": "high",
                "historical_support": {
                    "level": "not_applicable",
                },
                "requires_human_approval": False,
                "target": {
                    "entity_ids": [
                        "entity:payments"
                    ],
                    "change_event_id": None,
                    "uniquely_identified": True,
                },
                "satisfied_preconditions": [
                    "baseline_action_present",
                    "non_mutating_action",
                ],
                "missing_preconditions": [],
                "blockers": [],
                "cautions": [],
                "approval_context": {
                    "required": False,
                    "owner_team": "payments",
                    "oncall_contact": (
                        "pagerduty:payments"
                    ),
                },
            },
            {
                "action_id": "action:rollback",
                "baseline_rank": 2,
                "title": "Consider rollback deployment",
                "action_family": "rollback",
                "risk": "high",
                "mutation": True,
                "readiness_status": (
                    "needs_validation"
                ),
                "current_evidence_strength": "high",
                "historical_support": {
                    "level": "strongly_supported",
                },
                "requires_human_approval": True,
                "target": {
                    "entity_ids": [
                        "entity:payments"
                    ],
                    "change_event_id": "event:deploy",
                    "uniquely_identified": True,
                },
                "satisfied_preconditions": [
                    "baseline_action_present",
                    "current_evidence_sufficient",
                ],
                "missing_preconditions": [
                    "validation:action:validate"
                ],
                "blockers": [],
                "cautions": [
                    "Validation is not recorded."
                ],
                "approval_context": {
                    "required": True,
                    "owner_team": "payments",
                    "oncall_contact": (
                        "pagerduty:payments"
                    ),
                },
            },
        ],
        "deterministic_summary": (
            "Validation is required. No action was approved or executed."
        ),
        "ai_summary": None,
        "ai_status": "not_requested",
        "warnings": [
            "Historical evidence is supporting evidence only."
        ],
    }


def _runtime(payload: dict, output_format):
    return SimpleNamespace(
        output_format=output_format,
        client=SimpleNamespace(
            incident_execution_readiness=(
                lambda *args, **kwargs: payload
            )
        ),
    )


def test_client_requests_encoded_execution_readiness_path(
) -> None:
    client = TopoClient.__new__(TopoClient)
    calls = []
    payload = _payload()

    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return payload

    client._request = request
    result = client.incident_execution_readiness(
        "incident/1",
        history_limit=7,
        min_similarity=0.6,
        include_ai=True,
    )

    assert result is payload
    assert calls == [
        (
            "GET",
            (
                "/api/v1/incidents/incident%2F1/"
                "execution-readiness"
            ),
            {
                "params": {
                    "history_limit": 7,
                    "min_similarity": 0.6,
                    "include_ai": True,
                }
            },
        )
    ]


def test_json_preserves_complete_backend_response(
    monkeypatch,
) -> None:
    payload = _payload()
    emitted = []
    monkeypatch.setattr(
        incidents,
        "get_runtime",
        lambda context: _runtime(
            payload,
            OutputFormat.JSON,
        ),
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

    incidents.execution_readiness(
        context=object(),
        incident_id="incident:1",
        history_limit=5,
        min_similarity=0.5,
        include_ai=False,
    )

    assert emitted == [payload]


def test_human_output_shows_policy_and_action_safety_fields(
    monkeypatch,
) -> None:
    payload = _payload()
    details = []
    records = []
    monkeypatch.setattr(
        incidents,
        "get_runtime",
        lambda context: _runtime(
            payload,
            OutputFormat.TABLE,
        ),
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

    incidents.execution_readiness(
        context=object(),
        incident_id="incident:1",
        history_limit=5,
        min_similarity=0.5,
        include_ai=False,
    )

    summary = details[0][1]
    rows = records[0][1]
    rollback = next(
        row
        for row in rows
        if row["family"] == "rollback"
    )

    assert summary[
        "Overall Execution Posture"
    ] == "validation_required"
    assert summary["Policy Version"] == "14f-v1"
    assert rollback["risk"] == "high"
    assert rollback["mutation"] is True
    assert rollback["status"] == (
        "needs_validation"
    )
    assert rollback["current_evidence"] == "high"
    assert rollback["historical_support"] == (
        "strongly_supported"
    )
    assert rollback["human_approval"] is True
    assert rollback["owner"] == "payments"
    assert rollback["oncall"] == (
        "pagerduty:payments"
    )
    assert rollback["missing"] == [
        "validation:action:validate"
    ]


def test_cli_forwards_ai_and_history_options(
    monkeypatch,
) -> None:
    payload = _payload()
    calls = []
    runtime = _runtime(
        payload,
        OutputFormat.JSON,
    )

    def request(*args, **kwargs):
        calls.append((args, kwargs))
        return payload

    runtime.client.incident_execution_readiness = (
        request
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
        lambda value: None,
    )

    incidents.execution_readiness(
        context=object(),
        incident_id="incident:1",
        history_limit=9,
        min_similarity=0.75,
        include_ai=True,
    )

    assert calls == [
        (
            ("incident:1",),
            {
                "history_limit": 9,
                "min_similarity": 0.75,
                "include_ai": True,
            },
        )
    ]
