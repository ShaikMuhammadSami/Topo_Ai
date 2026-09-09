"""PH-6A external-LLM inventory and PH-6C handoff tests."""

from __future__ import annotations

from pathlib import Path

from app.security.egress_inventory import (
    EGRESS_CALLSITES,
    LLM_PURPOSES,
    PH6C_PROPOSED_BOUNDS,
    PH6C_PROPOSED_ENVELOPES,
    PH6C_RAW_MARKER_REGRESSION_ID,
    CustomerDataClass,
)
from app.services import incident_copilot, investigation_planner, post_incident_report
from app.services.llm_client import sanitize_structured


REPOSITORY = Path(__file__).resolve().parents[2]


def test_llm_purpose_and_provider_dispatch_inventory_is_exact() -> None:
    assert len(LLM_PURPOSES) == 8
    assert sum(len(item.provider_paths) for item in LLM_PURPOSES) == 12
    direct_groq = [
        item
        for item in EGRESS_CALLSITES
        if item.callsite_id.startswith("server.llm.groq-")
    ]
    assert {item.callsite_id for item in direct_groq} == {
        "server.llm.groq-copilot",
        "server.llm.groq-explanation",
        "server.llm.groq-planner",
        "server.llm.groq-report",
    }
    assert all("Direct central-client bypass" in item.notes for item in direct_groq)


def test_current_raw_payload_exposure_and_user_content_are_not_hidden() -> None:
    raw = {item.purpose_id for item in LLM_PURPOSES if item.raw_payload_reachable}
    assert raw == {
        "incident-explanation",
        "incident-copilot",
        "investigation-planner",
        "post-incident-report",
    }
    user_authored = {
        item.purpose_id for item in LLM_PURPOSES if item.user_authored_content
    }
    assert user_authored == {"incident-copilot", "post-incident-report"}
    assert all(item.tenant_filtering_point for item in LLM_PURPOSES)
    assert all(item.current_sanitizer for item in LLM_PURPOSES)
    assert all(item.current_bounds for item in LLM_PURPOSES)


def test_exact_ph6c_hostile_marker_survives_current_key_scrubbers() -> None:
    marker = PH6C_RAW_MARKER_REGRESSION_ID
    opaque = {"payload_json": f'{{"provider_message":"{marker}"}}'}
    scrubbed = (
        incident_copilot._redact(opaque),
        investigation_planner._redact(opaque),
        post_incident_report._redact(opaque),
        sanitize_structured(opaque),
    )
    assert all(marker in str(item) for item in scrubbed)


def test_ph6c_proposal_is_purpose_specific_allowlist_with_explicit_bounds() -> None:
    assert set(PH6C_PROPOSED_ENVELOPES) == {
        "LLMIncidentExplanationEnvelope",
        "LLMCopilotEnvelope",
        "LLMInvestigationPlannerEnvelope",
        "LLMPostIncidentReportEnvelope",
    }
    forbidden = {
        "raw_payload",
        "payload_json",
        "headers",
        "environment",
        "model_dump",
        "arbitrary_context",
    }
    for fields in PH6C_PROPOSED_ENVELOPES.values():
        assert len(fields) == len(set(fields))
        assert forbidden.isdisjoint(fields)
    assert PH6C_PROPOSED_BOUNDS["total_serialized_bytes"] == 65536
    assert PH6C_PROPOSED_BOUNDS["conversation_messages"] == 10
    assert PH6C_PROPOSED_BOUNDS["user_question_chars"] == 4096


def test_llm_calls_have_no_tool_authority_or_tenant_selected_base_url() -> None:
    sources = {
        "backend/app/services/llm_client.py",
        "backend/app/services/incident_copilot.py",
        "backend/app/services/incident_explanation.py",
        "backend/app/services/investigation_planner.py",
        "backend/app/services/post_incident_report.py",
    }
    joined = "\n".join(
        (REPOSITORY / source).read_text(encoding="utf-8") for source in sources
    )
    assert "base_url=" not in joined
    assert "tools=" not in joined
    assert "tool_choice=" not in joined
    assert "functions=" not in joined
    assert "function_call=" not in joined

    llm_calls = [item for item in EGRESS_CALLSITES if item.callsite_id.startswith("server.llm.")]
    assert len(llm_calls) == 6
    for item in llm_calls:
        assert CustomerDataClass.SECRET_MATERIAL not in item.data_classes
        assert CustomerDataClass.AUTHENTICATION_SECRET not in item.data_classes
        assert CustomerDataClass.AUTHENTICATION_SECRET in item.secret_classes

