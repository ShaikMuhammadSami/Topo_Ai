from __future__ import annotations

from pathlib import Path
import secrets
import pytest

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
        observed["tenant"] = request.get_header("X-topo-tenant-id")
        return _Response()

    monkeypatch.setattr("evaluation.topo_client.urllib.request.urlopen", open_request)
    client = TopoClient("http://127.0.0.1:8000", bearer_token=raw_secret)
    client.set_tenant("tenant:eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")

    response = client.get("/api/v1/system/whoami")

    assert response.status == 200
    assert observed["authorization"] == f"Bearer {raw_secret}"
    assert observed["tenant"] == "tenant:eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
    assert raw_secret not in repr(response)


def test_evaluation_runner_has_no_development_auth_bypass() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "runner.py"
    ).read_text(encoding="utf-8")

    assert '"TOPO_AUTH_MODE": "required"' in source
    assert "development-disabled" not in source
    assert "TOPO_AUTH_ENABLED=false" not in source


def test_disposable_evaluation_bootstraps_real_tenant_and_membership(tmp_path, monkeypatch) -> None:
    """Real local backend only: no agent, Kubernetes, or provider is started."""
    from evaluation.runner import ManagedTopoEnvironment, REPOSITORY_ROOT

    python = REPOSITORY_ROOT / "backend/.venv/Scripts/python.exe"
    if not python.is_file():
        pytest.skip("the managed Windows evaluation backend venv is required")
    runtime_root = tmp_path / "evaluation-runtime"
    runtime_root.mkdir()
    monkeypatch.setattr("evaluation.runner.tempfile.mkdtemp", lambda **_: str(runtime_root))
    environment = ManagedTopoEnvironment("no-infrastructure-test", None, 10)
    try:
        environment.start_backend()
        identity = environment.client.get("/api/v1/system/whoami")
        assert identity.status == 200
        assert identity.body["authentication_type"] == "human_api_token"
        tenants = environment.client.get("/api/v1/tenants")
        assert tenants.status == 200 and len(tenants.body) == 1
        context = environment.client.get("/api/v1/tenant-context")
        assert context.status == 200
        assert context.body["tenant_id"] == tenants.body[0]["tenant_id"]
        incidents = environment.client.get("/api/v1/incident-records")
        assert incidents.status == 200 and incidents.body == []
        environment.client.set_tenant(None)
        missing = environment.client.get("/api/v1/incident-records")
        assert missing.status == 400
        assert missing.body == {"detail": "TENANT_CONTEXT_REQUIRED"}
        assert environment.agent is None
    finally:
        assert environment.root.resolve() == runtime_root.resolve()
        assert runtime_root.resolve().is_relative_to(tmp_path.resolve())
        environment.close()
