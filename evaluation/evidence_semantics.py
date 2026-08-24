from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Iterable


NON_CAUSE_EVIDENCE_SEMANTICS_VERSION = "non-cause-evidence-v1"


class EvidenceInterpretation(str, Enum):
    CANDIDATE_FACT = "candidate_fact"
    CAUSAL_CONNECTIVITY = "causal_connectivity"
    EFFECT_EVIDENCE = "effect_evidence"
    LINEAGE_EVIDENCE = "lineage_evidence"
    UNKNOWN_AMBIGUOUS = "unknown_ambiguous"


LEGACY_CRITICAL_CLAIMS = frozenset(
    {
        "source_change",
        "identity_resolution",
        "entity_linkage",
        "topology_path",
        "relationship_provenance",
    }
)


@dataclass(frozen=True)
class InterpretedEvidence:
    hypothesis_id: str
    candidate_event_id: str
    candidate_entity_ids: tuple[str, ...]
    affected_entity_ids: tuple[str, ...]
    evidence_id: str | None
    claim_type: str
    interpretation: EvidenceInterpretation
    supports_candidate_to_effect: bool | None
    entity_ids: tuple[str, ...]
    relationship_ids: tuple[str, ...]
    change_event_ids: tuple[str, ...]
    source_reference_ids: tuple[str, ...]
    reason: str

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["interpretation"] = self.interpretation.value
        return value


@dataclass(frozen=True)
class NonCauseEvidenceSummary:
    legacy_raw_support_count: int
    candidate_fact_count: int
    effect_evidence_count: int
    lineage_evidence_count: int
    false_causal_support_count: int
    ambiguous_support_count: int
    interpretations: tuple[InterpretedEvidence, ...]

    def metrics(self) -> dict[str, Any]:
        by_class: dict[EvidenceInterpretation, list[InterpretedEvidence]] = {
            semantic: [] for semantic in EvidenceInterpretation
        }
        for item in self.interpretations:
            by_class[item.interpretation].append(item)

        false_items = [
            item
            for item in self.interpretations
            if item.supports_candidate_to_effect is True
        ]
        return {
            # Preserved with its original EVAL-1 meaning for artifact
            # compatibility and before/after auditability.
            "explicit_non_cause_supported_count": self.legacy_raw_support_count,
            "unsupported_critical_claim_count": self.legacy_raw_support_count,
            "explicit_non_cause_supporting_fact_count": self.candidate_fact_count,
            "explicit_non_cause_effect_evidence_count": self.effect_evidence_count,
            "explicit_non_cause_lineage_evidence_count": self.lineage_evidence_count,
            "explicit_non_cause_false_causal_support_count": (
                self.false_causal_support_count
            ),
            "unsupported_false_causal_claim_count": (
                self.false_causal_support_count
            ),
            "explicit_non_cause_ambiguous_support_count": (
                self.ambiguous_support_count
            ),
            "explicit_non_cause_candidate_fact_claim_types": _claim_types(
                by_class[EvidenceInterpretation.CANDIDATE_FACT]
            ),
            "explicit_non_cause_effect_evidence_claim_types": _claim_types(
                by_class[EvidenceInterpretation.EFFECT_EVIDENCE]
            ),
            "explicit_non_cause_lineage_evidence_claim_types": _claim_types(
                by_class[EvidenceInterpretation.LINEAGE_EVIDENCE]
            ),
            "explicit_non_cause_causal_claim_types": _claim_types(false_items),
            "explicit_non_cause_ambiguous_claim_types": _claim_types(
                by_class[EvidenceInterpretation.UNKNOWN_AMBIGUOUS]
            ),
            "explicit_non_cause_evidence_interpretations": [
                item.as_dict() for item in self.interpretations
            ],
        }


