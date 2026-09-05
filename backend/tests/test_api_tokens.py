import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base

from app.security.api_tokens import (
    resolve_principal,
    token_digest,
)


def test_resolves_valid_token(
    monkeypatch,
) -> None:
    token = "unit-test-token"

    registry = {
        token_digest(token): {
            "subject": "test-user",
            "display_name": (
                "Test User"
            ),
            "roles": [
                "operator",
            ],
        }
    }

    monkeypatch.setenv(
        "TOPO_API_TOKEN_HASHES_JSON",
        json.dumps(registry),
    )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        principal = resolve_principal(
            token,
            session=session,
            allow_provision=True,
        )

    assert principal is not None

    assert (
        principal.subject
        == "test-user"
    )

    assert principal.roles == (
        "operator",
    )
    assert principal.principal_id is not None
    assert principal.principal_type == "human"


def test_rejects_invalid_token(
    monkeypatch,
) -> None:
    registry = {
        token_digest(
            "valid-token"
        ): {
            "subject": "test-user",
            "roles": [
                "operator",
            ],
        }
    }

    monkeypatch.setenv(
        "TOPO_API_TOKEN_HASHES_JSON",
        json.dumps(registry),
    )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        assert (
            resolve_principal(
                "invalid-token",
                session=session,
            )
            is None
        )
