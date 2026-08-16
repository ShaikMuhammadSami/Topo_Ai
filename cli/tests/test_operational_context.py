from types import SimpleNamespace

from topo_cli.client import TopoClient
import topo_cli.commands.incidents as incidents
from topo_cli.output import OutputFormat


def _payload() -> dict:
    return {
        "incident_id": "incident:1",
        "causal_analysis_id": (
            "causal-analysis:1"
        ),
        "root_event_id": "event:commit",
        "root_event_title": "Bad commit",
        "root_event_source": "github",
        "root_entity_id": "entity:payments",
        "causal_confidence": 0.84,
        "root_cause_ownership": {
            "resolved": True,
            "owner_team": "payments",
            "owner_email": (
                "payments@example.com"
            ),
            "oncall_contact": (
                "pagerduty:payments"
            ),
            "service_name": "payments",
            "repository_url": (
                "https://example/payments"
            ),
            "business_capability": (
                "checkout"
            ),
            "criticality": "tier_1",
        },
        "overall_business_impact": {
            "business_impact_level": "high",
            "affected_entity_count": 2,
            "resolved_entity_count": 1,
            "unresolved_entity_count": 1,
            "owner_teams": ["payments"],
            "business_capabilities": [
                "checkout"
            ],
            "routing_recommendation": (
                "Route to payments."
            ),
        },
        "escalation_targets": [
            "pagerduty:payments"
        ],
        "warnings": [
            "One ownership is unresolved."
        ],
    }


def test_client_requests_operational_context(
) -> None:
    client = TopoClient.__new__(
        TopoClient
    )
    calls = []
    payload = _payload()

    def request(
        method,
        path,
        **kwargs,
    ):
        calls.append(
            (
                method,
                path,
                kwargs,
            )
        )
        return payload

    client._request = request

    result = (
        client.incident_operational_context(
            "incident/1"
        )
    )

    assert result is payload
    assert calls == [
        (
            "GET",
            (
                "/api/v1/incidents/"
                "incident%2F1/"
                "operational-context"
            ),
            {},
        )
    ]


def test_json_output_preserves_backend_response(
    monkeypatch,
) -> None:
    payload = _payload()
    emitted = []
    runtime = SimpleNamespace(
        output_format=OutputFormat.JSON,
        client=SimpleNamespace(
            incident_operational_context=(
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

    incidents.operational_context(
        context=object(),
        incident_id="incident:1",
    )

    assert emitted == [payload]


def test_table_output_contains_operational_fields(
    monkeypatch,
) -> None:
    payload = _payload()
    rendered = []
    runtime = SimpleNamespace(
        output_format=OutputFormat.TABLE,
        client=SimpleNamespace(
            incident_operational_context=(
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
            rendered.append(value),
    )

    incidents.operational_context(
        context=object(),
        incident_id="incident:1",
    )

    assert len(rendered) == 1
    summary = rendered[0]
    assert summary["Root Cause"] == (
        "Bad commit"
    )
    assert summary["Root Owner Team"] == (
        "payments"
    )
    assert summary[
        "Overall Business Impact"
    ] == "high"
    assert summary[
        "Escalation Targets"
    ] == ["pagerduty:payments"]
