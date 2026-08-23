from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from uuid import uuid4

from app.models.topology import (
    Entity,
    EntityType,
    Evidence,
    EvidenceType,
    GraphSnapshot,
    Relationship,
    RelationshipOrigin,
    RelationshipType,
)
from app.services.canonical_identity import (
    canonical_container_image_identity,
)
from app.services.relationship_provenance import (
    relationship_provenance,
    source_reference,
)


DIGEST_PATTERN = re.compile(
    r"(sha256:[0-9a-fA-F]{64})"
)


@dataclass(frozen=True)
class ParsedImageReference:
    raw_reference: str
    normalized_reference: str
    registry: str
    repository: str
    tag: str | None
    digest: str | None


def _remove_runtime_prefix(
    value: str,
) -> str:
    known_prefixes = (
        "docker-pullable://",
        "docker://",
        "containerd://",
        "cri-o://",
    )

    for prefix in known_prefixes:
        if value.startswith(prefix):
            return value[len(prefix):]

    return value


def _extract_digest(
    value: str | None,
) -> str | None:
    if not value:
        return None

    match = DIGEST_PATTERN.search(value)

    if match is None:
        return None

    return match.group(1).lower()


def parse_image_reference(
    image_reference: str,
) -> ParsedImageReference:
    raw_reference = image_reference.strip()

    reference = _remove_runtime_prefix(
        raw_reference
    )

    digest = _extract_digest(reference)

    reference_without_digest = reference.split(
        "@",
        maxsplit=1,
    )[0]

    final_segment = (
        reference_without_digest.rsplit(
            "/",
            maxsplit=1,
        )[-1]
    )

    tag: str | None = None
    repository_reference = (
        reference_without_digest
    )

    if ":" in final_segment:
        repository_reference, tag = (
            reference_without_digest.rsplit(
                ":",
                maxsplit=1,
            )
        )

    segments = repository_reference.split("/")

    first_segment = segments[0]

    first_segment_is_registry = (
        "." in first_segment
        or ":" in first_segment
        or first_segment == "localhost"
    )

    if len(segments) == 1:
        registry = "docker.io"
        repository = (
            f"library/{segments[0]}"
        )

    elif first_segment_is_registry:
        registry = first_segment
        repository = "/".join(
            segments[1:]
        )

    else:
        registry = "docker.io"
        repository = "/".join(segments)

    if digest:
        normalized_reference = (
            f"{registry}/{repository}@{digest}"
        )

    else:
        normalized_reference = (
            f"{registry}/{repository}:"
            f"{tag or 'latest'}"
        )

    return ParsedImageReference(
        raw_reference=raw_reference,
        normalized_reference=(
            normalized_reference
        ),
        registry=registry,
        repository=repository,
        tag=tag or (
            None if digest else "latest"
        ),
        digest=digest,
    )


def _image_entity_id(
    parsed: ParsedImageReference,
    digest: str | None,
) -> str:
    return canonical_container_image_identity(
        normalized_reference=parsed.normalized_reference,
        digest=digest,
    ).canonical_id


def _relationship_id(
    source_entity_id: str,
    target_entity_id: str,
) -> str:
    relationship_value = (
        f"{source_entity_id}|"
        f"{RelationshipType.USES.value}|"
        f"{target_entity_id}"
    )

    digest = sha256(
        relationship_value.encode("utf-8")
    ).hexdigest()[:20]

    return f"rel:{digest}"


def _container_list(
    entity: Entity,
) -> list[dict]:
    containers = entity.properties.get(
        "containers"
    )

    if not isinstance(containers, list):
        return []

    return [
        container
        for container in containers
        if isinstance(container, dict)
    ]


def _runtime_digests_by_reference(
    snapshot: GraphSnapshot,
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}

    for entity in snapshot.entities:
        if entity.kind != "KubernetesPod":
            continue

        for container in _container_list(entity):
            image = container.get("image")

            if not isinstance(image, str):
                continue

            parsed = parse_image_reference(
                image
            )

            digest = (
                _extract_digest(
                    container.get("image_id")
                    if isinstance(
                        container.get("image_id"),
                        str,
                    )
                    else None
                )
                or parsed.digest
            )

            if not digest:
                continue

            result.setdefault(
                parsed.normalized_reference,
                set(),
            ).add(digest)

    return result


