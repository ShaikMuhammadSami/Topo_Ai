from __future__ import annotations

from types import SimpleNamespace

from topo_agent.change_watch import (
    ChangeWatchRunner,
)
from topo_agent.change_watch_kubernetes import (
    CHANGE_REASONS,
    KubernetesChangePoller,
)
from topo_agent.config import AgentConfig
from topo_agent.runner import AgentRunner


class _Client:
    def __init__(self) -> None:
        self.snapshots = []
        self.failure_batches = []

    def submit_snapshot(self, payload):
        self.snapshots.append(payload)
        return {"snapshot_id": "snapshot:one"}

    def submit_change_events(self, events):
        return {
            "received_count": len(events),
            "event_ids": ["event:one"],
            "checkpoint_requested": True,
            "checkpoint_reason": (
                "automatic_change"
            ),
        }

    def submit_failure_signals(self, signals):
        self.failure_batches.append(signals)
        return {
            "received_count": len(signals),
        }

    def close(self) -> None:
        return None


class _Manager:
    def collect(self):
        return {
            "submission_id": "submission:one",
            "collected_at": (
                "2026-08-17T10:00:00+00:00"
            ),
            "cluster_name": "production",
            "environment": "production",
            "namespace_scope": [],
            "collector_version": "1.0",
            "inventory": {},
            "metadata": {
                "collection_status": "success"
            },
        }

    def plugin_names(self):
        return ["kubernetes"]

    def capabilities(self):
        return []

    def status_snapshot(self):
        return []

    def close(self) -> None:
        return None


class _Buffer:
    def size(self):
        return 0


class _DeferredWatch:
    def __init__(self) -> None:
        self.acknowledged = []

    def run_once(self):
        return {
            "kubernetes": {
                "status": "success",
                "event_ids": [],
                "checkpoint_requested": False,
                "failure_signals": [
                    {
                        "signal_id": "signal:failure",
                        "first_observed_at": (
                            "2026-08-17T10:00:00+00:00"
                        ),
                        "topology_snapshot_id": None,
                    }
                ],
            }
        }

    def ack_failure_signals(self, signals):
        self.acknowledged.extend(signals)


def test_agent_collection_marks_automatic_checkpoint_reason(
) -> None:
    client = _Client()
    runner = AgentRunner(
        config=AgentConfig(),
        client=client,
        plugin_manager=_Manager(),
        buffer=_Buffer(),
    )

    runner.collect_once(
        checkpoint_reason="automatic_change",
        trigger_event_ids=[
            "event:one",
            "event:one",
        ],
    )

    metadata = client.snapshots[0][
        "metadata"
    ]
    assert metadata["checkpoint_reason"] == (
        "automatic_change"
    )
    assert metadata["trigger_event_ids"] == [
        "event:one"
    ]


def test_change_watch_surfaces_checkpoint_request(
) -> None:
    runner = ChangeWatchRunner(
        client=_Client(),
        interval_seconds=30,
    )
    runner.register(
        "kubernetes",
        SimpleNamespace(
            poll=lambda: [
                {"kind": "topology"}
            ]
        ),
    )

    result = runner.run_once()["kubernetes"]

    assert result["checkpoint_requested"] is True
    assert result["event_ids"] == ["event:one"]


def test_failure_events_are_not_change_events(
) -> None:
    assert "CrashLoopBackOff" not in CHANGE_REASONS
    assert "ImagePullBackOff" not in CHANGE_REASONS
    assert "Failed" not in CHANGE_REASONS


def test_failure_watch_uses_separate_signal_contract(
) -> None:
    client = _Client()
    runner = ChangeWatchRunner(
        client=client,
        interval_seconds=30,
    )
    runner.register(
        "kubernetes",
        SimpleNamespace(
            poll=lambda: [],
            drain_failure_signals=lambda: [
                {"signal_id": "signal:failure"}
            ],
        ),
    )

    result = runner.run_once()["kubernetes"]

    assert result["observed"] == 0
    assert result["failure_observed"] == 1
    assert result["failure_submitted"] == 1
    assert client.failure_batches == [
        [{"signal_id": "signal:failure"}]
    ]


def test_normal_agent_path_pins_failure_without_manual_capture(
) -> None:
    client = _Client()
    watch = _DeferredWatch()
    runner = AgentRunner(
        config=AgentConfig(),
        client=client,
        plugin_manager=_Manager(),
        buffer=_Buffer(),
        change_watch_runner=watch,
    )

    result = runner.process_change_watch_once()

    assert result == {
        "checkpoint_requested": False,
        "failure_signal_count": 1,
        "snapshot_id": "snapshot:one",
    }
    snapshot_metadata = client.snapshots[0][
        "metadata"
    ]
    assert snapshot_metadata["checkpoint_reason"] == (
        "incident_boundary"
    )
    assert snapshot_metadata["trigger_signal_ids"] == [
        "signal:failure"
    ]
    assert snapshot_metadata[
        "trigger_signal_observations"
    ] == {
        "signal:failure": (
            "2026-08-17T10:00:00+00:00"
        )
    }
    submitted = client.failure_batches[0][0]
    assert submitted["topology_snapshot_id"] == (
        "snapshot:one"
    )
    assert watch.acknowledged == [submitted]


def test_failure_takes_incident_boundary_priority_over_change(
) -> None:
    client = _Client()

    class _MixedWatch(_DeferredWatch):
        def run_once(self):
            result = super().run_once()
            result["kubernetes"][
                "checkpoint_requested"
            ] = True
            result["kubernetes"]["event_ids"] = [
                "event:rollout"
            ]
            return result

    runner = AgentRunner(
        config=AgentConfig(),
        client=client,
        plugin_manager=_Manager(),
        buffer=_Buffer(),
        change_watch_runner=_MixedWatch(),
    )

    runner.process_change_watch_once()

    metadata = client.snapshots[0]["metadata"]
    assert metadata["checkpoint_reason"] == (
        "incident_boundary"
    )
    assert metadata["trigger_event_ids"] == [
        "event:rollout"
    ]
    assert metadata["trigger_signal_ids"] == [
        "signal:failure"
    ]


def test_kubernetes_watch_obeys_discovery_namespace_scope(
    monkeypatch,
) -> None:
    calls: list[str] = []

    class _Api:
        def list_namespaced_event(self, namespace):
            calls.append(namespace)
            return SimpleNamespace(items=[])

        def list_event_for_all_namespaces(self):
            raise AssertionError(
                "cluster-wide watch must not be used"
            )

    monkeypatch.setattr(
        "topo_agent.change_watch_kubernetes."
        "config.load_incluster_config",
        lambda: None,
    )
    monkeypatch.setattr(
        "topo_agent.change_watch_kubernetes."
        "client.CoreV1Api",
        lambda: _Api(),
    )
    poller = KubernetesChangePoller(
        cluster_name="production",
        namespaces=["payments", "checkout"],
    )

    assert poller.poll() == []
    assert calls == ["checkout", "payments"]
