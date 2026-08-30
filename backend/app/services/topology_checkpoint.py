from __future__ import annotations
from app.repositories.tenant_scope import (
    DomainTenant,
    tenant_predicate,
)

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SnapshotRecord
from app.models.change_events import (
    ChangeEventCreate,
    ChangeEventKind,
    ChangeEventSource,
)
from app.models.lifecycle_automation import (
    TopologyCheckpointReason,
    TopologyCheckpointResult,
)
from app.models.topology import GraphSnapshot
from app.repositories.change_repository import (
    save_changes,
)
from app.repositories.snapshot_repository import (
    load_snapshot,
    save_snapshot,
)
from app.services.change_event_bridge import (
    promote_normalized_changes,
)
from app.services.change_normalizer import (
    normalize_snapshot_changes,
)
from app.services.temporal_semantics import (
    safe_snapshot_record_at_or_before,
)

CHECKPOINT_DEBOUNCE_SECONDS = max(
    int(
        os.getenv(
            "TOPO_CHECKPOINT_DEBOUNCE_SECONDS",
            "30",
        )
    ),
    0,
)


TOPOLOGY_EVENT_SOURCES = {
    ChangeEventSource.KUBERNETES,
    ChangeEventSource.TERRAFORM,
    ChangeEventSource.AWS_CLOUDTRAIL,
    ChangeEventSource.AZURE_ACTIVITY_LOG,
    ChangeEventSource.GCP_AUDIT_LOG,
}


TOPOLOGY_EVENT_KINDS = {
    ChangeEventKind.DEPLOYMENT,
    ChangeEventKind.ROLLOUT,
    ChangeEventKind.CONFIGURATION,
    ChangeEventKind.INFRASTRUCTURE,
    ChangeEventKind.SCALING,
    ChangeEventKind.TOPOLOGY,
}


def is_topology_affecting_change_event(
    event: ChangeEventCreate,
) -> bool:
    """
    Keep source-code/pipeline observations separate
    from evidence that can alter the runtime graph.
    """

    return (
        event.source in TOPOLOGY_EVENT_SOURCES
        and event.kind in TOPOLOGY_EVENT_KINDS
    )


def _canonical_entity(entity) -> dict[str, Any]:
    return entity.model_dump(
        mode="json",
        exclude={"observed_at", "temporal"},
    )


def _canonical_relationship(
    relationship,
) -> dict[str, Any]:
    return relationship.model_dump(
        mode="json",
        exclude={
            "observed_at",
            "evidence_ids",
            "temporal",
        },
    )


def topology_state_digest(
    snapshot: GraphSnapshot,
) -> str:
    """
    Hash material graph state, not collection time,
    submission IDs, evidence IDs, or collector noise.
    """

    payload = {
        "schema_version": snapshot.schema_version,
        "scope": {
            key: value
            for key, value in snapshot.scope.items()
            if key != "agent_id"
        },
        "entities": sorted(
            (
                _canonical_entity(entity)
                for entity in snapshot.entities
            ),
            key=lambda item: item["id"],
        ),
        "relationships": sorted(
            (
                _canonical_relationship(relationship)
                for relationship in snapshot.relationships
            ),
            key=lambda item: item["id"],
        ),
    }

    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def latest_checkpoint_record(
    session: Session,
    *,
    cluster_name: str | None,
    namespace: str | None = None,
    tenant_id: DomainTenant,
) -> SnapshotRecord | None:
    statement = select(SnapshotRecord).where(
        tenant_predicate(SnapshotRecord, tenant_id)
    )

    if cluster_name:
        statement = statement.where(
            SnapshotRecord.cluster_name
            == cluster_name
        )

    if namespace is not None:
        statement = statement.where(
            SnapshotRecord.namespace
            == namespace
        )

    statement = (
        statement.order_by(
            SnapshotRecord.collected_at.desc()
        )
        .limit(1)
    )

    return session.scalar(statement)


def latest_checkpoint_at_or_before(
    session: Session,
    *,
    cluster_name: str,
    observed_at: str,
    namespace: str | None = None,
    tenant_id: DomainTenant,
) -> GraphSnapshot | None:
    record = safe_snapshot_record_at_or_before(
        session,
        cluster_name=cluster_name,
        namespace=namespace,
        boundary_at=observed_at,
        tenant_id=tenant_id,
    )

    if record is None:
        return None

    return GraphSnapshot.model_validate_json(
        record.payload_json
    )


def checkpoint_metadata(
    snapshot: GraphSnapshot,
) -> dict[str, Any]:
    checkpoint = snapshot.metadata.get(
        "topology_checkpoint",
        {},
    )

    return (
        checkpoint
        if isinstance(checkpoint, dict)
        else {}
    )


