from __future__ import annotations

import json
from types import SimpleNamespace

from kubernetes.client.exceptions import ApiException
import pytest
from typer.testing import CliRunner

from topo_agent.buffer import SnapshotBuffer
from topo_agent.collector import KubernetesCollector
from topo_agent.config import AgentConfig
from topo_agent.main import app
import topo_agent.main as agent_main
from topo_agent.plugins.kubernetes import KubernetesPlugin
from topo_agent.runner import AgentRunner


def _response() -> SimpleNamespace:
    return SimpleNamespace(items=[])


def _collector_with_replica_set_denied() -> KubernetesCollector:
    collector = object.__new__(KubernetesCollector)
    collector.config = AgentConfig(
        cluster_name="collection-integrity",
        namespaces=["payments"],
    )
    collector.access_mode = "test"
    collector.core = SimpleNamespace(
        list_namespace=lambda: _response(),
        list_node=lambda: _response(),
        list_pod_for_all_namespaces=lambda: _response(),
        list_namespaced_pod=lambda _: _response(),
        list_service_for_all_namespaces=lambda: _response(),
        list_namespaced_service=lambda _: _response(),
    )

    def forbidden(_: str) -> SimpleNamespace:
        raise ApiException(
            status=403,
            reason="Bearer must-not-leak",
        )

    collector.apps = SimpleNamespace(
        list_deployment_for_all_namespaces=lambda: _response(),
        list_namespaced_deployment=lambda _: _response(),
        list_replica_set_for_all_namespaces=lambda: _response(),
        list_namespaced_replica_set=forbidden,
    )
    collector.networking = SimpleNamespace(
        list_ingress_for_all_namespaces=lambda: _response(),
        list_namespaced_ingress=lambda _: _response(),
    )
    collector.discovery = SimpleNamespace(
        list_endpoint_slice_for_all_namespaces=lambda: _response(),
        list_namespaced_endpoint_slice=lambda _: _response(),
    )
    return collector


def _submission(
    status: str,
) -> dict:
    plugin_status = (
        "success"
        if status == "success"
        else "partial"
    )
    plugin = {
        "name": "kubernetes",
        "status": plugin_status,
        "errors": [],
        "inventory_counts": {},
    }
    if status != "success":
        plugin["collection_failures"] = [
            {
                "resource": "replicasets",
                "status_code": 403,
                "category": "authorization",
            }
        ]
    return {
        "submission_id": "submission:test",
        "collected_at": "2026-11-13T10:00:00+00:00",
        "cluster_name": "collection-integrity",
        "environment": "test",
        "namespace_scope": ["payments"],
        "collector_version": "1.0",
        "inventory": {
            "deployments": [],
            "replicasets": [],
        },
        "metadata": {
            "collection_status": status,
            "plugin_count": 1,
            "successful_plugin_count": int(status == "success"),
            "failed_plugin_count": int(status != "success"),
            "plugins": [plugin],
        },
    }


def _zero_plugin_submission() -> dict:
    payload = _submission("success")
    payload["inventory"] = {}
    payload["metadata"].update(
        {
            "plugin_count": 0,
            "successful_plugin_count": 0,
            "failed_plugin_count": 0,
            "plugins": [],
        }
    )
    return payload


class _Client:
    def __init__(self) -> None:
        self.snapshots: list[dict] = []

    def submit_snapshot(self, payload: dict) -> dict:
        self.snapshots.append(payload)
        return {"snapshot_id": "snapshot:accepted"}

    def close(self) -> None:
        return None


class _Manager:
    def __init__(self, submissions: list[dict]) -> None:
        self.submissions = submissions

    def collect(self) -> dict:
        return self.submissions.pop(0)

    def plugin_names(self) -> list[str]:
        return ["kubernetes"]

    def capabilities(self) -> list[str]:
        return []

    def status_snapshot(self) -> list[dict]:
        return self.submissions[:1]

    def close(self) -> None:
        return None


def test_required_replica_set_failure_is_safe_and_partial() -> None:
    collector = _collector_with_replica_set_denied()
    result = collector.collect()

    assert result["metadata"]["resource_completeness"][
        "replicasets"
    ] == "failed"
    assert result["metadata"]["collection_failures"] == [
        {
            "resource": "replicasets",
            "status_code": 403,
            "category": "authorization",
        }
    ]
    assert "must-not-leak" not in repr(result)

    plugin = object.__new__(KubernetesPlugin)
    plugin.collector = collector
    plugin_result = plugin.collect()
    assert plugin_result.status == "partial"
    assert plugin_result.metadata["collection_failures"]


def test_failed_collection_is_not_submitted_or_buffered(tmp_path) -> None:
    client = _Client()
    buffer = SnapshotBuffer(tmp_path, max_items=5)
    runner = AgentRunner(
        config=AgentConfig(),
        client=client,
        plugin_manager=_Manager([_submission("partial")]),
        buffer=buffer,
    )

    assert runner.collect_once() is None
    assert client.snapshots == []
    assert buffer.size() == 0
    assert runner.last_collection_status == "collection_failed"
    assert "replicasets HTTP 403" in str(runner.last_error)


