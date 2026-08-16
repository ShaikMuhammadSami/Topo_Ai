from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from topo_cli.client import TopoClient
import topo_cli.commands.incidents as incidents
from topo_cli.errors import ResourceNotFound
from topo_cli.output import OutputFormat


def _payload(
    *,
    support_level: str = "strongly_supported",
    ai_summary: str | None = None,
) -> dict:
    return {
        "incident_id": "incident:1",
        "response_plan_reference": (
            "response-plan:analysis:1"
        ),
        "causal_analysis_id": "analysis:1",
        "response_priority": "critical",
        "response_priority_reason": (
            "Critical checkout impact."
        ),
        "baseline_response_plan": {
            "incident_id": "incident:1",
            "causal_analysis_id": "analysis:1",
            "root_cause": {
                "event_title": (
                    "Payment retry change"
                ),
                "causal_confidence": 0.9,
            },
        },
        "actions": [
            {
                "action_id": "action:rollback",
                "sequence": 2,
                "baseline_rank": 2,
                "baseline_group": "recommended",
                "category": "rollback_candidate",
                "priority": "critical",
                "title": "Consider rollback deployment",
                "risk": "high",
                "requires_human_approval": True,
                "action_family": "rollback",
                "current_evidence_strength": "high",
                "historical_support": {
                    "level": support_level,
                    "score": (
                        0.9
                        if support_level
                        == "strongly_supported"
                        else 0.0
                    ),
                    "similar_incident_count": 3,
                    "action_observed_count": 3,
                    "effective_count": (
                        3
                        if support_level
                        == "strongly_supported"
                        else 1
                    ),
                    "ineffective_count": (
                        0
                        if support_level
                        == "strongly_supported"
                        else 2
                    ),
                    "supporting_incident_ids": [
                        "incident:old:1"
                    ],
                    "contradicting_incident_ids": (
                        []
                        if support_level
                        == "strongly_supported"
                        else ["incident:old:2"]
                    ),
                    "support_reasons": [
                        "Three matching cases."
                    ],
                    "caution_reasons": (
                        []
                        if support_level
                        == "strongly_supported"
                        else [
                            "Two matching actions "
                            "were ineffective."
                        ]
                    ),
                },
            }
        ],
        "rollback_candidate": {
            "baseline": {
                "available": True,
                "reason": "Current evidence permits review.",
                "change_event_id": "event:deploy",
                "requires_human_approval": True,
            },
            "historical_support": {
                "level": support_level,
                "score": 0.9,
                "supporting_incident_ids": [
                    "incident:old:1"
                ],
                "contradicting_incident_ids": [],
                "caution_reasons": [],
            },
        },
        "historical_resolution_patterns": [
            {
                "action_type": "rollback_deployment",
                "observed_cases": 3,
                "effective_cases": 3,
                "ineffective_cases": 0,
                "unknown_effectiveness_cases": 0,
            }
        ],
        "overall_historical_support": support_level,
        "deterministic_summary": (
            "Historical evidence is informative."
        ),
        "ai_summary": ai_summary,
        "ai_status": (
            "available"
            if ai_summary
            else "not_requested"
        ),
        "warnings": [
            "Historical evidence is not proof."
        ],
    }


def _runtime(payload: dict, output_format):
    return SimpleNamespace(
        output_format=output_format,
        client=SimpleNamespace(
            incident_response_intelligence=(
                lambda *args, **kwargs: payload
            )
        ),
    )


def test_client_requests_encoded_response_path(
) -> None:
    client = TopoClient.__new__(TopoClient)
    calls = []
    payload = _payload()

    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return payload

    client._request = request
    result = (
        client.incident_response_intelligence(
            "incident/1",
            history_limit=7,
            min_similarity=0.6,
            include_ai=True,
        )
    )

    assert result is payload
    assert calls == [
        (
            "GET",
            (
                "/api/v1/incidents/"
                "incident%2F1/"
                "response-intelligence"
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
    payload = _payload(
        ai_summary="Three cases support review."
    )
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

    incidents.response_intelligence(
        context=object(),
        incident_id="incident:1",
        history_limit=5,
        min_similarity=0.5,
        include_ai=True,
    )

    assert emitted == [payload]


def test_human_output_has_action_support_sections(
    monkeypatch,
) -> None:
    payload = _payload(
        ai_summary="Review validation before approval."
    )
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

    incidents.response_intelligence(
        context=object(),
        incident_id="incident:1",
        history_limit=5,
        min_similarity=0.5,
        include_ai=True,
    )

    summary = details[0][1]
    sections = {
        title: values
        for title, values in records
    }

    assert summary["Response Priority"] == "critical"
    assert summary["Root Cause"] == (
        "Payment retry change"
    )
    assert summary["AI Summary"] == (
        "Review validation before approval."
    )
    assert sections["Action Support"][0][
        "approval"
    ] is True
    assert sections["Action Support"][0][
        "historical_support"
    ] == "strongly_supported"
    assert (
        "Historical Resolution Patterns"
        in sections
    )
    rollback = next(
        value
        for title, value in details
        if title == "Rollback Candidate"
    )
    assert rollback[
        "Human Approval Required"
    ] is True


def test_conflicting_history_is_rendered(
    monkeypatch,
) -> None:
    payload = _payload(
        support_level="conflicting"
    )
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
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        incidents,
        "render_records",
        lambda value, **kwargs: records.append(
            (kwargs["title"], value)
        ),
    )

    incidents.response_intelligence(
        context=object(),
        incident_id="incident:1",
        history_limit=5,
        min_similarity=0.5,
        include_ai=False,
    )

    actions = dict(records)["Action Support"]
    assert actions[0][
        "historical_support"
    ] == "conflicting"
    assert actions[0]["ineffective"] == 2
    assert actions[0]["cautions"]


def test_missing_history_and_ai_unavailable_render(
    monkeypatch,
) -> None:
    payload = deepcopy(_payload())
    payload["overall_historical_support"] = (
        "insufficient_history"
    )
    payload["ai_status"] = "unavailable"
    payload["actions"][0][
        "historical_support"
    ]["level"] = "insufficient_history"
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
            value
        ),
    )
    monkeypatch.setattr(
        incidents,
        "render_records",
        lambda value, **kwargs: records.append(
            (kwargs["title"], value)
        ),
    )

    incidents.response_intelligence(
        context=object(),
        incident_id="incident:1",
        history_limit=5,
        min_similarity=0.5,
        include_ai=True,
    )

    assert details[0][
        "Overall Historical Support"
    ] == "insufficient_history"
    assert details[0]["AI Summary"] is None
    assert details[0]["AI Status"] == "unavailable"
    assert dict(records)["Action Support"][0][
        "historical_support"
    ] == "insufficient_history"


def test_command_uses_normal_api_errors(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        incidents,
        "get_runtime",
        lambda context: _runtime(
            {},
            OutputFormat.TABLE,
        ),
    )

    def fail(operation):
        raise ResourceNotFound(
            "Incident not found."
        )

    monkeypatch.setattr(
        incidents,
        "api_call",
        fail,
    )

    with pytest.raises(ResourceNotFound):
        incidents.response_intelligence(
            context=object(),
            incident_id="missing",
            history_limit=5,
            min_similarity=0.5,
            include_ai=False,
        )
