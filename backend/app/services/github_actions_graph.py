from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from urllib.parse import urlparse
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


WORKFLOW_RUN_ID_KEYS = (
    "topo.ai/workflow-run-id",
    "github.actions/run-id",
    "ci.workflow-run-id",
)

REVISION_KEYS = (
    "topo.ai/source-revision",
    "org.opencontainers.image.revision",
    "vcs.revision",
    "git.sha",
    "git.commit",
    "commit.sha",
    "commit_sha",
)

IMAGE_DIGEST_KEYS = (
    "topo.ai/image-digest",
    "org.opencontainers.image.digest",
)

REPOSITORY_KEYS = (
    "topo.ai/source-repository",
    "vcs.repository",
    "git.repository",
    "app.kubernetes.io/source",
)

DIGEST_PATTERN = re.compile(
    r"sha256:[0-9a-fA-F]{64}"
)


def _host_identifier(
    api_url: str,
) -> str:
    hostname = (
        urlparse(api_url).hostname
        or "github"
    )

    return re.sub(
        r"[^a-zA-Z0-9._-]+",
        "_",
        hostname,
    )


def _workflow_run_entity_id(
    api_url: str,
    run_id: int | str,
) -> str:
    return (
        f"github:{_host_identifier(api_url)}:"
        f"workflow-run:{run_id}"
    )


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


def _metadata_values(
    entity: Entity,
) -> dict[str, str]:
    values: dict[str, str] = {
        str(key): str(value)
        for key, value in entity.labels.items()
    }

    annotations = entity.properties.get(
        "annotations"
    )

    if isinstance(annotations, dict):
        for key, value in annotations.items():
            values[str(key)] = str(value)

    return values


def _find_value(
    entity: Entity,
    keys: tuple[str, ...],
) -> str | None:
    values = _metadata_values(entity)

    for key in keys:
        value = values.get(key)

        if value:
            return value.strip()

    return None


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
    expected_repository: str,
) -> bool:
    if not repository_hint:
        return True

    return (
        _normalize_repository(
            repository_hint
        )
        == _normalize_repository(
            expected_repository
        )
    )


def _normalize_sha(
    value: str | None,
) -> str | None:
    if not value:
        return None

    match = re.search(
        r"\b[0-9a-fA-F]{7,40}\b",
        value,
    )

    if not match:
        return None

    return match.group(0).lower()


def _extract_digest(
    value: str | None,
) -> str | None:
    if not value:
        return None

    match = DIGEST_PATTERN.search(value)

    return (
        match.group(0).lower()
        if match
        else None
    )


def _safe_datetime(
    value: Any,
    fallback: datetime,
) -> datetime:
    if not isinstance(value, str):
        return fallback

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

    except ValueError:
        return fallback