def _strings(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(sorted({str(value) for value in values if value}))


def _claim_types(items: Iterable[InterpretedEvidence]) -> list[str]:
    return sorted({item.claim_type for item in items})


def _event_links(event: dict[str, Any]) -> set[str]:
    links = event.get("links") or event.get("entity_links") or []
    return {
        str(link.get("entity_id"))
        for link in links
        if isinstance(link, dict) and link.get("entity_id")
    }


def _matching_relevance_audit(
    analysis: dict[str, Any],
    candidate_event_id: str,
) -> dict[str, Any]:
    matches = [
        item
        for item in analysis.get("candidate_relevance_audit", [])
        if str(item.get("candidate_event_id") or "") == candidate_event_id
    ]
    return sorted(
        matches,
        key=lambda item: (
            str(item.get("candidate_entity_id") or ""),
            str(item.get("affected_entity_id") or ""),
        ),
    )[0] if matches else {}


def _candidate_entities(
    hypothesis: dict[str, Any],
    analysis: dict[str, Any],
    change_by_id: dict[str, dict[str, Any]],
) -> tuple[str, set[str], dict[str, Any]]:
    candidate_event_id = str(
        hypothesis.get("target_event_id")
        or hypothesis.get("root_event_id")
        or ""
    )
    audit = _matching_relevance_audit(analysis, candidate_event_id)
    candidate_ids: set[str] = set()
    if audit.get("candidate_entity_id"):
        candidate_ids.add(str(audit["candidate_entity_id"]))

    for event_id in {
        candidate_event_id,
        str(hypothesis.get("root_event_id") or ""),
    }:
        candidate_ids.update(_event_links(change_by_id.get(event_id, {})))

    # Legacy EVAL-1 artifacts predate the CR-1 audit. Candidate-local TC-4
    # identity/linkage items are the narrowest structured fallback.
    ledger = hypothesis.get("evidence_ledger") or {}
    for item in ledger.get("supporting", []):
        if item.get("claim_type") in {"entity_linkage", "identity_resolution"}:
            candidate_ids.update(_strings(item.get("entity_ids", [])))
    return candidate_event_id, candidate_ids, audit


def _connected(
    edges: Iterable[tuple[str, str]],
    starts: set[str],
    targets: set[str],
) -> bool:
    if starts & targets:
        return True
    adjacency: dict[str, set[str]] = {}
    for left, right in edges:
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)
    queue = sorted(starts)
    visited = set(starts)
    while queue:
        node = queue.pop(0)
        for neighbor in sorted(adjacency.get(node, set())):
            if neighbor in targets:
                return True
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return False


def _path_context(
    hypothesis: dict[str, Any],
    audit: dict[str, Any],
    candidate_ids: set[str],
    affected_ids: set[str],
) -> tuple[bool, set[str], set[str]]:
    audit_entities = {str(value) for value in audit.get("path_entity_ids", [])}
    audit_relationships = {
        str(value) for value in audit.get("path_relationship_ids", [])
    }
    audit_status = str(audit.get("relevance_status") or "")
    audit_bridge = bool(
        audit_status in {"direct", "semantic_path"}
        and audit_entities & candidate_ids
        and audit_entities & affected_ids
    )
    if audit_bridge:
        return True, audit_entities, audit_relationships

    ledger = hypothesis.get("evidence_ledger") or {}
    topology_items = [
        item
        for item in ledger.get("supporting", [])
        if item.get("claim_type") == "topology_path"
    ]
    path_entities: set[str] = set()
    path_relationships: set[str] = set()
    edges: list[tuple[str, str]] = []
    direct_bridge = False
    for item in topology_items:
        entity_ids = _strings(item.get("entity_ids", []))
        path_entities.update(entity_ids)
        path_relationships.update(_strings(item.get("relationship_ids", [])))
        if set(entity_ids) & candidate_ids and set(entity_ids) & affected_ids:
            direct_bridge = True
        if len(entity_ids) == 2:
            edges.append((entity_ids[0], entity_ids[1]))
    bridge = direct_bridge or _connected(edges, candidate_ids, affected_ids)
    return bridge, path_entities, path_relationships


def _source_reference_ids(item: dict[str, Any]) -> tuple[str, ...]:
    return _strings(
        reference.get("reference_id")
        for reference in item.get("source_references", [])
        if isinstance(reference, dict)
    )


