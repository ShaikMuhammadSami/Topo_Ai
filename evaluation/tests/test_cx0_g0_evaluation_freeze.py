from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_PATH = (
    ROOT / "evaluation/golden/cx0/golden_evaluation_authority_v1.json"
)
CORPUS_PATH = ROOT / "evaluation/golden/cx0/golden_scenario_corpus_v1.json"
GROUND_TRUTH_PATH = ROOT / "evaluation/golden/cx0/golden_ground_truth_v1.json"
RECEIPT_SCHEMA_PATH = (
    ROOT
    / "docs/architecture/evaluation/cx0-golden-scenario-receipt-v1.schema.json"
)
DOCUMENT_PATH = (
    ROOT / "docs/architecture/evaluation/cx0-g0-evaluation-freeze-v1.md"
)

MANDATORY_IDS = (
    "G-POS-1",
    "G-EPH-1",
    "G-EPH-2",
    "G-EPH-3",
    "G-TIME-1",
    "G-TIME-2",
    "G-ADV-1",
    "G-ADV-2",
    "G-REC-1",
)
EXECUTION_CLASSES = {
    "OFFLINE_FIXTURE",
    "LIVE_GOLDEN",
    "LIVE_GOLDEN_SYNTHETIC_MUTATION",
    "FUTURE_EPHEMERAL_CLOUD",
}
RECEIPT_STATUSES = {
    "PASS",
    "FAIL",
    "CONSTRUCTION_BLOCKED",
    "INCOMPLETE",
}


class SchemaValidationError(ValueError):
    """Narrow local validator error for the frozen G0 receipt contract."""


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def authority() -> dict[str, Any]:
    return _load(AUTHORITY_PATH)


@pytest.fixture(scope="module")
def corpus() -> dict[str, Any]:
    return _load(CORPUS_PATH)


@pytest.fixture(scope="module")
def truth() -> dict[str, Any]:
    return _load(GROUND_TRUTH_PATH)


@pytest.fixture(scope="module")
def receipt_schema() -> dict[str, Any]:
    return _load(RECEIPT_SCHEMA_PATH)


def _sample_receipt(status: str = "PASS") -> dict[str, Any]:
    reason = (
        "evidence_model_nonseparable"
        if status == "CONSTRUCTION_BLOCKED"
        else None
    )
    return {
        "schema_version": "cx0-golden-scenario-receipt-v1",
        "scenario_id": "G-POS-1",
        "scenario_family": "canonical_source_to_runtime_recovery",
        "scenario_contract_version": "cx0-golden-scenario-v1",
        "execution_class": "LIVE_GOLDEN_SYNTHETIC_MUTATION",
        "ground_truth_ref": {
            "ground_truth_id": "gt:G-POS-1:v1",
            "ground_truth_version": "cx0-golden-ground-truth-v1",
            "path": "evaluation/golden/cx0/golden_ground_truth_v1.json",
        },
        "source_head": "a" * 40,
        "source_tree": "b" * 40,
        "backend_image_digest": "sha256:" + "1" * 64,
        "frontend_image_digest": "sha256:" + "2" * 64,
        "observer_image_digest": "sha256:" + "3" * 64,
        "database_migration_head": "0008_example",
        "infrastructure_fingerprint": "4" * 64,
        "scenario_start_utc": "2026-09-28T00:00:00Z",
        "scenario_end_utc": "2026-09-28T00:10:00Z",
        "precondition_fingerprint": "5" * 64,
        "authorized_mutation": {
            "mutation_class": "evaluation_namespace_workload_rollout",
            "scope": "topo-eval",
            "action_reference": "provider-action:1",
        },
        "expected_cause": {
            "cause_kind": "source_file_mutation",
            "logical_change": "healthy_to_fail",
            "semantic_level": "INITIATING_MUTATION",
        },
        "expected_abstention": False,
        "expected_affected_entities": [
            {
                "logical_alias": "failing_pod_uid",
                "canonical_entity_id": "k8s:pod:1",
                "provider_uid": "00000000-0000-0000-0000-000000000001",
            }
        ],
        "expected_required_causal_hops": [
            {
                "from": "source_commit",
                "predicate": "triggers",
                "to": "actions_run",
                "relationship_id": "rel:1",
            }
        ],
        "actual_incident_id": "incident:1",
        "actual_snapshot_id": "snapshot:1",
        "actual_supported_hypotheses": [
            {
                "hypothesis_id": "hypothesis:supported",
                "rank": 1,
                "root_event_id": "change-event:golden",
                "evidence_state": "supported_under_current_model",
                "support_qualified": True,
            }
        ],
        "actual_diagnostic_hypotheses": [
            {
                "hypothesis_id": "hypothesis:distractor",
                "rank": 1,
                "root_event_id": "change-event:distractor",
                "evidence_state": "insufficient_candidate_specific_evidence",
                "support_qualified": False,
            }
        ],
        "support_gate_result": {
            "policy_version": "causal-support-gate-v1",
            "state": "supported_under_current_model",
            "supported_hypothesis_ids": ["hypothesis:supported"],
        },
        "evidence_references": [
            {
                "evidence_id": "evidence:1",
                "evidence_type": "provider_lineage",
                "source_reference": "receipt:1",
            }
        ],
        "causal_path": [
            {
                "from": "source_commit",
                "predicate": "triggers",
                "to": "actions_run",
                "relationship_id": "rel:1",
            }
        ],
        "impact": None,
        "ownership": None,
        "response_guidance": None,
        "recovery_result": {
            "status": "VERIFIED",
            "summary": "Provider health recovered after a human action.",
            "references": ["provider-action:2"],
        },
        "cleanup_result": {
            "completed": True,
            "protected_control_plane_unchanged": True,
            "removed_scenario_assets": ["topo-eval/workload"],
            "warnings": [],
        },
        "post_cleanup_fingerprint": "6" * 64,
        "status": status,
        "construction_blocked_reason": reason,
        "limitations": ["single controlled scenario"],
    }


