from app.security.tenant_context import TenantContext, require_tenant_context
from fastapi import Depends
from collections import Counter

from fastapi import APIRouter

from app.models.topology import (
    GraphSnapshot,
    SnapshotValidationResult,
)
from app.services.sample_topology import build_sample_snapshot

router = APIRouter(
    prefix="/api/v1/topology",
    tags=["topology"],
)


def find_duplicates(values: list[str]) -> list[str]:
    counts = Counter(values)

    return [
        value
        for value, count in counts.items()
        if count > 1
    ]


@router.get(
    "/sample",
    response_model=GraphSnapshot,
)
def get_sample_topology() -> GraphSnapshot:
    """
    Return a small sample topology using the canonical graph contract.
    """
    return build_sample_snapshot()


@router.post(
    "/validate",
    response_model=SnapshotValidationResult,
)
def validate_snapshot(
    snapshot: GraphSnapshot,
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> SnapshotValidationResult:
    """
    Validate entity references and graph integrity.
    """
    errors: list[str] = []
    warnings: list[str] = []

    entity_ids = [
        entity.id
        for entity in snapshot.entities
    ]

    relationship_ids = [
        relationship.id
        for relationship in snapshot.relationships
    ]

    evidence_ids = [
        evidence.id
        for evidence in snapshot.evidence
    ]

    duplicate_entities = find_duplicates(entity_ids)
    duplicate_relationships = find_duplicates(relationship_ids)
    duplicate_evidence = find_duplicates(evidence_ids)

    if duplicate_entities:
        errors.append(
            f"Duplicate entity IDs: {duplicate_entities}"
        )

    if duplicate_relationships:
        errors.append(
            "Duplicate relationship IDs: "
            f"{duplicate_relationships}"
        )

    if duplicate_evidence:
        errors.append(
            f"Duplicate evidence IDs: {duplicate_evidence}"
        )

    entity_id_set = set(entity_ids)
    relationship_id_set = set(relationship_ids)
    evidence_id_set = set(evidence_ids)

    for relationship in snapshot.relationships:
        if relationship.source_entity_id not in entity_id_set:
            errors.append(
                f"Relationship {relationship.id} has an unknown "
                f"source entity: {relationship.source_entity_id}"
            )

        if relationship.target_entity_id not in entity_id_set:
            errors.append(
                f"Relationship {relationship.id} has an unknown "
                f"target entity: {relationship.target_entity_id}"
            )

        for evidence_id in relationship.evidence_ids:
            if evidence_id not in evidence_id_set:
                warnings.append(
                    f"Relationship {relationship.id} references "
                    f"unknown evidence: {evidence_id}"
                )

    for evidence in snapshot.evidence:
        for entity_id in evidence.related_entity_ids:
            if entity_id not in entity_id_set:
                errors.append(
                    f"Evidence {evidence.id} references unknown "
                    f"entity: {entity_id}"
                )

        for relationship_id in evidence.related_relationship_ids:
            if relationship_id not in relationship_id_set:
                errors.append(
                    f"Evidence {evidence.id} references unknown "
                    f"relationship: {relationship_id}"
                )

    if not snapshot.entities:
        warnings.append(
            "The snapshot contains no entities."
        )

    return SnapshotValidationResult(
        valid=not errors,
        entity_count=len(snapshot.entities),
        relationship_count=len(snapshot.relationships),
        evidence_count=len(snapshot.evidence),
        errors=errors,
        warnings=warnings,
    )
