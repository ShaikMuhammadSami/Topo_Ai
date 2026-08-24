from __future__ import annotations

import json
from typing import Any, Iterable

from evaluation.cause_fingerprint import (
    CAUSE_FINGERPRINT_VERSION,
    CAUSE_MATCH_VERSION,
    CauseFingerprint,
    CauseMatchResult,
    compare_causes,
    expected_cause_fingerprints,
    fingerprints_from_event,
)


STRUCTURED_CAUSE_MATCH_VERSION = CAUSE_MATCH_VERSION

_DEFINITE_MISMATCHES = {
    "value_mismatch",
    "entity_match_mutation_mismatch",
    "mutation_match_entity_mismatch",
    "different_cause",
}

_MISMATCH_PRIORITY = {
    "value_mismatch": 4,
    "entity_match_mutation_mismatch": 3,
    "mutation_match_entity_mismatch": 2,
    "different_cause": 1,
    "insufficient_structure": 0,
}


def _fingerprint_key(value: CauseFingerprint) -> str:
    return json.dumps(value.as_dict(), sort_keys=True, default=str)


def _accepted_partial(
    expected: CauseFingerprint,
    result: CauseMatchResult,
) -> bool:
    if result.status != "compatible_partial":
        return False
    comparisons = result.comparisons
    if any(
        comparisons.get(field) != "matched"
        for field in ("provider", "entity_identity", "mutation_family")
    ):
        return False
    independently_known = {
        "changed_field": expected.changed_field,
        "before_value": expected.before_value_hash,
        "after_value": expected.after_value_hash,
    }
    return all(
        value is None or comparisons.get(field) == "matched"
        for field, value in independently_known.items()
    )


def _accepted(
    expected: CauseFingerprint,
    result: CauseMatchResult,
) -> bool:
    return result.status == "exact" or _accepted_partial(expected, result)


def _indeterminate_identity_ambiguity(
    comparisons: list[tuple[CauseFingerprint, CauseFingerprint, CauseMatchResult]],
) -> bool:
    possible_actuals: set[str] = set()
    for _, actual, result in comparisons:
        states = result.comparisons
        if (
            states.get("entity_identity") == "not_comparable"
            and states.get("provider") == "matched"
            and states.get("mutation_family") == "matched"
            and states.get("changed_field") == "matched"
            and states.get("before_value") in {"matched", "not_comparable"}
            and states.get("after_value") in {"matched", "not_comparable"}
        ):
            possible_actuals.add(
                str(
                    actual.provider_native_entity_id
                    or actual.canonical_entity_id
                    or _fingerprint_key(actual)
                )
            )
    return len(possible_actuals) > 1