def _validate(schema: dict[str, Any], value: dict[str, Any]) -> None:
    properties = schema["properties"]
    missing = set(schema["required"]) - set(value)
    unexpected = set(value) - set(properties)
    if missing:
        raise SchemaValidationError(f"missing fields: {sorted(missing)}")
    if schema.get("additionalProperties") is False and unexpected:
        raise SchemaValidationError(f"unexpected fields: {sorted(unexpected)}")
    if value["status"] not in properties["status"]["enum"]:
        raise SchemaValidationError("unsupported status")
    reason = value["construction_blocked_reason"]
    if value["status"] == "CONSTRUCTION_BLOCKED":
        if not isinstance(reason, str) or not reason:
            raise SchemaValidationError("construction-blocked reason required")
    elif reason is not None:
        raise SchemaValidationError("reason is reserved for construction-blocked")
    for field in (
        "schema_version",
        "scenario_contract_version",
    ):
        expected = properties[field]["const"]
        if value[field] != expected:
            raise SchemaValidationError(f"invalid {field}")
    for field in ("source_head", "source_tree"):
        if re.fullmatch(properties[field]["pattern"], value[field]) is None:
            raise SchemaValidationError(f"invalid {field}")
    if value["execution_class"] not in properties["execution_class"]["enum"]:
        raise SchemaValidationError("unsupported execution class")


