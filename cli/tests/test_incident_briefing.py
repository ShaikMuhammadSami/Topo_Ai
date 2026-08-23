from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from topo_cli.client import TopoClient
import topo_cli.commands.incidents as incidents
from topo_cli.errors import ResourceNotFound
from topo_cli.output import OutputFormat


def _payload() -> dict:
    return {
        "incident": {
            "incident_id": "incident:1",
            "title": "Checkout degradation",
            "summary": "Checkout requests are failing.",
            "status": "open",
            "severity": "critical",
            "environment": "production",
            "cluster_name": "production",
            "namespace": "payments",
            "first_observed_at": (
                "2026-08-16T10:00:00+00:00"
            ),
            "current_state": "investigating",
        },
        "summary": {
            "text": (
                "The leading hypothesis points to the "
                "payment-api deployment."
            ),
            "evidence_references": [
                "analysis:13c"
            ],
        },
        "root_cause": {
            "causal_analysis_id": "analysis:13c",
            "root_event_id": "event:commit",
            "root_event_title": (
                "Payment retry code change"
            ),
            "root_event_source": "github",
            "root_entity_id": "entity:payments",
            "causal_confidence": 0.9,
            "confidence_level": "high",
            "confidence_semantics": {
                "semantics_version": "tc5.v1",
                "ranking_algorithm_version": "13c-causal-v1",
                "score_type": "heuristic_ranking",
                "ranking_score": 90.0,
                "score_minimum": 0.0,
                "score_maximum": 100.0,
                "ranking_strength": "high",
                "legacy_confidence": 0.9,
                "legacy_confidence_semantics": (
                    "legacy_normalized_heuristic_ranking_score"
                ),
                "evidence_summary": {
                    "supporting_count": 4,
                    "contradicting_count": 0,
                    "missing_count": 1,
                },
                "evidence_completeness": "partial",
                "evidence_state": "incomplete",
                "calibration_status": "not_calibrated",
                "calibrated_probability": None,
                "interpretation": "Heuristic ranking, not probability.",
            },
            "causal_change_title": (
                "Deploy payment-api revision 42"
            ),
            "causal_change_type": "deployment",
            "evidence_references": [
                "evidence:entity"
            ],
        },
        "recent_relevant_changes": [
            {
                "event_id": "event:deploy",
                "title": "Deploy payment-api revision 42",
                "role": "causal_target",
                "source": "github_actions",
                "change_type": "deployment",
                "occurred_at": (
                    "2026-08-16T09:56:00+00:00"
                ),
                "release_version": "42",
            }
        ],
        "dependency_path": [
            {
                "order": 1,
                "label": "Deploy payment-api revision 42",
                "node_type": "change_event",
                "relation_from_previous": None,
                "event_id": "event:deploy",
            },
            {
                "order": 2,
                "label": "payment-api",
                "node_type": "entity",
                "relation_from_previous": "touches_entity",
                "entity_id": "entity:payments",
            },
        ],
        "blast_radius": {
            "affected_entity_count": 3,
            "returned_entity_count": 3,
            "omitted_entity_count": 0,
            "direct_impact_count": 1,
            "indirect_impact_count": 1,
            "potential_impact_count": 1,
            "affected_services": ["payment-api"],
            "affected_dependency_types": [
                "depends_on"
            ],
            "affected_teams": ["Payments Platform"],
            "business_capabilities": ["Checkout"],
        },
        "operational_context": {
            "ownership": {
                "resolved": True,
                "owner_team": "Payments Platform",
                "owner_email": "payments@example.com",
                "oncall_contact": "pagerduty:payments",
                "service_name": "payment-api",
                "repository_url": (
                    "https://github.com/acme/payments"
                ),
                "business_capability": "Checkout",
                "criticality": "tier_1",
            },
            "business_impact": {
                "business_impact_level": "critical",
                "affected_entity_count": 3,
                "resolved_entity_count": 3,
                "unresolved_entity_count": 0,
                "owner_teams": ["Payments Platform"],
                "business_capabilities": ["Checkout"],
                "highest_criticality": "tier_1",
                "routing_recommendation": (
                    "Route to pagerduty:payments."
                ),
            },
            "escalation_targets": [
                "pagerduty:payments"
            ],
        },
        "remediation": {
            "read_only": True,
            "actions": [
                {
                    "rank": 1,
                    "action_id": "action:inspect",
                    "title": "Inspect deployment evidence",
                    "semantics": "investigation",
                    "priority": "critical",
                    "risk": "low",
                    "requires_human_approval": False,
                    "reason": "Current causal evidence.",
                    "entity_ids": ["entity:payments"],
                },
                {
                    "rank": 2,
                    "action_id": "action:rollback",
                    "title": "Consider manual reversion",
                    "semantics": "mitigation",
                    "priority": "high",
                    "risk": "high",
                    "requires_human_approval": True,
                    "reason": "Only after validation.",
                    "entity_ids": ["entity:payments"],
                },
            ],
            "previews": [
                {
                    "action_title": "Consider manual reversion",
                    "affected_target": {
                        "entity_ids": ["entity:payments"],
                        "change_event_ids": ["event:deploy"],
                    },
                    "potentially_impacted_entities": [
                        {"entity_id": "entity:checkout"}
                    ],
                    "risk": "high",
                    "intended_effect": (
                        "If the hypothesis is correct, the "
                        "previous state may restore service."
                    ),
                    "expected_observation_if_successful": (
                        "Symptoms should move toward recovery."
                    ),
                    "possible_failure_modes": [
                        "The hypothesis may be incorrect."
                    ],
                    "historical_observations": [
                        "One effective case was recorded."
                    ],
                    "potential_impact_scope_note": (
                        "Context only; not a simulation."
                    ),
                }
            ],
        },
        "historical_context": {
            "support_level": "limited",
            "summary": "History is informative, not proof.",
            "similar_incidents": [
                {
                    "incident_id": "incident:old:1",
                    "similarity": 0.88,
                    "why_it_matches": ["same root service"],
                    "important_differences": [
                        "different environment"
                    ],
                    "primary_resolution_action": (
                        "Rollback deployment"
                    ),
                    "primary_action_effectiveness": (
                        "effective"
                    ),
                }
            ],
        },
        "verification_plan": [
            {
                "title": "Confirm runtime revision",
                "description": (
                    "Inspect the manually observed revision."
                ),
                "expected_observation": (
                    "The intended state is visible."
                ),
                "entity_ids": ["entity:payments"],
                "evidence_references": [
                    "evidence:entity"
                ],
            }
        ],
        "outcome": {
            "status": "resolved",
            "mitigated_at": (
                "2026-08-16T10:05:00+00:00"
            ),
            "resolved_at": (
                "2026-08-16T10:15:00+00:00"
            ),
            "time_to_mitigation_seconds": 300,
            "time_to_resolution_seconds": 900,
            "final_rca_verdict": "confirmed",
            "primary_resolution_action": (
                "Rollback deployment"
            ),
            "resolution_summary": (
                "Manual rollback restored checkout."
            ),
        },
        "ai_summary": "Cautious responder narrative.",
        "ai_status": "available",
        "ai_provider": "openai",
        "ai_model": "gpt-test",
        "warnings": [
            "Historical evidence is not proof."
        ],
    }


