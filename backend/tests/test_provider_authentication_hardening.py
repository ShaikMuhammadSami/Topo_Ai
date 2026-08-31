from __future__ import annotations
from domain_tenant_fixtures import TEST_TENANT, TEST_HEADERS, seed_domain_tenant

import base64
import hashlib
import hmac
import json
import secrets
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_session
from app.db.models import (
    ChangeEventRecord,
    ChangeSourceDeadLetterRecord,
    ChangeSourceDeliveryRecord,
    ChangeSourceRecord,
)
from app.main import create_app
from app.security.api_tokens import token_digest
from app.security.auth_config import load_auth_configuration
from app.services.change_source_ingest import _verify
from app.services.webhook_security import WebhookAuthenticationError


AUTH_FAILED = {"detail": "Change-source authentication failed."}
AUTH_UNAVAILABLE = {
    "detail": "Change-source authentication is unavailable."
}
ORIGIN = "https://topo.test"


@pytest.fixture()
def provider_app(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine, subject="test:provider-admin")
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    human_token = "human-provider-test-" + secrets.token_urlsafe(32)
    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.setenv(
        "TOPO_API_TOKEN_HASHES_JSON",
        json.dumps(
            {
                token_digest(human_token): {
                    "subject": "test:provider-admin",
                    "display_name": "Provider Admin",
                    "roles": ["admin", "operator"],
                }
            }
        ),
    )
    monkeypatch.setenv(
        "TOPO_BROWSER_ALLOWED_ORIGINS_JSON",
        json.dumps([ORIGIN]),
    )
    configuration = load_auth_configuration(database_url="sqlite://")
    application = create_app(
        auth_configuration=configuration,
        session_factory=sessions,
        database_initializer=lambda: None,
    )

    def override_session():
        with sessions() as session:
            yield session

    application.dependency_overrides[get_session] = override_session
    try:
        yield application, sessions, human_token
    finally:
        application.dependency_overrides.clear()
        engine.dispose()


def _source(
    sessions,
    *,
    source_id: str = "source:github",
    source_type: str = "github",
    secret_ref: str = "TOPO_PROVIDER_TEST_SECRET",
    enabled: bool = True,
    config: dict | None = None,
) -> ChangeSourceRecord:
    record = ChangeSourceRecord(
        tenant_id=TEST_TENANT,
        source_id=source_id,
        name=f"{source_type} security test",
        source_type=source_type,
        enabled=enabled,
        secret_ref=secret_ref,
        config_json=json.dumps(config or {}),
        filters_json="{}",
        status="configured",
        delivery_count=0,
        failure_count=0,
        created_at="2026-08-29T00:00:00+00:00",
        updated_at="2026-08-29T00:00:00+00:00",
    )
    with sessions() as session:
        session.add(record)
        session.commit()
    return record


def _github_headers(secret: str, body: bytes, delivery: str = "delivery-1"):
    signature = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-GitHub-Event": "ping",
        "X-GitHub-Delivery": delivery,
        "X-Hub-Signature-256": f"sha256={signature}",
    }


def _row_counts(sessions) -> tuple[int, int, int]:
    with sessions() as session:
        return tuple(
            int(
                session.scalar(select(func.count()).select_from(model))
                or 0
            )
            for model in (
                ChangeSourceDeliveryRecord,
                ChangeEventRecord,
                ChangeSourceDeadLetterRecord,
            )
        )


def test_provider_source_states_have_safe_outward_semantics(
    provider_app,
    monkeypatch,
) -> None:
    application, sessions, _ = provider_app
    _source(
        sessions,
        source_id="source:disabled",
        enabled=False,
    )
    _source(
        sessions,
        source_id="source:unavailable",
        secret_ref="TOPO_PROVIDER_ABSENT_SECRET",
    )
    _source(
        sessions,
        source_id="source:bad-config",
    )
    monkeypatch.delenv("TOPO_PROVIDER_ABSENT_SECRET", raising=False)
    monkeypatch.setenv("TOPO_PROVIDER_TEST_SECRET", secrets.token_urlsafe(32))
    with sessions() as session:
        bad_config = session.get(ChangeSourceRecord, "source:bad-config")
        assert bad_config is not None
        bad_config.config_json = "{invalid-json"
        session.commit()

    with TestClient(application) as client:
        unknown = client.post(
            "/api/v1/change-source-webhooks/source%3Aunknown",
            content=b"{}",
        )
        disabled = client.post(
            "/api/v1/change-source-webhooks/source%3Adisabled",
            content=b"{}",
        )
        unavailable = client.post(
            "/api/v1/change-source-webhooks/source%3Aunavailable",
            content=b"{}",
        )
        bad_config = client.post(
            "/api/v1/change-source-webhooks/source%3Abad-config",
            content=b"{}",
        )

    assert unknown.status_code == disabled.status_code == 401
    assert unknown.json() == disabled.json() == AUTH_FAILED
    assert unavailable.status_code == 503
    assert unavailable.json() == AUTH_UNAVAILABLE
    assert bad_config.status_code == 503
    assert bad_config.json() == AUTH_UNAVAILABLE
    assert "TOPO_PROVIDER_ABSENT_SECRET" not in unavailable.text


