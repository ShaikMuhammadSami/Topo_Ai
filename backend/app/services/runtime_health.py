"""Minimal process and database health primitives for deployment probes."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import create_engine, literal, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool


DatabaseSessionFactory = Callable[[], Session]
DatabaseReadinessChecker = Callable[[], bool]

READINESS_CONNECT_TIMEOUT_SECONDS = 2
READINESS_STATEMENT_TIMEOUT_MILLISECONDS = 2_000
READINESS_CHECK_MAX_SECONDS = (
    READINESS_CONNECT_TIMEOUT_SECONDS
    + READINESS_STATEMENT_TIMEOUT_MILLISECONDS // 1_000
)


def _postgresql_readiness_engine_options() -> dict[str, object]:
    """Keep probe-only timeouts isolated from normal application queries."""
    return {
        "connect_args": {
            "connect_timeout": READINESS_CONNECT_TIMEOUT_SECONDS,
            "options": (
                "-c statement_timeout="
                f"{READINESS_STATEMENT_TIMEOUT_MILLISECONDS}"
            ),
        },
        "hide_parameters": True,
        "poolclass": NullPool,
    }


def database_session_is_ready(
    session_factory: DatabaseSessionFactory,
) -> bool:
    """Return only availability; never expose driver or credential details."""
    try:
        with session_factory() as session:
            statement = select(literal(1))
            return session.execute(statement).scalar_one() == 1
    except SQLAlchemyError:
        return False


def build_database_readiness_checker(
    database_url: str,
    fallback_session_factory: DatabaseSessionFactory,
) -> DatabaseReadinessChecker:
    """Build a bounded PostgreSQL probe without changing product sessions."""
    if make_url(database_url).get_backend_name() != "postgresql":
        return lambda: database_session_is_ready(fallback_session_factory)

    readiness_engine = create_engine(
        database_url,
        **_postgresql_readiness_engine_options(),
    )
    readiness_sessions = sessionmaker(
        bind=readiness_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    return lambda: database_session_is_ready(readiness_sessions)