def _runtime(
    payload: dict,
    output_format: OutputFormat,
):
    return SimpleNamespace(
        output_format=output_format,
        client=SimpleNamespace(
            incident_briefing=(
                lambda *args, **kwargs: payload
            )
        ),
    )


def _wire_command(
    monkeypatch,
    payload: dict,
    output_format: OutputFormat,
):
    monkeypatch.setattr(
        incidents,
        "get_runtime",
        lambda context: _runtime(
            payload,
            output_format,
        ),
    )
    monkeypatch.setattr(
        incidents,
        "api_call",
        lambda operation: operation(),
    )


def test_client_requests_encoded_briefing_path() -> None:
    client = TopoClient.__new__(TopoClient)
    calls = []
    payload = _payload()

    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return payload

    client._request = request
    result = client.incident_briefing(
        "incident/1",
        include_ai=True,
    )

    assert result is payload
    assert calls == [
        (
            "GET",
            (
                "/api/v1/incidents/"
                "incident%2F1/briefing"
            ),
            {
                "params": {
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
    _wire_command(
        monkeypatch,
        payload,
        OutputFormat.JSON,
    )
    monkeypatch.setattr(
        incidents,
        "emit_json",
        emitted.append,
    )

    incidents.incident_briefing(
        context=object(),
        incident_id="incident:1",
        include_ai=True,
    )

    assert emitted == [payload]


def test_human_readable_section_order(
    monkeypatch,
) -> None:
    sections = []
    _wire_command(
        monkeypatch,
        _payload(),
        OutputFormat.TABLE,
    )
    monkeypatch.setattr(
        incidents,
        "render_data",
        lambda value, **kwargs: sections.append(
            kwargs["title"]
        ),
    )
    monkeypatch.setattr(
        incidents,
        "render_records",
        lambda value, **kwargs: sections.append(
            kwargs["title"]
        ),
    )

    incidents.incident_briefing(
        context=object(),
        incident_id="incident:1",
        include_ai=True,
    )

    assert sections == [
        "INCIDENT",
        "WHAT HAPPENED",
        "ROOT CAUSE",
        "WHAT CHANGED",
        "DEPENDENCY PATH",
        "BLAST RADIUS",
        "OWNER / ON-CALL",
        "BUSINESS IMPACT",
        "WHAT TO DO NEXT",
        "REMEDIATION PREVIEW",
        "HOW TO VERIFY",
        "SIMILAR INCIDENTS",
        "OUTCOME",
        "AI SUMMARY",
        "WARNINGS",
    ]


def test_human_root_cause_uses_tc5_semantic_labels(
    monkeypatch,
) -> None:
    rendered = {}
    _wire_command(monkeypatch, _payload(), OutputFormat.TABLE)
    monkeypatch.setattr(
        incidents,
        "render_data",
        lambda value, **kwargs: rendered.setdefault(kwargs["title"], value),
    )
    monkeypatch.setattr(
        incidents,
        "render_records",
        lambda *args, **kwargs: None,
    )

    incidents.incident_briefing(
        context=object(),
        incident_id="incident:1",
        include_ai=False,
    )

    root = rendered["ROOT CAUSE"]
    assert root["Heuristic Ranking Score"] == 90.0
    assert root["Legacy Normalized Ranking"] == 0.9
    assert root["Evidence State"] == "incomplete"
    assert root["Calibration Status"] == "not_calibrated"
    assert root["Calibrated Probability"] is None
    assert "Causal Confidence" not in root


def test_remediation_preview_is_rendered(
    monkeypatch,
) -> None:
    rendered = {}
    _wire_command(
        monkeypatch,
        _payload(),
        OutputFormat.TABLE,
    )
    monkeypatch.setattr(
        incidents,
        "render_data",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        incidents,
        "render_records",
        lambda value, **kwargs: rendered.update(
            {kwargs["title"]: value}
        ),
    )

    incidents.incident_briefing(
        context=object(),
        incident_id="incident:1",
        include_ai=False,
    )

    preview = rendered["REMEDIATION PREVIEW"][0]
    assert preview["target"] == [
        "entity:payments",
        "event:deploy",
    ]
    assert preview["potential_impact"] == [
        "entity:checkout"
    ]
    assert "If the hypothesis" in (
        preview["intended_effect"]
    )


def test_verification_plan_is_rendered(
    monkeypatch,
) -> None:
    rendered = {}
    _wire_command(
        monkeypatch,
        _payload(),
        OutputFormat.TABLE,
    )
    monkeypatch.setattr(
        incidents,
        "render_data",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        incidents,
        "render_records",
        lambda value, **kwargs: rendered.update(
            {kwargs["title"]: value}
        ),
    )

    incidents.incident_briefing(
        context=object(),
        incident_id="incident:1",
        include_ai=False,
    )

    verification = rendered["HOW TO VERIFY"][0]
    assert verification["title"] == (
        "Confirm runtime revision"
    )
    assert verification["expected_observation"] == (
        "The intended state is visible."
    )


def test_historical_context_is_rendered(
    monkeypatch,
) -> None:
    rendered = {}
    _wire_command(
        monkeypatch,
        _payload(),
        OutputFormat.TABLE,
    )
    monkeypatch.setattr(
        incidents,
        "render_data",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        incidents,
        "render_records",
        lambda value, **kwargs: rendered.update(
            {kwargs["title"]: value}
        ),
    )

    incidents.incident_briefing(
        context=object(),
        incident_id="incident:1",
        include_ai=False,
    )

    historical = rendered["SIMILAR INCIDENTS"][0]
    assert historical["incident_id"] == (
        "incident:old:1"
    )
    assert historical["similarity"] == 0.88


def test_unresolved_incident_renders_in_progress_outcome(
    monkeypatch,
) -> None:
    payload = deepcopy(_payload())
    payload["outcome"] = None
    payload["incident"]["status"] = "investigating"
    details = {}
    _wire_command(
        monkeypatch,
        payload,
        OutputFormat.TABLE,
    )
    monkeypatch.setattr(
        incidents,
        "render_records",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        incidents,
        "render_data",
        lambda value, **kwargs: details.update(
            {kwargs["title"]: value}
        ),
    )

    incidents.incident_briefing(
        context=object(),
        incident_id="incident:1",
        include_ai=False,
    )

    assert details["OUTCOME"]["Status"] == (
        "investigating"
    )
    assert details["OUTCOME"][
        "Resolution Summary"
    ] == "No completed outcome is recorded."


def test_ai_unavailable_is_rendered(
    monkeypatch,
) -> None:
    payload = deepcopy(_payload())
    payload["ai_summary"] = None
    payload["ai_status"] = "unavailable"
    details = {}
    _wire_command(
        monkeypatch,
        payload,
        OutputFormat.TABLE,
    )
    monkeypatch.setattr(
        incidents,
        "render_records",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        incidents,
        "render_data",
        lambda value, **kwargs: details.update(
            {kwargs["title"]: value}
        ),
    )

    incidents.incident_briefing(
        context=object(),
        incident_id="incident:1",
        include_ai=True,
    )

    assert details["AI SUMMARY"]["Status"] == (
        "unavailable"
    )
    assert "structured facts" in (
        details["AI SUMMARY"]["Summary"]
    )


def test_normal_api_errors_are_preserved(
    monkeypatch,
) -> None:
    _wire_command(
        monkeypatch,
        {},
        OutputFormat.TABLE,
    )

    def fail(operation):
        raise ResourceNotFound(
            "No causal analysis exists."
        )

    monkeypatch.setattr(
        incidents,
        "api_call",
        fail,
    )

    with pytest.raises(ResourceNotFound):
        incidents.incident_briefing(
            context=object(),
            incident_id="incident:missing",
            include_ai=False,
        )
