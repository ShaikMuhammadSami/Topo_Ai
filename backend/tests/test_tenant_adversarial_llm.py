"""Capture final SDK arguments after real tenant filtering/context assembly."""

import json
from types import SimpleNamespace

import pytest

from app.models.causal_rca import CausalAnalysisRequest
from app.models.incident_explanation import IncidentExplanationGenerateRequest
from app.models.incident_copilot import CopilotSessionCreateRequest
from app.models.investigation_plan import InvestigationPlanGenerateRequest
from app.models.post_incident_report import PostIncidentReportGenerateRequest
from app.services import (incident_briefing, incident_explanation, incident_copilot,
    investigation_planner, post_incident_report, incident_similarity, response_intelligence, execution_readiness, llm_client)
from app.services.causal_rca import analyze_causal_rca
from app.db.models import IncidentRecord
from app.repositories.tenant_scope import tenant_get, tenant_commit
from test_tenant_adversarial_acceptance import hostile, worlds, save_outcome
from test_domain_tenant_enforcement import two_tenants, tenant_app, sqlite_tenant_app


def history(session, tenant, marker):
    current = tenant_get(session, IncidentRecord, "incident:same", tenant_id=tenant)
    # A second legitimate incident can reference the same immutable inventory.
    # Do not duplicate that snapshot within one tenant (correctly rejected).
    values = {column.name: getattr(current, column.name) for column in IncidentRecord.__table__.columns}
    values.update(incident_id="incident:history-shared", title=marker + "_HISTORY", summary=marker + "_HISTORY")
    session.add(IncidentRecord(**values))
    tenant_commit(session, tenant_id=tenant)
    analyze_causal_rca(session, incident_id="incident:history-shared", request=CausalAnalysisRequest(), tenant_id=tenant)
    save_outcome(session, tenant, incident="incident:history-shared", label=marker + "_RESOLUTION")


PATHS = ("briefing", "explanation", "copilot", "investigation", "report", "history", "response", "readiness")


def invoke(path, session, tenant, provider):
    if path == "briefing":
        return incident_briefing.build_incident_briefing(session, incident_id="incident:same", include_ai=True, tenant_id=tenant)
    if path == "explanation":
        return incident_explanation.generate_incident_explanation(session, "incident:same",
            IncidentExplanationGenerateRequest(provider=provider), tenant_id=tenant)
    if path == "copilot":
        conversation = incident_copilot.create_incident_copilot_session(session, "incident:same",
            CopilotSessionCreateRequest(provider=provider), tenant_id=tenant)
        return incident_copilot.answer_copilot_question(session, incident_id="incident:same",
            session_id=conversation.session_id, question="What evidence explains this incident?", tenant_id=tenant)
    if path == "investigation":
        return investigation_planner.generate_investigation_plan(session, incident_id="incident:same",
            request=InvestigationPlanGenerateRequest(provider=provider), tenant_id=tenant)
    if path == "report":
        return post_incident_report.generate_post_incident_report(session, incident_id="incident:same",
            request=PostIncidentReportGenerateRequest(provider=provider), tenant_id=tenant)
    if path == "history":
        return incident_similarity.build_historical_incident_intelligence(session, incident_id="incident:same",
            include_ai=True, min_similarity=0, tenant_id=tenant)
    if path == "readiness":
        return execution_readiness.build_incident_execution_readiness(session, incident_id="incident:same",
            include_ai=True, min_similarity=0, tenant_id=tenant)
    return response_intelligence.build_incident_response_intelligence(session, incident_id="incident:same",
        include_ai=True, min_similarity=0, tenant_id=tenant)


@pytest.mark.parametrize("provider,path", [("openai", p) for p in PATHS] +
    [("groq", p) for p in ("explanation", "copilot", "investigation", "report")])
@pytest.mark.parametrize("actor", ["A", "B"])
def test_outbound_context_is_tenant_owned_before_sdk_call(hostile, monkeypatch, provider, path, actor):
    h = hostile
    worlds(h)
    with h.factory() as session:
        for tenant, marker in ((h.a, "A_PRIVATE"), (h.b, "B_PRIVATE")):
            history(session, tenant, marker)
    captured = []

    def sdk_request(**kwargs):
        # Capture the last boundary, including normal sanitization. Deliberately
        # fail transport so real fallback behavior is exercised without an LLM.
        captured.append(kwargs)
        raise RuntimeError("PH3G outbound transport deliberately unavailable")

    monkeypatch.setattr(
        llm_client,
        "installation_secret_is_configured",
        lambda integration: integration == provider,
    )
    monkeypatch.setattr(
        llm_client,
        "installation_secret_text",
        lambda integration: "ph3g-not-a-live-key" if integration == provider else None,
    )
    monkeypatch.setenv("TOPO_AI_LLM_PROVIDER", provider)
    monkeypatch.setattr(llm_client, "OpenAI", lambda **_: SimpleNamespace(
        responses=SimpleNamespace(create=sdk_request, parse=sdk_request)))
    for module in (incident_explanation, incident_copilot, investigation_planner, post_incident_report):
        monkeypatch.setattr(
            module,
            "installation_secret_text",
            lambda integration: "ph3g-not-a-live-key" if integration == "groq" else None,
        )
        monkeypatch.setattr(module, "Groq", lambda **_: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=sdk_request))))
    with h.factory() as session:
        result = invoke(path, session, h.a if actor == "A" else h.b, "auto")
    assert captured, (provider, path, "no assembled context reached transport")
    encoded = json.dumps(captured, default=str)
    assert actor + "_PRIVATE" in encoded
    foreign = ("B" if actor == "A" else "A") + "_PRIVATE"
    assert foreign not in encoded
    assert foreign not in result.model_dump_json()
