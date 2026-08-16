from types import SimpleNamespace

import pytest

from topo_cli.client import TopoClient
import topo_cli.commands.incidents as incidents
from topo_cli.errors import ResourceNotFound
from topo_cli.output import OutputFormat


def _payload(
    *,
    ai_summary: str | None = None,
) -> dict:
    return {
        "incident_id": "incident:1",
        "analysis_context": {
            "causal_analysis_id": "analysis:1",
            "topology_snapshot_id": "snapshot:1",
            "root_event_id": "event:deploy",
            "root_event_title": "Deploy payments",
            "root_event_source": "github_actions",
            "root_entity_id": "entity:payments",
            "root_entity_kind": (
                "KubernetesDeployment"
            ),
            "root_service_name": "payments-api",
            "causal_change_kind": "deployment",
            "causal_change_source": (
                "github_actions"
            ),
            "business_capability": "checkout",
            "owner_team": "payments",
            "environment": "production",
            "severity": "critical",
        },
        "historical_support_level": "moderate",
        "matches": [
            {
                "incident_id": "incident:old",
                "incident_title": (
                    "Prior payments failure"
                ),
                "similarity_score": 0.91,
                "matched_factors": [
                    "same root service",
                    "same causal change kind",
                ],
                "differing_factors": [
                    "Different causal source"
                ],
                "resolution": {
                    "rca_verdict": "confirmed",
                    "primary_resolution_action": {
                        "title": (
                            "Rollback deployment"
                        ),
                        "effectiveness": "effective",
                    },
                    "time_to_mitigation_seconds": 300,
                    "time_to_resolution_seconds": 600,
                    "resolution_summary": (
                        "Rollback restored service."
                    ),
                },
            }
        ],
        "resolution_patterns": [
            {
                "action_type": (
                    "rollback_deployment"
                ),
                "observed_cases": 2,
                "effective_cases": 2,
                "ineffective_cases": 0,
                "unknown_effectiveness_cases": 0,
                "supporting_incident_ids": [
                    "incident:old",
                    "incident:older",
                ],
            }
        ],
        "summary": (
            "Two similar incidents were recorded."
        ),
        "ai_summary": ai_summary,
        "ai_status": (
            "available"
            if ai_summary
            else "not_requested"
        ),
        "ai_provider": (
            "openai" if ai_summary else None
        ),
        "ai_model": (
            "gpt-5-mini" if ai_summary else None
        ),
        "warnings": [
            "Historical support is not proof."
        ],
    }


def test_client_requests_encoded_history_path(
) -> None:
    client = TopoClient.__new__(TopoClient)
    calls = []
    payload = _payload()

    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return payload

    client._request = request
    result = (
        client.incident_historical_intelligence(
            "incident/1",
            limit=7,
            min_similarity=0.4,
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
                "historical-intelligence"
            ),
            {
                "params": {
                    "limit": 7,
                    "min_similarity": 0.4,
                    "include_ai": True,
                }
            },
        )
    ]


def test_history_json_preserves_complete_response(
    monkeypatch,
) -> None:
    payload = _payload(
        ai_summary="Prior cases support review."
    )
    emitted = []
    runtime = SimpleNamespace(
        output_format=OutputFormat.JSON,
        client=SimpleNamespace(
            incident_historical_intelligence=(
                lambda *args, **kwargs: payload
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

    incidents.incident_history(
        context=object(),
        incident_id="incident:1",
        limit=5,
        min_similarity=0.25,
        include_ai=True,
    )

    assert emitted == [payload]


def test_history_human_output_has_all_sections(
    monkeypatch,
) -> None:
    payload = _payload(
        ai_summary=(
            "Prior rollbacks are relevant but "
            "not conclusive."
        )
    )
    details = []
    records = []
    runtime = SimpleNamespace(
        output_format=OutputFormat.TABLE,
        client=SimpleNamespace(
            incident_historical_intelligence=(
                lambda *args, **kwargs: payload
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

    incidents.incident_history(
        context=object(),
        incident_id="incident:1",
        limit=5,
        min_similarity=0.25,
        include_ai=True,
    )

    summary = details[0][1]
    sections = {
        title: values
        for title, values in records
    }

    assert summary["Historical Support"] == (
        "moderate"
    )
    assert summary["Current Root Cause"] == (
        "Deploy payments"
    )
    assert summary["AI Historical Summary"] == (
        "Prior rollbacks are relevant but "
        "not conclusive."
    )
    assert "Historical Matches" in sections
    assert "Resolution Patterns" in sections
    assert sections["Historical Matches"][0][
        "why"
    ] == [
        "same root service",
        "same causal change kind",
    ]


def test_history_without_ai_is_graceful(
    monkeypatch,
) -> None:
    payload = _payload(ai_summary=None)
    details = []
    runtime = SimpleNamespace(
        output_format=OutputFormat.TABLE,
        client=SimpleNamespace(
            incident_historical_intelligence=(
                lambda *args, **kwargs: payload
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

    incidents.incident_history(
        context=object(),
        incident_id="incident:1",
        limit=5,
        min_similarity=0.25,
        include_ai=False,
    )

    assert details[0][
        "AI Historical Summary"
    ] is None
    assert details[0]["AI Status"] == (
        "not_requested"
    )


def test_history_uses_normal_api_error_handling(
    monkeypatch,
) -> None:
    runtime = SimpleNamespace(
        output_format=OutputFormat.TABLE,
        client=SimpleNamespace(),
    )
    monkeypatch.setattr(
        incidents,
        "get_runtime",
        lambda context: runtime,
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
        incidents.incident_history(
            context=object(),
            incident_id="missing",
            limit=5,
            min_similarity=0.25,
            include_ai=False,
        )
