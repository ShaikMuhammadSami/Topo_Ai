from __future__ import annotations

from pathlib import Path
import secrets

from evaluation.topo_client import TopoClient


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def read(self) -> bytes:
        return b"{}"


def test_evaluation_http_client_sends_runtime_bearer(monkeypatch) -> None:
    raw_secret = "topo_api_" + secrets.token_urlsafe(48)
    observed: dict[str, str | None] = {}

    def open_request(request, timeout):
        observed["authorization"] = request.get_header("Authorization")
        return _Response()

    monkeypatch.setattr("evaluation.topo_client.urllib.request.urlopen", open_request)
    client = TopoClient("http://127.0.0.1:8000", bearer_token=raw_secret)

    response = client.get("/api/v1/system/whoami")

    assert response.status == 200
    assert observed["authorization"] == f"Bearer {raw_secret}"
    assert raw_secret not in repr(response)


def test_evaluation_runner_has_no_development_auth_bypass() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "runner.py"
    ).read_text(encoding="utf-8")

    assert '"TOPO_AUTH_MODE": "required"' in source
    assert "development-disabled" not in source
    assert "TOPO_AUTH_ENABLED=false" not in source
