from __future__ import annotations

from topo_cli.client import TopoClient


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
