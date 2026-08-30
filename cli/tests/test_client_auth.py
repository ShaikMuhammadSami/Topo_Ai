from __future__ import annotations

import httpx
import pytest

from topo_cli.client import TopoClient
from topo_cli.errors import (
    AuthenticationFailure,
    AuthorizationFailure,
    ExitCode,
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
