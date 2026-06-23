from __future__ import annotations

from hashlib import sha256
from typing import Any

from app.models.identity import (
    IdentityMatchMethod,
    IdentityMember,
    IdentityOverrideAction,
    IdentityOverrideView,
    IdentityResolutionResult,
    IdentityRole,
    LogicalIdentity,
)
from app.models.topology import (
    Entity,
    GraphSnapshot,
)


ROLE_BY_KIND = {
    "KubernetesDeployment": (
        IdentityRole.DEPLOYMENT
    ),
    "KubernetesReplicaSet": (
        IdentityRole.REPLICA_SET
    ),
    "KubernetesPod": IdentityRole.POD,
    "KubernetesService": (
        IdentityRole.SERVICE
    ),
}


def _value(
    value: Any,
) -> str | None:
    if value is None:
        return None

    result = str(value).strip()

    return result or None


def _entity_namespace(
    entity: Entity,
) -> str | None:
    return _value(
        entity.properties.get("namespace")
    )


def _entity_cluster(
    entity: Entity,
) -> str | None:
    return _value(
        entity.properties.get("cluster")
    )


def _identity_id(
    cluster: str,
    namespace: str,
    canonical_name: str,
) -> str:
    raw_value = (
        f"{cluster}|"
        f"{namespace}|"
        f"{canonical_name}"
    )

    digest = sha256(
        raw_value.encode("utf-8")
    ).hexdigest()[:20]

    return f"identity:kubernetes:{digest}"


def _extract_images(
    entity: Entity,
) -> set[str]:
    images: set[str] = set()

    containers = entity.properties.get(
        "containers"
    )

    if not isinstance(containers, list):
        return images

    for container in containers:
        if not isinstance(container, dict):
            continue

        image = container.get("image")

        if isinstance(image, str) and image:
            images.add(image)

    return images


def _image_alias(
    image: str,
) -> str | None:
    without_digest = image.split(
        "@",
        maxsplit=1,
    )[0]

    final_segment = without_digest.rsplit(
        "/",
        maxsplit=1,
    )[-1]

    without_tag = final_segment.split(
        ":",
        maxsplit=1,
    )[0]

    return without_tag or None


def _refresh_identity_metadata(
    identity: LogicalIdentity,
    entities_by_id: dict[str, Entity],
) -> None:
    images: set[str] = set()
    aliases: set[str] = {
        identity.canonical_name
    }

    for member in identity.members:
        entity = entities_by_id.get(
            member.entity_id
        )

        if entity is None:
            continue

        aliases.add(entity.name)
        images.update(
            _extract_images(entity)
        )

    for image in images:
        alias = _image_alias(image)

        if alias:
            aliases.add(alias)

    identity.image_references = sorted(
        images
    )

    identity.aliases = sorted(aliases)

    identity.members.sort(
        key=lambda member: (
            member.role.value,
            member.name,
        )
    )


def apply_identity_overrides(
    snapshot: GraphSnapshot,
    automatic_result: IdentityResolutionResult,
    overrides: list[IdentityOverrideView],
) -> IdentityResolutionResult:
    result = automatic_result.model_copy(
        deep=True
    )

    entities_by_id = {
        entity.id: entity
        for entity in snapshot.entities
    }

    snapshot_cluster = snapshot.scope.get(
        "cluster"
    )

    for override in overrides:
        if not override.active:
            continue

        matches = [
            entity
            for entity in snapshot.entities
            if (
                entity.kind
                == override.entity_kind
                and entity.name
                == override.entity_name
                and (
                    _entity_cluster(entity)
                    or snapshot_cluster
                )
                == override.cluster_name
                and _entity_namespace(entity)
                == override.namespace
            )
        ]

        if not matches:
            result.warnings.append(
                (
                    f"Override "
                    f"{override.override_id} "
                    "did not match a resource: "
                    f"{override.entity_kind}/"
                    f"{override.entity_name}."
                )
            )

            continue

        if len(matches) > 1:
            result.warnings.append(
                (
                    f"Override "
                    f"{override.override_id} "
                    "matched multiple resources; "
                    "only the first was used."
                )
            )

        entity = matches[0]

        # Remove the resource from any automatic
        # identity before applying the override.
        for identity in result.identities:
            identity.members = [
                member
                for member in identity.members
                if member.entity_id != entity.id
            ]

        result.unresolved_entity_ids = [
            entity_id
            for entity_id
            in result.unresolved_entity_ids
            if entity_id != entity.id
        ]

        result.excluded_entity_ids = [
            entity_id
            for entity_id
            in result.excluded_entity_ids
            if entity_id != entity.id
        ]

        if (
            override.action
            == IdentityOverrideAction.EXCLUDE
        ):
            result.excluded_entity_ids.append(
                entity.id
            )

            continue

        canonical_name = (
            override.canonical_name
        )

        if not canonical_name:
            result.warnings.append(
                (
                    f"Override "
                    f"{override.override_id} "
                    "has no canonical name."
                )
            )

            continue

        role = ROLE_BY_KIND.get(entity.kind)

        if role is None:
            result.warnings.append(
                (
                    "Manual identity assignment "
                    "does not yet support kind "
                    f"{entity.kind}."
                )
            )

            continue

        target_identity = next(
            (
                identity
                for identity
                in result.identities
                if (
                    identity.canonical_name
                    == canonical_name
                    and identity.cluster
                    == override.cluster_name
                    and identity.namespace
                    == override.namespace
                )
            ),
            None,
        )

        if target_identity is None:
            target_identity = LogicalIdentity(
                identity_id=_identity_id(
                    cluster=(
                        override.cluster_name
                    ),
                    namespace=(
                        override.namespace
                    ),
                    canonical_name=(
                        canonical_name
                    ),
                ),
                canonical_name=canonical_name,
                cluster=override.cluster_name,
                namespace=override.namespace,
                environment=entity.environment,
                confidence=1.0,
                members=[],
                image_references=[],
                aliases=[],
                warnings=[
                    (
                        "Identity was created by a "
                        "manual override."
                    )
                ],
            )

            result.identities.append(
                target_identity
            )

        target_identity.members.append(
            IdentityMember(
                entity_id=entity.id,
                kind=entity.kind,
                name=entity.name,
                role=role,
                match_method=(
                    IdentityMatchMethod
                    .MANUAL_OVERRIDE
                ),
                confidence=1.0,
                evidence=[
                    (
                        f"Manual override "
                        f"{override.override_id}: "
                        f"{override.reason}"
                    )
                ],
            )
        )

        target_identity.confidence = max(
            target_identity.confidence,
            0.99,
        )

    result.identities = [
        identity
        for identity in result.identities
        if identity.members
    ]

    for identity in result.identities:
        _refresh_identity_metadata(
            identity=identity,
            entities_by_id=entities_by_id,
        )

    result.identities.sort(
        key=lambda identity: (
            identity.namespace or "",
            identity.canonical_name,
        )
    )

    result.unresolved_entity_ids = sorted(
        set(result.unresolved_entity_ids)
    )

    result.excluded_entity_ids = sorted(
        set(result.excluded_entity_ids)
    )

    return result