def augment_snapshot_with_container_images(
    snapshot: GraphSnapshot,
) -> GraphSnapshot:
    result = snapshot.model_copy(
        deep=True
    )

    evidence_id = (
        f"evidence:container-images:"
        f"{uuid4()}"
    )

    runtime_digests = (
        _runtime_digests_by_reference(
            result
        )
    )

    artifact_entities: dict[str, Entity] = {}

    image_relationships: dict[
        str,
        Relationship,
    ] = {}

    supported_kinds = {
        "KubernetesDeployment",
        "KubernetesPod",
    }

    for source_entity in result.entities:
        if source_entity.kind not in (
            supported_kinds
        ):
            continue

        for container in _container_list(
            source_entity
        ):
            requested_image = container.get(
                "image"
            )

            if not isinstance(
                requested_image,
                str,
            ):
                continue

            parsed = parse_image_reference(
                requested_image
            )

            runtime_image_id = (
                container.get("image_id")
                if isinstance(
                    container.get("image_id"),
                    str,
                )
                else None
            )

            direct_digest = (
                _extract_digest(
                    runtime_image_id
                )
                or parsed.digest
            )

            candidate_digests: set[
                str | None
            ]

            if direct_digest:
                candidate_digests = {
                    direct_digest
                }

            elif (
                source_entity.kind
                == "KubernetesDeployment"
                and runtime_digests.get(
                    parsed.normalized_reference
                )
            ):
                candidate_digests = set(
                    runtime_digests[
                        parsed.normalized_reference
                    ]
                )

            else:
                candidate_digests = {None}

            for candidate_digest in (
                candidate_digests
            ):
                artifact_identity = canonical_container_image_identity(
                    normalized_reference=(
                        parsed.normalized_reference
                    ),
                    digest=candidate_digest,
                )
                artifact_id = artifact_identity.canonical_id

                artifact = (
                    artifact_entities.get(
                        artifact_id
                    )
                )

                if artifact is None:
                    short_digest = (
                        candidate_digest.split(
                            ":",
                            maxsplit=1,
                        )[-1][:12]
                        if candidate_digest
                        else None
                    )

                    display_name = (
                        f"{parsed.repository}"
                        f"@{short_digest}"
                        if short_digest
                        else (
                            parsed
                            .normalized_reference
                        )
                    )

                    artifact = Entity(
                        id=artifact_id,
                        entity_type=(
                            EntityType.ARTIFACT
                        ),
                        kind="ContainerImage",
                        name=display_name,
                        source_system=(
                            "kubernetes"
                        ),
                        external_id=(
                            artifact_identity.source_native_id
                        ),
                        aliases=artifact_identity.aliases,
                        identity_version=(
                            artifact_identity.identity_version
                        ),
                        environment=None,
                        observed_at=(
                            result.collected_at
                        ),
                        confidence=(
                            1.0
                            if candidate_digest
                            else 0.80
                        ),
                        labels={},
                        properties={
                            "registry": (
                                parsed.registry
                            ),
                            "repository": (
                                parsed.repository
                            ),
                            "tag": parsed.tag,
                            "digest": (
                                candidate_digest
                            ),
                            "immutable": bool(
                                candidate_digest
                            ),
                            "requested_references": [
                                requested_image
                            ],
                            "environments": (
                                [
                                    source_entity
                                    .environment
                                ]
                                if (
                                    source_entity
                                    .environment
                                )
                                else []
                            ),
                            "discovered_via": (
                                "kubernetes"
                            ),
                        },
                    )

                    artifact_entities[
                        artifact_id
                    ] = artifact

                else:
                    requested_references = (
                        artifact.properties.get(
                            "requested_references",
                            [],
                        )
                    )

                    if (
                        requested_image
                        not in requested_references
                    ):
                        requested_references.append(
                            requested_image
                        )

                    artifact.properties[
                        "requested_references"
                    ] = sorted(
                        requested_references
                    )

                    environments = (
                        artifact.properties.get(
                            "environments",
                            [],
                        )
                    )

                    if (
                        source_entity.environment
                        and source_entity.environment
                        not in environments
                    ):
                        environments.append(
                            source_entity.environment
                        )

                    artifact.properties[
                        "environments"
                    ] = sorted(environments)

                relationship_id = (
                    _relationship_id(
                        source_entity_id=(
                            source_entity.id
                        ),
                        target_entity_id=(
                            artifact_id
                        ),
                    )
                )

                resolution_method = (
                    "runtime_digest"
                    if direct_digest
                    else (
                        "observed_pod_digest"
                        if candidate_digest
                        else (
                            "requested_reference"
                        )
                    )
                )

                image_relationships[
                    relationship_id
                ] = Relationship(
                    id=relationship_id,
                    source_entity_id=(
                        source_entity.id
                    ),
                    target_entity_id=(
                        artifact_id
                    ),
                    relationship_type=(
                        RelationshipType.USES
                    ),
                    source_system=(
                        "kubernetes"
                    ),
                    observed_at=(
                        result.collected_at
                    ),
                    directed=True,
                    evidence_ids=[
                        evidence_id
                    ],
                    provenance=relationship_provenance(
                        predicate=RelationshipType.USES,
                        origin=(
                            RelationshipOrigin.DERIVED
                            if candidate_digest
                            else RelationshipOrigin.DECLARED
                        ),
                        source_component=(
                            "backend.app.services.container_image_graph"
                        ),
                        source_references=[
                            source_reference(
                                reference_type="container_image_reference",
                                reference=requested_image,
                                source_system="kubernetes",
                                attributes={
                                    "container_name": container.get("name"),
                                },
                            ),
                            source_reference(
                                reference_type="container_image_digest",
                                reference=candidate_digest,
                                source_system="kubernetes",
                                attributes={
                                    "resolution_method": resolution_method,
                                },
                            ),
                        ],
                        linker_version="container-image-linker:v1",
                    ),
                    properties={
                        "container_name": (
                            container.get(
                                "name"
                            )
                        ),
                        "requested_image": (
                            requested_image
                        ),
                        "runtime_image_id": (
                            runtime_image_id
                        ),
                        "resolution_method": (
                            resolution_method
                        ),
                    },
                )

    if not artifact_entities:
        return result

    existing_entity_ids = {
        entity.id
        for entity in result.entities
    }

    existing_relationship_ids = {
        relationship.id
        for relationship
        in result.relationships
    }

    new_entities = [
        entity
        for entity
        in artifact_entities.values()
        if entity.id
        not in existing_entity_ids
    ]

    new_relationships = [
        relationship
        for relationship
        in image_relationships.values()
        if relationship.id
        not in existing_relationship_ids
    ]

    result.entities.extend(new_entities)

    result.relationships.extend(
        new_relationships
    )

    result.evidence.append(
        Evidence(
            id=evidence_id,
            evidence_type=(
                EvidenceType.RELATIONSHIP
            ),
            source_system="kubernetes",
            summary=(
                "Container image artifacts were "
                "resolved from Kubernetes workload "
                "specifications and runtime image "
                "digests."
            ),
            observed_at=(
                result.collected_at
            ),
            related_entity_ids=[
                entity.id
                for entity in new_entities
            ],
            related_relationship_ids=[
                relationship.id
                for relationship
                in new_relationships
            ],
            payload={
                "artifact_count": len(
                    artifact_entities
                ),
                "relationship_count": len(
                    image_relationships
                ),
                "digest_resolved_count": sum(
                    1
                    for entity
                    in artifact_entities.values()
                    if entity.properties.get(
                        "digest"
                    )
                ),
            },
        )
    )

    result.metadata[
        "container_image_artifacts"
    ] = {
        "count": len(
            artifact_entities
        ),
        "relationships": len(
            image_relationships
        ),
    }

    return result
