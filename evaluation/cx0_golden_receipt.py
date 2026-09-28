from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence


VALIDATOR_VERSION = "cx0-golden-receipt-validator-v1"
GROUND_TRUTH_VERSION = "cx0-golden-ground-truth-v1"
RECEIPT_VERSION = "cx0-golden-scenario-receipt-v1"
SUPPORTED_STATE = "supported_under_current_model"

_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_EVIDENCE_SEMANTICS = {"observed", "declared", "derived", "inferred"}
_EVIDENCE_QUALITY = {"direct", "strong", "limited", "legacy", "unknown"}
_ABSTENTION_STATES = {
    "insufficient_candidate_specific_evidence",
    "incomplete",
    "contested_with_gaps",
    "not_evaluated_no_incident",
}


@dataclass(frozen=True)
class GoldenReceiptDecision:
    scenario_id: str | None
    requested_status: str | None
    valid: bool
    errors: tuple[str, ...]
    validator_version: str = VALIDATOR_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "validator_version": self.validator_version,
            "scenario_id": self.scenario_id,
            "requested_status": self.requested_status,
            "valid": self.valid,
            "errors": list(self.errors),
        }


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"CX-0 authority is not an object: {path}")
    return value


def _present_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _utc_time(value: Any) -> bool:
    if not _present_text(value):
        return False
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _reference_ids(receipt: Mapping[str, Any]) -> set[str]:
    return {
        str(item.get("evidence_id"))
        for item in receipt.get("evidence_references") or []
        if isinstance(item, Mapping) and _present_text(item.get("evidence_id"))
    }


def _append_mismatch(
    errors: list[str],
    *,
    field: str,
    actual: Any,
    expected: Any,
) -> None:
    if actual != expected:
        errors.append(f"{field}_mismatch")


def _validate_hop_authority(
    hop: Mapping[str, Any],
    *,
    evidence_ids: set[str],
    errors: list[str],
    label: str,
) -> None:
    required_text = (
        "from",
        "to",
        "predicate",
        "relationship_id",
        "provenance_source",
        "valid_effective_time",
        "learned_recorded_time",
        "evidence_quality",
        "contradiction_or_missing_state",
    )
    if any(not _present_text(hop.get(field)) for field in required_text):
        errors.append(f"causal_hop_authority_incomplete:{label}")
        return
    references = hop.get("evidence_reference_ids")
    if not isinstance(references, list) or not references:
        errors.append(f"causal_hop_evidence_missing:{label}")
    elif any(reference not in evidence_ids for reference in references):
        errors.append(f"causal_hop_evidence_unresolved:{label}")
    if hop.get("evidence_semantics") not in _EVIDENCE_SEMANTICS:
        errors.append(f"causal_hop_evidence_semantics_invalid:{label}")
    if hop.get("evidence_quality") not in _EVIDENCE_QUALITY:
        errors.append(f"causal_hop_evidence_quality_invalid:{label}")
    if not _utc_time(hop.get("valid_effective_time")):
        errors.append(f"causal_hop_effective_time_invalid:{label}")
    if not _utc_time(hop.get("learned_recorded_time")):
        errors.append(f"causal_hop_recorded_time_invalid:{label}")
    if hop.get("contradiction_or_missing_state") != "none":
        errors.append(f"causal_hop_not_fully_supported:{label}")


def _validate_criteria(
    receipt: Mapping[str, Any],
    scenario: Mapping[str, Any],
    *,
    evidence_ids: set[str],
    errors: list[str],
) -> None:
    expected = list(scenario.get("pass_criteria") or [])
    results = receipt.get("pass_criteria_results")
    if not isinstance(results, list):
        errors.append("pass_criteria_results_missing")
        return
    by_id: dict[str, Mapping[str, Any]] = {}
    duplicates: set[str] = set()
    for item in results:
        if not isinstance(item, Mapping):
            errors.append("pass_criterion_result_invalid")
            continue
        criterion_id = item.get("criterion_id")
        if not _present_text(criterion_id):
            errors.append("pass_criterion_id_missing")
            continue
        key = str(criterion_id)
        if key in by_id:
            duplicates.add(key)
        by_id[key] = item
    if duplicates:
        errors.append("pass_criteria_duplicate")
    if set(by_id) != set(expected):
        errors.append("pass_criteria_set_mismatch")
    for criterion_id in expected:
        item = by_id.get(criterion_id)
        if item is None:
            continue
        if item.get("passed") is not True:
            errors.append(f"pass_criterion_failed:{criterion_id}")
        references = item.get("evidence_reference_ids")
        if not isinstance(references, list) or not references:
            errors.append(f"pass_criterion_evidence_missing:{criterion_id}")
        elif any(reference not in evidence_ids for reference in references):
            errors.append(f"pass_criterion_evidence_unresolved:{criterion_id}")


