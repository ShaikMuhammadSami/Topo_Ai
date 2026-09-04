from __future__ import annotations

import os
import stat
import logging

import httpx
import pytest
from typer.testing import CliRunner

from topo_agent import config
from topo_agent.client import AgentApiClient, AgentClientError
from topo_agent.main import app
from topo_agent.plugin_manager import PluginManager
from topo_agent.security import install_logging_redaction


def test_agent_argv_has_no_raw_token_option(monkeypatch, tmp_path):
    monkeypatch.setenv("TOPO_AGENT_HOME", str(tmp_path))
    result = CliRunner().invoke(app, ["enroll", "--help"])
    assert result.exit_code == 0
    assert "--token-stdin" in result.output
    assert "--token " not in result.output


def test_agent_client_disables_redirects_and_repr_redacts_token():
    marker = "topo_agent_" + "SYNTHETIC_REPR_1234567890"
    client = AgentApiClient(
        backend_url="https://topo.example", token=marker, timeout_seconds=1,
        verify_tls=True, max_retries=0, retry_backoff_seconds=0,
    )
    try:
        assert client.client.follow_redirects is False
        assert marker not in repr(client)
    finally:
        client.close()


def test_agent_backend_url_rejects_credential_components():
    for value in (
        "https://user:pass@topo.example",
        "https://topo.example?token=value",
        "https://topo.example#secret",
    ):
        with pytest.raises(ValueError):
            AgentApiClient(
                backend_url=value, token="value", timeout_seconds=1,
                verify_tls=True, max_retries=0, retry_backoff_seconds=0,
            )


def test_agent_redirect_does_not_forward_bearer_or_enrollment_body():
    bearer = "topo_agent_" + "SYNTHETIC_REDIRECT_1234567890"
    enrollment = "topo_enroll_" + "SYNTHETIC_REDIRECT_1234567890"
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            307,
            headers={"location": "https://foreign.example/collect"},
            request=request,
        )

    client = AgentApiClient(
        backend_url="https://topo.example", token=bearer, timeout_seconds=1,
        verify_tls=True, max_retries=0, retry_backoff_seconds=0,
    )
    client.client.close()
    client.client = httpx.Client(
        base_url="https://topo.example",
        headers={"Authorization": f"Bearer {bearer}"},
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    )
    try:
        with pytest.raises(AgentClientError, match="redirect was not accepted"):
            client.enroll({"enrollment_token": enrollment})
    finally:
        client.close()
    assert len(requests) == 1
    assert requests[0].url.host == "topo.example"


def test_agent_debug_logging_redacts_bearer_and_cloud_sdk_transport(caplog):
    marker = "topo_agent_" + "SYNTHETIC_DEBUG_LOG_1234567890"
    install_logging_redaction()
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("topo_agent.test").debug(
            "Authorization: Bearer %s", marker
        )
    assert marker not in caplog.text
    for name in ("httpx", "httpcore", "urllib3", "botocore", "azure", "google.auth"):
        assert logging.getLogger(name).level >= logging.WARNING


def test_plugin_diagnostics_do_not_persist_provider_exception_text():
    marker = "topo_agent_" + "SYNTHETIC_PROVIDER_EXCEPTION_1234567890"

    class FailingPlugin:
        name = "synthetic-cloud"
        version = "test"
        capabilities = ("cloud",)

        def doctor(self):
            raise RuntimeError(f"Authorization: Bearer {marker}")

        def collect(self):
            raise RuntimeError(f"https://user:{marker}@cloud.example/path?token={marker}")

        def close(self):
            return None

    manager = PluginManager(
        plugins=[FailingPlugin()],
        cluster_name="test",
        environment=None,
        namespace_scope=[],
    )
    assert marker not in repr(manager.diagnostics())
    assert marker not in repr(manager.collect()["metadata"])


def test_secure_agent_credential_round_trip_and_final_permissions(monkeypatch, tmp_path):
    monkeypatch.setenv("TOPO_AGENT_HOME", str(tmp_path))
    marker = "topo_agent_" + "SYNTHETIC_FILE_1234567890"
    config.preflight_agent_token_storage()
    path = config.store_agent_token(marker)
    assert config.load_agent_token() == marker
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    else:
        descriptor = config._windows_security_descriptor(path)
        assert descriptor.startswith("D:P")
        assert ";;;WD)" not in descriptor
        assert ";;;BU)" not in descriptor
        assert ";;;AU)" not in descriptor


def test_secure_agent_credential_rejects_symlink_target(monkeypatch, tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "linked"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation is unavailable for this test identity.")
    monkeypatch.setenv("TOPO_AGENT_HOME", str(link))
    with pytest.raises(OSError):
        config.store_agent_token("topo_agent_" + "SYNTHETIC_LINK_1234567890")
