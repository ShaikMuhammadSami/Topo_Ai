from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

from app.models.topology import (
    Entity,
    EntityType,
    Evidence,
    EvidenceType,
    GraphSnapshot,
    Relationship,
    RelationshipType,
)
from app.services.canonical_identity import (
    canonical_git_commit_identity,
    canonical_git_repository_identity,
)


REVISION_KEYS = (
    "topo.ai/source-revision",
    "org.opencontainers.image.revision",
    "vcs.revision",
    "git.sha",
    "git.commit",
    "commit.sha",
    "commit_sha",
    "build.commit",
    "ci.commit.sha",
)


REPOSITORY_KEYS = (
    "topo.ai/source-repository",
    "vcs.repository",
    "git.repository",
    "app.kubernetes.io/source",
)


SHA_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{7,40}\b"
)


@dataclass(frozen=True)
class GitHubEnrichmentStats:
    commits_collected: int
    mapped_commit_count: int
    mapped_image_count: int
    relationship_count: int
    unresolved_image_count: int
    warnings: list[str]


@dataclass(frozen=True)
class CommitImageCandidate:
    commit_entity_id: str
    commit_sha: str
    image_entity_id: str
    confidence: float
    method: str
    source_entity_id: str | None


def _repository_entity_id(
    api_url: str,
    repository_id: Any,
) -> str:
    return canonical_git_repository_identity(
        provider="github",
        api_url=api_url,
        repository_native_id=repository_id,
    ).canonical_id


def _commit_entity_id(
    repository_entity_id: str,
    sha: str,
) -> str:
    return canonical_git_commit_identity(
        repository_canonical_id=repository_entity_id,
        commit_sha=sha,
    ).canonical_id


def _relationship_id(
    source_entity_id: str,
    relationship_type: RelationshipType,
    target_entity_id: str,
) -> str:
    value = (
        f"{source_entity_id}|"
        f"{relationship_type.value}|"
        f"{target_entity_id}"
    )

    digest = sha256(
        value.encode("utf-8")
    ).hexdigest()[:20]

    return f"rel:{digest}"


def _annotations(
    entity: Entity,
) -> dict[str, str]:
    value = entity.properties.get(
        "annotations"
    )

    if not isinstance(value, dict):
        return {}

    return {
        str(key): str(item)
        for key, item in value.items()
    }


def _find_value(
    entity: Entity,
    keys: tuple[str, ...],
) -> str | None:
    annotations = _annotations(entity)

    for key in keys:
        value = annotations.get(key)

        if value:
            return value.strip()

    for key in keys:
        value = entity.labels.get(key)

        if value:
            return value.strip()

    return None


def _extract_revision(
    value: str | None,
) -> str | None:
    if not value:
        return None

    match = SHA_PATTERN.search(value)

    if not match:
        return None

    return match.group(0).lower()


def _normalize_repository(
    value: str,
) -> str:
    normalized = value.strip().lower()

    normalized = normalized.removesuffix(
        ".git"
    )

    if normalized.startswith(
        "git@github.com:"
    ):
        normalized = normalized.replace(
            "git@github.com:",
            "",
            1,
        )

    for prefix in (
        "https://github.com/",
        "http://github.com/",
        "ssh://git@github.com/",
    ):
        if normalized.startswith(prefix):
            normalized = normalized[
                len(prefix):
            ]

    return normalized.strip("/")


def _repository_matches(
    repository_hint: str | None,
    expected_full_name: str,
) -> bool:
    if not repository_hint:
        return True

    return (
        _normalize_repository(
            repository_hint
        )
        == _normalize_repository(
            expected_full_name
        )
    )


def _resolve_commit_sha(
    revision: str,
    commit_ids_by_sha: dict[str, str],
) -> tuple[str, str, float] | None:
    revision = revision.lower()

    exact_id = commit_ids_by_sha.get(
        revision
    )

    if exact_id:
        return (
            revision,
            exact_id,
            1.0,
        )

    matches = [
        (sha, entity_id)
        for sha, entity_id
        in commit_ids_by_sha.items()
        if sha.startswith(revision)
    ]

    if len(matches) != 1:
        return None

    sha, entity_id = matches[0]

    return (
        sha,
        entity_id,
        0.95,
    )


def _image_tag(
    entity: Entity,
) -> str | None:
    value = entity.properties.get("tag")

    return (
        value
        if isinstance(value, str)
        else None
    )


