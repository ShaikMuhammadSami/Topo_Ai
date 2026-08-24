from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable


CAUSE_FINGERPRINT_VERSION = "eval-cause-fingerprint-v1"
CAUSE_MATCH_VERSION = "eval-cause-match-v1"


_ACTION_FIELDS = {
    # This is an action-semantic mapping, not a scenario result override.
    "causal_bad_image": "spec.template.spec.containers[0].image",
}

_FIELD_EQUIVALENCE = {
    "properties.images": "kubernetes.workload.container_image",
    "properties.images[0]": "kubernetes.workload.container_image",
    "spec.template.spec.containers[0].image": "kubernetes.workload.container_image",
}


@dataclass(frozen=True)
class CauseFingerprint:
    fingerprint_version: str = CAUSE_FINGERPRINT_VERSION
    provider: str | None = None
    entity_kind: str | None = None
    canonical_entity_id: str | None = None
    provider_native_entity_id: str | None = None
    mutation_family: str | None = None
    changed_field: str | None = None
    before_value_ref: Any = None
    before_value_hash: str | None = None
    after_value_ref: Any = None
    after_value_hash: str | None = None
    initiating_event_id: str | None = None
    source_change_id: str | None = None
    scenario_logical_entity: str | None = None
    scenario_logical_change: str | None = None
    evidence_source: str | None = None
    fingerprint_completeness: str = "insufficient_structure"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CauseMatchResult:
    match_version: str
    status: str
    comparisons: dict[str, str]
    compared_fields: list[str]
    mismatched_fields: list[str]
    unavailable_fields: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalized_value(value: Any) -> Any:
    if isinstance(value, tuple):
        value = list(value)
    if isinstance(value, list) and len(value) == 1:
        return _normalized_value(value[0])
    if isinstance(value, list):
        return [_normalized_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalized_value(value[key]) for key in sorted(value)}
    return value


def value_hash(value: Any) -> str | None:
    if value is None:
        return None
    encoded = json.dumps(
        _normalized_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _kind(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value)
    if normalized.lower().startswith("kubernetes"):
        normalized = normalized[len("Kubernetes") :]
    return normalized or None


def _field(value: str | None) -> str | None:
    if value is None:
        return None
    return _FIELD_EQUIVALENCE.get(value, value)


def _provider_object(
    provider_verification: dict[str, Any], logical_entity: str
) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in provider_verification.get("objects", [])
            if item.get("logical_name") == logical_entity
        ),
        None,
    )


def _action(
    execution_receipt: dict[str, Any], logical_entity: str
) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in execution_receipt.get("actions", [])
            if item.get("logical_target") == logical_entity
        ),
        None,
    )


def _completeness(fingerprint: CauseFingerprint) -> str:
    identity = bool(
        fingerprint.canonical_entity_id or fingerprint.provider_native_entity_id
    )
    required = (
        fingerprint.provider,
        fingerprint.entity_kind,
        fingerprint.mutation_family,
        fingerprint.changed_field,
        fingerprint.before_value_hash,
        fingerprint.after_value_hash,
    )
    if identity and all(value is not None for value in required):
        return "complete"
    if identity or fingerprint.changed_field or fingerprint.mutation_family:
        return "partial"
    return "insufficient_structure"


def _finish(**values: Any) -> CauseFingerprint:
    provisional = CauseFingerprint(**values)
    return CauseFingerprint(
        **{
            **provisional.as_dict(),
            "fingerprint_completeness": _completeness(provisional),
        }
    )


def expected_cause_fingerprint(
    manifest: dict[str, Any],
    execution_receipt: dict[str, Any],
    provider_verification: dict[str, Any],
) -> CauseFingerprint:
    """Derive independent expected truth from only declared/provider inputs."""

    intent = manifest.get("causal_intent", {})
    logical_entity = str(intent.get("root_entity") or "")
    action = _action(execution_receipt, logical_entity) or {}
    provider_object = _provider_object(provider_verification, logical_entity) or {}
    action_type = str(action.get("action_type") or "")
    before = action.get("before", {})
    after = action.get("after", {})
    before_value = before.get("image") if isinstance(before, dict) else None
    after_value = after.get("image") if isinstance(after, dict) else None
    changed_field = _ACTION_FIELDS.get(action_type)
    native_id = action.get("provider_uid") or provider_object.get("uid")

    return _finish(
        provider="kubernetes" if provider_object or native_id else None,
        entity_kind=_kind(provider_object.get("provider_kind")),
        provider_native_entity_id=str(native_id) if native_id else None,
        mutation_family="field_change" if changed_field else None,
        changed_field=changed_field,
        before_value_ref=_normalized_value(before_value),
        before_value_hash=value_hash(before_value),
        after_value_ref=_normalized_value(after_value),
        after_value_hash=value_hash(after_value),
        scenario_logical_entity=logical_entity or None,
        scenario_logical_change=intent.get("root_change"),
        evidence_source="scenario_intent+execution_receipt+provider_verification",
    )


