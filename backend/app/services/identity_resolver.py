from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from app.models.identity import (
    IdentityMatchMethod,
    IdentityMember,
    IdentityResolutionResult,
    IdentityRole,
    LogicalIdentity,
)
from app.models.topology import (
    Entity,
    GraphSnapshot,
    RelationshipType,
)


APPLICATION_LABEL_KEYS = (
    "app.kubernetes.io/name",
    "app",
    "k8s-app",
)


def _safe_string(value: Any) -> str | None:
    if value is None:
        return None

    result = str(value).strip()

    return result or None


def _entity_namespace(
    entity: Entity,
) -> str | None:
    return _safe_string(
        entity.properties.get("namespace")
    )


def _entity_cluster(
    entity: Entity,
) -> str | None:
    return _safe_string(
        entity.properties.get("cluster")
    )


def _normalize_resource_name(
    name: str,
) -> str:
    """
    Remove common ReplicaSet and Pod hash suffixes.

    Examples:
    checkout-api-6f98d7c5d9-x2k9p -> checkout-api
    checkout-api-6f98d7c5d9       -> checkout-api
    """
    normalized = re.sub(
        r"-[a-f0-9]{8,10}-[a-z0-9]{5}$",
        "",
        name,
    )

    normalized = re.sub(
        r"-[a-f0-9]{8,10}$",
        "",
        normalized,
    )

    return normalized


def _identity_id(
    cluster: str | None,
    namespace: str | None,
    canonical_name: str,
) -> str:
    raw_value = (
        f"{cluster or 'unknown'}|"
        f"{namespace or 'unknown'}|"
        f"{canonical_name}"
    )

    digest = sha256(
        raw_value.encode("utf-8")
    ).hexdigest()[:20]

    return f"identity:kubernetes:{digest}"


def _canonical_name(
    deployment: Entity,
) -> tuple[
    str,
    IdentityMatchMethod,
    float,
    list[str],
]:
    for label_key in APPLICATION_LABEL_KEYS:
        label_value = deployment.labels.get(
            label_key
        )

        if label_value:
            return (
                label_value,
                IdentityMatchMethod.LABEL_EXACT,
                0.99,
                [
                    (
                        f"Deployment label "
                        f"{label_key}={label_value}"
                    )
                ],
            )

    normalized_name = _normalize_resource_name(
        deployment.name
    )

    return (
        normalized_name,
        IdentityMatchMethod.NAME_HEURISTIC,
        0.85,
        [
            (
                "No standard application label was "
                "present; the Deployment name was used."
            )
        ],
    )


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


def _member(
    entity: Entity,
    role: IdentityRole,
    match_method: IdentityMatchMethod,
    confidence: float,
    evidence: list[str],
) -> IdentityMember:
    return IdentityMember(
        entity_id=entity.id,
        kind=entity.kind,
        name=entity.name,
        role=role,
        match_method=match_method,
        confidence=confidence,
        evidence=evidence,
    )