def assess_hypothesis_cause(
    expected: Iterable[CauseFingerprint],
    hypothesis: dict[str, Any] | None,
    change_events: Iterable[dict[str, Any]],
    *,
    alternatives_explicit: bool,
) -> dict[str, Any]:
    expected_values = list(expected)
    hypothesis = hypothesis or {}
    root_event_id = hypothesis.get("root_event_id")
    events = [
        item for item in change_events if item.get("event_id") == root_event_id
    ]
    base = {
        "cause_match_version": STRUCTURED_CAUSE_MATCH_VERSION,
        "hypothesis_id": hypothesis.get("hypothesis_id"),
        "rank": hypothesis.get("rank"),
        "root_event_id": root_event_id,
        "root_title": hypothesis.get("root_title"),
        "actual_event_resolution": "topo_observation.change_events",
    }
    if not hypothesis:
        return {
            **base,
            "status": "insufficient_structure",
            "correct": None,
            "reason": "No causal hypothesis is available.",
            "actual_cause_fingerprint": None,
            "match": None,
            "all_matches": [],
        }
    if not expected_values:
        return {
            **base,
            "status": "insufficient_structure",
            "correct": None,
            "reason": "Independent expected cause structure is unavailable.",
            "actual_cause_fingerprint": None,
            "match": None,
            "all_matches": [],
        }
    if len(events) != 1:
        status = "ambiguous" if len(events) > 1 else "insufficient_structure"
        reason = (
            "Multiple serialized ChangeEvents share the selected root_event_id."
            if len(events) > 1
            else "The selected root_event_id cannot be resolved in serialized ChangeEvents."
        )
        return {
            **base,
            "status": status,
            "correct": None,
            "reason": reason,
            "actual_cause_fingerprint": None,
            "match": None,
            "all_matches": [],
        }

    actual_values = fingerprints_from_event(
        events[0], evidence_source="authoritative_root_event.metadata"
    )
    comparisons = [
        (expected_item, actual_item, compare_causes(expected_item, actual_item))
        for expected_item in expected_values
        for actual_item in actual_values
    ]
    serialized = [
        {
            "expected_cause_fingerprint": expected_item.as_dict(),
            "actual_cause_fingerprint": actual_item.as_dict(),
            "match": result.as_dict(),
            "accepted": _accepted(expected_item, result),
        }
        for expected_item, actual_item, result in comparisons
    ]
    accepted = [
        (expected_item, actual_item, result)
        for expected_item, actual_item, result in comparisons
        if _accepted(expected_item, result)
    ]
    accepted_actuals = {_fingerprint_key(item[1]) for item in accepted}
    if len(accepted_actuals) > 1 and not alternatives_explicit:
        return {
            **base,
            "status": "ambiguous",
            "correct": None,
            "reason": "Multiple structured causes satisfy a single expected cause.",
            "actual_cause_fingerprint": None,
            "match": None,
            "all_matches": serialized,
        }
    if accepted:
        selected = max(
            accepted,
            key=lambda item: (
                item[2].status == "exact",
                len(item[2].compared_fields),
                _fingerprint_key(item[1]),
            ),
        )
        return {
            **base,
            "status": selected[2].status,
            "correct": True,
            "reason": "The selected root event matches independent initiating-mutation truth.",
            "actual_cause_fingerprint": selected[1].as_dict(),
            "matched_expected_cause_fingerprint": selected[0].as_dict(),
            "match": selected[2].as_dict(),
            "all_matches": serialized,
        }

    if _indeterminate_identity_ambiguity(comparisons):
        return {
            **base,
            "status": "ambiguous",
            "correct": None,
            "reason": "Multiple actual entity identities remain structurally possible.",
            "actual_cause_fingerprint": None,
            "match": None,
            "all_matches": serialized,
        }
    definite = [item for item in comparisons if item[2].status in _DEFINITE_MISMATCHES]
    insufficient = [
        item for item in comparisons if item[2].status == "insufficient_structure"
    ]
    if insufficient and not definite:
        selected = max(
            insufficient,
            key=lambda item: (
                len(item[2].compared_fields),
                _fingerprint_key(item[1]),
            ),
        )
        return {
            **base,
            "status": "insufficient_structure",
            "correct": None,
            "reason": "Serialized root-event structure cannot safely establish equivalence.",
            "actual_cause_fingerprint": selected[1].as_dict(),
            "match": selected[2].as_dict(),
            "all_matches": serialized,
        }
    if definite:
        selected = max(
            definite,
            key=lambda item: (
                _MISMATCH_PRIORITY[item[2].status],
                len(item[2].compared_fields),
                _fingerprint_key(item[1]),
            ),
        )
        return {
            **base,
            "status": selected[2].status,
            "correct": False,
            "reason": "Structured root-event evidence establishes a different initiating cause.",
            "actual_cause_fingerprint": selected[1].as_dict(),
            "match": selected[2].as_dict(),
            "all_matches": serialized,
        }
    return {
        **base,
        "status": "insufficient_structure",
        "correct": None,
        "reason": "No comparable structured cause was available.",
        "actual_cause_fingerprint": None,
        "match": None,
        "all_matches": serialized,
    }


def evaluate_structured_root_causes(
    manifest: dict[str, Any],
    execution_receipt: dict[str, Any],
    provider_verification: dict[str, Any],
    topo_observation: dict[str, Any],
) -> dict[str, Any]:
    should_abstain = bool(
        manifest.get("expected_behavior", {}).get("should_abstain", False)
    )
    expected = expected_cause_fingerprints(
        manifest, execution_receipt, provider_verification
    )
    analysis = topo_observation.get("causal_analysis") or {}
    hypotheses = sorted(
        analysis.get("hypotheses", []), key=lambda item: item.get("rank", 999)
    )
    selectors = manifest.get("expected_behavior", {}).get(
        "accepted_top_causes", []
    )
    alternatives_explicit = len(
        {
            str(selector.get("entity_alias"))
            for selector in selectors
            if selector.get("entity_alias")
        }
    ) > 1
    top3 = [
        assess_hypothesis_cause(
            expected,
            hypothesis,
            topo_observation.get("change_events", []),
            alternatives_explicit=alternatives_explicit,
        )
        for hypothesis in hypotheses[:3]
    ]
    if should_abstain:
        top1_correct: bool | None = None
        top3_correct: bool | None = None
        status = "not_applicable_abstention"
    else:
        top1_correct = top3[0]["correct"] if top3 else None
        if any(item["correct"] is True for item in top3):
            top3_correct = True
        elif any(item["correct"] is None for item in top3) or not top3:
            top3_correct = None
        else:
            top3_correct = False
        status = (
            "matched"
            if top1_correct is True
            else "mismatched"
            if top1_correct is False
            else "inconclusive"
        )
    return {
        "cause_match_version": STRUCTURED_CAUSE_MATCH_VERSION,
        "cause_fingerprint_version": CAUSE_FINGERPRINT_VERSION,
        "cause_match_status": status,
        "expected_cause_fingerprints": [item.as_dict() for item in expected],
        "top1_actual_cause_fingerprint": (
            top3[0].get("actual_cause_fingerprint") if top3 else None
        ),
        "top1_cause_match": top3[0] if top3 else None,
        "top3_cause_matches": top3,
        "root_cause_top1_correct": top1_correct,
        "root_cause_top3_contains_truth": top3_correct,
        "diagnostics": {
            "authoritative_source": "root_event_id -> topo_observation.change_events.metadata",
            "expected_source": "scenario_intent+execution_receipt+provider_verification",
            "title_authoritative": False,
            "alternatives_explicit": alternatives_explicit,
        },
    }
