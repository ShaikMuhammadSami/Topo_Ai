"""PH-4E independent hostile secret-custody acceptance corpus.

The values in this module are generated test material.  The corpus exercises
real persistence, encryption, provider verification, consumer binding, outbound
delivery and public formatting boundaries without contacting a real provider.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import main as main_module
from app.db.database import Base
from app.db.models import (
    ChangeSourceDeadLetterRecord,
    ChangeSourceDeliveryRecord,
    ChangeSourceRecord,
    SecretRecord,
    SecretVersionRecord,
    TenantRecord,
    WebhookDeliveryRecord,
    WebhookEndpointRecord,
)
from app.main import create_app
from app.models.change_sources import ChangeSourceCreate, ChangeSourceUpdate
from app.models.secret_store import (
    SecretBinding,
    SecretMaterial,
    SecretPurpose,
    SecretScope,
    SecretStoreError,
)
from app.models.webhooks import WebhookEndpointCreate, WebhookEndpointUpdate
from app.security.secret_keyring import SecretKeyring, SecretStoreConfiguration
from app.security.secret_redaction import (
    REDACTED,
    TRUNCATED,
    install_logging_redaction,
    safe_text,
    safe_url,
    safe_validation_errors,
    sanitize_structured,
)
from app.services import change_source_ingest, secret_store as secret_store_module
from app.services.change_source_ingest import (
    _verify,
    ingest_change_source_webhook,
    replay_dead_letter,
)
from app.services.installation_secrets import installation_binding
from app.services.secret_consumer_policy import source_binding, webhook_binding
from app.services.secret_consumers import (
    create_change_source_secure,
    create_webhook_endpoint_secure,
    load_webhook_secrets,
    update_change_source_secure,
    update_webhook_endpoint_secure,
)
from app.services.secret_store import EncryptedDatabaseSecretStore
from app.services.webhook_delivery import create_test_event, deliver_event_to_endpoint
from app.services.webhook_security import WebhookAuthenticationError


UTC = timezone.utc
NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
TENANT_A = "tenant:44444444-4444-4444-8444-44444444444a"
TENANT_B = "tenant:44444444-4444-4444-8444-44444444444b"
INSTALLATION = "installation:44444444-4444-4444-8444-444444444444"


@dataclass(frozen=True)
class Markers:
    provider_a: str
    provider_b: str
    webhook_signing_a: str
    webhook_header_b: str
    install_openai: str
    install_groq: str
    install_github: str
    database_password: str

    @property
    def reversible(self) -> tuple[str, ...]:
        return (
            self.provider_a,
            self.provider_b,
            self.webhook_signing_a,
            self.webhook_header_b,
            self.install_openai,
            self.install_groq,
            self.install_github,
        )


def _marker(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(18)}"


@pytest.fixture()
def markers() -> Markers:
    return Markers(
        provider_a=_marker("TENANT_A_PROVIDER_SECRET"),
        provider_b=_marker("TENANT_B_PROVIDER_SECRET"),
        webhook_signing_a=_marker("WEBHOOK_A_SIGNING"),
        webhook_header_b=_marker("WEBHOOK_B_HEADER"),
        install_openai="sk-" + _marker("INSTALL_OPENAI"),
        install_groq="gsk_" + _marker("INSTALL_GROQ"),
        install_github="github_pat_" + _marker("INSTALL_GITHUB"),
        database_password=_marker("DB_PASSWORD"),
    )


@pytest.fixture(scope="module", params=["sqlite", "postgres"])
def custody_engine(request, tmp_path_factory):
    if request.param == "postgres":
        if not os.getenv("TOPO_TEST_POSTGRES_URL"):
            pytest.skip("set TOPO_TEST_POSTGRES_URL for PostgreSQL PH-4E proof")
        from test_postgres_runtime_compatibility import _temporary_database

        with _temporary_database("ph4e_custody") as engine:
            Base.metadata.create_all(engine)
            _seed_tenants(engine)
            yield engine
        return

    path = tmp_path_factory.mktemp("ph4e") / "hostile-custody.db"
    engine = create_engine(f"sqlite:///{path.as_posix()}", hide_parameters=True)

    @event.listens_for(engine, "connect")
    def _foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    _seed_tenants(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def _seed_tenants(engine) -> None:
    with Session(engine) as session, session.begin():
        for tenant_id in (TENANT_A, TENANT_B):
            session.add(
                TenantRecord(
                    tenant_id=tenant_id,
                    display_name=f"PH-4E {tenant_id[-1]}",
                    status="active",
                    created_at=NOW.isoformat(),
                    updated_at=NOW.isoformat(),
                    created_by_subject="test:ph4e",
                )
            )


@pytest.fixture()
def custody(custody_engine, monkeypatch):
    Base.metadata.drop_all(custody_engine)
    Base.metadata.create_all(custody_engine)
    _seed_tenants(custody_engine)
    monkeypatch.setattr(secret_store_module, "utc_now", lambda: NOW)
    keys = {"root-old": os.urandom(32), "root-new": os.urandom(32)}
    store = EncryptedDatabaseSecretStore(
        SecretStoreConfiguration(
            "encrypted_db", SecretKeyring(keys, "root-old"), INSTALLATION
        )
    )
    return custody_engine, store, keys


def _put(store, session, binding: SecretBinding, raw: str, operation: str):
    return store.put(
        session,
        binding,
        SecretMaterial(raw.encode()),
        operation_id=operation,
        actor="test:ph4e",
    )


def _count_raw(engine, marker_values: tuple[str, ...], *, tables=None) -> int:
    count = 0
    metadata = Base.metadata
    table_names = tables or tuple(inspect(engine).get_table_names())
    with engine.connect() as connection:
        for name in table_names:
            table = metadata.tables.get(name)
            if table is None:
                continue
            for row in connection.execute(select(table)).all():
                for value in row:
                    if isinstance(value, str):
                        count += sum(value.count(marker) for marker in marker_values)
                    elif isinstance(value, (bytes, bytearray, memoryview)):
                        raw = bytes(value)
                        count += sum(raw.count(marker.encode()) for marker in marker_values)
    return count


def _provider_secret(mode: str) -> str:
    if mode == "gitlab_signing":
        return "whsec_" + base64.b64encode(os.urandom(32)).decode("ascii")
    return _marker(f"PROVIDER_{mode.upper()}")


def _provider_parts(mode: str):
    if mode == "github":
        return "github", {}
    if mode == "gitlab_signing":
        return "gitlab", {"signature_max_age": 300}
    if mode == "gitlab_shared":
        return "gitlab", {"auth_mode": "secret_token"}
    if mode == "terraform":
        return "terraform_cloud", {}
    if mode == "jenkins":
        return "jenkins", {}
    if mode == "azure":
        return "azure_devops", {"username": "topo-ph4e"}
    raise AssertionError(mode)


def _provider_headers(
    mode: str, secret: str, body: bytes, *, delivery: str | None = None
) -> dict[str, str]:
    delivery = delivery or f"ph4e-{uuid4().hex}"
    if mode == "github":
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return {
            "X-GitHub-Event": "ping",
            "X-GitHub-Delivery": delivery,
            "X-Hub-Signature-256": f"sha256={digest}",
        }
    if mode == "gitlab_shared":
        return {"X-Gitlab-Token": secret, "X-Gitlab-Event": "ping"}
    if mode == "gitlab_signing":
        timestamp = str(int(time.time()))
        raw_key = base64.b64decode(secret.removeprefix("whsec_"), validate=True)
        signature = base64.b64encode(
            hmac.new(
                raw_key,
                f"{delivery}.{timestamp}.".encode() + body,
                hashlib.sha256,
            ).digest()
        ).decode("ascii")
        return {
            "Webhook-Id": delivery,
            "Webhook-Timestamp": timestamp,
            "Webhook-Signature": f"v1,{signature}",
            "X-Gitlab-Event": "ping",
        }
    if mode == "terraform":
        return {
            "X-TFE-Notification-Signature": hmac.new(
                secret.encode(), body, hashlib.sha512
            ).hexdigest()
        }
    if mode == "jenkins":
        return {
            "X-Topo-Signature-256": "sha256="
            + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        }
    if mode == "azure":
        proof = base64.b64encode(f"topo-ph4e:{secret}".encode()).decode("ascii")
        return {"Authorization": f"Basic {proof}"}
    raise AssertionError(mode)


def _create_source(session, store, *, tenant_id: str, mode: str, raw: str):
    source_type, config = _provider_parts(mode)
    source_id = f"source:ph4e:{mode}:{uuid4().hex}"
    binding = source_binding(
        tenant_id=tenant_id,
        source_id=source_id,
        source_type=source_type,
        config=config,
    )
    descriptor = _put(store, session, binding, raw, f"put:{source_id}")
    source = ChangeSourceRecord(
        tenant_id=tenant_id,
        source_id=source_id,
        name=f"PH-4E {mode}",
        source_type=source_type,
        enabled=True,
        secret_ref=descriptor.secret_ref,
        config_json=json.dumps(config, sort_keys=True, separators=(",", ":")),
        filters_json="{}",
        status="configured",
        delivery_count=0,
        failure_count=0,
        created_at=NOW.isoformat(),
        updated_at=NOW.isoformat(),
    )
    session.add(source)
    session.commit()
    return source, binding, descriptor


def test_database_read_attacker_sees_only_ciphertext_and_metadata(
    custody, markers
):
    engine, store, _ = custody
    bindings = (
        (
            SecretBinding(
                SecretScope.tenant(TENANT_A),
                "change_source",
                f"source:{uuid4().hex}",
                SecretPurpose.GITHUB_HMAC,
            ),
            markers.provider_a,
        ),
        (
            SecretBinding(
                SecretScope.tenant(TENANT_B),
                "change_source",
                f"source:{uuid4().hex}",
                SecretPurpose.GITHUB_HMAC,
            ),
            markers.provider_b,
        ),
        (
            SecretBinding(
                SecretScope.tenant(TENANT_A),
                "webhook_endpoint",
                f"webhook:{uuid4().hex}",
                SecretPurpose.WEBHOOK_SIGNING,
            ),
            markers.webhook_signing_a,
        ),
        (
            SecretBinding(
                SecretScope.tenant(TENANT_B),
                "webhook_endpoint",
                f"webhook:{uuid4().hex}",
                SecretPurpose.WEBHOOK_HEADERS,
            ),
            markers.webhook_header_b,
        ),
        (installation_binding("openai", installation_id=INSTALLATION), markers.install_openai),
        (installation_binding("groq", installation_id=INSTALLATION), markers.install_groq),
        (installation_binding("github", installation_id=INSTALLATION), markers.install_github),
    )
    descriptors = []
    with Session(engine) as session, session.begin():
        for index, (binding, raw) in enumerate(bindings):
            descriptors.append(_put(store, session, binding, raw, f"db-read:{index}"))

    assert _count_raw(engine, markers.reversible) == 0
    assert _count_raw(
        engine,
        markers.reversible,
        tables=("secret_records", "secret_versions"),
    ) == 0
    with Session(engine) as session:
        for descriptor, (binding, raw) in zip(descriptors, bindings):
            assert store.get_for_use(session, binding, descriptor.secret_ref)[0].reveal() == raw.encode()
        rows = session.scalars(select(SecretVersionRecord)).all()
        assert rows and all(raw.encode() not in bytes(row.ciphertext) for raw in markers.reversible for row in rows)
        rendered = repr(session.scalars(select(SecretRecord)).all()) + repr(rows)
        assert all(raw not in rendered for raw in markers.reversible)


def test_domain_reference_copy_attacks_fail_before_decrypt(custody, markers, monkeypatch):
    engine, store, _ = custody
    with Session(engine) as session:
        source_a, binding_a, _ = _create_source(
            session, store, tenant_id=TENANT_A, mode="github", raw=markers.provider_a
        )
        source_b, _, _ = _create_source(
            session, store, tenant_id=TENANT_B, mode="github", raw=markers.provider_b
        )
        source_a.secret_ref = source_b.secret_ref
        session.commit()
        monkeypatch.setattr(store, "_decrypt", lambda *args: pytest.fail("foreign material decrypted"))
        with pytest.raises(WebhookAuthenticationError):
            _verify(
                session,
                source=source_a,
                body=b"{}",
                headers=_provider_headers("github", markers.provider_a, b"{}"),
                secret_store=store,
            )

        wrong_purpose = replace(binding_a, purpose=SecretPurpose.JENKINS_HMAC)
        with pytest.raises(SecretStoreError, match="SECRET_NOT_FOUND"):
            store.get_for_use(session, wrong_purpose, source_b.secret_ref)


def test_root_key_retirement_rewrap_and_interruption_are_fail_closed(
    custody, markers, monkeypatch
):
    engine, old_store, keys = custody
    binding = SecretBinding(
        SecretScope.tenant(TENANT_A),
        "change_source",
        f"source:root:{uuid4().hex}",
        SecretPurpose.GITHUB_HMAC,
    )
    with Session(engine) as session, session.begin():
        descriptor = _put(old_store, session, binding, markers.provider_a, "root:put")
    wrong = EncryptedDatabaseSecretStore(
        SecretStoreConfiguration(
            "encrypted_db",
            SecretKeyring({"root-old": os.urandom(32)}, "root-old"),
            INSTALLATION,
        )
    )
    missing = EncryptedDatabaseSecretStore(
        SecretStoreConfiguration(
            "encrypted_db",
            SecretKeyring({"root-new": keys["root-new"]}, "root-new"),
            INSTALLATION,
        )
    )
    with Session(engine) as session:
        with pytest.raises(SecretStoreError, match="SECRET_DECRYPT_FAILED"):
            wrong.get_for_use(session, binding, descriptor.secret_ref)
        with pytest.raises(SecretStoreError, match="SECRET_REQUIRED_KEY_MISSING"):
            missing.validate_readiness(session)

    new_store = EncryptedDatabaseSecretStore(
        SecretStoreConfiguration(
            "encrypted_db", SecretKeyring(keys, "root-new"), INSTALLATION
        )
    )
    with Session(engine) as session:
        before = bytes(
            session.scalar(
                select(SecretVersionRecord).where(
                    SecretVersionRecord.secret_ref == descriptor.secret_ref
                )
            ).ciphertext
        )

    def fail_update(_connection, _cursor, statement, *_args):
        if statement.startswith("UPDATE secret_versions"):
            raise RuntimeError("synthetic rewrap interruption")

    event.listen(engine, "before_cursor_execute", fail_update)
    try:
        with Session(engine) as session, session.begin():
            with pytest.raises(RuntimeError, match="rewrap interruption"):
                new_store.rewrap(
                    session,
                    binding,
                    descriptor.secret_ref,
                    actor="test:ph4e",
                    expected_row_version=descriptor.row_version,
                )
    finally:
        event.remove(engine, "before_cursor_execute", fail_update)

    with Session(engine) as session:
        row = session.scalar(
            select(SecretVersionRecord).where(
                SecretVersionRecord.secret_ref == descriptor.secret_ref
            )
        )
        record = session.scalar(
            select(SecretRecord).where(SecretRecord.secret_ref == descriptor.secret_ref)
        )
        assert bytes(row.ciphertext) == before
        assert row.key_id == "root-old" and row.envelope_revision == 1
        assert record.active_version == 1 and record.row_version == 1

    with Session(engine) as session, session.begin():
        rewrapped = new_store.rewrap(
            session,
            binding,
            descriptor.secret_ref,
            actor="test:ph4e",
            expected_row_version=1,
        )
    assert rewrapped.active_version == 1
    retired = EncryptedDatabaseSecretStore(
        SecretStoreConfiguration(
            "encrypted_db",
            SecretKeyring({"root-new": keys["root-new"]}, "root-new"),
            INSTALLATION,
        )
    )
    with Session(engine) as session:
        retired.validate_readiness(session)
        assert retired.get_for_use(session, binding, descriptor.secret_ref)[0].reveal() == markers.provider_a.encode()


def test_expired_previous_and_revoked_material_do_not_require_retired_root_key(
    custody, markers, monkeypatch
):
    engine, store, keys = custody
    binding = SecretBinding(
        SecretScope.tenant(TENANT_A),
        "change_source",
        f"source:retirement:{uuid4().hex}",
        SecretPurpose.GITHUB_HMAC,
    )
    with Session(engine) as session, session.begin():
        first = _put(store, session, binding, markers.provider_a, "retire:put")
    rotated_store = EncryptedDatabaseSecretStore(
        SecretStoreConfiguration(
            "encrypted_db", SecretKeyring(keys, "root-new"), INSTALLATION
        )
    )
    with Session(engine) as session, session.begin():
        second = rotated_store.rotate(
            session,
            binding,
            first.secret_ref,
            SecretMaterial(markers.provider_b.encode()),
            operation_id="retire:rotate",
            actor="test:ph4e",
            expected_row_version=first.row_version,
            overlap_seconds=30,
        )
    no_old = EncryptedDatabaseSecretStore(
        SecretStoreConfiguration(
            "encrypted_db",
            SecretKeyring({"root-new": keys["root-new"]}, "root-new"),
            INSTALLATION,
        )
    )
    with Session(engine) as session, pytest.raises(
        SecretStoreError, match="SECRET_REQUIRED_KEY_MISSING"
    ):
        no_old.validate_readiness(session)

    monkeypatch.setattr(secret_store_module, "utc_now", lambda: NOW + timedelta(seconds=30))
    with Session(engine) as session:
        no_old.validate_readiness(session)
        assert no_old.get_for_use(session, binding, first.secret_ref)[0].reveal() == markers.provider_b.encode()
    with Session(engine) as session, session.begin():
        no_old.revoke(
            session,
            binding,
            first.secret_ref,
            actor="test:ph4e",
            expected_row_version=second.row_version,
        )
    with Session(engine) as session:
        no_old.validate_readiness(session)


@pytest.mark.parametrize(
    "mode",
    ["github", "gitlab_signing", "gitlab_shared", "terraform", "jenkins", "azure"],
)
def test_all_provider_modes_verify_rotate_revoke_and_reprovision(
    custody, mode, monkeypatch
):
    engine, store, _ = custody
    first = _provider_secret(mode)
    second = _provider_secret(mode)
    third = _provider_secret(mode)
    body = b"{}"
    with Session(engine) as session:
        source, binding, descriptor = _create_source(
            session, store, tenant_id=TENANT_A, mode=mode, raw=first
        )
        ingest_change_source_webhook(
            session,
            source=source,
            body=body,
            headers=_provider_headers(mode, first, body),
            secret_store=store,
        )
        with pytest.raises(WebhookAuthenticationError):
            _verify(
                session,
                source=source,
                body=body,
                headers=_provider_headers(mode, _provider_secret(mode), body),
                secret_store=store,
            )

        rotated = store.rotate(
            session,
            binding,
            descriptor.secret_ref,
            SecretMaterial(second.encode()),
            operation_id=f"rotate:{mode}",
            actor="test:ph4e",
            expected_row_version=descriptor.row_version,
            overlap_seconds=60,
        )
        session.commit()
        for raw in (first, second):
            _verify(
                session,
                source=source,
                body=body,
                headers=_provider_headers(mode, raw, body),
                secret_store=store,
            )

        monkeypatch.setattr(
            secret_store_module, "utc_now", lambda: NOW + timedelta(seconds=60)
        )
        with pytest.raises(WebhookAuthenticationError):
            _verify(
                session,
                source=source,
                body=body,
                headers=_provider_headers(mode, first, body),
                secret_store=store,
            )
        _verify(
            session,
            source=source,
            body=body,
            headers=_provider_headers(mode, second, body),
            secret_store=store,
        )

        revoked = store.revoke(
            session,
            binding,
            descriptor.secret_ref,
            actor="test:ph4e",
            expected_row_version=rotated.row_version,
        )
        session.commit()
        with pytest.raises(WebhookAuthenticationError):
            _verify(
                session,
                source=source,
                body=body,
                headers=_provider_headers(mode, second, body),
                secret_store=store,
            )
        active = store.reprovision(
            session,
            binding,
            descriptor.secret_ref,
            SecretMaterial(third.encode()),
            operation_id=f"reprovision:{mode}",
            actor="test:ph4e",
            expected_row_version=revoked.row_version,
        )
        session.commit()
        assert active.previous_version is None
        _verify(
            session,
            source=source,
            body=body,
            headers=_provider_headers(mode, third, body),
            secret_store=store,
        )
        with pytest.raises(WebhookAuthenticationError):
            _verify(
                session,
                source=source,
                body=body,
                headers=_provider_headers(mode, first, body),
                secret_store=store,
            )

    assert _count_raw(engine, (first, second, third)) == 0


def test_provider_invalid_proof_precedes_parse_and_auth_headers_are_not_durable(
    custody, monkeypatch, caplog
):
    engine, store, _ = custody
    raw = _provider_secret("github")
    malformed_marker = _marker("MALFORMED_UNTRUSTED_PAYLOAD")
    malformed = f'{{"credential":"{malformed_marker}"'.encode()
    with Session(engine) as session:
        source, _, _ = _create_source(
            session, store, tenant_id=TENANT_A, mode="github", raw=raw
        )
        before = session.scalars(select(ChangeSourceDeliveryRecord)).all()
        with pytest.raises(WebhookAuthenticationError), caplog.at_level(logging.WARNING):
            ingest_change_source_webhook(
                session,
                source=source,
                body=malformed,
                headers={"X-Hub-Signature-256": _marker("INVALID_PROOF")},
                secret_store=store,
            )
        assert session.scalars(select(ChangeSourceDeliveryRecord)).all() == before

        valid_body = b"{}"
        proof_headers = _provider_headers("github", raw, valid_body)
        ingest_change_source_webhook(
            session,
            source=source,
            body=valid_body,
            headers=proof_headers,
            secret_store=store,
        )
        delivery = session.scalars(
            select(ChangeSourceDeliveryRecord).where(
                ChangeSourceDeliveryRecord.source_id == source.source_id
            )
        ).all()[-1]
        persisted = delivery.headers_json + delivery.payload_json + (delivery.error or "")
        assert raw not in persisted
        assert proof_headers["X-Hub-Signature-256"] not in persisted
        assert raw not in caplog.text and malformed_marker not in caplog.text


def test_dead_letter_replay_never_reloads_retired_provider_material(
    custody, monkeypatch
):
    engine, store, _ = custody
    raw = _provider_secret("github")
    body = b"{}"
    with Session(engine) as session:
        source, binding, descriptor = _create_source(
            session, store, tenant_id=TENANT_A, mode="github", raw=raw
        )
        monkeypatch.setattr(
            change_source_ingest,
            "_normalize",
            lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("synthetic normalize failure")),
        )
        with pytest.raises(RuntimeError, match="Change source processing failed"):
            ingest_change_source_webhook(
                session,
                source=source,
                body=body,
                headers=_provider_headers("github", raw, body),
                secret_store=store,
            )
        dead_letter = session.scalar(
            select(ChangeSourceDeadLetterRecord).where(
                ChangeSourceDeadLetterRecord.source_id == source.source_id
            )
        )
        assert dead_letter is not None and raw not in dead_letter.payload_json
        store.revoke(
            session,
            binding,
            descriptor.secret_ref,
            actor="test:ph4e",
            expected_row_version=descriptor.row_version,
        )
        session.commit()

        monkeypatch.setattr(change_source_ingest, "_normalize", lambda **_kwargs: [])
        monkeypatch.setattr(
            store, "get_for_use", lambda *_args, **_kwargs: pytest.fail("replay reloaded secret")
        )
        result = replay_dead_letter(
            session, dead_letter_id=dead_letter.dead_letter_id, tenant_id=TENANT_A
        )
        assert result.succeeded is True


def test_webhook_signing_headers_replacement_clear_and_redirect_are_bounded(
    custody, markers, monkeypatch
):
    engine, store, _ = custody
    old_signing = markers.webhook_signing_a
    new_signing = _marker("WEBHOOK_A_REPLACEMENT")
    intended_requests = []

    class Response:
        status_code = 302
        text = _marker("REMOTE_ECHO") + old_signing + markers.webhook_header_b

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, *, content, headers):
            intended_requests.append((url, dict(headers), content))
            return Response()

    monkeypatch.setattr("app.services.webhook_delivery.httpx.Client", Client)
    monkeypatch.setattr("app.services.webhook_delivery.time.sleep", lambda *_args: None)
    with Session(engine) as session:
        view = create_webhook_endpoint_secure(
            session,
            request=WebhookEndpointCreate(
                name="PH-4E webhook",
                url="https://approved.example/topo",
                signing_secret=old_signing,
                headers={"Authorization": markers.webhook_header_b},
                max_attempts=1,
            ),
            tenant_id=TENANT_A,
            actor="test:ph4e",
            store=store,
        )
        endpoint = session.scalar(
            select(WebhookEndpointRecord).where(
                WebhookEndpointRecord.tenant_id == TENANT_A,
                WebhookEndpointRecord.webhook_id == view.webhook_id,
            )
        )
        signing, headers, _ = load_webhook_secrets(
            session, endpoint=endpoint, tenant_id=TENANT_A, store=store
        )
        assert signing == old_signing
        assert headers == {"Authorization": markers.webhook_header_b}

        delivered = deliver_event_to_endpoint(
            session,
            endpoint,
            create_test_event(view.webhook_id, "PH-4E"),
            tenant_id=TENANT_A,
            secret_store=store,
        )
        assert delivered.status.value == "failed"
        assert len(intended_requests) == 1
        assert intended_requests[0][0] == "https://approved.example/topo"
        assert intended_requests[0][1]["Authorization"] == markers.webhook_header_b
        assert intended_requests[0][1]["X-Topo-Signature"].startswith("sha256=")
        persisted = session.scalar(
            select(WebhookDeliveryRecord).where(
                WebhookDeliveryRecord.delivery_id == delivered.delivery_id
            )
        )
        assert persisted.response_body is None
        assert old_signing not in (persisted.error_message or "")
        assert markers.webhook_header_b not in (persisted.error_message or "")

        updated = update_webhook_endpoint_secure(
            session,
            webhook_id=view.webhook_id,
            request=WebhookEndpointUpdate(
                signing_secret=new_signing,
                headers={},
            ),
            tenant_id=TENANT_A,
            actor="test:ph4e",
            store=store,
            idempotency_key="ph4e-webhook-replace",
        )
        endpoint = session.scalar(
            select(WebhookEndpointRecord).where(
                WebhookEndpointRecord.tenant_id == TENANT_A,
                WebhookEndpointRecord.webhook_id == view.webhook_id,
            )
        )
        signing, headers, _ = load_webhook_secrets(
            session, endpoint=endpoint, tenant_id=TENANT_A, store=store
        )
        assert updated.has_signing_secret and not updated.has_protected_headers
        assert signing == new_signing and headers == {}

        cleared = update_webhook_endpoint_secure(
            session,
            webhook_id=view.webhook_id,
            request=WebhookEndpointUpdate(signing_secret=None),
            tenant_id=TENANT_A,
            actor="test:ph4e",
            store=store,
            idempotency_key=None,
        )
        assert not cleared.has_signing_secret
    assert _count_raw(engine, (old_signing, new_signing, markers.webhook_header_b)) == 0


def test_webhook_cross_tenant_and_purpose_reference_swaps_fail(custody, markers):
    engine, store, _ = custody
    with Session(engine) as session:
        a = create_webhook_endpoint_secure(
            session,
            request=WebhookEndpointCreate(
                name="A", url="https://a.example/topo", signing_secret=markers.webhook_signing_a
            ),
            tenant_id=TENANT_A,
            actor="test:ph4e",
            store=store,
        )
        b = create_webhook_endpoint_secure(
            session,
            request=WebhookEndpointCreate(
                name="B",
                url="https://b.example/topo",
                headers={"Authorization": markers.webhook_header_b},
            ),
            tenant_id=TENANT_B,
            actor="test:ph4e",
            store=store,
        )
        a_record = session.scalar(
            select(WebhookEndpointRecord).where(
                WebhookEndpointRecord.tenant_id == TENANT_A,
                WebhookEndpointRecord.webhook_id == a.webhook_id,
            )
        )
        b_record = session.scalar(
            select(WebhookEndpointRecord).where(
                WebhookEndpointRecord.tenant_id == TENANT_B,
                WebhookEndpointRecord.webhook_id == b.webhook_id,
            )
        )
        a_record.signing_secret_ref = b_record.protected_headers_secret_ref
        session.commit()
        with pytest.raises(Exception, match="Credential service is unavailable"):
            load_webhook_secrets(
                session, endpoint=a_record, tenant_id=TENANT_A, store=store
            )

        purpose_swap = webhook_binding(
            tenant_id=TENANT_B,
            webhook_id=b.webhook_id,
            purpose=SecretPurpose.WEBHOOK_SIGNING,
        )
        with pytest.raises(SecretStoreError, match="SECRET_NOT_FOUND"):
            store.get_for_use(
                session, purpose_swap, b_record.protected_headers_secret_ref
            )


@pytest.mark.parametrize("integration", ["openai", "groq", "github"])
def test_installation_bindings_are_active_only_revocable_and_scope_exact(
    custody, markers, integration
):
    engine, store, _ = custody
    raw = getattr(markers, f"install_{integration}")
    binding = installation_binding(integration, installation_id=INSTALLATION)
    with Session(engine) as session, session.begin():
        descriptor = _put(store, session, binding, raw, f"install:{integration}")
    with Session(engine) as session, session.begin():
        assert store.get_for_binding(session, binding)[0].reveal() == raw.encode()
        replacement = _marker(f"INSTALL_{integration.upper()}_ROTATED")
        rotated = store.rotate(
            session,
            binding,
            descriptor.secret_ref,
            SecretMaterial(replacement.encode()),
            operation_id=f"install:rotate:{integration}",
            actor="test:ph4e",
            expected_row_version=descriptor.row_version,
            overlap_seconds=0,
        )
        assert rotated.previous_version is None
        assert [value.reveal() for value in store.get_for_binding(session, binding)] == [replacement.encode()]
        revoked = store.revoke(
            session,
            binding,
            descriptor.secret_ref,
            actor="test:ph4e",
            expected_row_version=rotated.row_version,
        )
        assert revoked.status == "revoked"
        with pytest.raises(SecretStoreError, match="SECRET_REVOKED"):
            store.get_for_binding(session, binding)

    wrong = installation_binding(
        "openai" if integration != "openai" else "groq",
        installation_id=INSTALLATION,
    )
    with Session(engine) as session, pytest.raises(SecretStoreError, match="SECRET_NOT_FOUND"):
        store.get_for_use(session, wrong, descriptor.secret_ref)
    with pytest.raises(SecretStoreError, match="SECRET_OWNER_PURPOSE_INVALID"):
        replace(binding, scope=SecretScope.tenant(TENANT_A))


def test_database_validation_logging_repr_and_traceback_boundaries_are_zero_marker(
    markers, monkeypatch, caplog
):
    install_logging_redaction()
    marker_values = markers.reversible + (markers.database_password,)
    hostile = {
        "Authorization": f"Bearer {markers.install_openai}",
        "Proxy-Authorization": f"Basic {markers.database_password}",
        "Cookie": markers.provider_a,
        "client-secret": markers.provider_b,
        "token_count": 17,
        "credential_id": "credential:safe",
        "nested": [{"password": markers.database_password}],
    }
    deep = markers.install_groq
    for _ in range(8):
        deep = {"safe": deep}
    many = {f"item-{index}": markers.install_github for index in range(110)}
    sanitized = sanitize_structured(hostile)
    assert sanitized["token_count"] == 17
    assert sanitized["credential_id"] == "credential:safe"
    assert all(marker not in repr(sanitized) for marker in marker_values)
    assert TRUNCATED in repr(sanitize_structured(deep))
    assert TRUNCATED in sanitize_structured(many)
    assert all(
        marker not in safe_text(
            f"Authorization: Bearer {markers.install_openai}; "
            f"password={markers.database_password}; "
            f"https://user:{markers.provider_a}@db.example/topo?token={markers.provider_b}"
        )
        for marker in marker_values
    )
    database_url = (
        "postgresql"
        f"://operator:{markers.database_password}@db.example/topo?token={markers.provider_a}"
    )
    assert safe_url(database_url) == "[UNAVAILABLE]"
    validation = safe_validation_errors(
        [
            {
                "loc": ("body", "credential"),
                "msg": "invalid",
                "type": "value_error",
                "input": markers.provider_a,
                "ctx": {"secret": markers.provider_b},
            }
        ]
    )
    assert all(marker not in repr(validation) for marker in marker_values)

    logger = logging.getLogger("test.ph4e.hostile")
    with caplog.at_level(logging.WARNING):
        try:
            raise RuntimeError(f"Bearer {markers.install_openai}")
        except RuntimeError:
            logger.exception(
                "database_url=%s",
                "postgresql" + f"://u:{markers.database_password}@db/topo",
            )
        logger.warning("structured", extra={"credential": markers.provider_a})
    assert all(marker not in caplog.text for marker in marker_values)

    engine = create_engine("sqlite+pysqlite:///:memory:", hide_parameters=True)
    try:
        with engine.connect() as connection, pytest.raises(SQLAlchemyError) as captured:
            connection.execute(
                text("SELECT :password FROM ph4e_missing_table"),
                {"password": markers.database_password},
            )
        assert markers.database_password not in str(captured.value)
        assert "SQL parameters hidden" in str(captured.value)
    finally:
        engine.dispose()


def test_fastapi_validation_and_model_representations_never_echo_raw_input(
    markers, monkeypatch
):
    monkeypatch.setenv("TOPO_AUTH_MODE", "development-disabled")
    application = create_app(database_initializer=lambda: None)
    response = TestClient(application).post(
        "/api/v1/agents/enroll",
        json={
            "enrollment_token": markers.provider_a + ("x" * 2000),
            "name": "ph4e",
            "cluster_name": "ph4e",
            "version": "ph4e",
        },
    )
    assert response.status_code == 422
    assert markers.provider_a not in response.text
    assert "input" not in response.json()["detail"][0]
    model = ChangeSourceCreate(
        name="PH-4E repr", source_type="github", credential=markers.provider_b
    )
    assert markers.provider_b not in repr(model)
    assert model.credential.get_secret_value() == markers.provider_b


def test_no_secretstore_http_api_and_no_runtime_environment_authority():
    application = create_app(database_initializer=lambda: None)
    routes = {
        (method, route.path)
        for route in application.routes
        for method in getattr(route, "methods", set())
    }
    forbidden = {
        path
        for _, path in routes
        if any(word in path.lower() for word in ("secret-store", "decrypt", "keyring"))
    }
    assert forbidden == set()

    root = os.path.dirname(main_module.__file__)
    allowed = {
        os.path.normpath(os.path.join(root, "installation_secret_admin.py")),
    }
    matches = []
    for directory, _, filenames in os.walk(root):
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            path = os.path.normpath(os.path.join(directory, filename))
            source = open(path, encoding="utf-8").read()
            if any(name in source for name in ("OPENAI_API_KEY", "GROQ_API_KEY", "TOPO_GITHUB_TOKEN")):
                matches.append(path)
    assert set(matches) == allowed