def execution_cause_fingerprint(
    manifest: dict[str, Any], execution_receipt: dict[str, Any]
) -> CauseFingerprint:
    intent = manifest.get("causal_intent", {})
    logical_entity = str(intent.get("root_entity") or "")
    action = _action(execution_receipt, logical_entity) or {}
    action_type = str(action.get("action_type") or "")
    before = action.get("before", {})
    after = action.get("after", {})
    before_value = before.get("image") if isinstance(before, dict) else None
    after_value = after.get("image") if isinstance(after, dict) else None
    changed_field = _ACTION_FIELDS.get(action_type)
    return _finish(
        provider="kubernetes" if action else None,
        provider_native_entity_id=action.get("provider_uid"),
        mutation_family="field_change" if changed_field else None,
        changed_field=changed_field,
        before_value_ref=_normalized_value(before_value),
        before_value_hash=value_hash(before_value),
        after_value_ref=_normalized_value(after_value),
        after_value_hash=value_hash(after_value),
        scenario_logical_entity=logical_entity or None,
        scenario_logical_change=intent.get("root_change"),
        evidence_source="execution_receipt",
    )


def provider_cause_fingerprint(
    manifest: dict[str, Any],
    execution_receipt: dict[str, Any],
    provider_verification: dict[str, Any],
) -> CauseFingerprint:
    intent = manifest.get("causal_intent", {})
    logical_entity = str(intent.get("root_entity") or "")
    action = _action(execution_receipt, logical_entity) or {}
    provider_object = _provider_object(provider_verification, logical_entity) or {}
    action_type = str(action.get("action_type") or "")
    changed_field = _ACTION_FIELDS.get(action_type)
    before = action.get("before", {})
    provider_spec = provider_object.get("spec", {})
    before_value = before.get("image") if isinstance(before, dict) else None
    provider_images = (
        provider_spec.get("images") if isinstance(provider_spec, dict) else None
    )
    return _finish(
        provider="kubernetes" if provider_object else None,
        entity_kind=_kind(provider_object.get("provider_kind")),
        provider_native_entity_id=provider_object.get("uid"),
        mutation_family="field_change" if changed_field and provider_object else None,
        changed_field=changed_field if provider_object else None,
        before_value_ref=_normalized_value(before_value),
        before_value_hash=value_hash(before_value),
        after_value_ref=_normalized_value(provider_images),
        after_value_hash=value_hash(provider_images),
        scenario_logical_entity=logical_entity or None,
        scenario_logical_change=intent.get("root_change"),
        evidence_source="kubernetes_api+provider_receipt",
    )


def _native_id(change: dict[str, Any]) -> str | None:
    for side in (change.get("after"), change.get("before")):
        if isinstance(side, dict):
            properties = side.get("properties")
            if isinstance(properties, dict) and properties.get("uid"):
                return str(properties["uid"])
    entity_id = change.get("entity_id")
    if isinstance(entity_id, str) and entity_id.startswith("k8s:"):
        return entity_id.rsplit(":", 1)[-1]
    return None


def fingerprints_from_change(
    change: dict[str, Any] | None,
    *,
    evidence_source: str,
    initiating_event_id: str | None = None,
    source_change_id: str | None = None,
) -> list[CauseFingerprint]:
    """Derive only what this change layer itself carries."""

    if not change:
        return [CauseFingerprint(evidence_source=evidence_source)]
    changed_fields = change.get("changed_fields")
    if not isinstance(changed_fields, dict) or not changed_fields:
        return [
            _finish(
                provider=(
                    "kubernetes"
                    if str(change.get("entity_kind") or "").lower().startswith(
                        "kubernetes"
                    )
                    else None
                ),
                entity_kind=_kind(change.get("entity_kind")),
                canonical_entity_id=change.get("entity_id"),
                provider_native_entity_id=_native_id(change),
                mutation_family=(
                    "field_change" if change.get("change_type") == "entity_updated" else None
                ),
                initiating_event_id=initiating_event_id,
                source_change_id=source_change_id or change.get("change_id"),
                evidence_source=evidence_source,
            )
        ]
    results: list[CauseFingerprint] = []
    for field_name in sorted(changed_fields):
        values = changed_fields.get(field_name) or {}
        before = values.get("before") if isinstance(values, dict) else None
        after = values.get("after") if isinstance(values, dict) else None
        results.append(
            _finish(
                provider=(
                    "kubernetes"
                    if str(change.get("entity_kind") or "").lower().startswith(
                        "kubernetes"
                    )
                    else None
                ),
                entity_kind=_kind(change.get("entity_kind")),
                canonical_entity_id=change.get("entity_id"),
                provider_native_entity_id=_native_id(change),
                mutation_family="field_change",
                changed_field=field_name,
                before_value_ref=_normalized_value(before),
                before_value_hash=value_hash(before),
                after_value_ref=_normalized_value(after),
                after_value_hash=value_hash(after),
                initiating_event_id=initiating_event_id,
                source_change_id=source_change_id or change.get("change_id"),
                evidence_source=evidence_source,
            )
        )
    return results


