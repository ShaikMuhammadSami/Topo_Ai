from __future__ import annotations

import json
import secrets

from typer.testing import CliRunner

import topo_cli.main as main_module
from topo_cli.config import Profile, TopoConfig


class FakeCredentialClient:
    def __init__(self, **kwargs) -> None:
        self.calls: list[tuple[str, object]] = []
        self.raw_secret = "topo_api_" + secrets.token_urlsafe(48)

    def close(self) -> None:
        return None

    def create_api_credential(self, **kwargs):
        self.calls.append(("create", kwargs))
        return {
            "credential_id": "api-credential:test",
            "credential_hint": "safehint",
            "name": kwargs["name"],
            "caller_type": kwargs["caller_type"],
            "subject": kwargs["subject"],
            "display_name": kwargs["display_name"] or kwargs["subject"],
            "roles": kwargs["roles"],
            "created_at": "2026-08-29T00:00:00+00:00",
            "created_by_subject": "test:admin",
            "expires_at": "2026-09-28T00:00:00+00:00",
            "revoked_at": None,
            "revoked_by_subject": None,
            "last_used_at": None,
            "updated_at": "2026-08-29T00:00:00+00:00",
            "api_credential": self.raw_secret,
        }

    def list_api_credentials(self, **kwargs):
        self.calls.append(("list", kwargs))
        return [
            {
                "credential_id": "api-credential:test",
                "name": "operator",
                "caller_type": "human_api",
                "subject": "test:operator",
                "roles": ["admin"],
                "expires_at": "2026-09-28T00:00:00+00:00",
                "revoked_at": None,
                "last_used_at": None,
            }
        ]

    def revoke_api_credential(self, credential_id: str):
        self.calls.append(("revoke", credential_id))
        return {
            "credential_id": credential_id,
            "name": "operator",
            "revoked_at": "2026-08-29T01:00:00+00:00",
            "revoked_by_subject": "test:admin",
        }


def _install_runtime(monkeypatch) -> FakeCredentialClient:
    profile = Profile(api_url="https://topo.example")
    config = TopoConfig(active_profile="test", profiles={"test": profile})
    fake = FakeCredentialClient()
    monkeypatch.setattr(main_module, "load_config", lambda: config)
    monkeypatch.setattr(
        main_module,
        "resolve_profile",
        lambda config, selected: ("test", profile),
    )
    monkeypatch.setattr(main_module, "profile_token", lambda *args: "stored-token")
    monkeypatch.setattr(main_module, "TopoClient", lambda **kwargs: fake)
    return fake


def test_credential_create_requires_explicit_one_time_secret_output(
    monkeypatch,
) -> None:
    fake = _install_runtime(monkeypatch)
    runner = CliRunner()
    arguments = [
        "auth",
        "credentials",
        "create",
        "--name",
        "operator",
        "--subject",
        "test:operator",
        "--role",
        "admin",
    ]

    refused = runner.invoke(main_module.app, arguments)
    accepted = runner.invoke(
        main_module.app,
        arguments + ["--output-token-stdout"],
    )

    assert refused.exit_code == 7
    assert "--output-token-stdout" in refused.output
    assert accepted.exit_code == 0
    assert accepted.output.count(fake.raw_secret) == 1
    assert fake.calls[-1][0] == "create"


def test_credential_list_json_omits_secret_and_revoke_uses_identifier(
    monkeypatch,
) -> None:
    fake = _install_runtime(monkeypatch)
    runner = CliRunner()

    listing = runner.invoke(
        main_module.app,
        ["--output", "json", "auth", "credentials", "list"],
    )
    revoked = runner.invoke(
        main_module.app,
        ["auth", "credentials", "revoke", "api-credential:test"],
    )

    assert listing.exit_code == 0
    parsed = json.loads(listing.stdout)
    assert parsed[0]["credential_id"] == "api-credential:test"
    assert "api_credential" not in listing.stdout
    assert revoked.exit_code == 0
    assert ("revoke", "api-credential:test") in fake.calls


def test_named_credential_login_stores_only_in_keyring_boundary(
    monkeypatch,
) -> None:
    raw_secret = "topo_api_" + secrets.token_urlsafe(48)
    profile = Profile(api_url="https://topo.example")
    config = TopoConfig(active_profile="test", profiles={"test": profile})
    stored: list[tuple[str, str]] = []

    class LoginClient:
        def __init__(self, **kwargs) -> None:
            self.token = kwargs.get("token")

        def close(self) -> None:
            return None

        def whoami(self):
            assert self.token == raw_secret
            return {
                "subject": "test:named-operator",
                "display_name": "Named Operator",
                "roles": ["admin"],
                "authentication_type": "human_api_token",
            }

    monkeypatch.setattr(main_module, "load_config", lambda: config)
    monkeypatch.setattr(
        main_module,
        "resolve_profile",
        lambda config, selected: ("test", profile),
    )
    monkeypatch.setattr(main_module, "profile_token", lambda *args: None)
    monkeypatch.setattr(main_module, "TopoClient", LoginClient)
    monkeypatch.setattr(
        main_module,
        "store_profile_token",
        lambda profile_name, token: stored.append((profile_name, token)),
    )

    result = CliRunner().invoke(
        main_module.app,
        ["login", "--token-stdin"],
        input=raw_secret,
    )

    assert result.exit_code == 0
    assert stored == [("test", raw_secret)]
    assert raw_secret not in result.output
    assert raw_secret not in json.dumps(config, default=lambda value: value.__dict__)


def test_logout_is_local_only_and_does_not_revoke_server_credential(
    monkeypatch,
) -> None:
    fake = _install_runtime(monkeypatch)
    removed: list[str] = []
    monkeypatch.setattr(
        main_module,
        "delete_profile_token",
        lambda profile_name: removed.append(profile_name) or True,
    )

    result = CliRunner().invoke(main_module.app, ["logout"])

    assert result.exit_code == 0
    assert removed == ["test"]
    assert not any(call[0] == "revoke" for call in fake.calls)
    assert "Server credentials are unchanged" in result.output
