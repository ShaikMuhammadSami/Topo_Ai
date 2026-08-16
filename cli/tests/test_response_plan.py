from types import SimpleNamespace

import pytest

from topo_cli.client import TopoClient
import topo_cli.commands.incidents as incidents
from topo_cli.errors import ResourceNotFound
from topo_cli.output import OutputFormat


def _payload() -> dict:
    return {
        "incident_id": "incident:1",
        "causal_analysis_id": (
            "causal-analysis:1"
        ),
        "response_priority": "critical",
        "response_priority_reason": (
            "Tier-1 checkout is affected."
        ),
        "root_cause": {
            "event_id": "event:commit",
            "event_title": "Payment retry change",
            "event_source": "github",
            "event_kind": "code",
            "target_event_id": "event:deploy",
            "target_event_title": (
                "Deploy payments"
            ),
            "target_event_source": (
                "github_actions"
            ),
            "target_event_kind": "deployment",
            "entity_id": "entity:payments",
            "causal_confidence": 0.84,
            "confidence_level": "high",
            "evidence_ids": [
                "evidence:temporal"
            ],
        },
        "primary_owner": {
            "resolved": True,
            "owner_team": "payments",
            "owner_email": (
                "payments@example.com"
            ),
            "oncall_contact": (
                "pagerduty:payments"
            ),
            "service_name": "payments-api",
            "repository_url": (
                "https://example/payments"
            ),
        },
        "business_context": {
            "business_impact_level": (
                "critical"
            ),
            "highest_criticality": "tier_1",
            "affected_team_count": 2,
            "affected_capability_count": 1,
            "affected_entity_count": 3,
            "owner_teams": [
                "payments",
                "platform",
            ],
            "business_capabilities": [
                "checkout"
            ],
        },
        "recommended_actions": [
            {
                "action_id": "action:1",
                "sequence": 1,
                "category": "investigate",
                "priority": "critical",
                "title": (
                    "Inspect the causal deployment"
                ),
                "description": (
                    "Review event event:deploy."
                ),
                "reason": (
                    "Supported by causal evidence."
                ),
                "risk": "low",
                "requires_human_approval": False,
                "evidence_event_ids": [
                    "event:deploy"
                ],
            }
        ],
        "validation_checks": [
            {
                "action_id": "check:1",
                "sequence": 1,
                "category": "validate",
                "priority": "critical",
                "title": (
                    "Confirm the causal timeline"
                ),
                "description": (
                    "Validate event timing."
                ),
                "reason": (
                    "Timing can refute the cause."
                ),
                "risk": "low",
                "requires_human_approval": False,
                "evidence_event_ids": [
                    "event:deploy"
                ],
            }
        ],
        "rollback_candidate": {
            "available": True,
            "reason": (
                "Evidence supports a candidate."
            ),
            "change_event_id": "event:deploy",
            "requires_human_approval": True,
        },
        "runbooks": [
            {
                "runbook_id": "runbook:1",
                "title": "Payments runbook",
                "url": (
                    "https://docs.example/runbook"
                ),
                "source": "entity.labels",
            }
        ],
        "escalation_targets": [
            "pagerduty:payments"
        ],
        "warnings": [
            "One affected owner is unresolved."
        ],
    }


def test_client_requests_response_plan() -> None:
    client = TopoClient.__new__(TopoClient)
    calls = []
    payload = _payload()

    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return payload

    client._request = request

    result = client.incident_response_plan(
        "incident/1"
    )

    assert result is payload
    assert calls == [
        (
            "GET",
            (
                "/api/v1/incidents/"
                "incident%2F1/response-plan"
            ),
            {},
        )
    ]


def test_json_output_preserves_complete_response(
    monkeypatch,
) -> None:
    payload = _payload()
    emitted = []
    runtime = SimpleNamespace(
        output_format=OutputFormat.JSON,
        client=SimpleNamespace(
            incident_response_plan=(
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

    incidents.response_plan(
        context=object(),
        incident_id="incident:1",
    )

    assert emitted == [payload]


def test_table_output_contains_response_sections(
    monkeypatch,
) -> None:
    payload = _payload()
    details = []
    records = []
    runtime = SimpleNamespace(
        output_format=OutputFormat.TABLE,
        client=SimpleNamespace(
            incident_response_plan=(
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
        lambda value, **kwargs:
            details.append(
                (kwargs["title"], value)
            ),
    )
    monkeypatch.setattr(
        incidents,
        "render_records",
        lambda value, **kwargs:
            records.append(
                (kwargs["title"], value)
            ),
    )

    incidents.response_plan(
        context=object(),
        incident_id="incident:1",
    )

    summary = details[0][1]

    assert summary["Root Cause"] == (
        "Payment retry change"
    )
    assert summary["Primary Owner"] == (
        "payments"
    )
    assert summary["Business Impact"] == (
        "critical"
    )
    assert summary["Affected Entities"] == 3

    sections = {
        title: values
        for title, values in records
    }

    assert sections[
        "Recommended Actions"
    ][0]["risk"] == "low"
    assert sections[
        "Validation Checks"
    ][0]["category"] == "validate"
    assert sections["Runbooks"][0]["url"] == (
        "https://docs.example/runbook"
    )

    rollback = next(
        value
        for title, value in details
        if title == "Rollback Candidate"
    )

    assert rollback[
        "Human Approval Required"
    ] is True


def test_response_plan_uses_cli_error_handling(
    monkeypatch,
) -> None:
    runtime = SimpleNamespace(
        output_format=OutputFormat.TABLE,
        client=SimpleNamespace(
            incident_response_plan=(
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
            "Response plan not found."
        )

    monkeypatch.setattr(
        incidents,
        "api_call",
        fail,
    )

    with pytest.raises(ResourceNotFound):
        incidents.response_plan(
            context=object(),
            incident_id="incident:missing",
        )
