"""PH-6C typed external customer-data boundary acceptance tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

import app.services.llm_client as llm_client
from app.models.incident_copilot import CopilotMessageRole, CopilotMessageView
from app.models.incident_explanation import EvidenceType, GroundingEvidence
from app.models.secret_store import SecretMaterial
from app.models.webhooks import (
    IncidentCreatedWebhookPayload,
    WebhookEvent,
    WebhookEventType,
    WebhookTestPayload,
)
from app.security.customer_data_policy import (
    EXTERNAL_DATA_SINK_POLICIES,
    ExternalDataSink,
    policy_for_sink,
)
from app.security.egress_inventory import CustomerDataClass
from app.security.llm_data_boundary import (
    MAX_CONVERSATION_MESSAGES,
    MAX_ENVELOPE_BYTES,
    MAX_EVIDENCE_REFS,
    LLMCopilotEnvelope,
    LLMEgressPurpose,
    LLMExecutionReadinessSummaryEnvelope,
    LLMIncidentExplanationEnvelope,
    LLMInvestigationPlannerEnvelope,
    LLMPostIncidentReportEnvelope,
    LLMResponseIntelligenceSummaryEnvelope,
    LLMRootCauseFact,
    LLMSimilaritySummaryEnvelope,
    LLMUnifiedBriefingSummaryEnvelope,
    SafeLLMRequest,
    build_safe_llm_request,
    evidence_ids,
    safe_conversation_history,
    safe_evidence_references,
)
from app.services.webhook_delivery import MAX_WEBHOOK_BODY_BYTES, _event_body


REPOSITORY = Path(__file__).resolve().parents[2]
TENANT_A = "tenant:66666666-6666-4666-8666-66666666666a"
TENANT_B = "tenant:66666666-6666-4666-8666-66666666666b"
RAW_MARKER = "ph6c-opaque-raw-payload-marker"


def _evidence(*, data: dict | None = None) -> GroundingEvidence:
    return GroundingEvidence(
        evidence_id="signal:ph6c",
        evidence_type=EvidenceType.SIGNAL,
        summary="Remote event text is intentionally not forwarded.",
        observed_at="2026-09-12T12:00:00+00:00",
        data=data
        or {
            "signal_id": "signal:ph6c",
            "category": "workload_failure",
            "severity": "critical",
            "reason": "CrashLoopBackOff",
        },
    )


def _evidence_envelope(model):
    safe = safe_evidence_references([_evidence()], tenant_id=TENANT_A)
    return model(
        tenant_id=TENANT_A,
        incident_id="incident:ph6c",
        prompt_version="ph6c-v1",
        allowed_evidence_ids=evidence_ids(safe),
        evidence_catalog=safe,
    )


def _copilot_envelope() -> LLMCopilotEnvelope:
    safe = safe_evidence_references([_evidence()], tenant_id=TENANT_A)
    return LLMCopilotEnvelope(
        tenant_id=TENANT_A,
        incident_id="incident:ph6c",
        prompt_version="ph6c-v1",
        question="What should I verify?",
        allowed_evidence_ids=evidence_ids(safe),
        evidence_catalog=safe,
    )


def _root() -> LLMRootCauseFact:
    return LLMRootCauseFact(
        causal_analysis_id="analysis:ph6c",
        root_event_id="event:root",
        root_event_title="Deployment revision changed",
        root_event_source="github_actions",
        root_entity_id="entity:deployment:checkout",
        causal_confidence=0.83,
        causal_change_event_id="event:change",
        causal_change_title="Checkout image changed",
        causal_change_source="github",
        causal_change_type="deployment",
        summary="The deterministic causal graph ranks this change first.",
    )


def test_customer_data_classes_and_external_sink_registry_are_exact() -> None:
    assert len(CustomerDataClass) == 8
    assert set(EXTERNAL_DATA_SINK_POLICIES) == set(ExternalDataSink) == {
        ExternalDataSink.GITHUB,
        ExternalDataSink.TENANT_WEBHOOK,
        ExternalDataSink.OPENAI,
        ExternalDataSink.GROQ,
        ExternalDataSink.VERCEL_ANALYTICS,
    }
    assert not policy_for_sink(
        ExternalDataSink.VERCEL_ANALYTICS
    ).enabled_for_authenticated_product
    with pytest.raises(ValueError, match="external_sink_not_allowed"):
        policy_for_sink("UNKNOWN")  # type: ignore[arg-type]


def test_exact_eight_purposes_and_envelope_types() -> None:
    assert set(LLMEgressPurpose) == {
        LLMEgressPurpose.INCIDENT_EXPLANATION,
        LLMEgressPurpose.INCIDENT_COPILOT,
        LLMEgressPurpose.INVESTIGATION_PLANNER,
        LLMEgressPurpose.POST_INCIDENT_REPORT,
        LLMEgressPurpose.EXECUTION_READINESS_SUMMARY,
        LLMEgressPurpose.UNIFIED_BRIEFING_SUMMARY,
        LLMEgressPurpose.SIMILARITY_SUMMARY,
        LLMEgressPurpose.RESPONSE_INTELLIGENCE_SUMMARY,
    }
    envelopes = (
        _evidence_envelope(LLMIncidentExplanationEnvelope),
        _copilot_envelope(),
        _evidence_envelope(LLMInvestigationPlannerEnvelope),
        _evidence_envelope(LLMPostIncidentReportEnvelope),
        LLMExecutionReadinessSummaryEnvelope(
            tenant_id=TENANT_A,
            incident_id="incident:ph6c",
            policy_version="readiness-v1",
            overall_execution_posture="validation_required",
            deterministic_summary="Manual validation is required.",
        ),
        LLMUnifiedBriefingSummaryEnvelope(
            tenant_id=TENANT_A,
            incident_id="incident:ph6c",
            incident_title="Checkout degraded",
            incident_status="open",
            incident_severity="critical",
            summary="Checkout is degraded.",
            root_cause=_root(),
        ),
        LLMSimilaritySummaryEnvelope(
            tenant_id=TENANT_A,
            incident_id="incident:ph6c",
            historical_support_level="limited",
            deterministic_summary="One similar incident was found.",
        ),
        LLMResponseIntelligenceSummaryEnvelope(
            tenant_id=TENANT_A,
            incident_id="incident:ph6c",
            response_priority="high",
            root_cause=_root(),
            overall_historical_support="limited",
            deterministic_summary="Validate the revision before mitigation.",
        ),
    )
    assert {item.purpose for item in envelopes} == set(LLMEgressPurpose)
    assert all(
        build_safe_llm_request(tenant_id=TENANT_A, envelope=item)
        for item in envelopes
    )


@pytest.mark.parametrize(
    "field_name",
    (
        "raw_payload",
        "payload_json",
        "secret",
        "headers",
        "environment",
        "extra_unknown_field",
    ),
)
def test_unknown_fields_fail_closed(field_name: str) -> None:
    with pytest.raises(ValidationError):
        LLMIncidentExplanationEnvelope(
            tenant_id=TENANT_A,
            incident_id="incident:ph6c",
            prompt_version="ph6c-v1",
            **{field_name: {"forbidden": True}},
        )


def test_secret_objects_and_direct_safe_request_construction_fail_closed() -> None:
    with pytest.raises(ValidationError):
        LLMCopilotEnvelope(
            tenant_id=TENANT_A,
            incident_id="incident:ph6c",
            prompt_version="ph6c-v1",
            question=SecretMaterial(b"never-provider-content"),
        )
    with pytest.raises(TypeError):
        SafeLLMRequest(
            purpose=LLMEgressPurpose.INCIDENT_EXPLANATION,
            customer_context_json="{}",
            customer_context_bytes=2,
            customer_data_classes=frozenset(),
        )


def test_raw_payload_and_opaque_json_remain_internal_but_never_serialize() -> None:
    internal = _evidence(
        data={
            "signal_id": "signal:ph6c",
            "reason": "CrashLoopBackOff",
            "raw_payload": {"message": RAW_MARKER},
            "payload_json": json.dumps({"message": RAW_MARKER}),
            "unknown": RAW_MARKER,
        }
    )
    assert RAW_MARKER in str(internal.data)
    safe = safe_evidence_references([internal], tenant_id=TENANT_A)
    request = build_safe_llm_request(
        tenant_id=TENANT_A,
        envelope=LLMIncidentExplanationEnvelope(
            tenant_id=TENANT_A,
            incident_id="incident:ph6c",
            prompt_version="ph6c-v1",
            allowed_evidence_ids=evidence_ids(safe),
            evidence_catalog=safe,
        ),
    )
    assert RAW_MARKER not in request.customer_context_json
    assert "raw_payload" not in request.customer_context_json
    assert "payload_json" not in request.customer_context_json
    assert "unknown" not in request.customer_context_json


def test_secret_matrix_is_scrubbed_from_all_admitted_user_text() -> None:
    secrets = (
        "Bearer " + "human-secret-value-123456",
        "Basic service-secret-value-123456",
        "sk" + "-providerSecret1234567890",
        "gsk" + "_providerSecret1234567890",
        "postgresql://" + "operator:database-secret-value@db.example/topo",
        "https://user:password-value@example.com/hook?token=secret-value",
        "-----BEGIN " + "PRIVATE KEY-----\nprivate-value\n-----END PRIVATE KEY-----",
    )
    question = " | ".join(secrets)
    safe = safe_evidence_references([_evidence()], tenant_id=TENANT_A)
    request = build_safe_llm_request(
        tenant_id=TENANT_A,
        envelope=LLMCopilotEnvelope(
            tenant_id=TENANT_A,
            incident_id="incident:ph6c",
            prompt_version="ph6c-v1",
            question=question,
            allowed_evidence_ids=evidence_ids(safe),
            evidence_catalog=safe,
        ),
    )
    for value in (
        "human-secret-value-123456",
        "service-secret-value-123456",
        "providerSecret1234567890",
        "database-secret-value",
        "password-value",
        "private-value",
    ):
        assert value not in request.customer_context_json


def test_bounds_are_enforced_and_collection_selection_is_deterministic() -> None:
    history = [
        CopilotMessageView(
            message_id=f"message:{index}",
            session_id="session:ph6c",
            incident_id="incident:ph6c",
            role=CopilotMessageRole.USER,
            content=f"question {index}",
            provider=None,
            answer_status=None,
            confidence=None,
            evidence_ids=[],
            suggested_questions=[],
            warning=None,
            created_at="2026-09-12T12:00:00+00:00",
        )
        for index in range(12)
    ]
    selected = safe_conversation_history(history, tenant_id=TENANT_A)
    assert len(selected) == MAX_CONVERSATION_MESSAGES
    assert selected[0].content == "question 2"
    assert selected[-1].content == "question 11"
    evidence = [
        _evidence(data={"signal_id": f"signal:{index}"})
        .model_copy(update={"evidence_id": f"signal:{index}"})
        for index in range(MAX_EVIDENCE_REFS + 5)
    ]
    selected_evidence = safe_evidence_references(evidence, tenant_id=TENANT_A)
    assert len(selected_evidence) == MAX_EVIDENCE_REFS
    assert selected_evidence[-1].evidence_id == "signal:99"
    with pytest.raises(ValidationError):
        LLMIncidentExplanationEnvelope(
            tenant_id=TENANT_A,
            incident_id="i" * 257,
            prompt_version="ph6c-v1",
        )
    oversized = LLMExecutionReadinessSummaryEnvelope(
        tenant_id=TENANT_A,
        incident_id="incident:ph6c",
        policy_version="readiness-v1",
        overall_execution_posture="validation_required",
        deterministic_summary="x" * 1024,
        warnings=tuple("€" * 1024 for _ in range(50)),
    )
    with pytest.raises(ValueError, match="llm_envelope_too_large"):
        build_safe_llm_request(tenant_id=TENANT_A, envelope=oversized)


def test_tenant_identity_is_validation_only_and_mismatch_blocks_dispatch() -> None:
    envelope = _evidence_envelope(LLMIncidentExplanationEnvelope)
    request = build_safe_llm_request(tenant_id=TENANT_A, envelope=envelope)
    assert TENANT_A not in request.customer_context_json
    with pytest.raises(ValueError, match="llm_tenant_mismatch"):
        build_safe_llm_request(tenant_id=TENANT_B, envelope=envelope)
    foreign = _evidence(data={"tenant_id": TENANT_B, "signal_id": "signal:b"})
    with pytest.raises(ValueError, match="llm_tenant_mismatch"):
        safe_evidence_references([foreign], tenant_id=TENANT_A)


class _ProviderResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str


def test_openai_and_groq_receive_the_same_safe_customer_context(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class OpenAIResponses:
        def parse(self, **kwargs):
            captured["openai"] = kwargs["input"]
            return SimpleNamespace(output_parsed=_ProviderResult(answer="ok"))

    class GroqCompletions:
        def create(self, **kwargs):
            captured["groq"] = kwargs["messages"][1]["content"]
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"answer":"ok"}'))]
            )

    monkeypatch.setattr(
        llm_client,
        "_openai_client",
        lambda: SimpleNamespace(responses=OpenAIResponses()),
    )
    monkeypatch.setattr(
        llm_client,
        "create_groq_client",
        lambda: SimpleNamespace(
            chat=SimpleNamespace(completions=GroqCompletions())
        ),
    )
    request = build_safe_llm_request(
        tenant_id=TENANT_A,
        envelope=_evidence_envelope(LLMIncidentExplanationEnvelope),
    )
    openai = llm_client.generate_openai_structured(
        system_prompt="Code-owned test instruction.",
        request=request,
        response_model=_ProviderResult,
        model_name="test-openai",
    )
    groq = llm_client.generate_groq_structured(
        system_prompt="Code-owned test instruction.",
        request=request,
        response_model=_ProviderResult,
        schema_name="ph6c_result",
        model_name="test-groq",
    )
    assert openai.answer == groq.answer == "ok"
    assert captured["openai"] == captured["groq"] == request.customer_context_json
    assert len(captured["openai"].encode("utf-8")) <= MAX_ENVELOPE_BYTES


def test_webhook_contract_is_typed_scrubbed_and_bounded() -> None:
    with pytest.raises(ValidationError):
        IncidentCreatedWebhookPayload(
            incident_id="incident:ph6c",
            status="open",
            severity="critical",
            cluster_name="cluster-a",
            raw_payload={"marker": RAW_MARKER},
        )
    with pytest.raises(ValidationError):
        IncidentCreatedWebhookPayload(
            incident_id="incident:ph6c",
            status="open",
            severity="critical",
            cluster_name="Bearer " + "webhook-body-secret-123456",
        )
    with pytest.raises(ValidationError, match="webhook_payload_type_invalid"):
        WebhookEvent(
            event_id="event:wrong-payload",
            event_type=WebhookEventType.TEST,
            occurred_at=datetime.now(timezone.utc),
            resource_type="webhook",
            resource_id="webhook:ph6c",
            summary="Wrong typed payload must fail.",
            payload=IncidentCreatedWebhookPayload(
                incident_id="incident:ph6c",
                status="open",
                severity="critical",
                cluster_name="cluster-a",
            ),
        )
    event = WebhookEvent(
        event_id="event:ph6c",
        event_type=WebhookEventType.TEST,
        occurred_at=datetime.now(timezone.utc),
        resource_type="webhook",
        resource_id="webhook:ph6c",
        summary="Bearer " + "webhook-secret-value-123456",
        severity="info",
        payload=WebhookTestPayload(webhook_id="webhook:ph6c"),
    )
    body = _event_body(event)
    assert "webhook-secret-value-123456" not in body
    assert "raw_payload" not in body
    assert "payload_json" not in body
    assert len(body.encode("utf-8")) <= MAX_WEBHOOK_BODY_BYTES
    unsafe = event.model_copy(update={"summary": "x" * (MAX_WEBHOOK_BODY_BYTES + 1)})
    with pytest.raises(ValueError, match="webhook_body_too_large"):
        _event_body(unsafe)


def test_static_boundary_has_no_direct_content_bypass_or_authenticated_analytics() -> None:
    service_files = (
        "incident_explanation.py",
        "incident_copilot.py",
        "investigation_planner.py",
        "post_incident_report.py",
        "execution_readiness.py",
        "incident_briefing.py",
        "incident_similarity.py",
        "response_intelligence.py",
    )
    for name in service_files:
        source = (REPOSITORY / "backend/app/services" / name).read_text(
            encoding="utf-8"
        )
        assert "evidence_payload=" not in source
        assert "client.chat.completions.create(" not in source
        assert "create_groq_client" not in source
    for path in (REPOSITORY / "backend/app").rglob("*.py"):
        if path.name == "llm_client.py":
            continue
        source = path.read_text(encoding="utf-8")
        assert ".responses.create(" not in source, path
        assert ".responses.parse(" not in source, path
        assert ".chat.completions.create(" not in source, path
    client = (REPOSITORY / "backend/app/services/llm_client.py").read_text(
        encoding="utf-8"
    )
    assert "request: SafeLLMRequest" in client
    assert "tools=" not in client
    assert "functions=" not in client
    assert "store=False" in client
    layout = (REPOSITORY / "frontend/app/layout.tsx").read_text(encoding="utf-8")
    assert "@vercel/analytics" not in layout
    assert "<Analytics" not in layout