def test_signature_is_authoritative_before_json_or_persistence(
    provider_app,
    monkeypatch,
) -> None:
    application, sessions, _ = provider_app
    secret = secrets.token_urlsafe(32)
    monkeypatch.setenv("TOPO_PROVIDER_TEST_SECRET", secret)
    _source(sessions)
    malformed = b"{not-json"

    with TestClient(application) as client:
        invalid = client.post(
            "/api/v1/change-source-webhooks/source%3Agithub",
            content=malformed,
            headers={"X-Hub-Signature-256": "sha256=invalid"},
        )
        after_invalid = _row_counts(sessions)
        valid = client.post(
            "/api/v1/change-source-webhooks/source%3Agithub",
            content=malformed,
            headers=_github_headers(secret, malformed),
        )

    assert invalid.status_code == 401
    assert invalid.json() == AUTH_FAILED
    assert after_invalid == (0, 0, 0)
    assert valid.status_code == 400
    assert valid.json()["detail"] == "Webhook must contain valid JSON."
    assert _row_counts(sessions) == (0, 0, 0)


def test_authenticated_exact_replay_has_one_delivery_and_no_duplicate_effect(
    provider_app,
    monkeypatch,
) -> None:
    application, sessions, _ = provider_app
    secret = secrets.token_urlsafe(32)
    monkeypatch.setenv("TOPO_PROVIDER_TEST_SECRET", secret)
    _source(sessions)
    body = b"{}"
    headers = _github_headers(secret, body, "exact-replay")

    with TestClient(application) as client:
        first = client.post(
            "/api/v1/change-source-webhooks/source%3Agithub",
            content=body,
            headers=headers,
        )
        second = client.post(
            "/api/v1/change-source-webhooks/source%3Agithub",
            content=body,
            headers=headers,
        )

    assert first.status_code == second.status_code == 200
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert first.json()["delivery_id"] == second.json()["delivery_id"]
    assert _row_counts(sessions) == (1, 0, 0)


def test_human_session_bearer_and_agent_material_cannot_substitute_provider_auth(
    provider_app,
    monkeypatch,
) -> None:
    application, sessions, human_token = provider_app
    secret = secrets.token_urlsafe(32)
    monkeypatch.setenv("TOPO_PROVIDER_TEST_SECRET", secret)
    _source(sessions)

    with TestClient(application, base_url=ORIGIN) as client:
        login = client.post(
            "/api/v1/auth/session",
            headers={
                "Authorization": f"Bearer {human_token}",
                "Origin": ORIGIN,
            },
        )
        assert login.status_code == 201
        session_attempt = client.post(
            "/api/v1/change-source-webhooks/source%3Agithub",
            content=b"{}",
        )
        bearer_attempt = client.post(
            "/api/v1/change-source-webhooks/source%3Agithub",
            content=b"{}",
            headers={"Authorization": f"Bearer {human_token}"},
        )
        agent_attempt = client.post(
            "/api/v1/change-source-webhooks/source%3Agithub",
            content=b"{}",
            headers={
                "Authorization": "Bearer agent-" + "domain-material"
            },
        )
        provider_on_agent = client.get(
            "/api/v1/agent/config",
            headers=_github_headers(secret, b"{}"),
        )

    with TestClient(application) as credential_only_client:
        provider_on_human = credential_only_client.get(
            "/api/v1/system/whoami",
            headers=_github_headers(secret, b"{}"),
        )

    for response in (session_attempt, bearer_attempt, agent_attempt):
        assert response.status_code == 401
        assert response.json() == AUTH_FAILED
    assert provider_on_human.status_code == 401
    assert provider_on_agent.status_code == 401
    assert _row_counts(sessions) == (0, 0, 0)


