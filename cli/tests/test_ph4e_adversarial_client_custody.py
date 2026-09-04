"""PH-4E hostile CLI credential-boundary acceptance."""

from __future__ import annotations

import json

import httpx
import pytest

from topo_cli.client import TopoClient
from topo_cli.config import Profile, TopoConfig, save_config, store_profile_token
from topo_cli.errors import ApiFailure, FileOperationFailure


def _marker(prefix: str) -> str:
    import secrets

    return f"{prefix}_{secrets.token_hex(18)}"


def test_profile_file_never_contains_bearer_and_insecure_keyring_fails_closed(
    monkeypatch, tmp_path
):
    marker = _marker("CLI_BEARER")
    path = tmp_path / "config.json"
    monkeypatch.setenv("TOPO_CONFIG_FILE", str(path))
    save_config(
        TopoConfig(
            active_profile="ph4e",
            profiles={"ph4e": Profile(api_url="https://topo.example")},
        )
    )
    assert marker not in path.read_text(encoding="utf-8")
    assert "token" not in json.loads(path.read_text(encoding="utf-8"))["profiles"]["ph4e"]

    class PlaintextKeyring:
        pass

    PlaintextKeyring.__module__ = "keyring.backends.plaintext"
    monkeypatch.setattr("topo_cli.config.keyring.get_keyring", lambda: PlaintextKeyring())
    with pytest.raises(FileOperationFailure, match="not suitable") as caught:
        store_profile_token("ph4e", marker)
    assert marker not in str(caught.value)


def test_redirect_and_remote_error_never_release_cli_bearer():
    marker = _marker("CLI_REDIRECT_BEARER")
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            307,
            headers={"location": f"https://foreign.example/collect?token={marker}"},
            request=request,
        )

    client = TopoClient(
        api_url="https://topo.example",
        token=marker,
        timeout=1,
        verify_tls=True,
        snapshot_capture_path="/api/v1/snapshots/capture",
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
        with pytest.raises(ApiFailure) as caught:
            client.health()
        assert marker not in str(caught.value)
        assert marker not in repr(client)
    finally:
        client.close()
    assert len(requests) == 1
    assert requests[0].url.host == "topo.example"