def _validate_abstention(
    receipt: Mapping[str, Any],
    *,
    evidence_ids: set[str],
    errors: list[str],
) -> None:
    if receipt.get("actual_supported_hypotheses"):
        errors.append("abstention_supported_projection_not_empty")
    result = receipt.get("abstention_result")
    if not isinstance(result, Mapping):
        errors.append("abstention_result_missing")
        return
    if result.get("observed") is not True:
        errors.append("abstention_not_observed")
    if result.get("supported_projection_empty") is not True:
        errors.append("abstention_projection_not_proven_empty")
    if not _present_text(result.get("reason")):
        errors.append("abstention_reason_missing")
    references = result.get("evidence_reference_ids")
    if not isinstance(references, list) or not references:
        errors.append("abstention_evidence_missing")
    elif any(reference not in evidence_ids for reference in references):
        errors.append("abstention_evidence_unresolved")
    gate = receipt.get("support_gate_result")
    state = gate.get("state") if isinstance(gate, Mapping) else None
    if state not in _ABSTENTION_STATES:
        errors.append("abstention_support_gate_state_invalid")


def _validate_positive_cause(
    receipt: Mapping[str, Any],
    scenario: Mapping[str, Any],
    truth: Mapping[str, Any],
    *,
    evidence_ids: set[str],
    errors: list[str],
) -> None:
    supported = receipt.get("actual_supported_hypotheses")
    if not isinstance(supported, list) or not supported:
        errors.append("supported_top1_missing")
    else:
        rank_one = [
            item
            for item in supported
            if isinstance(item, Mapping) and item.get("rank") == 1
        ]
        if len(rank_one) != 1:
            errors.append("supported_top1_missing")
        else:
            top = rank_one[0]
            if top.get("cause") != truth.get("expected_supported_cause"):
                errors.append("supported_top1_mismatch")
            if top.get("support_qualified") is not True:
                errors.append("supported_top1_not_support_qualified")
            if top.get("evidence_state") != SUPPORTED_STATE:
                errors.append("supported_top1_evidence_state_invalid")
            gate = receipt.get("support_gate_result")
            gate_ids = (
                gate.get("supported_hypothesis_ids")
                if isinstance(gate, Mapping)
                else []
            )
            if top.get("hypothesis_id") not in (gate_ids or []):
                errors.append("supported_top1_not_in_support_gate_projection")

    actual_hops = receipt.get("causal_path")
    if not isinstance(actual_hops, list):
        errors.append("causal_path_missing")
        actual_hops = []
    triples: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for index, hop in enumerate(actual_hops):
        if not isinstance(hop, Mapping):
            errors.append(f"causal_hop_invalid:{index}")
            continue
        label = str(hop.get("relationship_id") or index)
        _validate_hop_authority(
            hop,
            evidence_ids=evidence_ids,
            errors=errors,
            label=label,
        )
        triple = (
            str(hop.get("from") or ""),
            str(hop.get("predicate") or ""),
            str(hop.get("to") or ""),
        )
        triples.setdefault(triple, []).append(hop)
    for required in scenario.get("expected_required_causal_hops") or []:
        key = (required["from"], required.get("predicate", ""), required["to"])
        if key not in triples:
            errors.append("required_causal_hop_missing:" + "|".join(key))


