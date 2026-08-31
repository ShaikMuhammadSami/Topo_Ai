from __future__ import annotations
from app.repositories.tenant_scope import (
    DomainTenant,
)

import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.connectors.github_connector import GitHubConnector, GitHubConnectorError
from app.models.build_artifacts import (
    BuildArtifactEvidence,
    BuildArtifactLineageStats,
)
from app.models.topology import (
    Evidence,
    EvidenceType,
    GraphSnapshot,
    Relationship,
    RelationshipOrigin,
    RelationshipProvenanceCompleteness,
    RelationshipType,
)
from app.repositories.build_artifact_evidence_repository import (
    list_build_artifact_evidence,
    save_build_artifact_evidence,
)
from app.services.canonical_identity import (
    canonical_container_image_identity,
    canonical_git_repository_identity,
    canonical_github_workflow_run_identity,
)
from app.services.github_actions_build_record import (
    parse_github_actions_docker_build_record,
)
from app.services.github_actions_graph import augment_snapshot_with_github_actions
from app.services.relationship_provenance import (
    relationship_provenance,
    source_reference,
)
from app.services.temporal_semantics import build_temporal_metadata
from app.models.temporal import TimeOrigin, TimeQuality

SOURCE_COMPONENT = "backend.app.services.github_actions_artifact_lineage"
LINKER_VERSION = "github-actions-build-artifact-lineage:v1"


def _relationship_id(source_id: str, target_id: str) -> str:
    value = f"{source_id}|{RelationshipType.PRODUCES.value}|{target_id}"
    return "rel:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def _graph_evidence_id(relationship_id: str, evidence_ids: list[str]) -> str:
    value = relationship_id + "|" + "|".join(sorted(evidence_ids))
    return "evidence:github-actions-build:" + hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:24]


def _normalized_image_repository(reference: str) -> str:
    value = reference.strip().lower().split("@", 1)[0]
    slash = value.rfind("/")
    colon = value.rfind(":")
    return value[:colon] if colon > slash else value


def _image_repository_matches(entity: Any, expected: str) -> bool:
    properties = entity.properties
    candidates: set[str] = set()
    registry = str(properties.get("registry") or "").strip().lower()
    repository = str(properties.get("repository") or "").strip().lower()
    if repository:
        candidates.add(f"{registry}/{repository}" if registry else repository)
    for value in properties.get("requested_references") or []:
        if isinstance(value, str):
            candidates.add(_normalized_image_repository(value))
    return expected.strip().lower() in candidates


def _replace_relationship(
    snapshot: GraphSnapshot,
    relationship: Relationship,
) -> None:
    for index, existing in enumerate(snapshot.relationships):
        if existing.id == relationship.id:
            snapshot.relationships[index] = relationship
            return
    snapshot.relationships.append(relationship)


