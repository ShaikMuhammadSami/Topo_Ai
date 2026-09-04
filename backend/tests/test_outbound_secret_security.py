from __future__ import annotations

import argparse
import io
import logging
import os
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import installation_secret_admin
from app.connectors.github_connector import GitHubConnector, GitHubSettings
from app.db.database import Base
from app.db.models import SecretRecord, SecretVersionRecord
from app.main import create_app
from app.models.agents import AgentEnrollResponse, AgentConfigView
from app.models.secret_store import (
    SecretBinding,
    SecretMaterial,
    SecretPurpose,
    SecretScope,
    SecretStoreError,
)
from app.security.secret_keyring import SecretKeyring, SecretStoreConfiguration
from app.security.secret_redaction import (
    REDACTED,
    TRUNCATED,
    install_logging_redaction,
    safe_text,
    safe_url,
    safe_validation_errors,
    safe_response_headers,
    sanitize_headers,
    sanitize_structured,
)
from app.services import llm_client
from app.services.installation_secrets import installation_binding
from app.services.secret_runtime import configure_runtime_secret_store
from app.services.secret_store import EncryptedDatabaseSecretStore

INSTALLATION = "installation:11111111-1111-4111-8111-111111111111"


@pytest.fixture()
def installation_runtime(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        hide_parameters=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    store = EncryptedDatabaseSecretStore(
        SecretStoreConfiguration(
            "encrypted_db",
            SecretKeyring({"test": os.urandom(32)}, "test"),
            INSTALLATION,
        )
    )
    monkeypatch.setenv("TOPO_INSTALLATION_ID", INSTALLATION)
    configure_runtime_secret_store(store, factory)
    try:
        yield store, factory
    finally:
        configure_runtime_secret_store(None)
        engine.dispose()


def _put(store, factory, integration: str, value: str):
    with factory() as session:
        descriptor = store.put(
            session,
            installation_binding(integration),
            SecretMaterial(value.encode()),
            operation_id=f"test:{integration}",
            actor="test:operator",
        )
        session.commit()
        return descriptor


def test_binding_lookup_is_exact_active_only_and_cross_purpose_safe(installation_runtime):
    store, factory = installation_runtime
    marker = "gsk_" + "SYNTHETIC_GROQ_ONLY_1234567890"
    descriptor = _put(store, factory, "groq", marker)
    with factory() as session:
        values = store.get_for_binding(session, installation_binding("groq"))
        assert values[0].reveal().decode() == marker
        with pytest.raises(SecretStoreError, match="SECRET_NOT_FOUND"):
            store.get_for_binding(session, installation_binding("openai"))
        store.revoke(
            session,
            installation_binding("groq"),
            descriptor.secret_ref,
            actor="test:operator",
            expected_row_version=descriptor.row_version,
        )
        session.commit()
    with factory() as session:
        with pytest.raises(SecretStoreError, match="SECRET_REVOKED"):
            store.get_for_binding(session, installation_binding("groq"))


def test_openai_uses_db_credential_and_never_environment_fallback(
    installation_runtime, monkeypatch
):
    store, factory = installation_runtime
    marker = "sk-" + "SYNTHETIC_DB_OPENAI_1234567890"
    _put(store, factory, "openai", marker)
    observed = []
    monkeypatch.setenv(
        "OPENAI_API_KEY", "sk-" + "ENVIRONMENT_MUST_NOT_BE_USED_1234567890"
    )
    monkeypatch.setattr(
        llm_client,
        "OpenAI",
        lambda **kwargs: observed.append(kwargs) or SimpleNamespace(),
    )
    llm_client._openai_client()
    assert observed == [{"api_key": marker, "timeout": 60.0, "max_retries": 2}]


def test_github_runtime_uses_db_credential_and_public_mode_remains_possible(
    installation_runtime, monkeypatch
):
    store, factory = installation_runtime
    marker = "github_pat_" + "SYNTHETIC_DB_GITHUB_12345678901234567890"
    _put(store, factory, "github", marker)
    monkeypatch.setenv("TOPO_GITHUB_OWNER", "example")
    monkeypatch.setenv("TOPO_GITHUB_REPO", "repo")
    monkeypatch.setenv(
        "TOPO_GITHUB_TOKEN",
        "github_pat_" + "ENVIRONMENT_MUST_NOT_BE_USED_1234567890",
    )
    settings = GitHubSettings.from_environment()
    assert settings.token is None
    assert GitHubConnector(settings)._headers()["Authorization"] == f"Bearer {marker}"

    configure_runtime_secret_store(None)
    settings = GitHubSettings.for_repository(owner="example", repository="repo")
    assert "Authorization" not in GitHubConnector(settings)._headers()


def test_github_artifact_cross_origin_redirect_strips_bearer(monkeypatch):
    marker = "github_pat_" + "SYNTHETIC_REDIRECT_12345678901234567890"
    settings = GitHubSettings(
        owner="example", repository="repo", token=marker,
        api_url="https://api.github.test", api_version="test",
        timeout_seconds=1, commit_limit=1,
    )
    observed = []

    def fake_get(url, **kwargs):
        observed.append((url, dict(kwargs["headers"])))
        request = httpx.Request("GET", url)
        if len(observed) == 1:
            return httpx.Response(
                302,
                headers={"location": "https://objects.example/artifact.zip?signature=secret"},
                request=request,
            )
        return httpx.Response(200, content=b"zip", request=request)

    monkeypatch.setattr("app.connectors.github_connector.httpx.get", fake_get)
    assert GitHubConnector(settings).download_actions_artifact(1) == b"zip"
    assert observed[0][1]["Authorization"] == f"Bearer {marker}"
    assert "Authorization" not in observed[1][1]


def test_central_redactor_matrix_is_bounded_and_preserves_safe_metadata():
    marker = "topo_agent_" + "SYNTHETIC_REDACTOR_1234567890"
    value = {
        "ApiKey": marker,
        "client-secret": marker,
        "token_count": 9,
        "token_budget": 100,
        "credential_id": "credential:safe",
        "secret_ref": "secret:safe-reference",
        "token_hint": "safehint",
        "nested": {"items": [{"authorization": f"Bearer {marker}"}]},
    }
    sanitized = sanitize_structured(value)
    assert marker not in repr(sanitized)
    assert sanitized["ApiKey"] == REDACTED
    assert sanitized["token_count"] == 9
    assert sanitized["secret_ref"] == "secret:safe-reference"
    deep = marker
    for _ in range(8):
        deep = {"safe": deep}
    result = sanitize_structured(deep)
    assert marker not in repr(result)
    assert TRUNCATED in repr(result)
    assert marker not in safe_text(f"Authorization: Bearer {marker}")
    assert safe_url("https://user:pass@example.test/path?token=secret#fragment") == (
        "https://example.test/path"
    )
    headers = sanitize_headers({"X-Custom-Auth": marker, "Content-Type": "json"})
    assert headers["X-Custom-Auth"] == REDACTED
    assert sanitize_headers({"cOoKiE": marker, "Set-Cookie": marker}) == {
        "cOoKiE": REDACTED,
        "Set-Cookie": REDACTED,
    }
    bounded = sanitize_structured({f"item-{index}": index for index in range(105)})
    assert TRUNCATED in bounded
    exception = sanitize_structured(RuntimeError(f"Bearer {marker}"))
    assert exception == {"error_type": "RuntimeError"}
    response_headers = safe_response_headers(
        {"Set-Cookie": marker, "Retry-After": "5"}
    )
    assert response_headers == {"Retry-After": "5"}


def test_validation_error_formatter_omits_rejected_input_and_context():
    marker = "topo_enroll_" + "SYNTHETIC_VALIDATION_1234567890"
    result = safe_validation_errors([
        {
            "loc": ("body", "enrollment_token"),
            "msg": "String should have at least 16 characters",
            "type": "string_too_short",
            "input": marker,
            "ctx": {"secret": marker},
        }
    ])
    assert marker not in repr(result)
    assert set(result[0]) == {"loc", "msg", "type"}


def test_public_validation_boundary_omits_agent_credential_input(monkeypatch):
    marker = "topo_enroll_" + "SYNTHETIC_HTTP_VALIDATION_1234567890"
    monkeypatch.setenv("TOPO_AUTH_MODE", "development-disabled")
    application = create_app(database_initializer=lambda: None)
    response = TestClient(application).post(
        "/api/v1/agents/enroll",
        json={
            "enrollment_token": marker + ("x" * 1000),
            "name": "test-agent",
            "cluster_name": "test-cluster",
            "version": "test",
        },
    )
    assert response.status_code == 422
    assert marker not in response.text
    assert "input" not in response.json()["detail"][0]
    assert "ctx" not in response.json()["detail"][0]


def test_one_time_agent_credential_models_have_safe_repr():
    marker = "topo_agent_" + "SYNTHETIC_RESPONSE_REPR_1234567890"
    response = AgentEnrollResponse(
        agent_id="agent:test",
        agent_token=marker,
        enrolled_at="2026-09-02T00:00:00+00:00",
        config=AgentConfigView(
            collection_interval_seconds=300,
            heartbeat_interval_seconds=30,
            namespace_scope=[],
        ),
    )
    assert marker not in repr(response)
    assert response.model_dump()["agent_token"] == marker


@pytest.mark.parametrize("integration", ["openai", "groq", "github"])
def test_installation_rotation_is_active_only(
    installation_runtime, integration: str
):
    store, factory = installation_runtime
    old = f"old-{integration}-credential-value"
    new = f"new-{integration}-credential-value"
    descriptor = _put(store, factory, integration, old)
    with factory() as session:
        rotated = store.rotate(
            session,
            installation_binding(integration),
            descriptor.secret_ref,
            SecretMaterial(new.encode()),
            operation_id=f"rotate:{integration}",
            actor="test:operator",
            expected_row_version=descriptor.row_version,
            overlap_seconds=0,
        )
        session.commit()
        values = store.get_for_binding(session, installation_binding(integration))
    assert rotated.previous_version is None
    assert [value.reveal().decode() for value in values] == [new]


def test_tenant_scope_cannot_be_substituted_for_installation_binding():
    with pytest.raises(SecretStoreError, match="SECRET_OWNER_PURPOSE_INVALID"):
        SecretBinding(
            scope=SecretScope.tenant("tenant:11111111-1111-4111-8111-111111111111"),
            owner_type="installation_integration",
            owner_id="openai",
            purpose=SecretPurpose.OPENAI_API,
        )


def test_operator_utility_accepts_only_safe_secret_inputs_and_outputs(
    installation_runtime, monkeypatch, capsys
):
    store, factory = installation_runtime
    marker = "sk-" + "SYNTHETIC_OPERATOR_DB_PROOF_1234567890"
    parser = installation_secret_admin._parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["set", "openai", "--secret", marker])
    assert marker not in capsys.readouterr().err
    with pytest.raises(SystemExit):
        parser.parse_args(["import-known-env", "openai", "--env", "OTHER_SECRET"])

    args = parser.parse_args(
        ["set", "openai", "--secret-stdin", "--operation-id", "test:operator:set"]
    )
    monkeypatch.setattr(installation_secret_admin.sys, "stdin", io.StringIO(marker))
    with factory() as session:
        result = installation_secret_admin._mutate(store, session, args)
        status = installation_secret_admin._safe_status(store, session, "openai")
        record_metadata = session.execute(
            select(
                SecretRecord.scope_kind,
                SecretRecord.scope_id,
                SecretRecord.owner_type,
                SecretRecord.owner_id,
                SecretRecord.purpose,
                SecretRecord.status,
            )
        ).all()
        protected_versions = session.scalars(select(SecretVersionRecord)).all()

    assert result["operation"] == "set"
    assert set(status) == {"integration", "configured", "status", "updated_at"}
    assert marker not in repr(result)
    assert marker not in repr(status)
    assert marker not in repr(record_metadata)
    assert all(marker.encode() not in version.ciphertext for version in protected_versions)
    forbidden = {"secret_ref", "key_id", "ciphertext", "material_version"}
    assert forbidden.isdisjoint(result)
    assert forbidden.isdisjoint(status)


