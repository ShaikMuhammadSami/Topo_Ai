from __future__ import annotations

import httpx
import pytest

from topo_cli.client import TopoClient
from topo_cli.errors import (
    AuthenticationFailure,
    AuthorizationFailure,
    ExitCode,
    ApiFailure,
)


def test_client_preserves_required_mode_bearer_transport() -> None:
    token = "ph2b-cli-test-bearer-" + ("c" * 32)
    client = TopoClient(
        api_url="https://topo.example",
        token=token,
        timeout=5.0,
        verify_tls=True,
        snapshot_capture_path="/api/v1/snapshots/capture",
    )

    try:
        assert client._client.headers["Authorization"] == f"Bearer {token}"
    finally:
        client.close()


def test_client_distinguishes_unauthenticated_from_forbidden() -> None:
    client = TopoClient(
        api_url="https://topo.example",
        token=None,
        timeout=5.0,
        verify_tls=True,
        snapshot_capture_path="/api/v1/snapshots/capture",
    )
    request = httpx.Request("GET", "https://topo.example/api/v1/system/whoami")
    try:
        with pytest.raises(AuthenticationFailure) as unauthenticated:
            client._raise_for_status(httpx.Response(401, request=request))
        with pytest.raises(AuthorizationFailure) as forbidden:
            client._raise_for_status(httpx.Response(403, request=request))
    finally:
        client.close()

    assert unauthenticated.value.exit_code == ExitCode.AUTHENTICATION
    assert forbidden.value.exit_code == ExitCode.AUTHORIZATION


def test_tenant_header_and_missing_context_guidance() -> None:
    with TopoClient(
        api_url="https://topo.example", token=None,
        tenant_id="tenant:11111111-1111-4111-8111-111111111111",
        timeout=5, verify_tls=True, snapshot_capture_path="/api/v1/snapshots/capture",
    ) as client:
        assert client._client.headers["X-Topo-Tenant-ID"] == "tenant:11111111-1111-4111-8111-111111111111"
        with pytest.raises(ApiFailure, match="--tenant"):
            client._raise_for_status(httpx.Response(400, json={"detail": "TENANT_CONTEXT_REQUIRED"}))
        with pytest.raises(AuthorizationFailure):
            client._raise_for_status(httpx.Response(403, json={"detail": "TENANT_ACCESS_DENIED"}))


def test_service_client_does_not_invent_a_tenant_selection() -> None:
    with TopoClient(
        api_url="https://topo.example", token="opaque-service-credential",
        timeout=5, verify_tls=True, snapshot_capture_path="/api/v1/snapshots/capture",
    ) as client:
        assert "X-Topo-Tenant-ID" not in client._client.headers


def test_cli_explicit_tenant_overrides_nonsecret_profile(monkeypatch):
    from typer.testing import CliRunner
    from topo_cli import main
    from topo_cli.config import Profile, TopoConfig

    observed = []
    class Client:
        def __init__(self, **kwargs):
            observed.append(kwargs["tenant_id"])
        def close(self):
            pass

    monkeypatch.setattr(main, "load_config", lambda: TopoConfig(profiles={"local": Profile(tenant_id="tenant:profile")}))
    monkeypatch.setattr(main, "profile_token", lambda *_: None)
    monkeypatch.setattr(main, "TopoClient", Client)
    runner = CliRunner()
    assert runner.invoke(main.app, ["--tenant", "tenant:explicit", "version"]).exit_code == 0
    assert runner.invoke(main.app, ["version"]).exit_code == 0
    assert observed == ["tenant:explicit", "tenant:profile"]