def persist_topology_checkpoint(
    session: Session,
    *,
    snapshot: GraphSnapshot,
    reason: TopologyCheckpointReason,
    trigger_event_ids: list[str] | None = None,
    trigger_signal_ids: list[str] | None = None,
    trigger_signal_observations: dict[str, str] | None = None,
    agent_id: str | None = None,
    derive_changes: bool = True,
    force: bool = False,
    tenant_id: DomainTenant,
) -> TopologyCheckpointResult:
    trigger_ids = list(
        dict.fromkeys(trigger_event_ids or [])
    )
    signal_ids = list(
        dict.fromkeys(trigger_signal_ids or [])
    )
    signal_observations = {
        str(key): str(value)
        for key, value in (
            trigger_signal_observations or {}
        ).items()
        if str(key) in signal_ids
    }
    digest = topology_state_digest(snapshot)
    existing_submission = load_snapshot(
        session,
        snapshot.snapshot_id,
        tenant_id=tenant_id,
    )

    if existing_submission is not None:
        existing_metadata = checkpoint_metadata(
            existing_submission
        )

        return TopologyCheckpointResult(
            snapshot_id=snapshot.snapshot_id,
            previous_snapshot_id=(
                existing_metadata.get(
                    "previous_snapshot_id"
                )
            ),
            reason=reason,
            created=False,
            reused=True,
            state_digest=(
                existing_metadata.get("state_digest")
                or topology_state_digest(
                    existing_submission
                )
            ),
            detected_change_count=0,
            trigger_event_ids=trigger_ids,
            trigger_signal_ids=signal_ids,
        )
    cluster_name = snapshot.scope.get("cluster")
    namespace = snapshot.scope.get("namespace")

    previous_record = latest_checkpoint_record(
        session,
        cluster_name=cluster_name,
        namespace=namespace,
        tenant_id=tenant_id,
    )
    previous = (
        load_snapshot(
            session,
            previous_record.snapshot_id,
            tenant_id=tenant_id,
        )
        if previous_record is not None
        else None
    )
    previous_digest = (
        checkpoint_metadata(previous).get(
            "state_digest"
        )
        if previous is not None
        else None
    )

    if previous is not None and not previous_digest:
        previous_digest = topology_state_digest(
            previous
        )

    boundary_requires_new = False

    if (
        reason == TopologyCheckpointReason.INCIDENT_BOUNDARY
        and signal_ids
        and previous is not None
    ):
        previous_trigger_ids = set(
            checkpoint_metadata(previous).get(
                "trigger_signal_ids",
                [],
            )
        )
        already_associated = bool(
            previous_trigger_ids.intersection(
                signal_ids
            )
        )
        observed_times = []

        for value in signal_observations.values():
            try:
                observed = datetime.fromisoformat(
                    value.replace("Z", "+00:00")
                )

                if observed.tzinfo is None:
                    observed = observed.replace(
                        tzinfo=timezone.utc
                    )

                observed_times.append(observed)

            except ValueError:
                continue

        boundary_is_pre_observation = bool(
            observed_times
            and previous.collected_at
            <= min(observed_times)
        )
        boundary_requires_new = not (
            already_associated
            or boundary_is_pre_observation
        )

    if (
        not force
        and not boundary_requires_new
        and previous_record is not None
        and previous_digest == digest
        and previous is not None
        and snapshot.collected_at
        >= previous.collected_at
    ):
        return TopologyCheckpointResult(
            snapshot_id=(
                previous_record.snapshot_id
            ),
            previous_snapshot_id=(
                previous_record.snapshot_id
            ),
            reason=reason,
            created=False,
            reused=True,
            debounced=(
                reason
                == TopologyCheckpointReason
                .AUTOMATIC_CHANGE
            ),
            state_digest=digest,
            detected_change_count=0,
            trigger_event_ids=trigger_ids,
            trigger_signal_ids=signal_ids,
        )

    metadata = dict(snapshot.metadata)
    metadata["topology_checkpoint"] = {
        "reason": reason.value,
        "automatic": reason
        != TopologyCheckpointReason.MANUAL,
        "state_digest": digest,
        "previous_snapshot_id": (
            previous_record.snapshot_id
            if previous_record is not None
            else None
        ),
        "trigger_event_ids": trigger_ids,
        "trigger_signal_ids": signal_ids,
        "trigger_signal_observations": (
            signal_observations
        ),
        "agent_id": agent_id,
        "debounce_window_seconds": (
            CHECKPOINT_DEBOUNCE_SECONDS
        ),
    }
    checkpoint = snapshot.model_copy(
        update={"metadata": metadata}
    )

    save_snapshot(
        session=session,
        snapshot=checkpoint,
        tenant_id=tenant_id,
    )

    detected_change_count = 0

    if derive_changes and previous is not None:
        changes = normalize_snapshot_changes(
            before=previous,
            after=checkpoint,
        )
        detected_change_count = len(changes)

        if changes:
            save_changes(
                session=session,
                changes=changes,
                tenant_id=tenant_id,
            )
            promote_normalized_changes(
                session,
                changes=changes,
                agent_id=agent_id,
                tenant_id=tenant_id,
            )

    return TopologyCheckpointResult(
        snapshot_id=checkpoint.snapshot_id,
        previous_snapshot_id=(
            previous_record.snapshot_id
            if previous_record is not None
            else None
        ),
        reason=reason,
        created=True,
        reused=False,
        state_digest=digest,
        detected_change_count=(
            detected_change_count
        ),
        trigger_event_ids=trigger_ids,
        trigger_signal_ids=signal_ids,
    )
