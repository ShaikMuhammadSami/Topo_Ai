from __future__ import annotations

from hashlib import sha256
from typing import Any

from app.models.changes import (
    ChangeCategory,
    ChangeImportance,
    ChangeType,
    NormalizedChange,
)
from app.models.topology import (
    Entity,
    GraphSnapshot,
    Relationship,
)
from app.services.snapshot_diff import (
    compare_snapshots,
)


def _deep_changes(
    before: Any,
    after: Any,
    prefix: str = "",
) -> dict[str, dict[str, Any]]:
    if before == after:
        return {}

    if (
        isinstance(before, dict)
        and isinstance(after, dict)
    ):
        result: dict[
            str,
            dict[str, Any],
        ] = {}

        for key in sorted(
            set(before) | set(after)
        ):
            child_prefix = (
                f"{prefix}.{key}"
                if prefix
                else str(key)
            )

            result.update(
                _deep_changes(
                    before.get(key),
                    after.get(key),
                    child_prefix,
                )
            )

        return result

    return {
        prefix or "value": {
            "before": before,
            "after": after,
        }
    }


def _entity_data(
    entity: Entity,
) -> dict[str, Any]:
    return entity.model_dump(
        mode="json",
        exclude={
            "id",
            "observed_at",
        },
    )


def _relationship_data(
    relationship: Relationship,
) -> dict[str, Any]:
    return relationship.model_dump(
        mode="json",
        exclude={
            "id",
            "observed_at",
            "evidence_ids",
        },
    )


def _namespace(
    entity: Entity | None,
    snapshot: GraphSnapshot,
) -> str | None:
    if entity:
        value = entity.properties.get(
            "namespace"
        )

        if isinstance(value, str):
            return value

    value = snapshot.scope.get(
        "namespace"
    )

    if value in (None, "*"):
        return None

    return value


def _category_for_entity(
    kind: str,
    changed_fields: dict[
        str,
        dict[str, Any],
    ],
) -> ChangeCategory:
    fields = set(changed_fields)

    if kind == "ContainerImage":
        return ChangeCategory.IMAGE

    if kind == "KubernetesDeployment":
        if any(
            "replicas" in field
            for field in fields
        ):
            return ChangeCategory.SCALING

        if any(
            "containers" in field
            or "image" in field
            for field in fields
        ):
            return ChangeCategory.DEPLOYMENT

        if any(
            "annotations" in field
            or "labels" in field
            or "selector" in field
            for field in fields
        ):
            return (
                ChangeCategory.CONFIGURATION
            )

        return ChangeCategory.DEPLOYMENT

    if kind in {
        "KubernetesReplicaSet",
        "KubernetesPod",
    }:
        return ChangeCategory.RUNTIME

    if kind == "KubernetesService":
        return ChangeCategory.SERVICE

    if kind in {
        "KubernetesIngress",
        "KubernetesNetworkPolicy",
    }:
        return ChangeCategory.NETWORKING

    if kind in {
        "KubernetesNamespace",
        "KubernetesCluster",
    }:
        return ChangeCategory.TOPOLOGY

    return ChangeCategory.OTHER


def _importance_for_entity(
    kind: str,
    change_type: ChangeType,
    category: ChangeCategory,
    changed_fields: dict[
        str,
        dict[str, Any],
    ],
) -> ChangeImportance:
    fields = set(changed_fields)

    if kind == "ContainerImage":
        return ChangeImportance.HIGH

    if (
        kind == "KubernetesDeployment"
        and any(
            "containers" in field
            or "image" in field
            for field in fields
        )
    ):
        return ChangeImportance.HIGH

    if (
        kind == "KubernetesService"
        and any(
            "selector" in field
            or "ports" in field
            for field in fields
        )
    ):
        return ChangeImportance.HIGH

    if category in {
        ChangeCategory.SCALING,
        ChangeCategory.CONFIGURATION,
        ChangeCategory.SERVICE,
    }:
        return ChangeImportance.MEDIUM

    if (
        kind == "KubernetesDeployment"
        and change_type
        in {
            ChangeType.ENTITY_ADDED,
            ChangeType.ENTITY_REMOVED,
        }
    ):
        return ChangeImportance.HIGH

    if kind in {
        "KubernetesPod",
        "KubernetesReplicaSet",
    }:
        return ChangeImportance.LOW

    return ChangeImportance.MEDIUM


