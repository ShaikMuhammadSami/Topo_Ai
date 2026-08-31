"""Opt-in PostgreSQL 16 proof for atomic agent enrollment consumption."""

from __future__ import annotations
from domain_tenant_fixtures import TEST_TENANT, TEST_HEADERS, seed_domain_tenant

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from alembic import command
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.db.database import _synchronous_database_url
from app.db.models import AgentEnrollmentTokenRecord, TopoAgentRecord
from app.db.schema_management import alembic_config
from app.models.agents import (
    AgentEnrollRequest,
    AgentEnrollmentTokenCreateRequest,
)
from app.repositories.agent_repository import (
    AgentEnrollmentRejected,
    authenticate_agent,
    create_enrollment_token,
    enroll_agent,
    revoke_agent,
)


POSTGRES_URL = os.getenv("TOPO_TEST_POSTGRES_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="set TOPO_TEST_POSTGRES_URL to run PostgreSQL enrollment tests",
)


@pytest.fixture(scope="module")
def postgres_engine() -> Engine:
    engine = create_engine(
        _synchronous_database_url(POSTGRES_URL),
        pool_pre_ping=True,
    )
    with engine.begin() as connection:
        configuration = alembic_config(connection=connection)
        # Load the real migration options, but do not let in-process Alembic
        # replace pytest handlers/disable app loggers for later auth tests.
        configuration.get_section(configuration.config_ini_section)
        configuration.config_file_name = None
        command.upgrade(configuration, "head")
    yield engine
    engine.dispose()


@pytest.fixture()
def sessions(postgres_engine: Engine):
    with postgres_engine.begin() as connection:
        connection.execute(text("DELETE FROM topo_agents"))
        connection.execute(text("DELETE FROM agent_enrollment_tokens"))
    seed_domain_tenant(postgres_engine, subject="test:postgres-security")
    factory = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    yield factory
    with postgres_engine.begin() as connection:
        connection.execute(text("DELETE FROM topo_agents"))
        connection.execute(text("DELETE FROM agent_enrollment_tokens"))


def _request(raw_token: str, contender: int) -> AgentEnrollRequest:
    return AgentEnrollRequest(
        enrollment_token=raw_token,
        name=f"postgres-agent-{contender}",
        cluster_name="postgres-security-cluster",
        version="1.0.0",
    )


def _token(sessions, max_uses: int) -> tuple[str, str]:
    with sessions() as session:
        issued = create_enrollment_token(
            session,
            tenant_id=TEST_TENANT,
            request=AgentEnrollmentTokenCreateRequest(
                max_uses=max_uses,
                expires_in_minutes=30,
            ),
            created_by="test:postgres-security",
        )
    return issued.enrollment_token_id, issued.enrollment_token


def _race(sessions, raw_token: str, attempts: int) -> list[str]:
    barrier = Barrier(attempts)

    def contender(index: int) -> str:
        barrier.wait(timeout=10)
        with sessions() as session:
            try:
                enroll_agent(session, request=_request(raw_token, index))
            except AgentEnrollmentRejected:
                return "rejected"
            return "accepted"

    with ThreadPoolExecutor(max_workers=attempts) as executor:
        return list(executor.map(contender, range(attempts)))


def _state(sessions, enrollment_id: str) -> tuple[int, int]:
    with sessions() as session:
        enrollment = session.get(AgentEnrollmentTokenRecord, enrollment_id)
        assert enrollment is not None
        agents = session.scalar(select(func.count()).select_from(TopoAgentRecord))
        return enrollment.use_count, int(agents or 0)


def test_postgres_baseline_is_read_committed(postgres_engine: Engine) -> None:
    with postgres_engine.connect() as connection:
        isolation = connection.scalar(text("SHOW transaction_isolation"))

    assert isolation == "read committed"


def test_postgres_max_one_two_attempts_have_one_winner(sessions) -> None:
    enrollment_id, raw_token = _token(sessions, 1)

    results = _race(sessions, raw_token, 2)

    assert sorted(results) == ["accepted", "rejected"]
    assert _state(sessions, enrollment_id) == (1, 1)


def test_postgres_max_two_three_attempts_have_two_winners(sessions) -> None:
    enrollment_id, raw_token = _token(sessions, 2)

    results = _race(sessions, raw_token, 3)

    assert results.count("accepted") == 2
    assert results.count("rejected") == 1
    assert _state(sessions, enrollment_id) == (2, 2)


def test_postgres_agent_insert_failure_rolls_back_token_consumption(
    sessions,
) -> None:
    enrollment_id, raw_token = _token(sessions, 1)

    def reject_insert(*_args) -> None:
        raise RuntimeError("synthetic postgres insert failure")

    event.listen(TopoAgentRecord, "before_insert", reject_insert)
    try:
        with sessions() as session:
            with pytest.raises(
                RuntimeError,
                match="synthetic postgres insert failure",
            ):
                enroll_agent(session, request=_request(raw_token, 1))
    finally:
        event.remove(TopoAgentRecord, "before_insert", reject_insert)

    assert _state(sessions, enrollment_id) == (0, 0)
    with sessions() as session:
        response = enroll_agent(session, request=_request(raw_token, 2))
    assert response.agent_token.startswith("topo_agent_")
    assert _state(sessions, enrollment_id) == (1, 1)


def test_postgres_agent_revocation_is_durable(sessions) -> None:
    _, raw_enrollment = _token(sessions, 1)
    with sessions() as session:
        enrolled = enroll_agent(session, request=_request(raw_enrollment, 1))
        assert authenticate_agent(
            session,
            token=enrolled.agent_token,
        ) is not None
        revoked = revoke_agent(session, agent_id=enrolled.agent_id, tenant_id=TEST_TENANT)
        assert revoked is not None
        assert revoked.revoked_at is not None

    with sessions() as restarted_session:
        assert authenticate_agent(
            restarted_session,
            token=enrolled.agent_token,
        ) is None
