import json

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

    principal = resolve_principal(
        token
    )

    assert principal is not None

    assert (
        principal.subject
        == "test-user"
    )

    assert principal.roles == (
        "operator",
    )


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

    assert (
        resolve_principal(
            "invalid-token"
        )
        is None
    )