def _relationship_category(
    relationship_type: str,
) -> ChangeCategory:
    if relationship_type == "uses":
        return ChangeCategory.IMAGE

    if relationship_type in {
        "selects",
        "routes_to",
        "exposes",
    }:
        return ChangeCategory.SERVICE

    if relationship_type in {
        "owns",
        "runs",
        "contains",
    }:
        return ChangeCategory.TOPOLOGY

    return ChangeCategory.OTHER


def _relationship_importance(
    relationship_type: str,
) -> ChangeImportance:
    if relationship_type == "uses":
        return ChangeImportance.HIGH

    if relationship_type in {
        "selects",
        "routes_to",
    }:
        return ChangeImportance.MEDIUM

    return ChangeImportance.LOW


def _fingerprint(
    cluster_name: str,
    namespace: str | None,
    change_type: ChangeType,
    subject_id: str,
    changed_fields: dict[
        str,
        dict[str, Any],
    ],
) -> str:
    fields = ",".join(
        sorted(changed_fields)
    )

    value = "|".join(
        [
            cluster_name,
            namespace or "",
            change_type.value,
            subject_id,
            fields,
        ]
    )

    return sha256(
        value.encode("utf-8")
    ).hexdigest()


def _change_id(
    from_snapshot_id: str,
    to_snapshot_id: str,
    change_type: ChangeType,
    subject_id: str,
) -> str:
    value = "|".join(
        [
            from_snapshot_id,
            to_snapshot_id,
            change_type.value,
            subject_id,
        ]
    )

    digest = sha256(
        value.encode("utf-8")
    ).hexdigest()[:32]

    return f"change:{digest}"


def _entity_title_and_summary(
    entity: Entity,
    change_type: ChangeType,
    category: ChangeCategory,
    changed_fields: dict[
        str,
        dict[str, Any],
    ],
) -> tuple[str, str]:
    resource = (
        f"{entity.kind}/"
        f"{entity.name}"
    )

    if change_type == (
        ChangeType.ENTITY_ADDED
    ):
        return (
            f"{entity.kind} added",
            f"{resource} appeared in the topology.",
        )

    if change_type == (
        ChangeType.ENTITY_REMOVED
    ):
        return (
            f"{entity.kind} removed",
            f"{resource} disappeared from the topology.",
        )

    replica_change = (
        changed_fields.get(
            "properties.desired_replicas"
        )
    )

    if replica_change:
        return (
            "Deployment scaled",
            (
                f"{resource} desired replicas "
                f"changed from "
                f"{replica_change['before']} "
                f"to "
                f"{replica_change['after']}."
            ),
        )

    if category == (
        ChangeCategory.DEPLOYMENT
    ):
        return (
            "Deployment configuration changed",
            (
                f"{resource} changed fields: "
                f"{', '.join(sorted(changed_fields))}."
            ),
        )

    if category == ChangeCategory.IMAGE:
        return (
            "Container image changed",
            (
                f"{resource} was added, removed "
                "or updated."
            ),
        )

    return (
        f"{entity.kind} updated",
        (
            f"{resource} changed fields: "
            f"{', '.join(sorted(changed_fields))}."
        ),
    )


