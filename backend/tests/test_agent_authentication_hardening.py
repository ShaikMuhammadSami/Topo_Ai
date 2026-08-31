from __future__ import annotations
from domain_tenant_fixtures import TEST_TENANT, TEST_HEADERS, seed_domain_tenant

import json
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.database import Base, get_session
from app.db.models import (
    AgentEnrollmentTokenRecord,
    TopoAgentRecord,
)
from app.main import create_app
from app.models.agents import (
    AgentEnrollRequest,
    AgentEnrollmentTokenCreateRequest,
)
from app.repositories.agent_repository import (
    AgentEnrollmentRejected,
    create_enrollment_token,
    enroll_agent,
)
from app.security.api_tokens import token_digest
from app.security.auth_config import load_auth_configuration


PUBLIC_REJECTION = (
    "The enrollment credential is invalid or unavailable."
)


@pytest.fixture()
def file_sessions(tmp_path):
    database_path = tmp_path / "agent-auth.sqlite3"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path.as_posix()}",
        connect_args={
            "check_same_thread": False,
            "timeout": 30,
        },
    )
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine, subject="test:admin")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


def _request(raw_token: str, contender: int = 0) -> AgentEnrollRequest:
    return AgentEnrollRequest(
        enrollment_token=raw_token,
        name=f"security-agent-{contender}",
        cluster_name="security-cluster",
        environment="test",
        version="1.0.0",
        namespace_scope=["payments"],
    )


def _token(
    sessions,
    *,
    max_uses: int = 1,
) -> tuple[str, str]:
    with sessions() as session:
        issued = create_enrollment_token(
            session,
            tenant_id=TEST_TENANT,
            request=AgentEnrollmentTokenCreateRequest(
                label="security-test",
                expires_in_minutes=30,
                max_uses=max_uses,
            ),
            created_by="test:security",
        )
    return issued.enrollment_token_id, issued.enrollment_token


def _counts(sessions, enrollment_token_id: str) -> tuple[int, int]:
    with sessions() as session:
        enrollment = session.get(
            AgentEnrollmentTokenRecord,
            enrollment_token_id,
        )
        assert enrollment is not None
        agent_count = session.scalar(
            select(func.count()).select_from(TopoAgentRecord)
        )
        return enrollment.use_count, int(agent_count or 0)


def _concurrent_enrollments(
    sessions,
    raw_token: str,
    attempts: int,
) -> list[str]:
    barrier = Barrier(attempts)

    def contender(index: int) -> str:
        barrier.wait(timeout=10)
        with sessions() as session:
            try:
                enroll_agent(
                    session,
                    request=_request(raw_token, index),
                )
            except AgentEnrollmentRejected:
                return "rejected"
            return "accepted"

    with ThreadPoolExecutor(max_workers=attempts) as executor:
        return list(executor.map(contender, range(attempts)))