def _consider_candidate(
    candidates: dict[
        str,
        list[CommitImageCandidate],
    ],
    candidate: CommitImageCandidate,
) -> None:
    candidates[
        candidate.image_entity_id
    ].append(candidate)


def augment_snapshot_with_github(
    snapshot: GraphSnapshot,
    repository: dict[str, Any],
    commits: list[dict[str, Any]],
    api_url: str,
) -> tuple[
    GraphSnapshot,
    GitHubEnrichmentStats,
]:
    result = snapshot.model_copy(
        deep=True
    )

    generated_at = datetime.now(
        timezone.utc
    )

    full_name = str(
        repository.get("full_name")
        or ""
    )

    repository_database_id = (
        repository.get("id")
        or full_name
    )

    repository_identity = canonical_git_repository_identity(
        provider="github",
        api_url=api_url,
        repository_native_id=repository_database_id,
        repository_name=full_name,
    )
    repository_id = repository_identity.canonical_id

    evidence_id = (
        f"evidence:github-enrichment:"
        f"{uuid4()}"
    )

    repository_entity = Entity(
        id=repository_id,
        entity_type=(
            EntityType.CODE_REPOSITORY
        ),
        kind="GitRepository",
        name=full_name,
        source_system="github",
        external_id=str(
            repository_database_id
        ),
        aliases=repository_identity.aliases,
        identity_version=(
            repository_identity.identity_version
        ),
        environment=None,
        observed_at=generated_at,
        confidence=1.0,
        labels={},
        properties={
            "full_name": full_name,
            "html_url": repository.get(
                "html_url"
            ),
            "clone_url": repository.get(
                "clone_url"
            ),
            "ssh_url": repository.get(
                "ssh_url"
            ),
            "default_branch": (
                repository.get(
                    "default_branch"
                )
            ),
            "private": bool(
                repository.get("private")
            ),
            "archived": bool(
                repository.get("archived")
            ),
        },
    )

    commit_entities: dict[
        str,
        Entity,
    ] = {}

    commit_ids_by_sha: dict[
        str,
        str,
    ] = {}

    repository_relationships: list[
        Relationship
    ] = []

    for item in commits:
        sha_value = item.get("sha")

        if not isinstance(
            sha_value,
            str,
        ):
            continue

        sha = sha_value.lower()

        commit_identity = canonical_git_commit_identity(
            repository_canonical_id=(
                repository_id
            ),
            commit_sha=sha,
        )
        commit_id = commit_identity.canonical_id

        commit_data = item.get("commit")

        if not isinstance(
            commit_data,
            dict,
        ):
            commit_data = {}

        author_data = commit_data.get(
            "author"
        )

        if not isinstance(
            author_data,
            dict,
        ):
            author_data = {}

        committer_data = commit_data.get(
            "committer"
        )

        if not isinstance(
            committer_data,
            dict,
        ):
            committer_data = {}

        message = str(
            commit_data.get("message")
            or ""
        )

        summary = (
            message.splitlines()[0]
            if message
            else sha[:12]
        )

        commit_entity = Entity(
            id=commit_id,
            entity_type=(
                EntityType.SOURCE_REVISION
            ),
            kind="GitCommit",
            name=sha[:12],
            source_system="github",
            external_id=sha,
            aliases=commit_identity.aliases,
            identity_version=(
                commit_identity.identity_version
            ),
            environment=None,
            observed_at=generated_at,
            confidence=1.0,
            labels={},
            properties={
                "sha": sha,
                "short_sha": sha[:12],
                "summary": summary,
                "message": message,
                "author_name": (
                    author_data.get("name")
                ),
                "author_email": (
                    author_data.get("email")
                ),
                "authored_at": (
                    author_data.get("date")
                ),
                "committer_name": (
                    committer_data.get(
                        "name"
                    )
                ),
                "committed_at": (
                    committer_data.get(
                        "date"
                    )
                ),
                "html_url": item.get(
                    "html_url"
                ),
                "parents": [
                    parent.get("sha")
                    for parent in (
                        item.get("parents")
                        or []
                    )
                    if isinstance(
                        parent,
                        dict,
                    )
                    and parent.get("sha")
                ],
            },
        )

        commit_entities[commit_id] = (
            commit_entity
        )

        commit_ids_by_sha[sha] = (
            commit_id
        )

        repository_relationships.append(
            Relationship(
                id=_relationship_id(
                    source_entity_id=(
                        repository_id
                    ),
                    relationship_type=(
                        RelationshipType
                        .CONTAINS
                    ),
                    target_entity_id=(
                        commit_id
                    ),
                ),
                source_entity_id=(
                    repository_id
                ),
                target_entity_id=(
                    commit_id
                ),
                relationship_type=(
                    RelationshipType.CONTAINS
                ),
                source_system="github",
                observed_at=generated_at,
                confidence=1.0,
                directed=True,
                evidence_ids=[
                    evidence_id
                ],
                properties={},
            )
        )

    entities_by_id = {
        entity.id: entity
        for entity in result.entities
    }

    image_entities = {
        entity.id: entity
        for entity in result.entities
        if entity.kind == "ContainerImage"
    }

    image_ids_by_source: dict[
        str,
        set[str],
    ] = defaultdict(set)

    for relationship in result.relationships:
        if (
            relationship.relationship_type
            != RelationshipType.USES
        ):
            continue

        if (
            relationship.target_entity_id
            not in image_entities
        ):
            continue

        image_ids_by_source[
            relationship.source_entity_id
        ].add(
            relationship.target_entity_id
        )

    candidates: dict[
        str,
        list[CommitImageCandidate],
    ] = defaultdict(list)

    workload_kinds = {
        "KubernetesDeployment",
        "KubernetesPod",
    }

    for (
        source_entity_id,
        image_ids,
    ) in image_ids_by_source.items():
        source_entity = entities_by_id.get(
            source_entity_id
        )

        if (
            source_entity is None
            or source_entity.kind
            not in workload_kinds
        ):
            continue

        repository_hint = _find_value(
            source_entity,
            REPOSITORY_KEYS,
        )

        if not _repository_matches(
            repository_hint=repository_hint,
            expected_full_name=full_name,
        ):
            continue

        revision_value = _find_value(
            source_entity,
            REVISION_KEYS,
        )

        revision = _extract_revision(
            revision_value
        )

        if not revision:
            continue

        resolved = _resolve_commit_sha(
            revision=revision,
            commit_ids_by_sha=(
                commit_ids_by_sha
            ),
        )

        if not resolved:
            continue

        (
            commit_sha,
            commit_entity_id,
            confidence,
        ) = resolved

        method = (
            "workload_annotation_exact"
            if len(revision) == 40
            else "workload_annotation_prefix"
        )

        for image_id in image_ids:
            _consider_candidate(
                candidates,
                CommitImageCandidate(
                    commit_entity_id=(
                        commit_entity_id
                    ),
                    commit_sha=commit_sha,
                    image_entity_id=image_id,
                    confidence=confidence,
                    method=method,
                    source_entity_id=(
                        source_entity.id
                    ),
                ),
            )

    for image_id, image in (
        image_entities.items()
    ):
        tag = _image_tag(image)

        revision = _extract_revision(tag)

        if not revision:
            continue

        resolved = _resolve_commit_sha(
            revision=revision,
            commit_ids_by_sha=(
                commit_ids_by_sha
            ),
        )

        if not resolved:
            continue

        (
            commit_sha,
            commit_entity_id,
            _,
        ) = resolved

        confidence = (
            0.98
            if len(revision) == 40
            else 0.90
        )

        method = (
            "image_tag_exact_sha"
            if len(revision) == 40
            else "image_tag_sha_prefix"
        )

        _consider_candidate(
            candidates,
            CommitImageCandidate(
                commit_entity_id=(
                    commit_entity_id
                ),
                commit_sha=commit_sha,
                image_entity_id=image_id,
                confidence=confidence,
                method=method,
                source_entity_id=None,
            ),
        )

    mapping_relationships: list[
        Relationship
    ] = []

    warnings: list[str] = []

    mapped_commit_ids: set[str] = set()
    mapped_image_ids: set[str] = set()

    for image_id, image_candidates in (
        candidates.items()
    ):
        ranked = sorted(
            image_candidates,
            key=lambda item: (
                item.confidence
            ),
            reverse=True,
        )

        highest_confidence = (
            ranked[0].confidence
        )

        highest_candidates = [
            candidate
            for candidate in ranked
            if candidate.confidence
            == highest_confidence
        ]

        unique_commits = {
            candidate.commit_entity_id
            for candidate
            in highest_candidates
        }

        if len(unique_commits) != 1:
            warnings.append(
                "Ambiguous commit mapping for "
                f"image {image_id}; no "
                "relationship was created."
            )

            continue

        selected = highest_candidates[0]

        relationship = Relationship(
            id=_relationship_id(
                source_entity_id=(
                    selected
                    .commit_entity_id
                ),
                relationship_type=(
                    RelationshipType
                    .PRODUCES
                ),
                target_entity_id=image_id,
            ),
            source_entity_id=(
                selected.commit_entity_id
            ),
            target_entity_id=image_id,
            relationship_type=(
                RelationshipType.PRODUCES
            ),
            source_system="github",
            observed_at=generated_at,
            confidence=(
                selected.confidence
            ),
            directed=True,
            evidence_ids=[
                evidence_id
            ],
            properties={
                "commit_sha": (
                    selected.commit_sha
                ),
                "mapping_method": (
                    selected.method
                ),
                "workload_entity_id": (
                    selected
                    .source_entity_id
                ),
            },
        )

        mapping_relationships.append(
            relationship
        )

        mapped_commit_ids.add(
            selected.commit_entity_id
        )

        mapped_image_ids.add(image_id)

    existing_entity_ids = {
        entity.id
        for entity in result.entities
    }

    if (
        repository_entity.id
        not in existing_entity_ids
    ):
        result.entities.append(
            repository_entity
        )

    existing_entity_ids.add(
        repository_entity.id
    )

    for entity in (
        commit_entities.values()
    ):
        if entity.id not in (
            existing_entity_ids
        ):
            result.entities.append(entity)
            existing_entity_ids.add(
                entity.id
            )

    existing_relationship_ids = {
        relationship.id
        for relationship
        in result.relationships
    }

    for relationship in (
        repository_relationships
        + mapping_relationships
    ):
        if (
            relationship.id
            not in existing_relationship_ids
        ):
            result.relationships.append(
                relationship
            )

            existing_relationship_ids.add(
                relationship.id
            )

    related_entity_ids = [
        repository_entity.id,
        *commit_entities.keys(),
        *mapped_image_ids,
    ]

    related_relationship_ids = [
        relationship.id
        for relationship
        in (
            repository_relationships
            + mapping_relationships
        )
    ]

    result.evidence.append(
        Evidence(
            id=evidence_id,
            evidence_type=(
                EvidenceType.RELATIONSHIP
            ),
            source_system="github",
            summary=(
                "GitHub repository commits were "
                "collected and correlated with "
                "container images using workload "
                "annotations and image tags."
            ),
            observed_at=generated_at,
            related_entity_ids=(
                related_entity_ids
            ),
            related_relationship_ids=(
                related_relationship_ids
            ),
            payload={
                "repository": full_name,
                "commits_collected": len(
                    commit_entities
                ),
                "mapped_commit_count": len(
                    mapped_commit_ids
                ),
                "mapped_image_count": len(
                    mapped_image_ids
                ),
                "relationship_count": len(
                    mapping_relationships
                ),
                "warnings": warnings,
            },
        )
    )

    base_snapshot_id = (
        result.snapshot_id
    )

    result.snapshot_id = (
        "snapshot:github-enriched:"
        f"{generated_at.strftime('%Y%m%dT%H%M%SZ')}:"
        f"{str(uuid4())[:8]}"
    )

    result.collected_at = generated_at

    result.collector_name = (
        "github-graph-enricher"
    )

    result.collector_version = "0.1.0"

    result.scope = {
        **result.scope,
        "github_repository": full_name,
    }

    result.metadata = {
        **result.metadata,
        "base_snapshot_id": (
            base_snapshot_id
        ),
        "github_enrichment": {
            "repository": full_name,
            "commits_collected": len(
                commit_entities
            ),
            "mapped_commit_count": len(
                mapped_commit_ids
            ),
            "mapped_image_count": len(
                mapped_image_ids
            ),
            "relationship_count": len(
                mapping_relationships
            ),
        },
    }

    unresolved_image_count = len(
        set(image_entities)
        - mapped_image_ids
    )

    stats = GitHubEnrichmentStats(
        commits_collected=len(
            commit_entities
        ),
        mapped_commit_count=len(
            mapped_commit_ids
        ),
        mapped_image_count=len(
            mapped_image_ids
        ),
        relationship_count=len(
            mapping_relationships
        ),
        unresolved_image_count=(
            unresolved_image_count
        ),
        warnings=warnings,
    )

    return result, stats