def normalize_snapshot_changes(
    before: GraphSnapshot,
    after: GraphSnapshot,
) -> list[NormalizedChange]:
    diff = compare_snapshots(
        before=before,
        after=after,
    )

    cluster_name = (
        after.scope.get("cluster")
        or before.scope.get("cluster")
        or "unknown"
    )

    before_entities = {
        entity.id: entity
        for entity in before.entities
    }

    after_entities = {
        entity.id: entity
        for entity in after.entities
    }

    before_relationships = {
        relationship.id: relationship
        for relationship
        in before.relationships
    }

    after_relationships = {
        relationship.id: relationship
        for relationship
        in after.relationships
    }

    changes: list[NormalizedChange] = []

    def add_entity_change(
        entity: Entity,
        change_type: ChangeType,
        before_value: (
            dict[str, Any] | None
        ),
        after_value: (
            dict[str, Any] | None
        ),
    ) -> None:
        changed_fields = (
            _deep_changes(
                before_value or {},
                after_value or {},
            )
            if (
                before_value is not None
                and after_value is not None
            )
            else {}
        )

        category = _category_for_entity(
            kind=entity.kind,
            changed_fields=changed_fields,
        )

        importance = (
            _importance_for_entity(
                kind=entity.kind,
                change_type=change_type,
                category=category,
                changed_fields=changed_fields,
            )
        )

        namespace = _namespace(
            entity=entity,
            snapshot=after,
        )

        title, summary = (
            _entity_title_and_summary(
                entity=entity,
                change_type=change_type,
                category=category,
                changed_fields=(
                    changed_fields
                ),
            )
        )

        changes.append(
            NormalizedChange(
                change_id=_change_id(
                    from_snapshot_id=(
                        before.snapshot_id
                    ),
                    to_snapshot_id=(
                        after.snapshot_id
                    ),
                    change_type=change_type,
                    subject_id=entity.id,
                ),
                fingerprint=_fingerprint(
                    cluster_name=cluster_name,
                    namespace=namespace,
                    change_type=change_type,
                    subject_id=entity.id,
                    changed_fields=(
                        changed_fields
                    ),
                ),
                change_type=change_type,
                category=category,
                importance=importance,
                title=title,
                summary=summary,
                detected_at=(
                    after.collected_at
                ),
                from_snapshot_id=(
                    before.snapshot_id
                ),
                to_snapshot_id=(
                    after.snapshot_id
                ),
                cluster_name=cluster_name,
                namespace=namespace,
                entity_id=entity.id,
                entity_kind=entity.kind,
                entity_name=entity.name,
                changed_fields=(
                    changed_fields
                ),
                before=before_value,
                after=after_value,
                related_entity_ids=[
                    entity.id
                ],
            )
        )

    for entity in diff.added_entities:
        add_entity_change(
            entity=entity,
            change_type=(
                ChangeType.ENTITY_ADDED
            ),
            before_value=None,
            after_value=entity.model_dump(
                mode="json"
            ),
        )

    for entity in diff.removed_entities:
        add_entity_change(
            entity=entity,
            change_type=(
                ChangeType.ENTITY_REMOVED
            ),
            before_value=entity.model_dump(
                mode="json"
            ),
            after_value=None,
        )

    for changed in diff.changed_entities:
        before_entity = (
            before_entities.get(
                changed.entity_id
            )
        )

        after_entity = (
            after_entities.get(
                changed.entity_id
            )
        )

        if (
            before_entity is None
            or after_entity is None
        ):
            continue

        add_entity_change(
            entity=after_entity,
            change_type=(
                ChangeType.ENTITY_UPDATED
            ),
            before_value=_entity_data(
                before_entity
            ),
            after_value=_entity_data(
                after_entity
            ),
        )

    def add_relationship_change(
        relationship: Relationship,
        change_type: ChangeType,
        before_value: (
            dict[str, Any] | None
        ),
        after_value: (
            dict[str, Any] | None
        ),
    ) -> None:
        relationship_type = (
            relationship
            .relationship_type
            .value
        )

        changed_fields = (
            _deep_changes(
                before_value or {},
                after_value or {},
            )
            if (
                before_value is not None
                and after_value is not None
            )
            else {}
        )

        category = (
            _relationship_category(
                relationship_type
            )
        )

        importance = (
            _relationship_importance(
                relationship_type
            )
        )

        source = (
            after_entities.get(
                relationship
                .source_entity_id
            )
            or before_entities.get(
                relationship
                .source_entity_id
            )
        )

        target = (
            after_entities.get(
                relationship
                .target_entity_id
            )
            or before_entities.get(
                relationship
                .target_entity_id
            )
        )

        source_name = (
            f"{source.kind}/{source.name}"
            if source
            else relationship
            .source_entity_id
        )

        target_name = (
            f"{target.kind}/{target.name}"
            if target
            else relationship
            .target_entity_id
        )

        verb = {
            ChangeType.RELATIONSHIP_ADDED:
                "added",
            ChangeType.RELATIONSHIP_REMOVED:
                "removed",
            ChangeType.RELATIONSHIP_UPDATED:
                "updated",
        }[change_type]

        namespace = _namespace(
            entity=source or target,
            snapshot=after,
        )

        changes.append(
            NormalizedChange(
                change_id=_change_id(
                    from_snapshot_id=(
                        before.snapshot_id
                    ),
                    to_snapshot_id=(
                        after.snapshot_id
                    ),
                    change_type=change_type,
                    subject_id=(
                        relationship.id
                    ),
                ),
                fingerprint=_fingerprint(
                    cluster_name=cluster_name,
                    namespace=namespace,
                    change_type=change_type,
                    subject_id=(
                        relationship.id
                    ),
                    changed_fields=(
                        changed_fields
                    ),
                ),
                change_type=change_type,
                category=category,
                importance=importance,
                title=(
                    f"{relationship_type} "
                    f"relationship {verb}"
                ),
                summary=(
                    f"{source_name} "
                    f"{relationship_type} "
                    f"{target_name}: {verb}."
                ),
                detected_at=(
                    after.collected_at
                ),
                from_snapshot_id=(
                    before.snapshot_id
                ),
                to_snapshot_id=(
                    after.snapshot_id
                ),
                cluster_name=cluster_name,
                namespace=namespace,
                relationship_id=(
                    relationship.id
                ),
                relationship_type=(
                    relationship_type
                ),
                source_entity_id=(
                    relationship
                    .source_entity_id
                ),
                target_entity_id=(
                    relationship
                    .target_entity_id
                ),
                changed_fields=(
                    changed_fields
                ),
                before=before_value,
                after=after_value,
                related_entity_ids=[
                    relationship
                    .source_entity_id,
                    relationship
                    .target_entity_id,
                ],
            )
        )

    for relationship in (
        diff.added_relationships
    ):
        add_relationship_change(
            relationship=relationship,
            change_type=(
                ChangeType
                .RELATIONSHIP_ADDED
            ),
            before_value=None,
            after_value=(
                relationship.model_dump(
                    mode="json"
                )
            ),
        )

    for relationship in (
        diff.removed_relationships
    ):
        add_relationship_change(
            relationship=relationship,
            change_type=(
                ChangeType
                .RELATIONSHIP_REMOVED
            ),
            before_value=(
                relationship.model_dump(
                    mode="json"
                )
            ),
            after_value=None,
        )

    for changed in (
        diff.changed_relationships
    ):
        before_relationship = (
            before_relationships.get(
                changed.relationship_id
            )
        )

        after_relationship = (
            after_relationships.get(
                changed.relationship_id
            )
        )

        if (
            before_relationship is None
            or after_relationship is None
        ):
            continue

        add_relationship_change(
            relationship=(
                after_relationship
            ),
            change_type=(
                ChangeType
                .RELATIONSHIP_UPDATED
            ),
            before_value=(
                _relationship_data(
                    before_relationship
                )
            ),
            after_value=(
                _relationship_data(
                    after_relationship
                )
            ),
        )

    return sorted(
        changes,
        key=lambda change: (
            change.importance.value,
            change.category.value,
            change.title,
        ),
    )