def _required_application(monkeypatch, sessions):
    human_token = "human-test-" + secrets.token_urlsafe(32)
    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.setenv(
        "TOPO_API_TOKEN_HASHES_JSON",
        json.dumps(
            {
                token_digest(human_token): {
                    "subject": "test:admin",
                    "display_name": "Test Admin",
                    "roles": ["admin", "operator"],
                }
            }
        ),
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
    return application, human_token


def test_http_enrollment_is_single_use_and_persists_only_digests(
    monkeypatch,
    file_sessions,
) -> None:
    enrollment_id, raw_enrollment = _token(file_sessions)
    application, _ = _required_application(monkeypatch, file_sessions)

    with TestClient(application) as client:
        first = client.post(
            "/api/v1/agents/enroll",
            json=_request(raw_enrollment).model_dump(),
        )
        second = client.post(
            "/api/v1/agents/enroll",
            json=_request(raw_enrollment, 2).model_dump(),
        )

    assert first.status_code == 201
    assert first.json()["agent_token"].startswith("topo_agent_")
    assert second.status_code == 401
    assert second.json() == {"detail": PUBLIC_REJECTION}
    assert _counts(file_sessions, enrollment_id) == (1, 1)

    raw_agent = first.json()["agent_token"]
    with file_sessions() as session:
        enrollment = session.get(AgentEnrollmentTokenRecord, enrollment_id)
        agent = session.scalar(select(TopoAgentRecord))
        assert enrollment is not None
        assert agent is not None
        persisted = " ".join(
            str(value)
            for record in (enrollment, agent)
            for value in vars(record).values()
        )
    assert raw_enrollment not in persisted
    assert raw_agent not in persisted


def test_file_sqlite_max_one_has_exactly_one_concurrent_winner(
    file_sessions,
) -> None:
    enrollment_id, raw_token = _token(file_sessions, max_uses=1)

    results = _concurrent_enrollments(file_sessions, raw_token, 2)

    assert sorted(results) == ["accepted", "rejected"]
    assert _counts(file_sessions, enrollment_id) == (1, 1)


def test_file_sqlite_max_two_has_exactly_two_concurrent_winners(
    file_sessions,
) -> None:
    enrollment_id, raw_token = _token(file_sessions, max_uses=2)

    results = _concurrent_enrollments(file_sessions, raw_token, 3)

    assert results.count("accepted") == 2
    assert results.count("rejected") == 1
    assert _counts(file_sessions, enrollment_id) == (2, 2)


def test_agent_insert_failure_rolls_back_consumption_and_allows_retry(
    file_sessions,
) -> None:
    enrollment_id, raw_token = _token(file_sessions)

    def reject_insert(*_args) -> None:
        raise RuntimeError("synthetic insert failure")

    event.listen(TopoAgentRecord, "before_insert", reject_insert)
    try:
        with file_sessions() as session:
            with pytest.raises(RuntimeError, match="synthetic insert failure"):
                enroll_agent(session, request=_request(raw_token))
    finally:
        event.remove(TopoAgentRecord, "before_insert", reject_insert)

    assert _counts(file_sessions, enrollment_id) == (0, 0)

    with file_sessions() as session:
        response = enroll_agent(session, request=_request(raw_token, 2))

    assert response.agent_token.startswith("topo_agent_")
    assert _counts(file_sessions, enrollment_id) == (1, 1)


@pytest.mark.parametrize("state", ["unknown", "revoked", "expired", "used"])
def test_unusable_enrollment_credentials_have_one_public_failure(
    monkeypatch,
    file_sessions,
    state: str,
) -> None:
    enrollment_id, raw_token = _token(file_sessions)
    if state == "unknown":
        raw_token = "unknown-token-" + secrets.token_urlsafe(24)
    else:
        with file_sessions() as session:
            record = session.get(AgentEnrollmentTokenRecord, enrollment_id)
            assert record is not None
            if state == "revoked":
                record.revoked_at = datetime.now(UTC).isoformat()
            elif state == "expired":
                record.expires_at = (
                    datetime.now(UTC) - timedelta(minutes=1)
                ).isoformat()
            else:
                record.use_count = record.max_uses
            session.commit()

    application, _ = _required_application(monkeypatch, file_sessions)
    with TestClient(application) as client:
        response = client.post(
            "/api/v1/agents/enroll",
            json=_request(raw_token).model_dump(),
        )

    assert response.status_code == 401
    assert response.json() == {"detail": PUBLIC_REJECTION}
    assert "agent_token" not in response.text
    with file_sessions() as session:
        assert session.scalar(
            select(func.count()).select_from(TopoAgentRecord)
        ) == 0


def test_agent_and_human_domains_remain_separate_and_revocation_is_durable(
    monkeypatch,
    file_sessions,
) -> None:
    _, raw_enrollment = _token(file_sessions)
    application, human_token = _required_application(monkeypatch, file_sessions)
    with TestClient(application) as client:
        enrolled = client.post(
            "/api/v1/agents/enroll",
            json=_request(raw_enrollment).model_dump(),
        ).json()
        agent_token = enrolled["agent_token"]
        agent_id = enrolled["agent_id"]
        agent_headers = {"Authorization": f"Bearer {agent_token}"}
        human_headers = {"Authorization": f"Bearer {human_token}", **TEST_HEADERS}

        assert client.get("/api/v1/agent/config", headers=agent_headers).status_code == 200
        assert client.get("/api/v1/agent/config").status_code == 401
        assert client.get(
            "/api/v1/agent/config",
            headers={"Authorization": "Bearer invalid-agent"},
        ).status_code == 401
        assert client.get("/api/v1/agent/config", headers=human_headers).status_code == 401
        assert client.get("/api/v1/system/whoami", headers=agent_headers).status_code == 401
        assert client.post(
            "/api/v1/agent/heartbeat",
            headers=agent_headers,
            json={"buffered_item_count": 0},
        ).status_code == 200
        assert client.post(
            f"/api/v1/agents/{agent_id}/revoke",
            headers=human_headers,
        ).status_code == 200
        assert client.get("/api/v1/agent/config", headers=agent_headers).status_code == 401

    restarted, _ = _required_application(monkeypatch, file_sessions)
    with TestClient(restarted) as client:
        assert client.get("/api/v1/agent/config", headers=agent_headers).status_code == 401


def test_agent_cluster_and_namespace_binding_remain_enforced(
    monkeypatch,
    file_sessions,
) -> None:
    _, raw_enrollment = _token(file_sessions)
    application, _ = _required_application(monkeypatch, file_sessions)
    with TestClient(application) as client:
        token = client.post(
            "/api/v1/agents/enroll",
            json=_request(raw_enrollment).model_dump(),
        ).json()["agent_token"]
        headers = {"Authorization": f"Bearer {token}"}
        snapshot = client.post(
            "/api/v1/agent/snapshots",
            headers=headers,
            json={
                "submission_id": "scope-test",
                "collected_at": datetime.now(UTC).isoformat(),
                "cluster_name": "other-cluster",
                "namespace_scope": ["payments"],
                "collector_version": "1.0.0",
                "inventory": {},
            },
        )
        signal_time = datetime.now(UTC).isoformat()
        signal = client.post(
            "/api/v1/agent/signals",
            headers=headers,
            json={
                "signals": [
                    {
                        "signal_id": "signal:scope-test",
                        "fingerprint": "scope-test",
                        "signal_type": "kubernetes_event",
                        "severity": "error",
                        "category": "health",
                        "source_system": "kubernetes",
                        "title": "Out of scope",
                        "summary": "Out of scope",
                        "first_observed_at": signal_time,
                        "last_observed_at": signal_time,
                        "cluster_name": "security-cluster",
                        "namespace": "outside-scope",
                    }
                ]
            },
        )

    assert snapshot.status_code == 400
    assert signal.status_code == 400


def test_enrollment_failure_does_not_log_raw_credentials(
    file_sessions,
    caplog,
) -> None:
    raw_token = "unknown-token-" + secrets.token_urlsafe(24)

    with file_sessions() as session:
        with pytest.raises(AgentEnrollmentRejected):
            enroll_agent(session, request=_request(raw_token))

    assert raw_token not in caplog.text
