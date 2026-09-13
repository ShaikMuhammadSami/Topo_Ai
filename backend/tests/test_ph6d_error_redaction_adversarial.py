"""PH-6D adversarial public-error, log and failure-mode acceptance."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.services.llm_client as llm_client
from app.db.database import Base
from app.security.llm_data_boundary import (
    LLMExecutionReadinessSummaryEnvelope,
    build_safe_llm_request,
)
from app.security.secret_redaction import install_logging_redaction
from app.services.webhook_delivery import create_test_event, deliver_event_to_endpoint
from test_ph6b_egress_policy import PUBLIC_V4, StaticResolver, _endpoint
from test_ph6c_llm_data_boundary import TENANT_A


def _safe_request():
    return build_safe_llm_request(
        tenant_id=TENANT_A,
        envelope=LLMExecutionReadinessSummaryEnvelope(
            tenant_id=TENANT_A,
            incident_id="incident:ph6d",
            policy_version="readiness-v1",
            overall_execution_posture="manual_only",
            deterministic_summary="Deterministic core truth remains available.",
        ),
    )


def test_provider_failure_never_echoes_customer_body_target_or_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "ph6d-provider-customer-secret"

    class Responses:
        def create(self, **kwargs):
            raise RuntimeError(
                f"{marker} https://10.0.0.8/path?signature={marker}"
            )

    monkeypatch.setattr(
        llm_client,
        "_openai_client",
        lambda: SimpleNamespace(responses=Responses()),
    )
    with pytest.raises(llm_client.OpenAIProviderError) as captured:
        llm_client.generate_openai_text(
            system_prompt="Code-owned instruction.",
            request=_safe_request(),
            model_name="test",
        )
    rendered = str(captured.value)
    assert rendered == "OpenAI Responses API request failed (RuntimeError)."
    assert marker not in rendered
    assert "10.0.0.8" not in rendered


def test_invalid_provider_response_has_bounded_non_authoritative_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        llm_client,
        "_openai_client",
        lambda: SimpleNamespace(
            responses=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(output_text="")
            )
        ),
    )
    with pytest.raises(
        llm_client.OpenAIProviderError,
        match="OpenAI returned an empty response",
    ):
        llm_client.generate_openai_text(
            system_prompt="Code-owned instruction.",
            request=_safe_request(),
            model_name="test",
        )


def test_webhook_transport_failure_persists_no_remote_error_or_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "ph6d-webhook-transport-secret"
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)

    def explode(*args, **kwargs):
        raise RuntimeError(
            f"Bearer {marker} https://169.254.169.254/?token={marker}"
        )

    monkeypatch.setattr("app.services.webhook_delivery.deliver_webhook_once", explode)
    try:
        with Session(engine) as session:
            endpoint = _endpoint("https://hooks.example/path")
            endpoint.signing_secret_ref = None
            endpoint.protected_headers_secret_ref = None
            endpoint.tenant_id = TENANT_A
            session.add(endpoint)
            session.commit()
            result = deliver_event_to_endpoint(
                session,
                endpoint,
                create_test_event(endpoint.webhook_id, "bounded test"),
                tenant_id=TENANT_A,
                secret_store=SimpleNamespace(),
                resolver=StaticResolver((PUBLIC_V4,)),
            )
        assert result.error_message == "Webhook transport failed (upstream_unavailable)."
        assert result.response_body is None
        assert marker not in (result.error_message or "")
        assert "169.254.169.254" not in (result.error_message or "")
    finally:
        engine.dispose()


def test_logging_boundary_removes_secrets_and_credential_urls(caplog) -> None:
    marker = "ph6d-log-secret-value"
    install_logging_redaction()
    logger = logging.getLogger("ph6d.acceptance")
    with caplog.at_level(logging.WARNING, logger=logger.name):
        logger.warning(
            "Bearer %s %s",
            marker,
            f"https://user:{marker}@example.com/path?token={marker}",
        )
    rendered = caplog.text
    assert marker not in rendered
    assert "?token=" not in rendered

