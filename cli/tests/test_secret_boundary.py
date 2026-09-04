from __future__ import annotations

import httpx
import pytest
from typer.testing import CliRunner

import topo_cli.main as main_module
from topo_cli.client import TopoClient
from topo_cli.config import (
    Profile,
    TopoConfig,
    profile_token,
    store_profile_token,
)
from topo_cli.errors import ApiFailure, FileOperationFailure


def test_cli_rejects_credential_bearing_base_urls():
    for value in (
        "https://user:pass@topo.example",
        "https://topo.example?token=value",
        "https://topo.example#secret",
    ):
        with pytest.raises(Exception):
            Profile(api_url=value)


def test_cli_authenticated_client_disables_redirects_and_redacts_repr():
    marker = "topo_api_" + "SYNTHETIC_CLI_1234567890"
    client = TopoClient(
        api_url="https://topo.example", token=marker, timeout=1,
        verify_tls=True, snapshot_capture_path="/api/v1/snapshots/capture",
    )
    try:
        assert client._client.follow_redirects is False
        assert marker not in repr(client)
    finally:
        client.close()


def test_cli_does_not_echo_untrusted_remote_error_detail():
    marker = "topo_agent_" + "SYNTHETIC_REMOTE_ERROR_1234567890"
    response = httpx.Response(500, json={"detail": marker})
    assert marker not in TopoClient._error_message(response)


def test_cli_rejects_redirect_without_forwarding_bearer():
    marker = "topo_api_" + "SYNTHETIC_REDIRECT_1234567890"
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            302,
            headers={"location": "https://foreign.example/collect"},
            request=request,
        )

    client = TopoClient(
        api_url="https://topo.example", token=marker, timeout=1,
        verify_tls=True, snapshot_capture_path="/api/v1/snapshots/capture",
        max_retries=0,
    )
    client._client.close()
    client._client = httpx.Client(
        base_url="https://topo.example",
        headers={"Authorization": f"Bearer {marker}"},
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    )
    try:
        with pytest.raises(ApiFailure, match="redirect was not accepted"):
            client.health()
    finally:
        client.close()
    assert len(requests) == 1
    assert requests[0].url.host == "topo.example"


def test_cli_rejects_known_insecure_keyring_and_preserves_env_precedence(
    monkeypatch,
):
    class NullKeyring:
        pass

    NullKeyring.__module__ = "keyring.backends.null"
    monkeypatch.setattr("topo_cli.config.keyring.get_keyring", lambda: NullKeyring())
    with pytest.raises(FileOperationFailure, match="not suitable"):
        store_profile_token("test", "topo_api_" + "SYNTHETIC_KEYRING_1234567890")

    monkeypatch.setenv("TOPO_TEST_TOKEN", "environment-token")
    profile = Profile(token_env="TOPO_TEST_TOKEN")
    assert profile_token(profile, "test") == "environment-token"


def test_agent_enrollment_token_is_metadata_only_without_explicit_stdout(
    monkeypatch,
):
    marker = "topo_enroll_" + "SYNTHETIC_CLI_ISSUANCE_1234567890"

    class FakeClient:
        def close(self):
            return None

        def create_agent_enrollment_token(self, **kwargs):
            return {
                "enrollment_token_id": "agent-enrollment-token:test",
                "enrollment_token": marker,
                "token_hint": "safehint",
                "label": kwargs["label"],
                "max_uses": kwargs["max_uses"],
                "expires_at": "2026-09-03T00:00:00+00:00",
                "created_at": "2026-09-02T00:00:00+00:00",
            }

    profile = Profile(api_url="https://topo.example")
    config = TopoConfig(active_profile="test", profiles={"test": profile})
    monkeypatch.setattr(main_module, "load_config", lambda: config)
    monkeypatch.setattr(
        main_module, "resolve_profile", lambda config, selected: ("test", profile)
    )
    monkeypatch.setattr(main_module, "profile_token", lambda *args: "stored-token")
    monkeypatch.setattr(main_module, "TopoClient", lambda **kwargs: FakeClient())

    runner = CliRunner()
    default = runner.invoke(main_module.app, ["agents", "create-token"])
    explicit = runner.invoke(
        main_module.app,
        ["agents", "create-token", "--output-token-stdout"],
    )
    assert default.exit_code == 0
    assert marker not in default.output
    assert "safehint" in default.output
    assert explicit.exit_code == 0
    assert explicit.output.count(marker) == 1