def _interpret_item(
    item: dict[str, Any],
    *,
    hypothesis_id: str,
    candidate_event_id: str,
    candidate_ids: set[str],
    affected_ids: set[str],
    path_bridge: bool,
    path_entity_ids: set[str],
    path_relationship_ids: set[str],
) -> InterpretedEvidence:
    claim = str(item.get("claim_type") or "unknown")
    entity_ids = set(_strings(item.get("entity_ids", [])))
    relationship_ids = set(_strings(item.get("relationship_ids", [])))
    change_event_ids = set(_strings(item.get("change_event_ids", [])))
    interpretation = EvidenceInterpretation.UNKNOWN_AMBIGUOUS
    causal: bool | None = None
    reason = "The serialized fields do not safely establish evidence scope."

    if claim in {"source_change", "identity_resolution", "temporal_precedence"}:
        interpretation = EvidenceInterpretation.CANDIDATE_FACT
        causal = False
        reason = (
            "This establishes the candidate's existence, identity, or timing; "
            "it does not connect the candidate to the incident effect."
        )
    elif claim == "runtime_failure":
        if entity_ids & affected_ids:
            interpretation = EvidenceInterpretation.EFFECT_EVIDENCE
            causal = False
            reason = (
                "The item establishes the incident effect on the affected entity, "
                "not which candidate caused it."
            )
        elif entity_ids and entity_ids <= candidate_ids:
            interpretation = EvidenceInterpretation.CANDIDATE_FACT
            causal = False
            reason = "The failure fact is scoped only to the candidate entity."
    elif claim == "entity_linkage":
        links_candidate = bool(entity_ids & candidate_ids)
        links_effect = bool(entity_ids & affected_ids)
        event_scoped = candidate_event_id in change_event_ids
        if links_effect and (links_candidate or event_scoped):
            interpretation = EvidenceInterpretation.CAUSAL_CONNECTIVITY
            causal = True
            reason = (
                "The structured linkage connects the candidate/event to an "
                "incident affected entity."
            )
        elif links_candidate and not links_effect:
            interpretation = EvidenceInterpretation.CANDIDATE_FACT
            causal = False
            reason = (
                "The linkage connects the change only to its own candidate entity."
            )
    elif claim == "topology_path":
        item_bridge = bool(entity_ids & candidate_ids and entity_ids & affected_ids)
        on_selected_path = bool(
            path_bridge
            and entity_ids
            and entity_ids <= path_entity_ids
            and (
                not relationship_ids
                or relationship_ids & path_relationship_ids
            )
        )
        if item_bridge or on_selected_path:
            interpretation = EvidenceInterpretation.CAUSAL_CONNECTIVITY
            causal = True
            reason = (
                "The supporting topology item belongs to a selected path from "
                "the candidate entity to the incident effect."
            )
    elif claim == "relationship_provenance":
        if path_bridge and relationship_ids & path_relationship_ids:
            interpretation = EvidenceInterpretation.CAUSAL_CONNECTIVITY
            causal = True
            reason = (
                "The provenance item describes a relationship used by the "
                "candidate-to-effect path."
            )
        elif entity_ids & candidate_ids and not entity_ids & affected_ids:
            interpretation = EvidenceInterpretation.CANDIDATE_FACT
            causal = False
            reason = (
                "The relationship is candidate-local and is not part of the "
                "selected candidate-to-effect path."
            )
    elif claim == "artifact_provenance":
        item_bridge = bool(entity_ids & candidate_ids and entity_ids & affected_ids)
        selected_bridge = bool(
            path_bridge and relationship_ids & path_relationship_ids
        )
        candidate_scoped = bool(
            entity_ids & candidate_ids or candidate_event_id in change_event_ids
        )
        if item_bridge or selected_bridge or candidate_scoped:
            interpretation = EvidenceInterpretation.LINEAGE_EVIDENCE
            causal = item_bridge or selected_bridge
            reason = (
                "Artifact lineage participates in the selected source-to-effect path."
                if causal
                else (
                    "Artifact evidence is local to the candidate/source and does not "
                    "reach an affected entity in the serialized evidence."
                )
            )
    elif claim == "event_lineage":
        if candidate_event_id in change_event_ids:
            interpretation = EvidenceInterpretation.LINEAGE_EVIDENCE
            causal = path_bridge
            reason = (
                "Event lineage feeds a selected candidate-to-effect path."
                if causal
                else (
                    "Event lineage is tied to the candidate but no structured "
                    "candidate-to-effect path is present."
                )
            )

    return InterpretedEvidence(
        hypothesis_id=hypothesis_id,
        candidate_event_id=candidate_event_id,
        candidate_entity_ids=_strings(candidate_ids),
        affected_entity_ids=_strings(affected_ids),
        evidence_id=(str(item["evidence_id"]) if item.get("evidence_id") else None),
        claim_type=claim,
        interpretation=interpretation,
        supports_candidate_to_effect=causal,
        entity_ids=_strings(entity_ids),
        relationship_ids=_strings(relationship_ids),
        change_event_ids=_strings(change_event_ids),
        source_reference_ids=_source_reference_ids(item),
        reason=reason,
    )