def _validate_time_two(
    receipt: Mapping[str, Any],
    *,
    errors: list[str],
) -> None:
    audit = receipt.get("temporal_audit")
    if not isinstance(audit, Mapping):
        errors.append("g_time_2_temporal_audit_missing")
        return
    if not _utc_time(audit.get("valid_effective_time")):
        errors.append("g_time_2_effective_time_invalid")
    if not _utc_time(audit.get("learned_recorded_time")):
        errors.append("g_time_2_recorded_time_invalid")
    if audit.get("arrival_order_rewrites_provider_truth") is not False:
        errors.append("g_time_2_arrival_order_rewrite_detected")
    if audit.get("future_state_substitution_used") is not False:
        errors.append("g_time_2_future_state_substitution_detected")
    if audit.get("historical_entity_identity_unchanged") is not True:
        errors.append("g_time_2_historical_identity_changed")
    if audit.get("recomputation_performed") is True:
        for field in (
            "prior_analysis_id",
            "prior_analysis_state",
            "revised_analysis_id",
            "revised_analysis_state",
        ):
            if not _present_text(audit.get(field)):
                errors.append(f"g_time_2_{field}_missing")
        if audit.get("prior_analysis_id") == audit.get("revised_analysis_id"):
            errors.append("g_time_2_analysis_revision_identity_not_distinct")
    elif any(
        audit.get(field) is not None
        for field in (
            "prior_analysis_id",
            "prior_analysis_state",
            "revised_analysis_id",
            "revised_analysis_state",
        )
    ):
        errors.append("g_time_2_analysis_revision_present_without_recomputation")


def _validate_pass(
    receipt: Mapping[str, Any],
    scenario: Mapping[str, Any],
    truth: Mapping[str, Any],
    *,
    errors: list[str],
) -> None:
    evidence_ids = _reference_ids(receipt)
    _validate_criteria(
        receipt,
        scenario,
        evidence_ids=evidence_ids,
        errors=errors,
    )
    if not _SHA1.fullmatch(str(receipt.get("source_head") or "")):
        errors.append("source_head_authority_missing")
    if not _SHA1.fullmatch(str(receipt.get("source_tree") or "")):
        errors.append("source_tree_authority_missing")
    if not _SHA256.fullmatch(
        str(receipt.get("precondition_fingerprint") or "")
    ):
        errors.append("precondition_fingerprint_missing")
    if not _SHA256.fullmatch(
        str(receipt.get("infrastructure_fingerprint") or "")
    ):
        errors.append("infrastructure_fingerprint_missing")
    if not _SHA256.fullmatch(
        str(receipt.get("post_cleanup_fingerprint") or "")
    ):
        errors.append("post_cleanup_fingerprint_missing")
    if not _utc_time(receipt.get("scenario_end_utc")):
        errors.append("scenario_end_utc_missing")
    cleanup = receipt.get("cleanup_result")
    if not isinstance(cleanup, Mapping) or cleanup.get("completed") is not True:
        errors.append("cleanup_incomplete")
    if (
        not isinstance(cleanup, Mapping)
        or cleanup.get("protected_control_plane_unchanged") is not True
    ):
        errors.append("protected_control_plane_changed")
    if receipt.get("unsupported_critical_hop_count") != 0:
        errors.append("unsupported_critical_hops_present")

    requirements = scenario.get("receipt_requirements") or {}
    if requirements.get("actual_incident_required") and not _present_text(
        receipt.get("actual_incident_id")
    ):
        errors.append("actual_incident_required")
    if requirements.get("actual_snapshot_required") and not _present_text(
        receipt.get("actual_snapshot_id")
    ):
        errors.append("actual_snapshot_required")

    expected_cause = truth.get("expected_supported_cause")
    if truth.get("expected_abstention"):
        _validate_abstention(
            receipt,
            evidence_ids=evidence_ids,
            errors=errors,
        )
    elif expected_cause is not None:
        _validate_positive_cause(
            receipt,
            scenario,
            truth,
            evidence_ids=evidence_ids,
            errors=errors,
        )

    live_positive = (
        str(scenario.get("execution_class", "")).startswith("LIVE_GOLDEN")
        and expected_cause is not None
    )
    if live_positive:
        for field in (
            "backend_image_digest",
            "frontend_image_digest",
            "observer_image_digest",
        ):
            if not _IMAGE_DIGEST.fullmatch(str(receipt.get(field) or "")):
                errors.append(f"{field}_authority_missing")
        if not _present_text(receipt.get("database_migration_head")):
            errors.append("database_migration_head_missing")
        if receipt.get("schema_version") != RECEIPT_VERSION:
            errors.append("receipt_schema_authority_invalid")

    if truth.get("expected_recovery_condition") is not None:
        recovery = receipt.get("recovery_result")
        if not isinstance(recovery, Mapping) or recovery.get("status") != "VERIFIED":
            errors.append("recovery_not_verified")
        elif not recovery.get("references"):
            errors.append("recovery_evidence_missing")

    if scenario.get("scenario_id") == "G-TIME-2":
        _validate_time_two(receipt, errors=errors)


