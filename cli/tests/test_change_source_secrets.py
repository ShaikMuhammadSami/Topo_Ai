from __future__ import annotations

from typer.testing import CliRunner

import topo_cli.main as main_module
from topo_cli.config import Profile, TopoConfig


class FakeChangeSourceClient:
    def __init__(self) -> None:
        self.creates: list[dict] = []
        self.updates: list[tuple[str, dict, str | None]] = []

    def close(self) -> None:
        return None

    def create_change_source(self, request: dict):
        self.creates.append(request)
        return {
            "source_id": "change-source:github:test",
            "source_type": request["source_type"],
            "enabled": True,
            "credential_configured": True,
            "credential_status": "configured",
        }

    def update_change_source(self, source_id: str, request: dict, *, idempotency_key=None):
        self.updates.append((source_id, request, idempotency_key))
        return {
            "source_id": source_id,
            "enabled": request.get("credential", {}).get("action") != "revoke",
            "credential_configured": request.get("credential", {}).get("action") != "revoke",
        }


def _runtime(monkeypatch) -> FakeChangeSourceClient:
    profile = Profile(api_url="https://topo.example")
    config = TopoConfig(active_profile="test", profiles={"test": profile})
    fake = FakeChangeSourceClient()
    monkeypatch.setattr(main_module, "load_config", lambda: config)
    monkeypatch.setattr(main_module, "resolve_profile", lambda config, selected: ("test", profile))
    monkeypatch.setattr(main_module, "profile_token", lambda *args: "stored-token")
    monkeypatch.setattr(main_module, "TopoClient", lambda **kwargs: fake)
    return fake


def test_create_reads_local_environment_and_never_sends_server_secret_reference(monkeypatch):
    fake = _runtime(monkeypatch)
    marker = "ph4c-cli-transient-marker"
    monkeypatch.setenv("TOPO_TEST_PROVIDER_INPUT", marker)
    result = CliRunner().invoke(main_module.app, [
        "change-sources", "create-github", "--name", "Secure GitHub",
        "--secret-env", "TOPO_TEST_PROVIDER_INPUT",
    ])
    assert result.exit_code == 0, result.output
    assert fake.creates[0]["credential"] == marker
    assert "secret_ref" not in fake.creates[0]
    assert marker not in result.output


def test_rotate_uses_write_only_input_and_stable_non_secret_operation_id(monkeypatch):
    fake = _runtime(monkeypatch)
    marker = "ph4c-cli-rotation-marker"
    monkeypatch.setenv("TOPO_TEST_PROVIDER_ROTATION", marker)
    result = CliRunner().invoke(main_module.app, [
        "change-sources", "rotate", "source:one", "--secret-env",
        "TOPO_TEST_PROVIDER_ROTATION", "--overlap-seconds", "60",
    ])
    assert result.exit_code == 0, result.output
    source_id, request, operation_id = fake.updates[0]
    assert source_id == "source:one"
    assert request == {"credential": {
        "action": "rotate", "credential": marker, "overlap_seconds": 60,
    }}
    assert operation_id and marker not in operation_id
    assert marker not in result.output


def test_revoke_sends_no_raw_credential(monkeypatch):
    fake = _runtime(monkeypatch)
    result = CliRunner().invoke(
        main_module.app, ["change-sources", "revoke", "source:one"]
    )
    assert result.exit_code == 0, result.output
    _, request, operation_id = fake.updates[0]
    assert request == {"credential": {"action": "revoke"}}
    assert operation_id