def resolve_kubernetes_identities(
    snapshot: GraphSnapshot,
) -> IdentityResolutionResult:
    entities_by_id = {
        entity.id: entity
        for entity in snapshot.entities
    }

    deployments = [
        entity
        for entity in snapshot.entities
        if entity.kind
        == "KubernetesDeployment"
    ]

    deployment_to_replica_sets: dict[
        str,
        set[str],
    ] = defaultdict(set)

    replica_set_to_pods: dict[
        str,
        set[str],
    ] = defaultdict(set)

    pod_to_services: dict[
        str,
        set[str],
    ] = defaultdict(set)

    for relationship in snapshot.relationships:
        if (
            relationship.relationship_type
            == RelationshipType.OWNS
        ):
            deployment_to_replica_sets[
                relationship.source_entity_id
            ].add(
                relationship.target_entity_id
            )

        elif (
            relationship.relationship_type
            == RelationshipType.RUNS
        ):
            replica_set_to_pods[
                relationship.source_entity_id
            ].add(
                relationship.target_entity_id
            )

        elif (
            relationship.relationship_type
            == RelationshipType.SELECTS
        ):
            pod_to_services[
                relationship.target_entity_id
            ].add(
                relationship.source_entity_id
            )

    identities: list[LogicalIdentity] = []
    resolved_entity_ids: set[str] = set()

    for deployment in deployments:
        (
            canonical_name,
            name_match_method,
            name_confidence,
            name_evidence,
        ) = _canonical_name(deployment)

        cluster = _entity_cluster(deployment)
        namespace = _entity_namespace(deployment)

        member_map: dict[
            str,
            IdentityMember,
        ] = {}

        deployment_member = _member(
            entity=deployment,
            role=IdentityRole.DEPLOYMENT,
            match_method=name_match_method,
            confidence=name_confidence,
            evidence=name_evidence,
        )

        member_map[
            deployment.id
        ] = deployment_member

        replica_set_ids = (
            deployment_to_replica_sets.get(
                deployment.id,
                set(),
            )
        )

        pod_ids: set[str] = set()

        for replica_set_id in replica_set_ids:
            replica_set = entities_by_id.get(
                replica_set_id
            )

            if replica_set is None:
                continue

            member_map[
                replica_set.id
            ] = _member(
                entity=replica_set,
                role=IdentityRole.REPLICA_SET,
                match_method=(
                    IdentityMatchMethod
                    .OWNER_REFERENCE
                ),
                confidence=0.99,
                evidence=[
                    (
                        "ReplicaSet ownerReference "
                        f"points to Deployment "
                        f"{deployment.name}."
                    )
                ],
            )

            pod_ids.update(
                replica_set_to_pods.get(
                    replica_set.id,
                    set(),
                )
            )

        for pod_id in pod_ids:
            pod = entities_by_id.get(pod_id)

            if pod is None:
                continue

            member_map[pod.id] = _member(
                entity=pod,
                role=IdentityRole.POD,
                match_method=(
                    IdentityMatchMethod
                    .OWNER_REFERENCE
                ),
                confidence=0.99,
                evidence=[
                    (
                        "Pod ownerReference points "
                        "to a ReplicaSet owned by "
                        f"Deployment {deployment.name}."
                    )
                ],
            )

        service_ids: set[str] = set()

        for pod_id in pod_ids:
            service_ids.update(
                pod_to_services.get(
                    pod_id,
                    set(),
                )
            )

        for service_id in service_ids:
            service = entities_by_id.get(
                service_id
            )

            if service is None:
                continue

            member_map[
                service.id
            ] = _member(
                entity=service,
                role=IdentityRole.SERVICE,
                match_method=(
                    IdentityMatchMethod
                    .SERVICE_SELECTOR
                ),
                confidence=0.97,
                evidence=[
                    (
                        "Service selector matched "
                        "Pods owned by Deployment "
                        f"{deployment.name}."
                    )
                ],
            )

        images: set[str] = set()

        for member in member_map.values():
            entity = entities_by_id.get(
                member.entity_id
            )

            if entity is not None:
                images.update(
                    _extract_images(entity)
                )

        aliases = {
            member.name
            for member in member_map.values()
        }

        for image in images:
            image_without_digest = image.split(
                "@",
                maxsplit=1,
            )[0]

            image_without_tag = (
                image_without_digest.rsplit(
                    ":",
                    maxsplit=1,
                )[0]
            )

            image_name = (
                image_without_tag.rsplit(
                    "/",
                    maxsplit=1,
                )[-1]
            )

            if image_name:
                aliases.add(image_name)

        warnings: list[str] = []

        if not images:
            warnings.append(
                "No container image reference was "
                "found for this identity."
            )

        if (
            name_match_method
            == IdentityMatchMethod.NAME_HEURISTIC
        ):
            warnings.append(
                "Canonical name was inferred from "
                "the Deployment name."
            )

        members = sorted(
            member_map.values(),
            key=lambda item: (
                item.role.value,
                item.name,
            ),
        )

        identity = LogicalIdentity(
            identity_id=_identity_id(
                cluster=cluster,
                namespace=namespace,
                canonical_name=canonical_name,
            ),
            canonical_name=canonical_name,
            cluster=cluster,
            namespace=namespace,
            environment=deployment.environment,
            confidence=name_confidence,
            members=members,
            image_references=sorted(images),
            aliases=sorted(aliases),
            warnings=warnings,
        )

        identities.append(identity)

        resolved_entity_ids.update(
            member_map.keys()
        )

    resolvable_kinds = {
        "KubernetesDeployment",
        "KubernetesReplicaSet",
        "KubernetesPod",
        "KubernetesService",
    }

    unresolved_entity_ids = sorted(
        entity.id
        for entity in snapshot.entities
        if (
            entity.kind in resolvable_kinds
            and entity.id
            not in resolved_entity_ids
        )
    )

    identities.sort(
        key=lambda identity: (
            identity.namespace or "",
            identity.canonical_name,
        )
    )

    return IdentityResolutionResult(
        snapshot_id=snapshot.snapshot_id,
        generated_at=datetime.now(
            timezone.utc
        ),
        identities=identities,
        unresolved_entity_ids=(
            unresolved_entity_ids
        ),
    )