def reconcile_build_artifact_lineage(
    snapshot: GraphSnapshot,
    *,
    evidence: list[BuildArtifactEvidence],
    api_url: str,
) -> tuple[GraphSnapshot, BuildArtifactLineageStats]:
    """Resolve durable explicit provider evidence against one current graph."""

    result = snapshot.model_copy(deep=True)
    entities_by_id: dict[str, list[Any]] = {}
    for entity in result.entities:
        entities_by_id.setdefault(entity.id, []).append(entity)

    warnings: list[str] = []
    relationships: dict[str, list[BuildArtifactEvidence]] = {}
    mapped_runs: set[str] = set()
    mapped_images: set[str] = set()
    unresolved = 0

    for item in sorted(evidence, key=lambda value: value.evidence_id):
        repository_id = canonical_git_repository_identity(
            provider="github",
            api_url=api_url,
            repository_native_id=item.repository_id,
        ).canonical_id
        run_id = canonical_github_workflow_run_identity(
            api_url=api_url,
            run_id=item.run_id,
        ).canonical_id
        image_id = canonical_container_image_identity(
            normalized_reference=item.immutable_image_ref,
            digest=item.image_digest,
        ).canonical_id
        runs = entities_by_id.get(run_id, [])
        images = entities_by_id.get(image_id, [])
        if len(runs) != 1:
            unresolved += 1
            code = "RUN_ENTITY_MISSING" if not runs else "RUN_ENTITY_AMBIGUOUS"
            warnings.append(f"build_artifact_unresolved:{code}:evidence={item.evidence_id}")
            continue
        if len(images) != 1:
            unresolved += 1
            code = "IMAGE_ENTITY_MISSING" if not images else "IMAGE_ENTITY_AMBIGUOUS"
            warnings.append(f"build_artifact_unresolved:{code}:evidence={item.evidence_id}")
            continue
        run = runs[0]
        image = images[0]
        run_properties = run.properties
        if (
            run.kind != "GitHubWorkflowRun"
            or str(run.external_id or "") != item.run_id
            or str(run_properties.get("run_id") or "") != item.run_id
            or run_properties.get("run_attempt") != item.run_attempt
            or str(run_properties.get("head_sha") or "").lower() != item.commit_sha
        ):
            unresolved += 1
            warnings.append(
                f"build_artifact_unresolved:RUN_IDENTITY_MISMATCH:evidence={item.evidence_id}"
            )
            continue
        repository_scope = any(
            relationship.source_entity_id == repository_id
            and relationship.target_entity_id == run_id
            and relationship.relationship_type == RelationshipType.CONTAINS
            for relationship in result.relationships
        )
        if not repository_scope:
            unresolved += 1
            warnings.append(
                f"build_artifact_unresolved:RUN_REPOSITORY_SCOPE_MISMATCH:evidence={item.evidence_id}"
            )
            continue
        if (
            image.kind != "ContainerImage"
            or str(image.external_id or "").lower() != item.image_digest
            or str(image.properties.get("digest") or "").lower() != item.image_digest
            or image.properties.get("immutable") is not True
            or not _image_repository_matches(image, item.image_repository)
        ):
            unresolved += 1
            warnings.append(
                f"build_artifact_unresolved:IMAGE_IDENTITY_MISMATCH:evidence={item.evidence_id}"
            )
            continue
        relationship_id = _relationship_id(run_id, image_id)
        relationships.setdefault(relationship_id, []).append(item)
        mapped_runs.add(run_id)
        mapped_images.add(image_id)

    graph_evidence: list[Evidence] = []
    for relationship_id in sorted(relationships):
        items = sorted(relationships[relationship_id], key=lambda value: value.evidence_id)
        first = items[0]
        run_id = canonical_github_workflow_run_identity(
            api_url=api_url, run_id=first.run_id
        ).canonical_id
        image_id = canonical_container_image_identity(
            normalized_reference=first.immutable_image_ref,
            digest=first.image_digest,
        ).canonical_id
        observed_at = min(item.observed_at for item in items)
        run_updated_at = min(item.provider_run_updated_at for item in items)
        temporal = build_temporal_metadata(
            source_event_at=run_updated_at,
            observed_at=observed_at,
            recorded_at=observed_at,
            source_time_trusted=True,
            source_field="github_workflow_run.updated_at",
            source_origin=TimeOrigin.SOURCE_REPORTED,
            source_quality=TimeQuality.EXACT,
        )
        references = []
        for item in items:
            references.extend(
                [
                    source_reference(
                        reference_type="github_repository_id",
                        reference=item.repository_id,
                        source_system="github",
                    ),
                    source_reference(
                        reference_type="github_workflow_run_id",
                        reference=item.run_id,
                        source_system="github-actions",
                    ),
                    source_reference(
                        reference_type="github_workflow_run_attempt",
                        reference=item.run_attempt,
                        source_system="github-actions",
                    ),
                    source_reference(
                        reference_type="github_actions_artifact_id",
                        reference=item.provider_evidence_id,
                        source_system="github-actions",
                    ),
                    source_reference(
                        reference_type="github_actions_artifact",
                        reference=item.provider_evidence_reference,
                        source_system="github-actions",
                    ),
                    source_reference(
                        reference_type="github_actions_artifact_digest",
                        reference=item.provider_evidence_digest,
                        source_system="github-actions",
                    ),
                    source_reference(
                        reference_type="docker_build_record_digest",
                        reference=item.provider_build_record_digest,
                        source_system="docker-buildx",
                    ),
                    source_reference(
                        reference_type="provider_builder_id",
                        reference=item.provider_builder_id,
                        source_system="github-actions",
                    ),
                    source_reference(
                        reference_type="container_image_digest",
                        reference=item.image_digest,
                        source_system="docker-buildx",
                    ),
                    source_reference(
                        reference_type="immutable_image_reference",
                        reference=item.immutable_image_ref,
                        source_system="docker-buildx",
                    ),
                    source_reference(
                        reference_type="git_commit_sha",
                        reference=item.commit_sha,
                        source_system="github",
                    ),
                ]
            )
            if item.workflow_id:
                references.append(
                    source_reference(
                        reference_type="github_workflow_id",
                        reference=item.workflow_id,
                        source_system="github-actions",
                    )
                )
            if item.workflow_ref:
                references.append(
                    source_reference(
                        reference_type="github_workflow_ref",
                        reference=item.workflow_ref,
                        source_system="github-actions",
                    )
                )
        graph_evidence_id = _graph_evidence_id(
            relationship_id, [item.evidence_id for item in items]
        )
        relationship = Relationship(
            id=relationship_id,
            source_entity_id=run_id,
            target_entity_id=image_id,
            relationship_type=RelationshipType.PRODUCES,
            source_system="github-actions",
            observed_at=observed_at,
            temporal=temporal,
            directed=True,
            evidence_ids=[graph_evidence_id],
            provenance=relationship_provenance(
                predicate=RelationshipType.PRODUCES,
                origin=RelationshipOrigin.OBSERVED,
                source_component=SOURCE_COMPONENT,
                source_references=references,
                completeness=RelationshipProvenanceCompleteness.COMPLETE,
                linker_version=LINKER_VERSION,
            ),
            properties={
                "mapping_method": "provider_docker_build_record",
                "repository_id": first.repository_id,
                "workflow_run_id": first.run_id,
                "workflow_run_attempt": first.run_attempt,
                "image_repository": first.image_repository,
                "image_digest": first.image_digest,
                "provider_evidence_ids": [item.evidence_id for item in items],
                "provider_build_started_at": [
                    item.provider_build_started_at.isoformat()
                    for item in items
                    if item.provider_build_started_at
                ],
                "provider_build_finished_at": [
                    item.provider_build_finished_at.isoformat()
                    for item in items
                    if item.provider_build_finished_at
                ],
            },
        )
        _replace_relationship(result, relationship)
        graph_evidence.append(
            Evidence(
                id=graph_evidence_id,
                evidence_type=EvidenceType.RELATIONSHIP,
                source_system="github-actions",
                summary=(
                    "Provider-managed Docker build records establish an exact "
                    "GitHub Actions run-to-immutable-image relationship."
                ),
                observed_at=observed_at,
                temporal=temporal,
                related_entity_ids=[run_id, image_id],
                related_relationship_ids=[relationship_id],
                payload={
                    "provider_evidence_type": first.provider_evidence_type.value,
                    "provider_evidence_ids": [item.evidence_id for item in items],
                    "run_id": first.run_id,
                    "run_attempt": first.run_attempt,
                    "image_digest": first.image_digest,
                },
            )
        )
    existing_evidence_ids = {item.id for item in result.evidence}
    result.evidence.extend(
        item for item in graph_evidence if item.id not in existing_evidence_ids
    )
    result.metadata = {
        **result.metadata,
        "github_actions_build_artifact_lineage": {
            "evidence_records_considered": len(evidence),
            "relationship_count": len(relationships),
            "unresolved_evidence_count": unresolved,
        },
    }
    return result, BuildArtifactLineageStats(
        evidence_records_considered=len(evidence),
        relationship_count=len(relationships),
        mapped_run_count=len(mapped_runs),
        mapped_image_count=len(mapped_images),
        unresolved_evidence_count=unresolved,
        warnings=sorted(set(warnings)),
    )


