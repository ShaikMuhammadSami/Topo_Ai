from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.changes import (
    ChangeCategory,
    ChangeImportance,
    NormalizedChange,
)
from app.models.change_events import (
    ChangeEventCreate,
    ChangeEventEntityReference,
    ChangeEventKind,
    ChangeEventSource,
)
from app.repositories.change_event_repository import (
    ingest_change_event,
)
from app.models.temporal import TimeOrigin, TimeQuality


CATEGORY_TO_KIND = {
    ChangeCategory.DEPLOYMENT:
        ChangeEventKind.DEPLOYMENT,

    ChangeCategory.SCALING:
        ChangeEventKind.SCALING,

    ChangeCategory.IMAGE:
        ChangeEventKind.DEPLOYMENT,

    ChangeCategory.CONFIGURATION:
        ChangeEventKind.CONFIGURATION,

    ChangeCategory.RUNTIME:
        ChangeEventKind.TOPOLOGY,

    ChangeCategory.SERVICE:
        ChangeEventKind.CONFIGURATION,

    ChangeCategory.NETWORKING:
        ChangeEventKind.INFRASTRUCTURE,

    ChangeCategory.TOPOLOGY:
        ChangeEventKind.TOPOLOGY,

    ChangeCategory.OTHER:
        ChangeEventKind.UNKNOWN,
}


IMPORTANCE_TO_RISK = {
    ChangeImportance.LOW: 20,
    ChangeImportance.MEDIUM: 50,
    ChangeImportance.HIGH: 80,
}

def _event_kind(
    change: NormalizedChange,
) -> ChangeEventKind:
    mapped = CATEGORY_TO_KIND.get(
        change.category,
        ChangeEventKind.UNKNOWN,
    )

    if mapped != ChangeEventKind.UNKNOWN:
        return mapped

    entity_kind = (
        change.entity_kind
        or ""
    ).lower()

    # Cloud control-plane resources.
    if entity_kind.startswith(
        (
            "aws",
            "azure",
            "gcp",
        )
    ):
        return (
            ChangeEventKind
            .INFRASTRUCTURE
        )

    # Kubernetes structural resources
    # that the original normalizer may
    # classify as OTHER.
    if entity_kind in {
        "kubernetesnode",
        "kubernetesnamespace",
        "kubernetesendpointslice",
        "kubernetescluster",
    }:
        return (
            ChangeEventKind.TOPOLOGY
        )

    return ChangeEventKind.UNKNOWN


def normalized_change_to_event(
    change: NormalizedChange,
) -> ChangeEventCreate:
    refs: list[
        ChangeEventEntityReference
    ] = []

    added_ids: set[str] = set()

    if change.entity_id:
        refs.append(
            ChangeEventEntityReference(
                entity_id=change.entity_id,
                kind=change.entity_kind,
                name=change.entity_name,
                namespace=(
                    change.namespace
                ),
                cluster_name=(
                    change.cluster_name
                ),
            )
        )

        added_ids.add(
            change.entity_id
        )

    for entity_id in (
        change.related_entity_ids
    ):
        if (
            not entity_id
            or entity_id in added_ids
        ):
            continue

        refs.append(
            ChangeEventEntityReference(
                entity_id=entity_id,
                namespace=(
                    change.namespace
                ),
                cluster_name=(
                    change.cluster_name
                ),
            )
        )

        added_ids.add(entity_id)

    return ChangeEventCreate(
        source=(
            ChangeEventSource
            .TOPOLOGY_DIFF
        ),

        kind=_event_kind(change),

        # Existing change ID becomes the
        # external idempotency key.
        external_id=(
            change.change_id
        ),

        origin_change_id=(
            change.change_id
        ),

        title=change.title,

        summary=change.summary,

        actor="topo",

        occurred_at=(
            change.detected_at
            .isoformat()
        ),

        cluster_name=(
            change.cluster_name
        ),

        namespace=change.namespace,

        risk_score=(
            IMPORTANCE_TO_RISK[
                change.importance
            ]
        ),

        entity_refs=refs,

        metadata={
            "normalized_fingerprint":
                change.fingerprint,

            "change_type":
                change.change_type.value,

            "category":
                change.category.value,

            "importance":
                change.importance.value,

            "source_system":
                change.source_system,

            "from_snapshot_id":
                change.from_snapshot_id,

            "to_snapshot_id":
                change.to_snapshot_id,

            "relationship_id":
                change.relationship_id,

            "relationship_type":
                change.relationship_type,

            "source_entity_id":
                change.source_entity_id,

            "target_entity_id":
                change.target_entity_id,

            "changed_fields":
                change.changed_fields,

            "before":
                change.before,

            "after":
                change.after,

            "related_entity_ids":
                change.related_entity_ids,
        },

        raw_payload={},
    )


def promote_normalized_changes(
    session: Session,
    *,
    changes: list[
        NormalizedChange
    ],
    agent_id: str | None = None,
) -> dict[str, int]:
    created = 0
    duplicates = 0

    for change in changes:
        event = (
            normalized_change_to_event(
                change
            )
        )

        receipt = ingest_change_event(
            session,
            request=event,
            agent_id=agent_id,

            # Correlate against the
            # exact "after" snapshot.
            correlation_snapshot_id=(
                change.to_snapshot_id
            ),

            auto_correlate=True,

            source_time_trusted=True,
            observed_at=change.detected_at.isoformat(),
            source_time_origin=TimeOrigin.DERIVED,
            source_time_quality=TimeQuality.BOUNDED,

            commit=False,
        )

        if receipt.duplicate:
            duplicates += 1

        else:
            created += 1

    session.commit()

    return {
        "created": created,
        "duplicates": duplicates,
    }
