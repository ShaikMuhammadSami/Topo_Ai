from __future__ import annotations

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
    RelationshipOrigin,
    RelationshipType,
)
from app.services.canonical_identity import (
    canonical_github_workflow_run_identity,
)
from app.services.relationship_provenance import (
    relationship_provenance,
    source_reference,
)


def _workflow_run_entity_id(
    api_url: str,
    run_id: int | str,
) -> str:
    return canonical_github_workflow_run_identity(
        api_url=api_url,
        run_id=run_id,
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


def _normalize_repository(
    value: str,
) -> str:
    normalized = value.strip().lower().removesuffix(".git")

    if normalized.startswith("git@github.com:"):
        normalized = normalized.replace("git@github.com:", "", 1)

    for prefix in (
        "https://github.com/",
        "http://github.com/",
        "ssh://git@github.com/",
    ):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]

    return normalized.strip("/")


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

    run_entities: dict[
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

    for run in workflow_runs:
        run_id = run.get("id")

        if run_id is None:
            continue

        external_run_id = str(run_id)

        run_identity = canonical_github_workflow_run_identity(
            api_url=api_url,
            run_id=run_id,
        )
        run_entity_id = run_identity.canonical_id

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
            aliases=run_identity.aliases,
            identity_version=(
                run_identity.identity_version
            ),
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
                directed=True,
                evidence_ids=[
                    evidence_id
                ],
                provenance=relationship_provenance(
                    predicate=RelationshipType.CONTAINS,
                    origin=RelationshipOrigin.OBSERVED,
                    source_component=(
                        "backend.app.services.github_actions_graph"
                    ),
                    source_references=[
                        source_reference(
                            reference_type="github_repository_id",
                            reference=repository_entity.external_id,
                            source_system="github",
                        ),
                        source_reference(
                            reference_type="github_workflow_run_id",
                            reference=external_run_id,
                            source_system="github-actions",
                        ),
                    ],
                    linker_version="github-actions-run-linker:v1",
                ),
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
            directed=True,
            evidence_ids=[
                evidence_id
            ],
            provenance=relationship_provenance(
                predicate=RelationshipType.TRIGGERS,
                origin=RelationshipOrigin.OBSERVED,
                source_component=(
                    "backend.app.services.github_actions_graph"
                ),
                source_references=[
                    source_reference(
                        reference_type="git_commit_sha",
                        reference=head_sha,
                        source_system="github",
                    ),
                    source_reference(
                        reference_type="github_workflow_run_id",
                        reference=external_run_id,
                        source_system="github-actions",
                    ),
                ],
                linker_version="github-actions-trigger-linker:v1",
            ),
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

    run_image_relationships: dict[
        str,
        Relationship,
    ] = {}

    warnings: list[str] = []

    mapped_run_ids: set[str] = set()
    mapped_image_ids: set[str] = set()

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
                "were connected to Git repositories "
                "and commits using provider-native "
                "run metadata. Immutable artifact "
                "lineage requires separate explicit "
                "provider build evidence."
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