def test_later_collection_recovers_without_replaying_partial_data(
    tmp_path,
) -> None:
    client = _Client()
    manager = _Manager(
        [
            _submission("partial"),
            _submission("success"),
        ]
    )
    runner = AgentRunner(
        config=AgentConfig(),
        client=client,
        plugin_manager=manager,
        buffer=SnapshotBuffer(tmp_path, max_items=5),
    )

    assert runner.collect_once() is None
    assert runner.collect_once() == {
        "snapshot_id": "snapshot:accepted"
    }
    assert len(client.snapshots) == 1
    assert client.snapshots[0]["metadata"][
        "collection_status"
    ] == "success"


def test_incomplete_buffer_entry_cannot_be_replayed(tmp_path) -> None:
    buffer = SnapshotBuffer(tmp_path, max_items=5)
    invalid_path = tmp_path / "legacy-incomplete.json"
    invalid_path.write_text(
        json.dumps(_submission("partial")),
        encoding="utf-8",
    )
    client = _Client()
    runner = AgentRunner(
        config=AgentConfig(),
        client=client,
        plugin_manager=_Manager([]),
        buffer=buffer,
    )

    assert runner.replay_buffer() == 0
    assert client.snapshots == []
    assert invalid_path.exists()


def test_buffer_rejects_incomplete_collection(tmp_path) -> None:
    buffer = SnapshotBuffer(tmp_path, max_items=5)

    try:
        buffer.enqueue(_submission("partial"))
    except ValueError as exc:
        assert "incomplete" in str(exc).lower()
    else:
        raise AssertionError("partial collection entered the buffer")

    assert buffer.size() == 0


def test_zero_plugin_collection_is_never_buffered(tmp_path) -> None:
    buffer = SnapshotBuffer(tmp_path, max_items=5)

    with pytest.raises(
        ValueError,
        match="At least one completed plugin",
    ):
        buffer.enqueue(_zero_plugin_submission())

    assert buffer.size() == 0


def test_success_label_cannot_hide_failed_required_resource(
    tmp_path,
) -> None:
    payload = _submission("success")
    payload["metadata"]["plugins"][0][
        "resource_completeness"
    ] = {
        "deployments": "complete",
        "replicasets": "failed",
    }
    buffer = SnapshotBuffer(tmp_path, max_items=5)

    with pytest.raises(ValueError):
        buffer.enqueue(payload)


def test_shared_buffer_still_accepts_non_topology_payloads(
    tmp_path,
) -> None:
    buffer = SnapshotBuffer(tmp_path, max_items=5)

    path = buffer.enqueue(
        {
            "batch_id": "runtime:one",
            "dependencies": [],
        }
    )

    assert path.exists()


def test_successful_plugin_with_empty_resource_lists_is_accepted(
    tmp_path,
) -> None:
    client = _Client()
    payload = _submission("success")
    runner = AgentRunner(
        config=AgentConfig(),
        client=client,
        plugin_manager=_Manager([payload]),
        buffer=SnapshotBuffer(tmp_path, max_items=5),
    )

    assert runner.collect_once() == {
        "snapshot_id": "snapshot:accepted"
    }
    assert client.snapshots[0]["inventory"] == {
        "deployments": [],
        "replicasets": [],
    }


def test_empty_plugin_configuration_fails_closed(
    monkeypatch,
) -> None:
    with pytest.raises(
        ValueError,
        match="At least one agent plugin",
    ):
        AgentConfig.from_dict(
            {"enabled_plugins": []}
        )

    monkeypatch.setenv(
        "TOPO_ENABLED_PLUGINS",
        "",
    )
    with pytest.raises(
        ValueError,
        match="At least one agent plugin",
    ):
        AgentConfig().apply_environment()


def test_manual_collect_exits_nonzero_without_success_receipt(
    monkeypatch,
    tmp_path,
) -> None:
    client = _Client()
    manager = _Manager([_submission("partial")])
    buffer = SnapshotBuffer(tmp_path, max_items=5)
    monkeypatch.setattr(
        "topo_agent.main._runtime",
        lambda selected_plugins=None: (
            AgentConfig(),
            client,
            manager,
            buffer,
        ),
    )

    result = CliRunner().invoke(app, ["collect"])

    assert result.exit_code == 1
    assert "collection_failed" in result.stdout
    assert "snapshot:accepted" not in result.stdout
    assert client.snapshots == []


def test_manual_collect_with_no_enabled_plugins_exits_nonzero(
    monkeypatch,
) -> None:
    client = _Client()
    monkeypatch.setattr(
        agent_main,
        "load_config",
        lambda: AgentConfig(
            enabled_plugins=[]
        ),
    )
    monkeypatch.setattr(
        agent_main,
        "load_agent_token",
        lambda: "test-agent-token",
    )
    monkeypatch.setattr(
        agent_main,
        "_client",
        lambda config, token: client,
    )

    result = CliRunner().invoke(
        app,
        ["collect"],
    )

    assert result.exit_code != 0
    assert "At least one agent plugin" in result.output
    assert client.snapshots == []
