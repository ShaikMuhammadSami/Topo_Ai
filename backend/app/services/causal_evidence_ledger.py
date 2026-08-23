from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable

from app.models.canonical_identity import (
    CanonicalIdentityResolution,
    CanonicalIdentityResolutionStatus,
)
from app.models.causal_rca import (
    CAUSAL_EVIDENCE_LEDGER_VERSION,
    CausalEvidenceClaimType,
    CausalEvidenceLedger,
    CausalEvidenceLedgerItem,
    CausalEvidenceQuality,
    CausalEvidenceSourceCategory,
    CausalEvidenceSourceReference,
    CausalEvidenceStance,
    CausalRelationshipEvidenceReference,
)
from app.models.change_events import IncidentChangeCandidate
from app.models.signals import NormalizedSignal
from app.models.temporal import (
    TemporalStatus,
    TimeOrigin,
)
from app.models.topology import (
    Entity,
    GraphSnapshot,
    Relationship,
    RelationshipOrigin,
    RelationshipProvenanceCompleteness,
    RelationshipType,
)
from app.services.canonical_identity import (
    resolve_snapshot_entity_identity,
)


def _enum_value(value: Any) -> str:
    return str(value.value) if hasattr(value, "value") else str(value)


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _dedupe_sorted(values: Iterable[str | None]) -> list[str]:
    return sorted({str(value) for value in values if value})