def interpret_explicit_non_cause_evidence(
    *,
    analysis: dict[str, Any],
    change_events: Iterable[dict[str, Any]],
    non_cause_entity_ids: Iterable[str],
    affected_entity_ids: Iterable[str],
) -> NonCauseEvidenceSummary:
    """Interpret serialized Topo evidence without importing product logic."""

    noncause_ids = set(_strings(non_cause_entity_ids))
    affected_ids = set(_strings(affected_entity_ids))
    change_by_id = {
        str(event.get("event_id")): event
        for event in change_events
        if event.get("event_id")
    }
    hypotheses = sorted(
        analysis.get("hypotheses", []),
        key=lambda item: (
            int(item.get("rank", 999)),
            str(item.get("hypothesis_id") or ""),
        ),
    )

    legacy_count = 0
    for hypothesis in hypotheses:
        for item in (hypothesis.get("evidence_ledger") or {}).get("supporting", []):
            if (
                str(item.get("claim_type") or "") in LEGACY_CRITICAL_CLAIMS
                and set(_strings(item.get("entity_ids", []))) & noncause_ids
            ):
                legacy_count += 1

    interpreted: list[InterpretedEvidence] = []
    for hypothesis in hypotheses:
        candidate_event_id, all_candidate_ids, audit = _candidate_entities(
            hypothesis,
            analysis,
            change_by_id,
        )
        candidate_ids = all_candidate_ids & noncause_ids
        if not candidate_ids:
            continue
        path_bridge, path_entity_ids, path_relationship_ids = _path_context(
            hypothesis,
            audit,
            candidate_ids,
            affected_ids,
        )
        for item in (hypothesis.get("evidence_ledger") or {}).get("supporting", []):
            interpreted.append(
                _interpret_item(
                    item,
                    hypothesis_id=str(hypothesis.get("hypothesis_id") or ""),
                    candidate_event_id=candidate_event_id,
                    candidate_ids=candidate_ids,
                    affected_ids=affected_ids,
                    path_bridge=path_bridge,
                    path_entity_ids=path_entity_ids,
                    path_relationship_ids=path_relationship_ids,
                )
            )

    interpreted.sort(
        key=lambda item: (
            item.hypothesis_id,
            item.claim_type,
            item.evidence_id or "",
            item.entity_ids,
            item.relationship_ids,
        )
    )
    candidate_facts = sum(
        item.interpretation == EvidenceInterpretation.CANDIDATE_FACT
        for item in interpreted
    )
    effect_evidence = sum(
        item.interpretation == EvidenceInterpretation.EFFECT_EVIDENCE
        for item in interpreted
    )
    lineage_evidence = sum(
        item.interpretation == EvidenceInterpretation.LINEAGE_EVIDENCE
        for item in interpreted
    )
    false_causal = sum(
        item.supports_candidate_to_effect is True for item in interpreted
    )
    ambiguous = sum(
        item.interpretation == EvidenceInterpretation.UNKNOWN_AMBIGUOUS
        for item in interpreted
    )
    return NonCauseEvidenceSummary(
        legacy_raw_support_count=legacy_count,
        candidate_fact_count=candidate_facts,
        effect_evidence_count=effect_evidence,
        lineage_evidence_count=lineage_evidence,
        false_causal_support_count=false_causal,
        ambiguous_support_count=ambiguous,
        interpretations=tuple(interpreted),
    )
