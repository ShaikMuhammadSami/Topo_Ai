"""PH-6D adversarial LLM, tenant and webhook customer-data acceptance."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.services.llm_client as llm_client
from app.db.database import Base
from app.models.incident_copilot import CopilotMessageRole, CopilotMessageView
from app.models.incident_explanation import EvidenceType, GroundingEvidence
from app.models.webhooks import (
    ChangeRiskDetectedWebhookPayload,
    IncidentCreatedWebhookPayload,
    IncidentStatusChangedWebhookPayload,
    RecommendationGeneratedWebhookPayload,
    RecoveryWebhookPayload,
    WebhookEvent,
    WebhookEventType,
    WebhookTestPayload,
)
from app.repositories.tenant_scope import TenantResourceNotFound
from app.security.customer_data_policy import (
    EXTERNAL_DATA_SINK_POLICIES,
    ExternalDataSink,
)
from app.security.egress_inventory import CustomerDataClass
from app.security.llm_data_boundary import (
    MAX_ENVELOPE_BYTES,
    LLMCopilotEnvelope,
    LLMEgressPurpose,
    LLMExecutionReadinessSummaryEnvelope,
    LLMIncidentExplanationEnvelope,
    LLMInvestigationPlannerEnvelope,
    LLMPostIncidentReportEnvelope,
    LLMResponseIntelligenceSummaryEnvelope,
    LLMSimilaritySummaryEnvelope,
    LLMUnifiedBriefingSummaryEnvelope,
    build_safe_llm_request,
    evidence_ids,
    responder_notes_from_evidence,
    safe_conversation_history,
    safe_evidence_references,
)
from app.services.webhook_delivery import (
    MAX_WEBHOOK_BODY_BYTES,
    _event_body,
    deliver_event_to_endpoint,
)
from test_ph6b_egress_policy import _endpoint
from test_ph6c_llm_data_boundary import (
    RAW_MARKER,
    TENANT_A,
    TENANT_B,
    _copilot_envelope,
    _evidence,
    _evidence_envelope,
    _root,
)


class _ProviderResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str


def _all_envelopes():
    safe = safe_evidence_references([_evidence()], tenant_id=TENANT_A)
    return (
        _evidence_envelope(LLMIncidentExplanationEnvelope),
        _copilot_envelope(),
        _evidence_envelope(LLMInvestigationPlannerEnvelope),
        LLMPostIncidentReportEnvelope(
            tenant_id=TENANT_A,
            incident_id="incident:ph6d",
            prompt_version="ph6d-v1",
            allowed_evidence_ids=evidence_ids(safe),
            evidence_catalog=safe,
            responder_notes=("Validate the observed revision.",),
        ),
        LLMExecutionReadinessSummaryEnvelope(
            tenant_id=TENANT_A,
            incident_id="incident:ph6d",
            policy_version="readiness-v1",
            overall_execution_posture="manual_only",
            deterministic_summary="Manual validation remains required.",
        ),
        LLMUnifiedBriefingSummaryEnvelope(
            tenant_id=TENANT_A,
            incident_id="incident:ph6d",
            incident_title="Checkout degraded",
            incident_status="open",
            incident_severity="critical",
            summary="Deterministic incident facts are available.",
            root_cause=_root(),
        ),
        LLMSimilaritySummaryEnvelope(
            tenant_id=TENANT_A,
            incident_id="incident:ph6d",
            historical_support_level="limited",
            deterministic_summary="One comparable incident exists.",
        ),
        LLMResponseIntelligenceSummaryEnvelope(
            tenant_id=TENANT_A,
            incident_id="incident:ph6d",
            response_priority="high",
            root_cause=_root(),
            overall_historical_support="limited",
            deterministic_summary="Validate before manual mitigation.",
        ),
    )


def test_customer_data_sink_and_llm_vocabulary_are_closed() -> None:
    assert len(CustomerDataClass) == 8
    assert len(EXTERNAL_DATA_SINK_POLICIES) == len(ExternalDataSink) == 5
    assert set(ExternalDataSink) == {
        ExternalDataSink.GITHUB,
        ExternalDataSink.TENANT_WEBHOOK,
        ExternalDataSink.OPENAI,
        ExternalDataSink.GROQ,
        ExternalDataSink.VERCEL_ANALYTICS,
    }
    assert len(LLMEgressPurpose) == 8
    assert {envelope.purpose for envelope in _all_envelopes()} == set(
        LLMEgressPurpose
    )


def test_all_eight_envelopes_are_tenant_hidden_bounded_and_deterministic() -> None:
    for envelope in _all_envelopes():
        first = build_safe_llm_request(tenant_id=TENANT_A, envelope=envelope)
        second = build_safe_llm_request(tenant_id=TENANT_A, envelope=envelope)
        assert first.customer_context_json == second.customer_context_json
        assert first.customer_context_bytes == len(
            first.customer_context_json.encode("utf-8")
        )
        assert first.customer_context_bytes <= MAX_ENVELOPE_BYTES
        assert TENANT_A not in first.customer_context_json


def test_raw_nested_json_and_unreviewed_evidence_keys_never_reach_provider() -> None:
    internal = _evidence(
        data={
            "tenant_id": TENANT_A,
            "signal_id": "signal:ph6d",
            "reason": "CrashLoopBackOff",
            "raw_payload": {"deep": {"message": RAW_MARKER}},
            "payload_json": json.dumps(
                {"encoded": json.dumps({"message": RAW_MARKER})}
            ),
            "arbitrary_extra": {"message": RAW_MARKER},
        }
    )
    assert RAW_MARKER in str(internal.data)
    safe = safe_evidence_references([internal], tenant_id=TENANT_A)
    request = build_safe_llm_request(
        tenant_id=TENANT_A,
        envelope=LLMIncidentExplanationEnvelope(
            tenant_id=TENANT_A,
            incident_id="incident:ph6d",
            prompt_version="ph6d-v1",
            allowed_evidence_ids=evidence_ids(safe),
            evidence_catalog=safe,
        ),
    )
    assert RAW_MARKER not in request.customer_context_json
    for forbidden in ("raw_payload", "payload_json", "arbitrary_extra"):
        assert forbidden not in request.customer_context_json


@pytest.mark.parametrize(
    "field_name",
    (
        "raw_payload",
        "payload_json",
        "headers",
        "secret",
        "environment",
        "provider_body",
        "arbitrary_extra",
    ),
)
def test_unknown_envelope_fields_fail_closed(field_name: str) -> None:
    with pytest.raises(ValidationError):
        LLMIncidentExplanationEnvelope(
            tenant_id=TENANT_A,
            incident_id="incident:ph6d",
            prompt_version="ph6d-v1",
            **{field_name: {"marker": RAW_MARKER}},
        )


def test_foreign_or_unbacked_evidence_ids_fail_before_provider_dispatch() -> None:
    safe = safe_evidence_references([_evidence()], tenant_id=TENANT_A)
    with pytest.raises(ValueError, match="llm_evidence_reference_invalid"):
        LLMIncidentExplanationEnvelope(
            tenant_id=TENANT_A,
            incident_id="incident:ph6d",
            prompt_version="ph6d-v1",
            allowed_evidence_ids=("signal:foreign-tenant",),
            evidence_catalog=safe,
        )


def test_cross_tenant_envelope_and_evidence_never_reach_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_calls = 0

    def provider() -> None:
        nonlocal provider_calls
        provider_calls += 1

    monkeypatch.setattr(llm_client, "_openai_client", provider)
    envelope = _evidence_envelope(LLMIncidentExplanationEnvelope)
    with pytest.raises(ValueError, match="llm_tenant_mismatch"):
        build_safe_llm_request(tenant_id=TENANT_B, envelope=envelope)
    foreign = _evidence(data={"tenant_id": TENANT_B, "signal_id": "signal:b"})
    with pytest.raises(ValueError, match="llm_tenant_mismatch"):
        safe_evidence_references([foreign], tenant_id=TENANT_A)
    assert provider_calls == 0


def test_user_history_and_responder_note_secret_matrix_is_scrubbed() -> None:
    secret_text = " | ".join(
        (
            "Bearer ph6d-bearer-secret",
            "Basic ph6d-basic-secret",
            "sk" + "-ph6dProviderSecret123456",
            "gsk" + "_ph6dGroqSecret123456",
            "postgresql://" + "user:ph6d-db-secret@db.example/topo",
            "https://user:ph6d-url-secret@example.com/path?token=hidden",
            "-----BEGIN "
            + "PRIVATE KEY-----\nph6d-private-secret\n-----END PRIVATE KEY-----",
        )
    )
    history = [
        CopilotMessageView(
            message_id="message:ph6d",
            session_id="session:ph6d",
            incident_id="incident:ph6d",
            role=CopilotMessageRole.USER,
            content=secret_text,
            provider=None,
            answer_status=None,
            confidence=None,
            evidence_ids=[],
            suggested_questions=[],
            warning=None,
            created_at="2026-09-13T00:00:00+00:00",
        )
    ]
    conversation = safe_conversation_history(history, tenant_id=TENANT_A)
    note_evidence = GroundingEvidence(
        evidence_id="investigation:ph6d",
        evidence_type=EvidenceType.INVESTIGATION,
        summary="Responder note",
        observed_at="2026-09-13T00:00:00+00:00",
        data={
            "tenant_id": TENANT_A,
            "findings": [{"responder_notes": secret_text}],
        },
    )
    notes = responder_notes_from_evidence([note_evidence], tenant_id=TENANT_A)
    envelope = LLMCopilotEnvelope(
        tenant_id=TENANT_A,
        incident_id="incident:ph6d",
        prompt_version="ph6d-v1",
        question=secret_text,
        conversation_history=conversation,
    )
    copilot_json = build_safe_llm_request(
        tenant_id=TENANT_A, envelope=envelope
    ).customer_context_json
    report_json = build_safe_llm_request(
        tenant_id=TENANT_A,
        envelope=LLMPostIncidentReportEnvelope(
            tenant_id=TENANT_A,
            incident_id="incident:ph6d",
            prompt_version="ph6d-v1",
            responder_notes=notes,
        ),
    ).customer_context_json
    combined = copilot_json + report_json
    for marker in (
        "ph6d-bearer-secret",
        "ph6d-basic-secret",
        "ph6dProviderSecret123456",
        "ph6dGroqSecret123456",
        "ph6d-db-secret",
        "ph6d-url-secret",
        "ph6d-private-secret",
    ):
        assert marker not in combined


def test_openai_and_groq_receive_identical_safe_context_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    class OpenAIResponses:
        def parse(self, **kwargs):
            captured["openai"] = kwargs["input"]
            return SimpleNamespace(output_parsed=_ProviderResult(answer="ok"))

    class GroqCompletions:
        def create(self, **kwargs):
            captured["groq"] = kwargs["messages"][1]["content"]
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"answer":"ok"}')
                    )
                ]
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
    llm_client.generate_openai_structured(
        system_prompt="Code-owned instruction.",
        request=request,
        response_model=_ProviderResult,
        model_name="test",
    )
    llm_client.generate_groq_structured(
        system_prompt="Code-owned instruction.",
        request=request,
        response_model=_ProviderResult,
        schema_name="ph6d",
        model_name="test",
    )
    assert captured == {
        "openai": request.customer_context_json,
        "groq": request.customer_context_json,
    }
    assert TENANT_A not in captured["openai"]


def _webhook_events() -> tuple[WebhookEvent, ...]:
    common = {
        "occurred_at": datetime(2026, 9, 13, tzinfo=timezone.utc),
        "source": "topo-ai",
        "severity": "critical",
    }
    cases = (
        (
            WebhookEventType.INCIDENT_CREATED,
            IncidentCreatedWebhookPayload(
                incident_id="incident:ph6d",
                status="open",
                severity="critical",
                cluster_name="cluster-a",
            ),
        ),
        (
            WebhookEventType.INCIDENT_STATUS_CHANGED,
            IncidentStatusChangedWebhookPayload(
                incident_id="incident:ph6d",
                status="resolved",
                updated_at="2026-09-13T00:00:00+00:00",
            ),
        ),
        (
            WebhookEventType.RECOMMENDATION_GENERATED,
            RecommendationGeneratedWebhookPayload(
                recommendation_id="recommendation:ph6d",
                analysis_id="analysis:ph6d",
                signal_id="signal:ph6d",
                action_type="rollback",
                status="proposed",
                confidence=0.8,
                risk="medium",
            ),
        ),
        (
            WebhookEventType.RECOVERY_VERIFIED,
            RecoveryWebhookPayload(
                verification_id="verification:ph6d",
                recommendation_id="recommendation:ph6d",
                analysis_id="analysis:ph6d",
                status="verified",
                confidence=0.9,
                passed_count=3,
                failed_count=0,
                unknown_count=0,
            ),
        ),
        (
            WebhookEventType.RECOVERY_FAILED,
            RecoveryWebhookPayload(
                verification_id="verification:failed",
                recommendation_id="recommendation:ph6d",
                analysis_id="analysis:ph6d",
                status="failed",
                confidence=0.9,
                passed_count=0,
                failed_count=1,
                unknown_count=0,
            ),
        ),
        (
            WebhookEventType.RECOVERY_INCONCLUSIVE,
            RecoveryWebhookPayload(
                verification_id="verification:unknown",
                recommendation_id="recommendation:ph6d",
                analysis_id="analysis:ph6d",
                status="inconclusive",
                confidence=0.4,
                passed_count=0,
                failed_count=0,
                unknown_count=1,
            ),
        ),
        (
            WebhookEventType.CHANGE_RISK_DETECTED,
            ChangeRiskDetectedWebhookPayload(
                analysis_id="analysis:ph6d",
                snapshot_id="snapshot:ph6d",
                root_entity_id="entity:ph6d",
                root_entity_name="checkout",
                change_type="deployment",
                risk_score=0.8,
                risk_level="high",
                deployment_decision="manual_review",
                affected_entity_count=3,
                recommendation="Validate the new revision.",
            ),
        ),
        (
            WebhookEventType.TEST,
            WebhookTestPayload(webhook_id="webhook:ph6d"),
        ),
    )
    return tuple(
        WebhookEvent(
            event_id=f"event:{index}",
            event_type=event_type,
            resource_type="incident",
            resource_id="incident:ph6d",
            summary="Typed event.",
            payload=payload,
            **common,
        )
        for index, (event_type, payload) in enumerate(cases)
    )


def test_all_webhook_event_types_are_typed_and_raw_fields_are_impossible() -> None:
    events = _webhook_events()
    assert {event.event_type for event in events} == set(WebhookEventType)
    for event in events:
        body = _event_body(event)
        assert len(body.encode("utf-8")) <= MAX_WEBHOOK_BODY_BYTES
        assert "raw_payload" not in body
        assert "payload_json" not in body
    with pytest.raises(ValidationError):
        IncidentCreatedWebhookPayload(
            incident_id="incident:ph6d",
            status="open",
            severity="critical",
            cluster_name="cluster-a",
            payload_json={"marker": RAW_MARKER},
        )


def test_webhook_utf8_byte_limit_and_secret_body_scrubbing() -> None:
    event = _webhook_events()[-1].model_copy(
        update={"summary": "€" * MAX_WEBHOOK_BODY_BYTES}
    )
    with pytest.raises(ValueError, match="webhook_body_too_large"):
        _event_body(event)
    secret_event = WebhookEvent(
        event_id="event:secret",
        event_type=WebhookEventType.TEST,
        occurred_at=datetime(2026, 9, 13, tzinfo=timezone.utc),
        resource_type="webhook",
        resource_id="webhook:ph6d",
        summary="Bearer ph6d-webhook-secret",
        payload=WebhookTestPayload(webhook_id="webhook:ph6d"),
    )
    body = _event_body(secret_event)
    assert "ph6d-webhook-secret" not in body


def test_cross_tenant_webhook_endpoint_fails_before_external_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    dispatches = 0

    def dispatch(*args, **kwargs):
        nonlocal dispatches
        dispatches += 1
        return 200

    monkeypatch.setattr("app.services.webhook_delivery.deliver_webhook_once", dispatch)
    try:
        with Session(engine) as session:
            endpoint = _endpoint("https://hooks.example/path")
            endpoint.signing_secret_ref = None
            endpoint.protected_headers_secret_ref = None
            endpoint.tenant_id = TENANT_B
            session.add(endpoint)
            session.commit()
            with pytest.raises(TenantResourceNotFound):
                deliver_event_to_endpoint(
                    session,
                    endpoint,
                    _webhook_events()[-1],
                    tenant_id=TENANT_A,
                    secret_store=SimpleNamespace(),
                )
    finally:
        engine.dispose()
    assert dispatches == 0