def validate_golden_receipt(
    receipt: Mapping[str, Any],
    *,
    repository_root: Path | None = None,
) -> GoldenReceiptDecision:
    """Validate whether a requested CX-0 receipt status is semantically valid.

    JSON Schema validation remains the structural boundary. This deterministic
    grader binds the receipt to frozen authority, scenario, and independent
    truth, then enforces status-specific semantics without product imports.
    """

    root = repository_root or _repository_root()
    authority = _load_json(
        root / "evaluation/golden/cx0/golden_evaluation_authority_v1.json"
    )
    corpus = _load_json(
        root / "evaluation/golden/cx0/golden_scenario_corpus_v1.json"
    )
    ground_truth = _load_json(
        root / "evaluation/golden/cx0/golden_ground_truth_v1.json"
    )
    errors: list[str] = []
    scenario_id = receipt.get("scenario_id")
    requested_status = receipt.get("status")
    scenarios = {
        item["scenario_id"]: item for item in corpus.get("scenarios") or []
    }
    truths = {
        item["scenario_id"]: item
        for item in ground_truth.get("ground_truth_records") or []
    }
    scenario = scenarios.get(scenario_id)
    truth = truths.get(scenario_id)
    if scenario is None:
        errors.append("scenario_not_in_frozen_corpus")
    if truth is None:
        errors.append("ground_truth_not_frozen")
    if scenario is None or truth is None:
        return GoldenReceiptDecision(
            scenario_id=str(scenario_id) if scenario_id is not None else None,
            requested_status=(
                str(requested_status) if requested_status is not None else None
            ),
            valid=False,
            errors=tuple(errors),
        )

    _append_mismatch(
        errors,
        field="scenario_family",
        actual=receipt.get("scenario_family"),
        expected=scenario.get("scenario_family"),
    )
    _append_mismatch(
        errors,
        field="scenario_contract_version",
        actual=receipt.get("scenario_contract_version"),
        expected=scenario.get("scenario_contract_version"),
    )
    _append_mismatch(
        errors,
        field="execution_class",
        actual=receipt.get("execution_class"),
        expected=scenario.get("execution_class"),
    )
    expected_ref = {
        "ground_truth_id": truth.get("ground_truth_id"),
        "ground_truth_version": GROUND_TRUTH_VERSION,
        "path": "evaluation/golden/cx0/golden_ground_truth_v1.json",
    }
    _append_mismatch(
        errors,
        field="ground_truth_ref",
        actual=receipt.get("ground_truth_ref"),
        expected=expected_ref,
    )
    for receipt_field, truth_field in (
        ("expected_cause", "expected_supported_cause"),
        ("expected_abstention", "expected_abstention"),
        ("expected_affected_entities", "expected_affected_entities"),
        ("expected_required_causal_hops", "expected_required_causal_hops"),
    ):
        _append_mismatch(
            errors,
            field=receipt_field,
            actual=receipt.get(receipt_field),
            expected=truth.get(truth_field),
        )

    allowed_statuses = set(authority["result_contract"]["status_values"])
    if requested_status not in allowed_statuses:
        errors.append("requested_status_invalid")
    elif requested_status == "PASS":
        _validate_pass(receipt, scenario, truth, errors=errors)
    elif requested_status == "CONSTRUCTION_BLOCKED":
        allowed_reasons = set(
            authority["construction_blocked_contract"]["allowed_reason_codes"]
        )
        if receipt.get("construction_blocked_reason") not in allowed_reasons:
            errors.append("construction_blocked_reason_not_representability_failure")
    elif receipt.get("construction_blocked_reason") is not None:
        errors.append("construction_blocked_reason_reserved")

    return GoldenReceiptDecision(
        scenario_id=str(scenario_id),
        requested_status=str(requested_status),
        valid=not errors,
        errors=tuple(errors),
    )


def validate_golden_receipt_path(
    receipt_path: Path,
    *,
    repository_root: Path | None = None,
) -> GoldenReceiptDecision:
    return validate_golden_receipt(
        _load_json(receipt_path),
        repository_root=repository_root,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate one sanitized CX-0 golden scenario receipt."
    )
    parser.add_argument("receipt", type=Path)
    arguments = parser.parse_args(argv)
    decision = validate_golden_receipt_path(arguments.receipt)
    print(json.dumps(decision.as_dict(), indent=2, sort_keys=True))
    return 0 if decision.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