def test_every_supported_provider_verifier_accepts_only_its_credential(
    monkeypatch,
) -> None:
    body = b"{}"
    secret = secrets.token_urlsafe(32)
    monkeypatch.setenv("TOPO_PROVIDER_TEST_SECRET", secret)

    github = ChangeSourceRecord(
        tenant_id=TEST_TENANT,
        source_id="source:github",
        name="github",
        source_type="github",
        enabled=True,
        secret_ref="TOPO_PROVIDER_TEST_SECRET",
        config_json="{}",
        filters_json="{}",
        status="configured",
        delivery_count=0,
        failure_count=0,
    )
    _verify(source=github, body=body, headers=_github_headers(secret, body))

    terraform = ChangeSourceRecord(
        tenant_id=TEST_TENANT,
        source_id="source:terraform",
        name="terraform",
        source_type="terraform_cloud",
        enabled=True,
        secret_ref="TOPO_PROVIDER_TEST_SECRET",
        config_json="{}",
        filters_json="{}",
        status="configured",
        delivery_count=0,
        failure_count=0,
    )
    _verify(
        source=terraform,
        body=body,
        headers={
            "X-TFE-Notification-Signature": hmac.new(
                secret.encode(), body, hashlib.sha512
            ).hexdigest()
        },
    )

    jenkins = ChangeSourceRecord(
        tenant_id=TEST_TENANT,
        source_id="source:jenkins",
        name="jenkins",
        source_type="jenkins",
        enabled=True,
        secret_ref="TOPO_PROVIDER_TEST_SECRET",
        config_json="{}",
        filters_json="{}",
        status="configured",
        delivery_count=0,
        failure_count=0,
    )
    _verify(
        source=jenkins,
        body=body,
        headers={
            "X-Topo-Signature-256": "sha256="
            + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        },
    )

    azure = ChangeSourceRecord(
        tenant_id=TEST_TENANT,
        source_id="source:azure",
        name="azure",
        source_type="azure_devops",
        enabled=True,
        secret_ref="TOPO_PROVIDER_TEST_SECRET",
        config_json=json.dumps({"username": "topo-webhook"}),
        filters_json="{}",
        status="configured",
        delivery_count=0,
        failure_count=0,
    )
    basic = base64.b64encode(f"topo-webhook:{secret}".encode()).decode()
    _verify(
        source=azure,
        body=body,
        headers={"Authorization": f"Basic {basic}"},
    )

    gitlab_key = secrets.token_bytes(32)
    gitlab_secret = "whsec_" + base64.b64encode(gitlab_key).decode()
    monkeypatch.setenv("TOPO_PROVIDER_GITLAB_SECRET", gitlab_secret)
    gitlab = ChangeSourceRecord(
        tenant_id=TEST_TENANT,
        source_id="source:gitlab",
        name="gitlab",
        source_type="gitlab",
        enabled=True,
        secret_ref="TOPO_PROVIDER_GITLAB_SECRET",
        config_json=json.dumps({"signature_max_age": 300}),
        filters_json="{}",
        status="configured",
        delivery_count=0,
        failure_count=0,
    )
    timestamp = str(int(time.time()))
    webhook_id = "gitlab-delivery"
    signature = "v1," + base64.b64encode(
        hmac.new(
            gitlab_key,
            f"{webhook_id}.{timestamp}.".encode() + body,
            hashlib.sha256,
        ).digest()
    ).decode()
    headers = {
        "Webhook-Id": webhook_id,
        "Webhook-Timestamp": timestamp,
        "Webhook-Signature": signature,
    }
    _verify(source=gitlab, body=body, headers=headers)

    stale_timestamp = str(int(time.time()) - 301)
    stale_signature = "v1," + base64.b64encode(
        hmac.new(
            gitlab_key,
            f"{webhook_id}.{stale_timestamp}.".encode() + body,
            hashlib.sha256,
        ).digest()
    ).decode()
    with pytest.raises(WebhookAuthenticationError):
        _verify(
            source=gitlab,
            body=body,
            headers={
                "Webhook-Id": webhook_id,
                "Webhook-Timestamp": stale_timestamp,
                "Webhook-Signature": stale_signature,
            },
        )

    gitlab_secret_token = ChangeSourceRecord(
        tenant_id=TEST_TENANT,
        source_id="source:gitlab-secret-token",
        name="gitlab secret token",
        source_type="gitlab",
        enabled=True,
        secret_ref="TOPO_PROVIDER_TEST_SECRET",
        config_json=json.dumps({"auth_mode": "secret_token"}),
        filters_json="{}",
        status="configured",
        delivery_count=0,
        failure_count=0,
    )
    _verify(
        source=gitlab_secret_token,
        body=body,
        headers={"X-Gitlab-Token": secret},
    )


def test_invalid_provider_credentials_are_not_logged(
    provider_app,
    monkeypatch,
    caplog,
) -> None:
    application, sessions, _ = provider_app
    secret = secrets.token_urlsafe(32)
    signature_marker = "sha256=" + secrets.token_hex(32)
    monkeypatch.setenv("TOPO_PROVIDER_TEST_SECRET", secret)
    _source(sessions)

    with TestClient(application) as client:
        response = client.post(
            "/api/v1/change-source-webhooks/source%3Agithub",
            content=b"{}",
            headers={"X-Hub-Signature-256": signature_marker},
        )

    assert response.status_code == 401
    assert secret not in response.text
    assert signature_marker not in response.text
    assert secret not in caplog.text
    assert signature_marker not in caplog.text