def test_central_logging_and_sql_errors_hide_bound_credentials(caplog):
    marker = "topo_api_" + "SYNTHETIC_LOG_SQL_1234567890"
    install_logging_redaction()
    logger = logging.getLogger("test.ph4d")
    with caplog.at_level(logging.WARNING):
        logger.warning("Authorization: Bearer %s", marker)
    assert marker not in caplog.text

    engine = create_engine("sqlite+pysqlite:///:memory:", hide_parameters=True)
    try:
        with engine.connect() as connection, pytest.raises(SQLAlchemyError) as captured:
            connection.execute(
                text("SELECT :credential FROM ph4d_missing_table"),
                {"credential": marker},
            )
        assert marker not in str(captured.value)
        assert "SQL parameters hidden" in str(captured.value)
    finally:
        engine.dispose()


def test_github_base_url_rejects_credentials_query_and_fragment(monkeypatch):
    monkeypatch.setenv("TOPO_GITHUB_OWNER", "example")
    monkeypatch.setenv("TOPO_GITHUB_REPO", "repo")
    for value in (
        "https://user:pass@api.github.test",
        "https://api.github.test?token=value",
        "https://api.github.test#credential",
    ):
        monkeypatch.setenv("TOPO_GITHUB_API_URL", value)
        with pytest.raises(ValueError):
            GitHubSettings.from_environment()
