from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from app.models.topology import (
    RelationshipOrigin,
    RelationshipProvenance,
    RelationshipProvenanceCompleteness,
    RelationshipSourceReference,
    RelationshipType,
)


RELATIONSHIP_LINKER_VERSION = "tc2.v1"

ACTIVE_RELATIONSHIP_PREDICATES = frozenset(
    {
        "attached_to",
        "calls",
        "contains",
        "depends_on",
        "exposes",
        "owns",
        "produces",
        "protects",
        "resolves_to",
        "routes_to",
        "runs",
        "selects",
        "triggers",
        "uses",
    }
)


def source_reference(
    *,
    reference_type: str,
    reference: Any,
    source_system: str,
    attributes: dict[str, Any] | None = None,
) -> RelationshipSourceReference | None:
    """Return a real source reference, or nothing when no value exists."""

    if reference is None:
        return None

    if isinstance(reference, str):
        normalized = reference.strip()
    else:
        normalized = json.dumps(
            reference,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

    if not normalized:
        return None

    return RelationshipSourceReference(
        reference_type=reference_type,
        reference=normalized,
        source_system=source_system,
        attributes=attributes or {},
    )


def relationship_provenance(
    *,
    predicate: RelationshipType | str,
    origin: RelationshipOrigin,
    source_component: str,
    source_references: Iterable[
        RelationshipSourceReference | None
    ] = (),
    completeness: RelationshipProvenanceCompleteness | None = None,
    linker_version: str = RELATIONSHIP_LINKER_VERSION,
) -> RelationshipProvenance:
    """Build deterministic provenance without manufacturing evidence IDs."""

    predicate_value = (
        predicate.value
        if isinstance(predicate, RelationshipType)
        else str(predicate).lower()
    )
    if predicate_value not in ACTIVE_RELATIONSHIP_PREDICATES:
        raise ValueError(
            "Relationship predicate is not registered as actively "
            f"constructed: {predicate_value}"
        )

    unique: dict[str, RelationshipSourceReference] = {}

    for item in source_references:
        if item is None:
            continue

        key = json.dumps(
            item.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        unique[key] = item

    ordered = [
        unique[key]
        for key in sorted(unique)
    ]

    resolved_completeness = completeness
    if resolved_completeness is None:
        resolved_completeness = (
            RelationshipProvenanceCompleteness.COMPLETE
            if ordered
            else RelationshipProvenanceCompleteness.PARTIAL
        )

    return RelationshipProvenance(
        origin=origin,
        source_component=source_component,
        source_references=ordered,
        linker_version=linker_version,
        completeness=resolved_completeness,
    )
