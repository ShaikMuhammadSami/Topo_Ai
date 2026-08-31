import os
import json

import pytest


# The product default remains required. Existing SQLite API tests opt into the
# explicit local-development mode until their individual callers are migrated
# to authenticated fixtures.
os.environ["TOPO_AUTH_MODE"] = "development-disabled"
os.environ.pop("TOPO_AUTH_ENABLED", None)
os.environ.pop("TOPO_API_TOKEN_HASHES_JSON", None)
os.environ["TOPO_BROWSER_ALLOWED_ORIGINS_JSON"] = json.dumps(
    [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
)


from app.db.database import SessionLocal  # noqa: E402


@pytest.fixture
def db_session():
    """Provides a transactional database session for tests."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def required_auth_app(monkeypatch):
    from app.main import create_app
    from app.security.api_tokens import token_digest

    token = "ph2b-test-human-bearer-" + ("x" * 32)
    registry = {
        token_digest(token): {
            "subject": "test:admin",
            "display_name": "Test Admin",
            "roles": ["admin", "operator"],
        }
    }
    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.setenv("TOPO_API_TOKEN_HASHES_JSON", json.dumps(registry))
    # Startup now verifies SecretStore emptiness even when disabled. Keep this
    # auth fixture independent of the protected developer database and supply a
    # real disposable schema instead of bypassing the readiness invariant.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.db.database import Base

    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    try:
        yield create_app(database_initializer=lambda: None,
                         session_factory=sessionmaker(engine))
    finally:
        engine.dispose()