def _assert_local_refs_resolve(schema: dict[str, Any], value: Any) -> None:
    if isinstance(value, dict):
        reference = value.get("$ref")
        if reference is not None:
            assert reference.startswith("#/$defs/")
            assert reference.removeprefix("#/$defs/") in schema["$defs"]
        for item in value.values():
            _assert_local_refs_resolve(schema, item)
    elif isinstance(value, list):
        for item in value:
            _assert_local_refs_resolve(schema, item)


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            keys.append(str(key).lower())
            keys.extend(_walk_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.extend(_walk_keys(item))
    return keys


def test_authority_binds_accepted_pre_g0_source_and_versioned_contracts(
    authority: dict[str, Any],
) -> None:
    assert authority["schema_version"] == "cx0-golden-evaluation-authority-v1"
    assert authority["source_head_at_freeze"] == (
        "0e2e6b2588c7eef67315a726dbb1ee80d7562f9d"
    )
    assert authority["source_tree_at_freeze"] == (
        "cdda46c8eace68d54607cf458f4e7c07f6fcfba6"
    )
    assert authority["evaluation_harness"]["contract_version"] == "eval-1.v1"
    assert authority["scenario_corpus"]["contract_version"] == (
        "cx0-golden-scenario-corpus-v1"
    )
    assert authority["ground_truth"]["contract_version"] == (
        "cx0-golden-ground-truth-v1"
    )
    assert authority["result_contract"]["schema_version"] == (
        "cx0-golden-scenario-receipt-v1"
    )


def test_all_and_only_mandatory_scenarios_are_frozen(
    authority: dict[str, Any], corpus: dict[str, Any]
) -> None:
    scenario_ids = tuple(item["scenario_id"] for item in corpus["scenarios"])
    assert scenario_ids == MANDATORY_IDS
    assert tuple(authority["mandatory_pre_cx0b_scenarios"]) == MANDATORY_IDS
    assert len(scenario_ids) == 9


def test_every_scenario_has_frozen_independent_ground_truth(
    corpus: dict[str, Any], truth: dict[str, Any]
) -> None:
    records = {
        item["ground_truth_id"]: item for item in truth["ground_truth_records"]
    }
    assert truth["schema_version"] == "cx0-golden-ground-truth-v1"
    assert len(records) == 9
    for scenario in corpus["scenarios"]:
        record = records[scenario["ground_truth_id"]]
        assert record["scenario_id"] == scenario["scenario_id"]
        assert record["system_under_test_cannot_modify_truth"] is True
        assert record["expected_abstention"] == scenario["expected_abstention"]
        assert record["expected_supported_cause"] == scenario["expected_supported_cause"]
        assert record["truth_source_authorities"]


def test_execution_classes_and_live_protection_boundary(corpus: dict[str, Any]) -> None:
    assert set(corpus["execution_classes"]) == EXECUTION_CLASSES
    for scenario in corpus["scenarios"]:
        assert scenario["execution_class"] in EXECUTION_CLASSES
        assert scenario["scenario_contract_version"] == "cx0-golden-scenario-v1"
        if scenario["execution_class"].startswith("LIVE_GOLDEN"):
            scope = scenario["mutation_scope"]
            assert scope["evaluation_namespace"] == "topo-eval"
            assert scope["protected_control_plane"] == "topo-system"
            assert "topo_system_mutation" in scenario["prohibited_mutation_classes"]
            assert scenario["cleanup_contract"][
                "protected_control_plane_must_be_unchanged"
            ] is True


def test_each_scenario_freezes_required_contract_fields(corpus: dict[str, Any]) -> None:
    required = {
        "scenario_id",
        "scenario_family",
        "scenario_contract_version",
        "execution_class",
        "prerequisites",
        "authorized_mutation_classes",
        "prohibited_mutation_classes",
        "expected_supported_cause",
        "expected_abstention",
        "expected_affected_entities",
        "expected_required_causal_hops",
        "expected_identity_invariants",
        "expected_temporal_invariants",
        "expected_support_gate_behavior",
        "cleanup_contract",
        "pass_criteria",
        "ground_truth_id",
    }
    for scenario in corpus["scenarios"]:
        assert required <= set(scenario)
        assert scenario["prerequisites"]
        assert scenario["prohibited_mutation_classes"]
        assert scenario["expected_identity_invariants"]
        assert scenario["expected_temporal_invariants"]
        assert scenario["pass_criteria"]


def test_receipt_schema_is_valid_and_contains_every_required_field(
    receipt_schema: dict[str, Any],
) -> None:
    assert receipt_schema["$schema"] == (
        "https://json-schema.org/draft/2020-12/schema"
    )
    assert receipt_schema["type"] == "object"
    assert receipt_schema["additionalProperties"] is False
    _assert_local_refs_resolve(receipt_schema, receipt_schema)
    required = {
        "scenario_id",
        "scenario_family",
        "scenario_contract_version",
        "execution_class",
        "source_head",
        "source_tree",
        "backend_image_digest",
        "frontend_image_digest",
        "observer_image_digest",
        "database_migration_head",
        "infrastructure_fingerprint",
        "scenario_start_utc",
        "scenario_end_utc",
        "precondition_fingerprint",
        "authorized_mutation",
        "expected_cause",
        "expected_abstention",
        "expected_affected_entities",
        "expected_required_causal_hops",
        "actual_incident_id",
        "actual_snapshot_id",
        "actual_supported_hypotheses",
        "actual_diagnostic_hypotheses",
        "support_gate_result",
        "evidence_references",
        "causal_path",
        "impact",
        "ownership",
        "response_guidance",
        "recovery_result",
        "cleanup_result",
        "post_cleanup_fingerprint",
        "status",
        "construction_blocked_reason",
        "limitations",
        "ground_truth_ref",
    }
    assert required <= set(receipt_schema["required"])


@pytest.mark.parametrize("status", sorted(RECEIPT_STATUSES))
def test_receipt_status_contract_accepts_exactly_frozen_statuses(
    receipt_schema: dict[str, Any], status: str
) -> None:
    _validate(receipt_schema, _sample_receipt(status))
    assert set(receipt_schema["properties"]["status"]["enum"]) == RECEIPT_STATUSES


def test_construction_blocked_requires_reason_and_other_statuses_forbid_it(
    receipt_schema: dict[str, Any],
) -> None:
    blocked = _sample_receipt("CONSTRUCTION_BLOCKED")
    blocked["construction_blocked_reason"] = None
    with pytest.raises(SchemaValidationError):
        _validate(receipt_schema, blocked)

    passed = _sample_receipt("PASS")
    passed["construction_blocked_reason"] = "test_was_inconvenient"
    with pytest.raises(SchemaValidationError):
        _validate(receipt_schema, passed)

    invalid = _sample_receipt("PASS")
    invalid["status"] = "HARNESS_ERROR"
    with pytest.raises(SchemaValidationError):
        _validate(receipt_schema, invalid)


def test_result_receipt_references_but_cannot_become_ground_truth_authority(
    authority: dict[str, Any], receipt_schema: dict[str, Any]
) -> None:
    assert "ground_truth" not in receipt_schema["properties"]
    assert "ground_truth_ref" in receipt_schema["required"]
    for path in authority["ground_truth"]["authority_paths"]:
        assert not path.startswith("evaluation/results/")
    assert authority["ground_truth"]["derived_from_result_output"] is False


def test_secret_bearing_fields_are_not_part_of_any_g0_machine_contract(
    authority: dict[str, Any],
    corpus: dict[str, Any],
    truth: dict[str, Any],
    receipt_schema: dict[str, Any],
) -> None:
    forbidden_keys = {
        "password",
        "database_url",
        "db_url",
        "token",
        "cookie",
        "kubeconfig",
        "secret_value",
        "secretstore_value",
        "keyring",
    }
    for contract in (authority, corpus, truth, receipt_schema):
        assert forbidden_keys.isdisjoint(_walk_keys(contract))

    receipt = _sample_receipt()
    receipt["password"] = "forbidden"
    with pytest.raises(SchemaValidationError):
        _validate(receipt_schema, receipt)


def test_supported_and_diagnostic_projections_remain_distinct(
    authority: dict[str, Any], receipt_schema: dict[str, Any]
) -> None:
    assert authority["supported_projection_contract"]["policy_version"] == (
        "causal-support-gate-v1"
    )
    assert authority["diagnostic_projection_contract"]["policy_version"] == (
        "causal-hypothesis-projection-v1"
    )
    required = set(receipt_schema["required"])
    assert "actual_supported_hypotheses" in required
    assert "actual_diagnostic_hypotheses" in required
    receipt = _sample_receipt()
    assert receipt["actual_supported_hypotheses"][0]["hypothesis_id"] != (
        receipt["actual_diagnostic_hypotheses"][0]["hypothesis_id"]
    )
    _validate(receipt_schema, receipt)


def test_raw_or_diagnostic_top1_is_not_required_to_equal_supported_top1(
    authority: dict[str, Any],
) -> None:
    rule = authority["canonical_positive_rule"]
    assert rule == {
        "diagnostic_top1_must_match_expected": False,
        "raw_top1_must_match_expected": False,
        "supported_top1_must_match_expected": True,
    }


def test_distractor_and_missing_lineage_contracts_preserve_support_semantics(
    corpus: dict[str, Any],
) -> None:
    scenarios = {item["scenario_id"]: item for item in corpus["scenarios"]}
    distractor = scenarios["G-ADV-1"]
    assert distractor["expected_support_gate_behavior"][
        "unsupported_candidates_consume_supported_capacity"
    ] is False
    assert (
        "unsupported_high_ranked_distractors_consume_zero_supported_capacity"
        in distractor["pass_criteria"]
    )

    broken = scenarios["G-ADV-2"]
    assert broken["expected_abstention"] is True
    assert broken["expected_supported_cause"] is None
    assert broken["expected_support_gate_behavior"]["supported_projection"] == (
        "EMPTY"
    )
    assert "stale_derived_edge_retention" in broken["prohibited_mutation_classes"]
    assert "partial_atomic_authoritative_observation" in broken[
        "prohibited_mutation_classes"
    ]


def test_cleanup_and_authority_binding_are_mandatory(
    corpus: dict[str, Any], receipt_schema: dict[str, Any]
) -> None:
    assert "cleanup_result" in receipt_schema["required"]
    assert "post_cleanup_fingerprint" in receipt_schema["required"]
    assert "source_head" in receipt_schema["required"]
    assert "source_tree" in receipt_schema["required"]
    assert "backend_image_digest" in receipt_schema["required"]
    assert "frontend_image_digest" in receipt_schema["required"]
    assert "observer_image_digest" in receipt_schema["required"]
    assert "infrastructure_fingerprint" in receipt_schema["required"]
    for scenario in corpus["scenarios"]:
        assert scenario["cleanup_contract"]["post_cleanup_fingerprint_required"]


def test_document_records_inventory_and_claim_boundary() -> None:
    text = DOCUMENT_PATH.read_text(encoding="utf-8")
    for heading in ("REUSE", "EXTEND", "RETIRE / LEGACY", "MISSING after G0"):
        assert heading in text
    assert "EVALUATION_FREEZE_IS_NOT_PRODUCT_CORRECTNESS_PROOF" in text
    assert "CX-0B teardown is not authorized" in text
    assert "G1-G6 sequence" in text


def test_receipt_schema_does_not_mutate_when_validating(
    receipt_schema: dict[str, Any],
) -> None:
    before = deepcopy(receipt_schema)
    _validate(receipt_schema, _sample_receipt())
    assert receipt_schema == before
