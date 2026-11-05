from types import SimpleNamespace

from app.models.changes import ChangeType
from app.services.causal_rca import (
    _event_chain_confidence,
    _is_contextual_entity_creation_predecessor,
    _shortest_path,
)


def _candidate(
    *,
    event_id: str,
    occurred_at: str,
    source: str,
    repository: str | None = None,
    commit_sha: str | None = None,
    cluster_name: str | None = None,
    namespace: str | None = None,
    entity_id: str | None = None,
):
    event = SimpleNamespace(
        event_id=event_id,
        occurred_at=occurred_at,
        source=source,
        repository=repository,
        commit_sha=commit_sha,
        release_version=None,
        pipeline_name=None,
        cluster_name=cluster_name,
        namespace=namespace,
        links=[],
    )

    return SimpleNamespace(
        event=event,
        direct_entity_matches=(
            [entity_id]
            if entity_id
            else []
        ),
        neighboring_entity_matches=[],
    )


def test_event_chain_same_commit() -> None:
    earlier = _candidate(
        event_id="event:commit",
        occurred_at=(
            "2026-08-12T10:00:00Z"
        ),
        source="github",
        repository="company/payments",
        commit_sha="abc123",
        cluster_name="prod",
    )

    later = _candidate(
        event_id="event:deploy",
        occurred_at=(
            "2026-08-12T10:05:00Z"
        ),
        source="github_actions",
        repository="company/payments",
        commit_sha="abc123",
        cluster_name="prod",
    )

    confidence, reasons = (
        _event_chain_confidence(
            earlier,
            later,
        )
    )

    assert confidence >= 0.70

    assert "Same commit SHA." in reasons


def test_unproven_topology_creation_does_not_replace_update_root() -> None:
    earlier = _candidate(
        event_id="event:created",
        occurred_at="2026-08-12T10:00:00Z",
        source="topology_diff",
        cluster_name="prod",
        namespace="payments",
        entity_id="deployment:payment",
    )
    later = _candidate(
        event_id="event:updated",
        occurred_at="2026-08-12T10:05:00Z",
        source="topology_diff",
        cluster_name="prod",
        namespace="payments",
        entity_id="deployment:payment",
    )

    assert _is_contextual_entity_creation_predecessor(
        earlier,
        later,
        earlier_change_type=ChangeType.ENTITY_ADDED,
        later_change_type=ChangeType.ENTITY_UPDATED,
    ) is True


def test_immutable_lineage_preserves_creation_predecessor() -> None:
    earlier = _candidate(
        event_id="event:created",
        occurred_at="2026-08-12T10:00:00Z",
        source="topology_diff",
        commit_sha="abc123",
        entity_id="deployment:payment",
    )
    later = _candidate(
        event_id="event:updated",
        occurred_at="2026-08-12T10:05:00Z",
        source="topology_diff",
        commit_sha="abc123",
        entity_id="deployment:payment",
    )

    assert _is_contextual_entity_creation_predecessor(
        earlier,
        later,
        earlier_change_type=ChangeType.ENTITY_ADDED,
        later_change_type=ChangeType.ENTITY_UPDATED,
    ) is False


def test_shortest_topology_path() -> None:
    adjacency = {
        "deployment": [
            ("replicaset", "owns")
        ],
        "replicaset": [
            ("deployment", "owns"),
            ("pod", "owns"),
        ],
        "pod": [
            ("replicaset", "owns")
        ],
    }

    path = _shortest_path(
        adjacency,
        start="deployment",
        targets={
            "pod"
        },
        max_hops=4,
    )

    assert path == [
        "deployment",
        "replicaset",
        "pod",
    ]
