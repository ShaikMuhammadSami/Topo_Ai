from __future__ import annotations

from types import MappingProxyType

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

import app.main as main_module
from app.db.database import (
    Base,
    POSTGRES_CONNECT_TIMEOUT_SECONDS,
    POSTGRES_POOL_TIMEOUT_SECONDS,
    _engine_options,
)
from app.security.auth_config import AuthConfiguration, AuthMode, TokenIdentity
from app.security.secret_keyring import SecretStoreConfiguration
from app.services.runtime_health import (
    READINESS_CHECK_MAX_SECONDS,
    READINESS_CONNECT_TIMEOUT_SECONDS,
    READINESS_STATEMENT_TIMEOUT_MILLISECONDS,
    _postgresql_readiness_engine_options,
    build_database_readiness_checker,
    database_session_is_ready,
)


def _configuration() -> AuthConfiguration:
    return AuthConfiguration(
        mode=AuthMode.REQUIRED,
        token_registry=MappingProxyType(
            {
                "a" * 64: TokenIdentity(
                    subject="test:runtime-health",
                    display_name="Runtime Health Test",
                    roles=("admin",),
                )
            }
        ),
        browser_allowed_origins=(),
        session_absolute_ttl_minutes=480,
        session_idle_ttl_minutes=60,
    )


def _database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)


def _database_outage() -> OperationalError:
    return OperationalError(
        "database readiness probe",
        {},
        RuntimeError("synthetic database unavailable"),
    )


def test_database_probe_returns_only_boolean_availability() -> None:
    engine, factory = _database()
    try:
        assert database_session_is_ready(factory) is True

        def unavailable_factory():
            raise _database_outage()

        assert database_session_is_ready(unavailable_factory) is False
    finally:
        engine.dispose()


def test_postgresql_engine_connect_and_pool_waits_are_bounded() -> None:
    options = _engine_options("postgresql+psycopg://db.internal/topo")

    assert options["pool_pre_ping"] is True
    assert options["connect_args"] == {
        "connect_timeout": POSTGRES_CONNECT_TIMEOUT_SECONDS
    }
    assert options["pool_timeout"] == POSTGRES_POOL_TIMEOUT_SECONDS
    assert POSTGRES_CONNECT_TIMEOUT_SECONDS == 3
    assert POSTGRES_POOL_TIMEOUT_SECONDS == 2


def test_postgresql_readiness_has_isolated_connect_and_statement_bounds() -> None:
    options = _postgresql_readiness_engine_options()

    assert options["poolclass"] is NullPool
    assert options["hide_parameters"] is True
    assert options["connect_args"] == {
        "connect_timeout": READINESS_CONNECT_TIMEOUT_SECONDS,
        "options": (
            "-c statement_timeout="
            f"{READINESS_STATEMENT_TIMEOUT_MILLISECONDS}"
        ),
    }
    assert READINESS_CONNECT_TIMEOUT_SECONDS == 2
    assert READINESS_STATEMENT_TIMEOUT_MILLISECONDS == 2_000
    assert READINESS_CHECK_MAX_SECONDS == 4


def test_non_postgresql_readiness_reuses_supplied_session_factory() -> None:
    engine, factory = _database()
    try:
        checker = build_database_readiness_checker("sqlite://", factory)
        assert checker() is True
    finally:
        engine.dispose()


def test_database_outage_removes_readiness_without_failing_liveness(
    monkeypatch,
) -> None:
    engine, factory = _database()
    available = {"value": True}
    monkeypatch.setattr(
        main_module,
        "load_secret_store_configuration",
        SecretStoreConfiguration,
    )
    application = main_module.create_app(
        auth_configuration=_configuration(),
        session_factory=factory,
        database_initializer=lambda: None,
        database_readiness_checker=lambda: available["value"],
    )

    try:
        with TestClient(application) as client:
            assert client.get("/startup").json() == {"status": "started"}
            assert client.get("/ready").json() == {"status": "ready"}

            available["value"] = False
            health = client.get("/health")
            not_ready = client.get("/ready")

            assert health.status_code == 200
            assert health.json() == {
                "status": "available",
                "service": "Topo AI",
                "version": "0.1.0",
            }
            assert not_ready.status_code == 503
            assert not_ready.json() == {"status": "not_ready"}
            assert client.get("/startup").json() == {"status": "started"}

            available["value"] = True
            assert client.get("/ready").json() == {"status": "ready"}
            assert client.get("/startup").json() == {"status": "started"}
    finally:
        engine.dispose()


def test_transient_database_outage_during_startup_retries_without_process_death(
    monkeypatch,
) -> None:
    engine, factory = _database()
    attempts = {"count": 0}

    def initialize() -> None:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise _database_outage()

    monkeypatch.setattr(
        main_module,
        "load_secret_store_configuration",
        SecretStoreConfiguration,
    )
    application = main_module.create_app(
        auth_configuration=_configuration(),
        session_factory=factory,
        database_initializer=initialize,
        database_readiness_checker=lambda: True,
    )

    try:
        with TestClient(application) as client:
            started = client.get("/startup")
            assert client.get("/health").status_code == 200
            first = client.get("/ready")
            second = client.get("/ready")

            assert started.status_code == 200
            assert started.json() == {"status": "started"}
            assert first.status_code == 503
            assert first.json() == {"status": "not_ready"}
            assert second.status_code == 200
            assert second.json() == {"status": "ready"}
            assert attempts["count"] == 3
    finally:
        engine.dispose()


def test_readiness_failure_never_exposes_database_exception(
    monkeypatch,
    caplog,
) -> None:
    engine, factory = _database()
    marker = "private-database-diagnostic-marker"

    def fail_probe() -> bool:
        raise OperationalError(
            "database readiness probe",
            {},
            RuntimeError(marker),
        )

    monkeypatch.setattr(
        main_module,
        "load_secret_store_configuration",
        SecretStoreConfiguration,
    )
    application = main_module.create_app(
        auth_configuration=_configuration(),
        session_factory=factory,
        database_initializer=lambda: None,
        database_readiness_checker=fail_probe,
    )

    try:
        with TestClient(application) as client:
            started = client.get("/startup")
            response = client.get("/ready")
        assert started.status_code == 200
        assert started.json() == {"status": "started"}
        assert response.status_code == 503
        assert response.json() == {"status": "not_ready"}
        assert marker not in started.text
        assert marker not in response.text
        assert marker not in caplog.text
    finally:
        engine.dispose()