def augment_snapshot_with_github_actions(
    snapshot: GraphSnapshot,
    workflow_runs: list[dict[str, Any]],
    repository_full_name: str,
    api_url: str,
) -> tuple[
    GraphSnapshot,
    dict[str, Any],
]:
    result = snapshot.model_copy(
        deep=True
    )

    observed_at = datetime.now(
        timezone.utc
    )

    evidence_id = (
        f"evidence:github-actions:"
        f"{uuid4()}"
    )

    repository_entities = [
        entity
        for entity in result.entities
        if (
            entity.kind == "GitRepository"
            and _normalize_repository(
                entity.name
            )
            == _normalize_repository(
                repository_full_name
            )
        )
    ]

    if not repository_entities:
        raise ValueError(
            "The snapshot does not contain the "
            "configured GitRepository. Run the "
            "GitHub commit enrichment first."
        )

    repository_entity = (
        repository_entities[0]
    )

    commits_by_sha = {
        str(
            entity.properties.get("sha")
            or entity.external_id
            or ""
        ).lower(): entity
        for entity in result.entities
        if entity.kind == "GitCommit"
    }

    image_entities = {
        entity.id: entity
        for entity in result.entities
        if entity.kind == "ContainerImage"
    }

    images_by_workload: dict[
        str,
        set[str],
    ] = defaultdict(set)

    for relationship in result.relationships:
        if (
            relationship.relationship_type
            == RelationshipType.USES
            and relationship.target_entity_id
            in image_entities
        ):
            images_by_workload[
                relationship.source_entity_id
            ].add(
                relationship.target_entity_id
            )

    run_entities: dict[
        str,
        Entity,
    ] = {}

    runs_by_external_id: dict[
        str,
        Entity,
    ] = {}

    commit_run_relationships: dict[
        str,
        Relationship,
    ] = {}

    repository_run_relationships: dict[
        str,
        Relationship,
    ] = {}

    run_payloads_by_id: dict[
        str,
        dict[str, Any],
    ] = {}

    for run in workflow_runs:
        run_id = run.get("id")

        if run_id is None:
            continue

        external_run_id = str(run_id)

        run_entity_id = (
            _workflow_run_entity_id(
                api_url=api_url,
                run_id=run_id,
            )
        )

        head_sha = str(
            run.get("head_sha")
            or ""
        ).lower()

        workflow_name = str(
            run.get("name")
            or run.get("display_title")
            or "GitHub Actions"
        )

        run_number = run.get(
            "run_number"
        )

        run_attempt = run.get(
            "run_attempt"
        )

        run_entity = Entity(
            id=run_entity_id,
            entity_type=EntityType.PIPELINE,
            kind="GitHubWorkflowRun",
            name=(
                f"{workflow_name} "
                f"#{run_number}"
            ),
            source_system="github-actions",
            external_id=external_run_id,
            environment=None,
            observed_at=_safe_datetime(
                run.get("updated_at"),
                observed_at,
            ),
            confidence=1.0,
            labels={},
            properties={
                "run_id": external_run_id,
                "workflow_id": run.get(
                    "workflow_id"
                ),
                "workflow_name": workflow_name,
                "run_number": run_number,
                "run_attempt": run_attempt,
                "head_sha": head_sha,
                "head_branch": run.get(
                    "head_branch"
                ),
                "event": run.get("event"),
                "status": run.get("status"),
                "conclusion": run.get(
                    "conclusion"
                ),
                "created_at": run.get(
                    "created_at"
                ),
                "updated_at": run.get(
                    "updated_at"
                ),
                "run_started_at": run.get(
                    "run_started_at"
                ),
                "html_url": run.get(
                    "html_url"
                ),
                "jobs_url": run.get(
                    "jobs_url"
                ),
                "logs_url": run.get(
                    "logs_url"
                ),
                "actor": (
                    run.get("actor", {})
                    .get("login")
                    if isinstance(
                        run.get("actor"),
                        dict,
                    )
                    else None
                ),
            },
        )

        run_entities[
            run_entity_id
        ] = run_entity

        runs_by_external_id[
            external_run_id
        ] = run_entity

        run_payloads_by_id[
            external_run_id
        ] = run

        repository_relationship = (
            Relationship(
                id=_relationship_id(
                    repository_entity.id,
                    RelationshipType.CONTAINS,
                    run_entity_id,
                ),
                source_entity_id=(
                    repository_entity.id
                ),
                target_entity_id=(
                    run_entity_id
                ),
                relationship_type=(
                    RelationshipType.CONTAINS
                ),
                source_system=(
                    "github-actions"
                ),
                observed_at=observed_at,
                confidence=1.0,
                directed=True,
                evidence_ids=[
                    evidence_id
                ],
                properties={
                    "object": (
                        "workflow_run"
                    ),
                },
            )
        )

        repository_run_relationships[
            repository_relationship.id
        ] = repository_relationship

        commit_entity = (
            commits_by_sha.get(head_sha)
        )

        if commit_entity is None:
            continue

        trigger_relationship = Relationship(
            id=_relationship_id(
                commit_entity.id,
                RelationshipType.TRIGGERS,
                run_entity_id,
            ),
            source_entity_id=(
                commit_entity.id
            ),
            target_entity_id=run_entity_id,
            relationship_type=(
                RelationshipType.TRIGGERS
            ),
            source_system="github-actions",
            observed_at=observed_at,
            confidence=1.0,
            directed=True,
            evidence_ids=[
                evidence_id
            ],
            properties={
                "head_sha": head_sha,
                "event": run.get("event"),
                "run_number": run_number,
                "run_attempt": run_attempt,
            },
        )

        commit_run_relationships[
            trigger_relationship.id
        ] = trigger_relationship

    entities_by_id = {
        entity.id: entity
        for entity in result.entities
    }

    run_image_relationships: dict[
        str,
        Relationship,
    ] = {}

    warnings: list[str] = []

    mapped_run_ids: set[str] = set()
    mapped_image_ids: set[str] = set()

    workload_kinds = {
        "KubernetesDeployment",
        "KubernetesPod",
    }

    for workload_id, image_ids in (
        images_by_workload.items()
    ):
        workload = entities_by_id.get(
            workload_id
        )

        if (
            workload is None
            or workload.kind
            not in workload_kinds
        ):
            continue

        repository_hint = _find_value(
            workload,
            REPOSITORY_KEYS,
        )

        if not _repository_matches(
            repository_hint,
            repository_full_name,
        ):
            continue

        run_id = _find_value(
            workload,
            WORKFLOW_RUN_ID_KEYS,
        )

        if not run_id:
            continue

        run_entity = (
            runs_by_external_id.get(
                run_id
            )
        )

        run_payload = (
            run_payloads_by_id.get(
                run_id
            )
        )

        if (
            run_entity is None
            or run_payload is None
        ):
            warnings.append(
                (
                    f"Workload {workload.name} "
                    f"references workflow run "
                    f"{run_id}, but that run was "
                    "not included in the collected "
                    "GitHub Actions window."
                )
            )

            continue

        if (
            run_payload.get("conclusion")
            != "success"
        ):
            warnings.append(
                (
                    f"Workflow run {run_id} was "
                    "not successful, so no image "
                    "production relationship was "
                    "created."
                )
            )

            continue

        workload_revision = (
            _normalize_sha(
                _find_value(
                    workload,
                    REVISION_KEYS,
                )
            )
        )

        run_revision = str(
            run_payload.get("head_sha")
            or ""
        ).lower()

        revision_matches = bool(
            workload_revision
            and (
                run_revision
                == workload_revision
                or run_revision.startswith(
                    workload_revision
                )
            )
        )

        annotated_digest = (
            _extract_digest(
                _find_value(
                    workload,
                    IMAGE_DIGEST_KEYS,
                )
            )
        )

        for image_id in image_ids:
            image = image_entities.get(
                image_id
            )

            if image is None:
                continue

            graph_digest = (
                _extract_digest(
                    str(
                        image.properties.get(
                            "digest"
                        )
                        or ""
                    )
                )
            )

            digest_matches = bool(
                annotated_digest
                and graph_digest
                and annotated_digest
                == graph_digest
            )

            if (
                annotated_digest
                and graph_digest
                and not digest_matches
            ):
                warnings.append(
                    (
                        f"Image digest mismatch for "
                        f"{workload.name}: metadata "
                        f"contains {annotated_digest}, "
                        f"but runtime contains "
                        f"{graph_digest}."
                    )
                )

                continue

            if (
                revision_matches
                and digest_matches
            ):
                confidence = 0.99
                method = (
                    "run_id_revision_digest"
                )

            elif revision_matches:
                confidence = 0.95
                method = (
                    "run_id_revision"
                )

            else:
                confidence = 0.85
                method = "run_id_only"

            relationship = Relationship(
                id=_relationship_id(
                    run_entity.id,
                    RelationshipType.PRODUCES,
                    image_id,
                ),
                source_entity_id=(
                    run_entity.id
                ),
                target_entity_id=image_id,
                relationship_type=(
                    RelationshipType.PRODUCES
                ),
                source_system=(
                    "github-actions"
                ),
                observed_at=observed_at,
                confidence=confidence,
                directed=True,
                evidence_ids=[
                    evidence_id
                ],
                properties={
                    "mapping_method": method,
                    "workflow_run_id": (
                        run_id
                    ),
                    "workflow_head_sha": (
                        run_revision
                    ),
                    "workload_revision": (
                        workload_revision
                    ),
                    "annotated_digest": (
                        annotated_digest
                    ),
                    "runtime_digest": (
                        graph_digest
                    ),
                    "workload_entity_id": (
                        workload.id
                    ),
                    "workload_kind": (
                        workload.kind
                    ),
                },
            )

            run_image_relationships[
                relationship.id
            ] = relationship

            mapped_run_ids.add(
                run_entity.id
            )

            mapped_image_ids.add(
                image_id
            )

    existing_entity_ids = {
        entity.id
        for entity in result.entities
    }

    for entity in run_entities.values():
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

    new_relationships = [
        *repository_run_relationships.values(),
        *commit_run_relationships.values(),
        *run_image_relationships.values(),
    ]

    for relationship in new_relationships:
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

    result.evidence.append(
        Evidence(
            id=evidence_id,
            evidence_type=(
                EvidenceType.RELATIONSHIP
            ),
            source_system="github-actions",
            summary=(
                "GitHub Actions workflow runs "
                "were connected to Git commits "
                "and container images using run, "
                "revision and image-digest "
                "provenance metadata."
            ),
            observed_at=observed_at,
            related_entity_ids=[
                repository_entity.id,
                *run_entities.keys(),
                *mapped_image_ids,
            ],
            related_relationship_ids=[
                relationship.id
                for relationship
                in new_relationships
            ],
            payload={
                "repository": (
                    repository_full_name
                ),
                "workflow_runs_collected": (
                    len(run_entities)
                ),
                "commit_run_relationships": (
                    len(
                        commit_run_relationships
                    )
                ),
                "run_image_relationships": (
                    len(
                        run_image_relationships
                    )
                ),
                "warnings": warnings,
            },
        )
    )

    base_snapshot_id = result.snapshot_id

    result.snapshot_id = (
        "snapshot:actions-enriched:"
        f"{observed_at.strftime('%Y%m%dT%H%M%SZ')}:"
        f"{str(uuid4())[:8]}"
    )

    result.collected_at = observed_at
    result.collector_name = (
        "github-actions-graph-enricher"
    )
    result.collector_version = "0.1.0"

    result.metadata = {
        **result.metadata,
        "base_snapshot_id": (
            base_snapshot_id
        ),
        "github_actions_enrichment": {
            "repository": (
                repository_full_name
            ),
            "workflow_runs_collected": (
                len(run_entities)
            ),
            "commit_run_relationships": (
                len(
                    commit_run_relationships
                )
            ),
            "run_image_relationships": (
                len(
                    run_image_relationships
                )
            ),
        },
    }

    stats = {
        "workflow_runs_collected": len(
            run_entities
        ),
        "commit_run_relationship_count": (
            len(commit_run_relationships)
        ),
        "run_image_relationship_count": (
            len(run_image_relationships)
        ),
        "mapped_run_count": len(
            mapped_run_ids
        ),
        "mapped_image_count": len(
            mapped_image_ids
        ),
        "unresolved_run_count": (
            len(run_entities)
            - len(mapped_run_ids)
        ),
        "warnings": warnings,
    }

    return result, stats