"""PH-4C provider/webhook consumer integration and secrecy acceptance."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.db.database import Base, get_session
from app.db.models import (
    ChangeSourceDeliveryRecord,
    ChangeSourceRecord,
    SecretRecord,
    SecretVersionRecord,
    WebhookEndpointRecord,
)
from app.main import create_app
from app.models.change_sources import ChangeSourceCreate, ChangeSourceUpdate
from app.models.webhooks import WebhookEndpointCreate, WebhookEndpointUpdate
from app.security.api_tokens import token_digest
from app.security.auth_config import load_auth_configuration
from app.security.secret_keyring import SecretKeyring, SecretStoreConfiguration
from app.services.secret_store import EncryptedDatabaseSecretStore
from app.services.secret_consumer_policy import source_binding, webhook_binding
from app.services.secret_consumers import (
    create_change_source_secure,
    create_webhook_endpoint_secure,
    update_change_source_secure,
    update_webhook_endpoint_secure,
)
from app.models.secret_store import SecretPurpose
from domain_tenant_fixtures import TEST_TENANT, seed_domain_tenant


@pytest.fixture()
def consumer_app(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine, subject="test:secret-consumer-admin")
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    token = "consumer-admin-" + secrets.token_urlsafe(32)
    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.setenv("TOPO_API_TOKEN_HASHES_JSON", json.dumps({
        token_digest(token): {
            "subject": "test:secret-consumer-admin", "display_name": "Admin",
            "roles": ["admin", "operator"],
        }
    }))
    configuration = load_auth_configuration(database_url="sqlite://")
    store = EncryptedDatabaseSecretStore(SecretStoreConfiguration(
        "encrypted_db", SecretKeyring({"test": secrets.token_bytes(32)}, "test")
    ))
    monkeypatch.setattr(main_module, "load_secret_store_configuration", lambda: store.configuration)
    application = create_app(
        auth_configuration=configuration, session_factory=sessions,
        database_initializer=lambda: None,
    )

    def override_session():
        with sessions() as session:
            yield session

    application.dependency_overrides[get_session] = override_session
    try:
        yield application, sessions, store, {
            "Authorization": f"Bearer {token}", "X-Topo-Tenant-ID": TEST_TENANT,
        }
    finally:
        application.dependency_overrides.clear()
        engine.dispose()


def _github_headers(secret: str, body: bytes) -> dict[str, str]:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {
        "X-GitHub-Event": "ping", "X-GitHub-Delivery": secrets.token_hex(8),
        "X-Hub-Signature-256": f"sha256={digest}",
    }


def test_source_api_is_write_only_atomic_and_provider_uses_secret_store(consumer_app):
    application, sessions, _, headers = consumer_app
    raw = "ph4c-provider-marker-" + secrets.token_urlsafe(24)
    with TestClient(application) as client:
        created = client.post("/api/v1/change-sources", headers=headers, json={
            "name": "GitHub PH-4C", "source_type": "github", "credential": raw,
            "enabled": True, "config": {}, "filters": {},
        })
        assert created.status_code == 201
        value = created.json()
        assert value["credential_configured"] is True
        assert "secret_ref" not in value and raw not in created.text
        source_id = value["source_id"]
        doctor = client.get(
            f"/api/v1/change-sources/{source_id}/doctor", headers=headers
        )
        assert doctor.status_code == 200
        assert "secret_ref" not in doctor.text and raw not in doctor.text
        body = b"{}"
        callback = client.post(
            f"/api/v1/change-source-webhooks/{source_id}", content=body,
            headers=_github_headers(raw, body),
        )
        assert callback.status_code == 200

    with Session(sessions.kw["bind"]) as session:
        source = session.scalar(select(ChangeSourceRecord).where(ChangeSourceRecord.source_id == source_id))
        assert source is not None and source.secret_ref.startswith("secret:")
        assert session.scalar(select(SecretRecord).where(SecretRecord.secret_ref == source.secret_ref)) is not None
        for version in session.scalars(select(SecretVersionRecord)).all():
            assert raw.encode() not in version.ciphertext
        receipt = session.scalar(select(ChangeSourceDeliveryRecord))
        assert receipt is not None
        persisted_headers = json.loads(receipt.headers_json)
        assert "x-hub-signature-256" not in {
            name.lower() for name in persisted_headers
        }


def test_source_rotation_overlap_and_revoke_are_explicit(consumer_app):
    application, _, _, headers = consumer_app
    first = "ph4c-first-" + secrets.token_urlsafe(24)
    second = "ph4c-second-" + secrets.token_urlsafe(24)
    with TestClient(application) as client:
        created = client.post("/api/v1/change-sources", headers=headers, json={
            "name": "Rotate", "source_type": "github", "credential": first,
            "config": {}, "filters": {},
        })
        source_id = created.json()["source_id"]
        rotated = client.patch(
            f"/api/v1/change-sources/{source_id}",
            headers={**headers, "Idempotency-Key": "rotate-one"},
            json={"credential": {"action": "rotate", "credential": second, "overlap_seconds": 60}},
        )
        assert rotated.status_code == 200
        for credential in (first, second):
            body = b"{}"
            assert client.post(
                f"/api/v1/change-source-webhooks/{source_id}", content=body,
                headers=_github_headers(credential, body),
            ).status_code == 200
        revoked = client.patch(
            f"/api/v1/change-sources/{source_id}", headers=headers,
            json={"credential": {"action": "revoke"}},
        )
        assert revoked.status_code == 200
        assert revoked.json()["enabled"] is False
        assert revoked.json()["credential_configured"] is False


def test_webhook_credentials_are_reference_only_and_decrypted_at_delivery(consumer_app, monkeypatch):
    application, sessions, _, headers = consumer_app
    signing = "ph4c-signing-marker-" + secrets.token_urlsafe(24)
    header_value = "ph4c-header-marker-" + secrets.token_urlsafe(24)
    observed: dict[str, str] = {}

    class Response:
        status_code = 204
        text = "ok"

    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def post(self, url, *, content, headers):
            observed.update(headers)
            return Response()

    monkeypatch.setattr("app.services.webhook_delivery.httpx.Client", Client)
    with TestClient(application) as client:
        created = client.post("/api/v1/integrations/webhooks", headers=headers, json={
            "name": "Secure outbound", "url": "https://example.test/topo",
            "signing_secret": signing,
            "headers": {"Authorization": header_value, "X-Customer-Key": header_value},
        })
        assert created.status_code == 201
        value = created.json()
        assert value["has_signing_secret"] is True
        assert value["has_protected_headers"] is True
        assert value["protected_header_names"] == ["Authorization", "X-Customer-Key"]
        assert signing not in created.text and header_value not in created.text
        assert "signing_secret_ref" not in created.text and "protected_headers_secret_ref" not in created.text
        delivered = client.post(
            f"/api/v1/integrations/webhooks/{value['webhook_id']}/test",
            headers=headers, json={"summary": "test"},
        )
        assert delivered.status_code == 200
        assert observed["Authorization"] == header_value
        assert observed["X-Customer-Key"] == header_value
        assert observed["X-Topo-Signature"].startswith("sha256=")

    with Session(sessions.kw["bind"]) as session:
        endpoint = session.get(WebhookEndpointRecord, value["webhook_id"])
        assert endpoint is not None
        assert endpoint.signing_secret_ref and endpoint.protected_headers_secret_ref
        assert not hasattr(endpoint, "signing_secret") and not hasattr(endpoint, "headers_json")
        for version in session.scalars(select(SecretVersionRecord)).all():
            assert signing.encode() not in version.ciphertext
            assert header_value.encode() not in version.ciphertext


def test_webhook_rejects_credential_url_and_controlled_header_without_echo(consumer_app):
    application, _, _, headers = consumer_app
    marker = "ph4c-url-marker-secret"
    with TestClient(application) as client:
        url_result = client.post("/api/v1/integrations/webhooks", headers=headers, json={
            "name": "bad", "url": f"https://user:{marker}@example.test/path",
        })
        header_result = client.post("/api/v1/integrations/webhooks", headers=headers, json={
            "name": "bad-header", "url": "https://example.test/path",
            "headers": {"Host": marker},
        })
    assert url_result.status_code == header_result.status_code == 400
    assert marker not in url_result.text and marker not in header_result.text


def test_provider_config_rejects_secret_injection_and_unbounded_values(consumer_app):
    application, _, _, headers = consumer_app
    marker = "ph4c-config-secret-marker"
    with TestClient(application) as client:
        injected = client.post("/api/v1/change-sources", headers=headers, json={
            "name": "Injected", "source_type": "github", "credential": "safe-credential",
            "config": {"token": marker},
        })
        oversized = client.post("/api/v1/change-sources", headers=headers, json={
            "name": "Oversized", "source_type": "github", "credential": "safe-credential",
            "filters": {"repositories": ["r" * 1001]},
        })
    assert injected.status_code == oversized.status_code == 400
    assert marker not in injected.text


def test_outbound_replacement_is_active_only_and_clear_revokes(consumer_app, monkeypatch):
    application, _, _, headers = consumer_app
    old = "ph4c-old-signing-" + secrets.token_urlsafe(24)
    new = "ph4c-new-signing-" + secrets.token_urlsafe(24)
    signatures: list[str | None] = []

    class Response:
        status_code = 204
        text = "ok"

    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def post(self, url, *, content, headers):
            signatures.append(headers.get("X-Topo-Signature"))
            return Response()

    monkeypatch.setattr("app.services.webhook_delivery.httpx.Client", Client)
    with TestClient(application) as client:
        created = client.post("/api/v1/integrations/webhooks", headers=headers, json={
            "name": "Replace", "url": "https://example.test/replace",
            "signing_secret": old,
        })
        webhook_id = created.json()["webhook_id"]
        replaced = client.patch(
            f"/api/v1/integrations/webhooks/{webhook_id}",
            headers={**headers, "Idempotency-Key": "replace-one"},
            json={"signing_secret": new},
        )
        assert replaced.status_code == 200 and old not in replaced.text and new not in replaced.text
        assert client.post(
            f"/api/v1/integrations/webhooks/{webhook_id}/test",
            headers=headers, json={"summary": "replacement"},
        ).status_code == 200
        cleared = client.patch(
            f"/api/v1/integrations/webhooks/{webhook_id}",
            headers=headers, json={"signing_secret": None},
        )
        assert cleared.status_code == 200
        assert cleared.json()["has_signing_secret"] is False
        assert client.post(
            f"/api/v1/integrations/webhooks/{webhook_id}/test",
            headers=headers, json={"summary": "cleared"},
        ).status_code == 200
    assert signatures[0] is not None and signatures[0].startswith("sha256=")
    assert signatures[1] is None


def test_source_and_webhook_create_roll_back_secret_records_on_domain_failure(
    consumer_app, monkeypatch,
):
    _, sessions, store, _ = consumer_app
    from app.services import secret_consumers

    def fail_commit(*args, **kwargs):
        raise RuntimeError("injected domain failure")

    monkeypatch.setattr(secret_consumers, "tenant_commit", fail_commit)
    with sessions() as session:
        with pytest.raises(RuntimeError, match="injected domain failure"):
            create_change_source_secure(
                session,
                request=ChangeSourceCreate(
                    name="Atomic source", source_type="github", credential="provider-atomic-marker"
                ),
                tenant_id=TEST_TENANT, actor="test:atomic", store=store,
            )
    with sessions() as session:
        assert session.scalar(select(ChangeSourceRecord)) is None
        assert session.scalar(select(SecretRecord)) is None
        assert session.scalar(select(SecretVersionRecord)) is None

    with sessions() as session:
        with pytest.raises(RuntimeError, match="injected domain failure"):
            create_webhook_endpoint_secure(
                session,
                request=WebhookEndpointCreate(
                    name="Atomic webhook", url="https://example.test/atomic",
                    signing_secret="webhook-atomic-signing-marker",
                    headers={"Authorization": "webhook-atomic-header-marker"},
                ),
                tenant_id=TEST_TENANT, actor="test:atomic", store=store,
            )
    with sessions() as session:
        assert session.scalar(select(WebhookEndpointRecord)) is None
        assert session.scalar(select(SecretRecord)) is None
        assert session.scalar(select(SecretVersionRecord)) is None


def test_source_rotation_and_webhook_replacement_roll_back_with_domain_failure(
    consumer_app, monkeypatch,
):
    _, sessions, store, _ = consumer_app
    from app.services import secret_consumers

    with sessions() as session:
        source = create_change_source_secure(
            session,
            request=ChangeSourceCreate(
                name="Rollback rotate", source_type="github", credential="old-provider-marker"
            ),
            tenant_id=TEST_TENANT, actor="test:atomic", store=store,
        )
        endpoint = create_webhook_endpoint_secure(
            session,
            request=WebhookEndpointCreate(
                name="Rollback replace", url="https://example.test/rollback",
                signing_secret="old-webhook-signing-marker",
            ),
            tenant_id=TEST_TENANT, actor="test:atomic", store=store,
        )

    def fail_commit(*args, **kwargs):
        raise RuntimeError("injected domain failure")

    monkeypatch.setattr(secret_consumers, "tenant_commit", fail_commit)
    with sessions() as session:
        with pytest.raises(RuntimeError, match="injected domain failure"):
            update_change_source_secure(
                session, source_id=source.source_id,
                request=ChangeSourceUpdate.model_validate({
                    "credential": {
                        "action": "rotate", "credential": "new-provider-marker",
                        "overlap_seconds": 60,
                    }
                }),
                tenant_id=TEST_TENANT, actor="test:atomic", store=store,
                idempotency_key="rollback-source",
            )
    with sessions() as session:
        record = session.get(ChangeSourceRecord, source.source_id)
        binding = source_binding(
            tenant_id=TEST_TENANT, source_id=source.source_id,
            source_type=record.source_type, config=json.loads(record.config_json),
        )
        materials = store.get_for_use(session, binding, record.secret_ref)
        assert [item.reveal() for item in materials] == [b"old-provider-marker"]

    with sessions() as session:
        with pytest.raises(RuntimeError, match="injected domain failure"):
            update_webhook_endpoint_secure(
                session, webhook_id=endpoint.webhook_id,
                request=WebhookEndpointUpdate(signing_secret="new-webhook-signing-marker"),
                tenant_id=TEST_TENANT, actor="test:atomic", store=store,
                idempotency_key="rollback-webhook",
            )
    with sessions() as session:
        record = session.get(WebhookEndpointRecord, endpoint.webhook_id)
        binding = webhook_binding(
            tenant_id=TEST_TENANT, webhook_id=endpoint.webhook_id,
            purpose=SecretPurpose.WEBHOOK_SIGNING,
        )
        materials = store.get_for_use(session, binding, record.signing_secret_ref)
        assert [item.reveal() for item in materials] == [b"old-webhook-signing-marker"]