def fingerprints_from_event(
    event: dict[str, Any] | None, *, evidence_source: str
) -> list[CauseFingerprint]:
    if not event:
        return [CauseFingerprint(evidence_source=evidence_source)]
    metadata = event.get("metadata")
    change = dict(metadata) if isinstance(metadata, dict) else {}
    refs = change.get("entity_refs") or []
    if refs and isinstance(refs[0], dict):
        change.setdefault("entity_id", refs[0].get("entity_id"))
        change.setdefault("entity_kind", refs[0].get("kind"))
    return fingerprints_from_change(
        change,
        evidence_source=evidence_source,
        initiating_event_id=event.get("event_id"),
        source_change_id=event.get("origin_change_id"),
    )


def _comparison(expected: Any, actual: Any) -> str:
    if expected is None or actual is None:
        return "not_comparable"
    return "matched" if expected == actual else "mismatched"


def compare_causes(
    expected: CauseFingerprint, actual: CauseFingerprint
) -> CauseMatchResult:
    expected_identity = (
        ("provider_native_entity_id", expected.provider_native_entity_id)
        if expected.provider_native_entity_id
        else ("canonical_entity_id", expected.canonical_entity_id)
    )
    actual_identity = (
        actual.provider_native_entity_id
        if expected_identity[0] == "provider_native_entity_id"
        else actual.canonical_entity_id
    )
    comparisons = {
        "provider": _comparison(expected.provider, actual.provider),
        "entity_kind": _comparison(_kind(expected.entity_kind), _kind(actual.entity_kind)),
        "entity_identity": _comparison(expected_identity[1], actual_identity),
        "mutation_family": _comparison(
            expected.mutation_family, actual.mutation_family
        ),
        "changed_field": _comparison(
            _field(expected.changed_field), _field(actual.changed_field)
        ),
        "before_value": _comparison(
            expected.before_value_hash, actual.before_value_hash
        ),
        "after_value": _comparison(
            expected.after_value_hash, actual.after_value_hash
        ),
        "initiating_event_id": _comparison(
            expected.initiating_event_id, actual.initiating_event_id
        ),
        "source_change_id": _comparison(
            expected.source_change_id, actual.source_change_id
        ),
    }
    compared = sorted(key for key, value in comparisons.items() if value != "not_comparable")
    mismatched = sorted(key for key, value in comparisons.items() if value == "mismatched")
    unavailable = sorted(
        key for key, value in comparisons.items() if value == "not_comparable"
    )

    entity_match = comparisons["entity_identity"] == "matched"
    mutation_matches = all(
        comparisons[key] == "matched"
        for key in ("mutation_family", "changed_field")
    )
    core = (
        "provider",
        "entity_kind",
        "entity_identity",
        "mutation_family",
        "changed_field",
        "before_value",
        "after_value",
    )
    if mismatched:
        if entity_match and any(
            comparisons[key] == "mismatched"
            for key in ("mutation_family", "changed_field", "before_value", "after_value")
        ):
            status = "entity_match_mutation_mismatch"
        elif mutation_matches and comparisons["entity_identity"] == "mismatched":
            status = "mutation_match_entity_mismatch"
        else:
            status = "different_cause"
    elif all(comparisons[key] == "matched" for key in core):
        status = "exact"
    elif entity_match and mutation_matches:
        status = "compatible_partial"
    else:
        status = "insufficient_structure"
    return CauseMatchResult(
        match_version=CAUSE_MATCH_VERSION,
        status=status,
        comparisons=comparisons,
        compared_fields=compared,
        mismatched_fields=mismatched,
        unavailable_fields=unavailable,
    )


def best_cause_match(
    expected: CauseFingerprint, actual: Iterable[CauseFingerprint]
) -> tuple[CauseFingerprint, CauseMatchResult]:
    priority = {
        "exact": 5,
        "compatible_partial": 4,
        "insufficient_structure": 3,
        "entity_match_mutation_mismatch": 2,
        "mutation_match_entity_mismatch": 1,
        "different_cause": 0,
    }
    choices = [(item, compare_causes(expected, item)) for item in actual]
    if not choices:
        item = CauseFingerprint()
        return item, compare_causes(expected, item)
    return max(
        choices,
        key=lambda choice: (
            priority[choice[1].status],
            len(choice[1].compared_fields),
            json.dumps(choice[0].as_dict(), sort_keys=True, default=str),
        ),
    )