def enrich_snapshot_with_github_actions_provider_evidence(
    session: Session,
    *,
    snapshot: GraphSnapshot,
    connector: GitHubConnector,
    repository: dict[str, Any],
    workflow_runs: list[dict[str, Any]],
    observed_at: datetime | None = None,
    tenant_id: DomainTenant,
) -> tuple[GraphSnapshot, dict[str, Any], BuildArtifactLineageStats]:
    """Collect, retain, and reconcile explicit provider build evidence."""

    from app.services.tenant_world_model import bind_world_value

    bind_world_value(snapshot, tenant_id=tenant_id)

    observed = observed_at or datetime.now(timezone.utc)
    repository_name = str(
        repository.get("full_name") or connector.settings.full_name
    )
    base, graph_stats = augment_snapshot_with_github_actions(
        snapshot=snapshot,
        workflow_runs=workflow_runs,
        repository_full_name=repository_name,
        api_url=connector.settings.api_url,
    )
    warnings: list[str] = []
    inspected = 0
    accepted = 0
    persisted = 0
    for run in workflow_runs:
        run_id = run.get("id")
        if run_id is None or run.get("conclusion") != "success":
            continue
        try:
            artifacts = connector.list_workflow_run_artifacts(run_id)
        except GitHubConnectorError:
            warnings.append(
                f"build_artifact_provider_unavailable:run={run_id}"
            )
            continue
        for artifact in artifacts:
            if not str(artifact.get("name") or "").casefold().endswith(".dockerbuild"):
                continue
            inspected += 1
            if artifact.get("expired") is True:
                warnings.append(
                    f"build_artifact_rejected:PROVIDER_ARTIFACT_EXPIRED:artifact={artifact.get('id')}"
                )
                continue
            try:
                payload = connector.download_actions_artifact(artifact["id"])
            except (KeyError, GitHubConnectorError):
                warnings.append(
                    f"build_artifact_provider_unavailable:artifact={artifact.get('id')}"
                )
                continue
            parsed = parse_github_actions_docker_build_record(
                artifact=artifact,
                artifact_payload=payload,
                repository=repository,
                workflow_run=run,
                observed_at=observed,
            )
            warnings.extend(parsed.warnings)
            if parsed.evidence:
                accepted += 1
            for item in parsed.evidence:
                _saved, created = save_build_artifact_evidence(
                    session,
                    evidence=item,
                    commit=False,
                    tenant_id=tenant_id,
                )
                persisted += int(created)
    run_ids = {str(run["id"]) for run in workflow_runs if run.get("id") is not None}
    durable = list_build_artifact_evidence(
        session,
        repository_id=str(repository.get("id") or ""),
        run_ids=run_ids,
        tenant_id=tenant_id,
    )
    result, lineage = reconcile_build_artifact_lineage(
        base,
        evidence=durable,
        api_url=connector.settings.api_url,
    )
    all_warnings = sorted(set(warnings + graph_stats["warnings"] + lineage.warnings))
    combined = {
        **graph_stats,
        "run_image_relationship_count": lineage.relationship_count,
        "mapped_run_count": lineage.mapped_run_count,
        "mapped_image_count": lineage.mapped_image_count,
        "unresolved_run_count": max(
            0, graph_stats["unresolved_run_count"] - lineage.mapped_run_count
        ),
        "warnings": all_warnings,
    }
    lineage = lineage.model_copy(
        update={
            "provider_artifacts_inspected": inspected,
            "provider_build_records_accepted": accepted,
            "evidence_records_persisted": persisted,
            "warnings": all_warnings,
        }
    )
    return result, combined, lineage