def _canonical_references(
    references: Iterable[CausalEvidenceSourceReference],
) -> list[CausalEvidenceSourceReference]:
    unique: dict[str, CausalEvidenceSourceReference] = {}
    for reference in references:
        key = json.dumps(
            reference.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        unique[key] = reference
    return [unique[key] for key in sorted(unique)]


def _reference(
    reference_type: str,
    reference_id: str,
    *,
    source_system: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> CausalEvidenceSourceReference:
    return CausalEvidenceSourceReference(
        reference_type=reference_type,
        reference_id=reference_id,
        source_system=source_system,
        attributes=attributes or {},
    )


def _evidence_id(
    *,
    hypothesis_id: str,
    stance: CausalEvidenceStance,
    claim_type: CausalEvidenceClaimType,
    source_references: list[CausalEvidenceSourceReference],
    entity_ids: list[str],
    relationship_ids: list[str],
    change_event_ids: list[str],
    signal_ids: list[str],
    snapshot_id: str | None,
) -> str:
    # Deliberately excludes prose, timestamps, backend recorded_at, quality,
    # and provenance serialization. Identity follows the durable facts that
    # make this the same logical evidence claim.
    identity = {
        "ledger_version": CAUSAL_EVIDENCE_LEDGER_VERSION,
        "hypothesis_id": hypothesis_id,
        "stance": stance.value,
        "claim_type": claim_type.value,
        "source_references": sorted(
            (
                item.reference_type,
                item.reference_id,
                item.source_system or "",
            )
            for item in source_references
        ),
        "entity_ids": entity_ids,
        "relationship_ids": relationship_ids,
        "change_event_ids": change_event_ids,
        "signal_ids": signal_ids,
        "snapshot_id": snapshot_id,
    }
    digest = hashlib.sha256(
        json.dumps(
            identity,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:32]
    return f"causal-ledger-evidence:{digest}"


def _item(
    *,
    hypothesis_id: str,
    stance: CausalEvidenceStance,
    claim_type: CausalEvidenceClaimType,
    summary: str,
    reason: str,
    source_category: CausalEvidenceSourceCategory,
    quality: CausalEvidenceQuality,
    why_it_matters: str,
    source_references: Iterable[CausalEvidenceSourceReference] = (),
    entity_ids: Iterable[str] = (),
    relationship_ids: Iterable[str] = (),
    change_event_ids: Iterable[str] = (),
    signal_ids: Iterable[str] = (),
    snapshot_id: str | None = None,
    temporal=None,
    incident_boundary_at: str | None = None,
    relationship: CausalRelationshipEvidenceReference | None = None,
    identity_resolution: CanonicalIdentityResolution | None = None,
    expectation_basis: str | None = None,
) -> CausalEvidenceLedgerItem:
    references = _canonical_references(source_references)
    entities = _dedupe_sorted(entity_ids)
    relationships = _dedupe_sorted(relationship_ids)
    events = _dedupe_sorted(change_event_ids)
    signals = _dedupe_sorted(signal_ids)
    return CausalEvidenceLedgerItem(
        evidence_id=_evidence_id(
            hypothesis_id=hypothesis_id,
            stance=stance,
            claim_type=claim_type,
            source_references=references,
            entity_ids=entities,
            relationship_ids=relationships,
            change_event_ids=events,
            signal_ids=signals,
            snapshot_id=snapshot_id,
        ),
        hypothesis_id=hypothesis_id,
        stance=stance,
        claim_type=claim_type,
        summary=summary,
        reason=reason,
        source_category=source_category,
        source_references=references,
        entity_ids=entities,
        relationship_ids=relationships,
        change_event_ids=events,
        signal_ids=signals,
        snapshot_id=snapshot_id,
        temporal=temporal,
        incident_boundary_at=incident_boundary_at,
        relationship=relationship,
        identity_resolution=identity_resolution,
        quality=quality,
        why_it_matters=why_it_matters,
        expectation_basis=expectation_basis,
    )


def _relationship_reference(
    relationship: Relationship,
    *,
    left_entity_id: str,
) -> CausalRelationshipEvidenceReference:
    provenance = relationship.provenance
    return CausalRelationshipEvidenceReference(
        relationship_id=relationship.id,
        predicate=relationship.relationship_type.value,
        direction=(
            "forward"
            if relationship.source_entity_id == left_entity_id
            else "reverse"
        ),
        origin=provenance.origin if provenance is not None else None,
        source_component=(
            provenance.source_component if provenance is not None else None
        ),
        source_references=(
            list(provenance.source_references)
            if provenance is not None
            else []
        ),
        linker_version=(
            provenance.linker_version if provenance is not None else None
        ),
        completeness=(
            provenance.completeness
            if provenance is not None
            else RelationshipProvenanceCompleteness.LEGACY_UNSPECIFIED
        ),
    )


def _relationship_quality(
    relationship: Relationship,
) -> CausalEvidenceQuality:
    provenance = relationship.provenance
    if provenance is None:
        return CausalEvidenceQuality.LEGACY
    if provenance.completeness != RelationshipProvenanceCompleteness.COMPLETE:
        return CausalEvidenceQuality.LIMITED
    if provenance.origin in {
        RelationshipOrigin.OBSERVED,
        RelationshipOrigin.DECLARED,
    }:
        return CausalEvidenceQuality.DIRECT
    if provenance.origin == RelationshipOrigin.DERIVED:
        return CausalEvidenceQuality.STRONG
    return CausalEvidenceQuality.LIMITED


def _relationship_between(
    snapshot: GraphSnapshot,
    left_entity_id: str,
    right_entity_id: str,
) -> Relationship | None:
    matches = [
        relationship
        for relationship in snapshot.relationships
        if {
            relationship.source_entity_id,
            relationship.target_entity_id,
        }
        == {left_entity_id, right_entity_id}
    ]
    return sorted(matches, key=lambda item: item.id)[0] if matches else None


def _identity_resolutions(
    snapshot: GraphSnapshot,
    candidate: IncidentChangeCandidate,
) -> list[CanonicalIdentityResolution]:
    raw_refs = candidate.event.metadata.get("entity_refs", [])
    if not isinstance(raw_refs, list):
        return []
    results: list[CanonicalIdentityResolution] = []
    for raw in raw_refs:
        if not isinstance(raw, dict):
            continue
        native = raw.get("external_id") or raw.get("provider_resource_id")
        results.append(
            resolve_snapshot_entity_identity(
                snapshot,
                identifier=(str(raw["entity_id"]) if raw.get("entity_id") else None),
                source_native_id=str(native) if native else None,
                kind=str(raw["kind"]) if raw.get("kind") else None,
                name=str(raw["name"]) if raw.get("name") else None,
                cluster_name=(
                    str(raw["cluster_name"])
                    if raw.get("cluster_name")
                    else candidate.event.cluster_name
                ),
                namespace=(
                    str(raw["namespace"])
                    if raw.get("namespace")
                    else candidate.event.namespace
                ),
                account_id=candidate.event.account_id,
                project_id=(
                    candidate.event.account_id
                    if _enum_value(candidate.event.source) == "gcp_audit_log"
                    else None
                ),
                subscription_id=(
                    candidate.event.account_id
                    if _enum_value(candidate.event.source) == "azure_activity_log"
                    else None
                ),
            )
        )
    return results


def _entity_by_id(snapshot: GraphSnapshot | None) -> dict[str, Entity]:
    return (
        {entity.id: entity for entity in snapshot.entities}
        if snapshot is not None
        else {}
    )


def _is_workload(entity: Entity | None) -> bool:
    if entity is None:
        return False
    return entity.entity_type.value in {"workload", "runtime_instance"} or any(
        token in entity.kind.casefold()
        for token in ("deployment", "replicaset", "pod", "workload")
    )


def _scope_conflicts(candidate: IncidentChangeCandidate, incident: Any) -> list[str]:
    conflicts: list[str] = []
    pairs = (
        ("cluster", candidate.event.cluster_name, getattr(incident, "cluster_name", None)),
        ("namespace", candidate.event.namespace, getattr(incident, "namespace", None)),
        ("environment", candidate.event.environment, getattr(incident, "environment", None)),
    )
    for label, event_value, incident_value in pairs:
        if (
            event_value
            and incident_value
            and str(event_value).casefold() != str(incident_value).casefold()
        ):
            conflicts.append(
                f"Candidate {label} '{event_value}' differs from incident "
                f"{label} '{incident_value}'."
            )
    return conflicts


def build_hypothesis_evidence_ledger(
    *,
    hypothesis_id: str,
    candidate: IncidentChangeCandidate,
    candidate_by_event: dict[str, IncidentChangeCandidate],
    event_chain: list[str],
    entity_path: list[str] | None,
    incident: Any,
    incident_time: datetime,
    snapshot: GraphSnapshot | None,
    primary_signal: NormalizedSignal | None,
) -> CausalEvidenceLedger:
    items: dict[str, CausalEvidenceLedgerItem] = {}

    def add(item: CausalEvidenceLedgerItem) -> None:
        items[item.evidence_id] = item

    snapshot_id = snapshot.snapshot_id if snapshot is not None else None
    entity_index = _entity_by_id(snapshot)

    # Durable change records establish that each event in the chosen lineage
    # exists. They do not independently prove causality.
    for event_id in event_chain:
        chain_candidate = candidate_by_event[event_id]
        event = chain_candidate.event
        references = [
            _reference(
                "change_event",
                event.event_id,
                source_system=_enum_value(event.source),
            )
        ]
        if event.origin_change_id:
            references.append(
                _reference("normalized_change", event.origin_change_id)
            )
        add(
            _item(
                hypothesis_id=hypothesis_id,
                stance=CausalEvidenceStance.SUPPORTING,
                claim_type=CausalEvidenceClaimType.SOURCE_CHANGE,
                summary="Durable change evidence exists for this candidate.",
                reason=(
                    f"Change event '{event.event_id}' is persisted from "
                    f"source '{_enum_value(event.source)}'. This establishes "
                    "the event, not causality by itself."
                ),
                source_category=CausalEvidenceSourceCategory.CHANGE,
                quality=CausalEvidenceQuality.DIRECT,
                why_it_matters=(
                    "A causal hypothesis must reference an inspectable change "
                    "rather than generated prose."
                ),
                source_references=references,
                change_event_ids=[event.event_id],
            )
        )

        temporal = event.temporal
        effective_at = (
            temporal.effective_at
            if temporal is not None
            else _parse_time(event.occurred_at)
        )
        minutes_before = (incident_time - effective_at).total_seconds() / 60
        source_time_authoritative = bool(
            temporal is not None and temporal.source_time_authoritative
        )
        if source_time_authoritative:
            temporal_stance = (
                CausalEvidenceStance.SUPPORTING
                if minutes_before >= 0
                else CausalEvidenceStance.CONTRADICTING
            )
            add(
                _item(
                    hypothesis_id=hypothesis_id,
                    stance=temporal_stance,
                    claim_type=CausalEvidenceClaimType.TEMPORAL_PRECEDENCE,
                    summary=(
                        "The change precedes the incident boundary."
                        if minutes_before >= 0
                        else "The change follows the incident boundary."
                    ),
                    reason=(
                        f"Change effective_at is {effective_at.isoformat()} and "
                        f"incident boundary is {incident_time.isoformat()} "
                        f"({abs(minutes_before):.2f} minutes "
                        f"{'before' if minutes_before >= 0 else 'after'})."
                    ),
                    source_category=CausalEvidenceSourceCategory.TEMPORAL,
                    quality=CausalEvidenceQuality.DIRECT,
                    why_it_matters=(
                        "A cause must occur before the effect; a genuinely "
                        "post-incident change conflicts with temporal precedence."
                    ),
                    source_references=references,
                    change_event_ids=[event.event_id],
                    temporal=temporal,
                    incident_boundary_at=incident_time.isoformat(),
                )
            )
        else:
            quality = (
                CausalEvidenceQuality.LEGACY
                if temporal is None
                or temporal.status == TemporalStatus.LEGACY_UNSPECIFIED
                or temporal.time_origin == TimeOrigin.LEGACY_UNKNOWN
                else CausalEvidenceQuality.LIMITED
            )
            add(
                _item(
                    hypothesis_id=hypothesis_id,
                    stance=CausalEvidenceStance.MISSING,
                    claim_type=CausalEvidenceClaimType.TEMPORAL_PRECEDENCE,
                    summary="Authoritative source event time is unavailable.",
                    reason=(
                        "Temporal ordering uses a legacy effective-time fallback."
                        if temporal is None
                        else (
                            "Temporal ordering uses the explicitly labeled "
                            f"{temporal.time_origin.value}/"
                            f"{temporal.time_quality.value} effective-time fallback."
                        )
                    ),
                    source_category=CausalEvidenceSourceCategory.TEMPORAL,
                    quality=quality,
                    why_it_matters=(
                        "Source time would distinguish customer-system event "
                        "time from when Topo observed or recorded the change."
                    ),
                    expectation_basis=(
                        "This change is used in causal temporal ordering, so "
                        "authoritative source time would materially strengthen "
                        "or weaken the hypothesis."
                    ),
                    source_references=references,
                    change_event_ids=[event.event_id],
                    temporal=temporal,
                    incident_boundary_at=incident_time.isoformat(),
                )
            )

    # Preserve only lineage already selected by the current 13C algorithm.
    for predecessor, successor in zip(event_chain, event_chain[1:]):
        add(
            _item(
                hypothesis_id=hypothesis_id,
                stance=CausalEvidenceStance.SUPPORTING,
                claim_type=CausalEvidenceClaimType.EVENT_LINEAGE,
                summary="The current 13C event chain links two durable changes.",
                reason=(
                    f"The existing deterministic lineage selected "
                    f"'{predecessor}' before '{successor}'."
                ),
                source_category=CausalEvidenceSourceCategory.LINEAGE,
                quality=CausalEvidenceQuality.STRONG,
                why_it_matters=(
                    "The hypothesis root and target remain traceable to the "
                    "same event lineage used by the existing ranker."
                ),
                source_references=[
                    _reference("change_event", predecessor),
                    _reference("change_event", successor),
                ],
                change_event_ids=[predecessor, successor],
            )
        )

    event = candidate.event
    links = sorted(event.links, key=lambda item: item.link_id)
    linked_ids = _dedupe_sorted(
        [link.entity_id for link in links]
        + candidate.direct_entity_matches
        + candidate.neighboring_entity_matches
    )
    link_references = [
        _reference(
            "change_entity_link",
            link.link_id,
            attributes={
                "link_type": link.link_type.value,
                "reason": link.reason,
                "snapshot_id": link.snapshot_id,
            },
        )
        for link in links
    ]

    scope_conflicts = _scope_conflicts(candidate, incident)
    if scope_conflicts:
        add(
            _item(
                hypothesis_id=hypothesis_id,
                stance=CausalEvidenceStance.CONTRADICTING,
                claim_type=CausalEvidenceClaimType.ENTITY_LINKAGE,
                summary="The candidate and incident have incompatible scope.",
                reason=" ".join(scope_conflicts),
                source_category=CausalEvidenceSourceCategory.IDENTITY,
                quality=CausalEvidenceQuality.DIRECT,
                why_it_matters=(
                    "A change proven to apply to another operational scope "
                    "conflicts with the required affected-entity linkage."
                ),
                source_references=[
                    _reference("change_event", event.event_id),
                    _reference("incident", str(incident.incident_id)),
                ],
                entity_ids=[getattr(incident, "affected_entity_id", None)],
                change_event_ids=[event.event_id],
                snapshot_id=snapshot_id,
            )
        )

    if linked_ids:
        path_start = entity_path[0] if entity_path else linked_ids[0]
        path_links = [link for link in links if link.entity_id == path_start]
        add(
            _item(
                hypothesis_id=hypothesis_id,
                stance=CausalEvidenceStance.SUPPORTING,
                claim_type=CausalEvidenceClaimType.ENTITY_LINKAGE,
                summary="The candidate change is linked to a topology entity.",
                reason=(
                    f"Durable change correlation links '{event.event_id}' to "
                    f"'{path_start}'."
                ),
                source_category=CausalEvidenceSourceCategory.IDENTITY,
                quality=(
                    CausalEvidenceQuality.LIMITED
                    if any(link.link_type.value == "derived" for link in path_links)
                    else CausalEvidenceQuality.STRONG
                ),
                why_it_matters=(
                    "The causal candidate must connect to the infrastructure "
                    "represented in the incident snapshot."
                ),
                source_references=(
                    path_links and [
                        reference
                        for reference in link_references
                        if reference.reference_id
                        in {link.link_id for link in path_links}
                    ]
                    or [_reference("change_event", event.event_id)]
                ),
                entity_ids=[path_start],
                change_event_ids=[event.event_id],
                snapshot_id=snapshot_id,
            )
        )

    if snapshot is not None:
        resolutions = _identity_resolutions(snapshot, candidate)
        resolved = sorted(
            [
                resolution
                for resolution in resolutions
                if resolution.status
                == CanonicalIdentityResolutionStatus.RESOLVED
            ],
            key=lambda item: (
                item.strategy.value,
                item.resolved_entity_id or "",
            ),
        )
        unresolved = sorted(
            [
                resolution
                for resolution in resolutions
                if resolution.status
                != CanonicalIdentityResolutionStatus.RESOLVED
            ],
            key=lambda item: (
                item.status.value,
                item.input_identifier or "",
            ),
        )
        matched_resolved = [
            resolution
            for resolution in resolved
            if not linked_ids or resolution.resolved_entity_id in linked_ids
        ]
        if matched_resolved:
            resolution = matched_resolved[0]
            add(
                _item(
                    hypothesis_id=hypothesis_id,
                    stance=CausalEvidenceStance.SUPPORTING,
                    claim_type=CausalEvidenceClaimType.IDENTITY_RESOLUTION,
                    summary="Deterministic TC-1 identity resolution succeeded.",
                    reason=resolution.reason,
                    source_category=CausalEvidenceSourceCategory.IDENTITY,
                    quality=(
                        CausalEvidenceQuality.DIRECT
                        if resolution.strategy.value
                        in {"canonical_id", "source_native_id"}
                        else CausalEvidenceQuality.STRONG
                    ),
                    why_it_matters=(
                        "The change-to-entity claim must resolve without fuzzy "
                        "or ambiguous identity selection."
                    ),
                    source_references=(
                        link_references
                        or [_reference("change_event", event.event_id)]
                    ),
                    entity_ids=[resolution.resolved_entity_id],
                    change_event_ids=[event.event_id],
                    snapshot_id=snapshot_id,
                    identity_resolution=resolution,
                )
            )
        elif resolved and linked_ids:
            resolution = resolved[0]
            resolved_entity_id = str(resolution.resolved_entity_id)
            add(
                _item(
                    hypothesis_id=hypothesis_id,
                    stance=CausalEvidenceStance.SUPPORTING,
                    claim_type=CausalEvidenceClaimType.IDENTITY_RESOLUTION,
                    summary="Deterministic TC-1 identity resolution succeeded.",
                    reason=resolution.reason,
                    source_category=CausalEvidenceSourceCategory.IDENTITY,
                    quality=(
                        CausalEvidenceQuality.DIRECT
                        if resolution.strategy.value
                        in {"canonical_id", "source_native_id"}
                        else CausalEvidenceQuality.STRONG
                    ),
                    why_it_matters=(
                        "The source reference itself resolves deterministically, "
                        "even though it conflicts with the stored entity link."
                    ),
                    source_references=[
                        _reference("change_event", event.event_id)
                    ],
                    entity_ids=[resolved_entity_id],
                    change_event_ids=[event.event_id],
                    snapshot_id=snapshot_id,
                    identity_resolution=resolution,
                )
            )
            add(
                _item(
                    hypothesis_id=hypothesis_id,
                    stance=CausalEvidenceStance.CONTRADICTING,
                    claim_type=CausalEvidenceClaimType.ENTITY_LINKAGE,
                    summary=(
                        "Resolved source identity conflicts with the durable "
                        "candidate entity link."
                    ),
                    reason=(
                        f"TC-1 resolves the source reference to "
                        f"'{resolved_entity_id}', while stored correlation links "
                        f"the candidate to {', '.join(linked_ids)}."
                    ),
                    source_category=CausalEvidenceSourceCategory.IDENTITY,
                    quality=CausalEvidenceQuality.DIRECT,
                    why_it_matters=(
                        "Two durable identity facts point to different topology "
                        "entities, so this linkage cannot be treated as support."
                    ),
                    source_references=[
                        _reference("change_event", event.event_id),
                        *link_references,
                    ],
                    entity_ids=[resolved_entity_id, *linked_ids],
                    change_event_ids=[event.event_id],
                    snapshot_id=snapshot_id,
                )
            )
        if unresolved:
            unresolved_resolution = unresolved[0]
            add(
                _item(
                    hypothesis_id=hypothesis_id,
                    stance=CausalEvidenceStance.MISSING,
                    claim_type=CausalEvidenceClaimType.IDENTITY_RESOLUTION,
                    summary=(
                        "Required change-to-entity identity is ambiguous."
                        if unresolved_resolution.status
                        == CanonicalIdentityResolutionStatus.AMBIGUOUS
                        else "Required change-to-entity identity is unresolved."
                    ),
                    reason=unresolved_resolution.reason,
                    source_category=CausalEvidenceSourceCategory.IDENTITY,
                    quality=CausalEvidenceQuality.UNKNOWN,
                    why_it_matters=(
                        "Without deterministic identity resolution, the change "
                        "cannot be positively tied to the causal entity."
                    ),
                    expectation_basis=(
                        "The change event supplied entity references that are "
                        "required for this hypothesis but TC-1 could not select "
                        "one unambiguous snapshot entity."
                    ),
                    source_references=[
                        _reference("change_event", event.event_id)
                    ],
                    entity_ids=unresolved_resolution.candidate_entity_ids,
                    change_event_ids=[event.event_id],
                    snapshot_id=snapshot_id,
                    identity_resolution=unresolved_resolution,
                )
            )

    if snapshot is not None and entity_path:
        for left_id, right_id in zip(entity_path, entity_path[1:]):
            relationship = _relationship_between(snapshot, left_id, right_id)
            if relationship is None:
                add(
                    _item(
                        hypothesis_id=hypothesis_id,
                        stance=CausalEvidenceStance.MISSING,
                        claim_type=CausalEvidenceClaimType.TOPOLOGY_PATH,
                        summary="A required topology hop is unavailable.",
                        reason=(
                            f"No exact relationship connects '{left_id}' and "
                            f"'{right_id}' in pinned snapshot '{snapshot_id}'."
                        ),
                        source_category=CausalEvidenceSourceCategory.TOPOLOGY,
                        quality=CausalEvidenceQuality.UNKNOWN,
                        why_it_matters=(
                            "The hypothesis requires an inspectable graph path "
                            "from the change target to the affected entity."
                        ),
                        expectation_basis=(
                            "The current 13C causal chain requires this entity "
                            "hop, so an exact pinned relationship is expected."
                        ),
                        source_references=[
                            _reference("topology_snapshot", snapshot_id or "unknown")
                        ],
                        entity_ids=[left_id, right_id],
                        change_event_ids=[event.event_id],
                        snapshot_id=snapshot_id,
                    )
                )
                continue
            relationship_ref = _relationship_reference(
                relationship,
                left_entity_id=left_id,
            )
            quality = _relationship_quality(relationship)
            common = {
                "source_references": [
                    _reference(
                        "relationship",
                        relationship.id,
                        source_system=relationship.source_system,
                    )
                ],
                "entity_ids": [left_id, right_id],
                "relationship_ids": [relationship.id],
                "change_event_ids": [event.event_id],
                "snapshot_id": snapshot_id,
                "relationship": relationship_ref,
            }
            add(
                _item(
                    hypothesis_id=hypothesis_id,
                    stance=CausalEvidenceStance.SUPPORTING,
                    claim_type=CausalEvidenceClaimType.TOPOLOGY_PATH,
                    summary="Pinned topology contains the causal path hop.",
                    reason=(
                        f"Relationship '{relationship.id}' connects '{left_id}' "
                        f"to '{right_id}' using predicate "
                        f"'{relationship.relationship_type.value}'."
                    ),
                    source_category=CausalEvidenceSourceCategory.TOPOLOGY,
                    quality=quality,
                    why_it_matters=(
                        "This is the exact incident-time relationship traversed "
                        "by the existing 13C shortest path."
                    ),
                    **common,
                )
            )
            if (
                relationship.provenance is not None
                and relationship.provenance.completeness
                == RelationshipProvenanceCompleteness.COMPLETE
            ):
                add(
                    _item(
                        hypothesis_id=hypothesis_id,
                        stance=CausalEvidenceStance.SUPPORTING,
                        claim_type=(
                            CausalEvidenceClaimType.RELATIONSHIP_PROVENANCE
                        ),
                        summary="TC-2 provenance describes the traversed edge.",
                        reason=(
                            f"The edge was {relationship.provenance.origin.value} "
                            f"by {relationship.provenance.source_component} "
                            f"({relationship.provenance.linker_version})."
                        ),
                        source_category=CausalEvidenceSourceCategory.TOPOLOGY,
                        quality=quality,
                        why_it_matters=(
                            "Provenance distinguishes observed or declared "
                            "relationships from derived or inferred links."
                        ),
                        **common,
                    )
                )
            if (
                relationship.provenance is None
                or relationship.provenance.completeness
                != RelationshipProvenanceCompleteness.COMPLETE
            ):
                add(
                    _item(
                        hypothesis_id=hypothesis_id,
                        stance=CausalEvidenceStance.MISSING,
                        claim_type=(
                            CausalEvidenceClaimType.RELATIONSHIP_PROVENANCE
                        ),
                        summary="Complete provenance for a traversed edge is unavailable.",
                        reason=(
                            "The pinned relationship is legacy_unspecified."
                            if relationship.provenance is None
                            else "The pinned relationship records partial provenance."
                        ),
                        source_category=CausalEvidenceSourceCategory.TOPOLOGY,
                        quality=(
                            CausalEvidenceQuality.LEGACY
                            if relationship.provenance is None
                            else CausalEvidenceQuality.LIMITED
                        ),
                        why_it_matters=(
                            "The path exists, but its assertion origin cannot be "
                            "fully audited without complete TC-2 provenance."
                        ),
                        expectation_basis=(
                            "This exact relationship is traversed by the causal "
                            "hypothesis, so its assertion provenance is required."
                        ),
                        **common,
                    )
                )
    elif snapshot is not None and linked_ids and getattr(
        incident,
        "affected_entity_id",
        None,
    ):
        add(
            _item(
                hypothesis_id=hypothesis_id,
                stance=CausalEvidenceStance.MISSING,
                claim_type=CausalEvidenceClaimType.TOPOLOGY_PATH,
                summary="No bounded topology path supports this candidate.",
                reason=(
                    "The pinned snapshot contains the candidate and affected "
                    "entity references, but 13C found no path within the "
                    "configured hop limit."
                ),
                source_category=CausalEvidenceSourceCategory.TOPOLOGY,
                quality=CausalEvidenceQuality.UNKNOWN,
                why_it_matters=(
                    "A graph path would connect the changed component to the "
                    "recorded incident symptom."
                ),
                expectation_basis=(
                    "The hypothesis has a durable entity link and an affected "
                    "entity, so topology connectivity is materially relevant."
                ),
                source_references=[
                    _reference("topology_snapshot", snapshot_id or "unknown")
                ],
                entity_ids=[*linked_ids, incident.affected_entity_id],
                change_event_ids=[event.event_id],
                snapshot_id=snapshot_id,
            )
        )

    if getattr(incident, "primary_signal_id", None):
        signal_id = str(incident.primary_signal_id)
        if primary_signal is not None:
            add(
                _item(
                    hypothesis_id=hypothesis_id,
                    stance=CausalEvidenceStance.SUPPORTING,
                    claim_type=CausalEvidenceClaimType.RUNTIME_FAILURE,
                    summary="A durable failure signal records the incident symptom.",
                    reason=(
                        f"Primary signal '{signal_id}' records "
                        f"'{primary_signal.reason or primary_signal.title}'."
                    ),
                    source_category=CausalEvidenceSourceCategory.SIGNAL,
                    quality=CausalEvidenceQuality.DIRECT,
                    why_it_matters=(
                        "The hypothesis is evaluated against the actual durable "
                        "failure observation, not only the incident title."
                    ),
                    source_references=[
                        _reference(
                            "signal",
                            signal_id,
                            source_system=primary_signal.source_system,
                        )
                    ],
                    entity_ids=[
                        primary_signal.involved_entity_id,
                        getattr(incident, "affected_entity_id", None),
                    ],
                    signal_ids=[signal_id],
                    snapshot_id=(
                        primary_signal.topology_snapshot_id or snapshot_id
                    ),
                    temporal=primary_signal.temporal,
                    incident_boundary_at=incident_time.isoformat(),
                )
            )
        else:
            add(
                _item(
                    hypothesis_id=hypothesis_id,
                    stance=CausalEvidenceStance.MISSING,
                    claim_type=CausalEvidenceClaimType.RUNTIME_FAILURE,
                    summary="The referenced primary failure signal is unavailable.",
                    reason=(
                        f"Incident references signal '{signal_id}', but its "
                        "durable signal record could not be loaded."
                    ),
                    source_category=CausalEvidenceSourceCategory.SIGNAL,
                    quality=CausalEvidenceQuality.UNKNOWN,
                    why_it_matters=(
                        "The causal hypothesis should remain traceable to the "
                        "failure observation it is intended to explain."
                    ),
                    expectation_basis=(
                        "The incident explicitly stores this primary signal ID, "
                        "so its durable record is expected."
                    ),
                    source_references=[_reference("signal", signal_id)],
                    signal_ids=[signal_id],
                    snapshot_id=snapshot_id,
                )
            )

    # Deployment/rollout hypotheses have a defensible expectation of a
    # workload-artifact association only when the pinned graph actually
    # contains a relevant workload/image observation.
    if snapshot is not None and _enum_value(event.kind) in {
        "deployment",
        "rollout",
        "pipeline",
    }:
        relevant_ids = set(linked_ids) | set(entity_path or [])
        workload_ids = {
            entity_id
            for entity_id in relevant_ids
            if _is_workload(entity_index.get(entity_id))
        }
        uses_edges = sorted(
            [
                relationship
                for relationship in snapshot.relationships
                if relationship.relationship_type == RelationshipType.USES
                and relationship.source_entity_id in workload_ids
            ],
            key=lambda item: item.id,
        )
        for relationship in uses_edges[:3]:
            image = entity_index.get(relationship.target_entity_id)
            immutable = bool(
                image
                and (
                    image.properties.get("immutable")
                    or image.properties.get("digest")
                    or image.id.startswith("artifact:container-image:sha256:")
                )
            )
            relationship_ref = _relationship_reference(
                relationship,
                left_entity_id=relationship.source_entity_id,
            )
            common = {
                "source_references": [
                    _reference("relationship", relationship.id),
                    _reference("change_event", event.event_id),
                ],
                "entity_ids": [
                    relationship.source_entity_id,
                    relationship.target_entity_id,
                ],
                "relationship_ids": [relationship.id],
                "change_event_ids": [event.event_id],
                "snapshot_id": snapshot_id,
                "relationship": relationship_ref,
            }
            add(
                _item(
                    hypothesis_id=hypothesis_id,
                    stance=CausalEvidenceStance.SUPPORTING,
                    claim_type=CausalEvidenceClaimType.ARTIFACT_PROVENANCE,
                    summary=(
                        "Pinned runtime/workload evidence uses an immutable image digest."
                        if immutable
                        else "Pinned workload evidence references a mutable image tag."
                    ),
                    reason=(
                        f"Relationship '{relationship.id}' links workload "
                        f"'{relationship.source_entity_id}' to image "
                        f"'{relationship.target_entity_id}'."
                    ),
                    source_category=CausalEvidenceSourceCategory.ARTIFACT,
                    quality=(
                        CausalEvidenceQuality.DIRECT
                        if immutable
                        else CausalEvidenceQuality.LIMITED
                    ),
                    why_it_matters=(
                        "An immutable digest is stronger source-to-runtime "
                        "evidence than a mutable image reference."
                    ),
                    **common,
                )
            )
            produces_edges = [
                item
                for item in snapshot.relationships
                if item.relationship_type == RelationshipType.PRODUCES
                and item.target_entity_id == relationship.target_entity_id
            ]
            if not immutable or not produces_edges:
                gaps = []
                if not immutable:
                    gaps.append("immutable image digest")
                if not produces_edges:
                    gaps.append("build/source-to-image producer relationship")
                add(
                    _item(
                        hypothesis_id=hypothesis_id,
                        stance=CausalEvidenceStance.MISSING,
                        claim_type=CausalEvidenceClaimType.ARTIFACT_PROVENANCE,
                        summary="Complete immutable build-to-runtime proof is unavailable.",
                        reason="Missing " + " and ".join(gaps) + ".",
                        source_category=CausalEvidenceSourceCategory.ARTIFACT,
                        quality=CausalEvidenceQuality.LIMITED,
                        why_it_matters=(
                            "Without the missing artifact proof, Topo cannot "
                            "claim that a specific build produced the exact "
                            "content observed by the workload."
                        ),
                        expectation_basis=(
                            "This deployment/rollout hypothesis is linked to a "
                            "pinned workload-image relationship, making the "
                            "immutable build-to-runtime chain materially relevant."
                        ),
                        **common,
                    )
                )

    ordered = sorted(
        items.values(),
        key=lambda item: (item.claim_type.value, item.evidence_id),
    )
    return CausalEvidenceLedger(
        hypothesis_id=hypothesis_id,
        snapshot_id=snapshot_id,
        supporting=[
            item for item in ordered
            if item.stance == CausalEvidenceStance.SUPPORTING
        ],
        contradicting=[
            item for item in ordered
            if item.stance == CausalEvidenceStance.CONTRADICTING
        ],
        missing=[
            item for item in ordered
            if item.stance == CausalEvidenceStance.MISSING
        ],
    )
