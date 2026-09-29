from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from evaluation.cx0_golden_receipt import validate_golden_receipt


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


def _causal_hop(
    ordinal: int,
    source: str,
    predicate: str,
    target: str,
) -> dict[str, Any]:
    return {
        "from": source,
        "to": target,
        "predicate": predicate,
        "relationship_id": f"rel:{ordinal}",
        "provenance_source": "provider_and_topology_evidence",
        "evidence_reference_ids": [f"evidence:{ordinal}"],
        "evidence_semantics": "observed",
        "valid_effective_time": f"2026-09-28T00:0{ordinal}:00Z",
        "learned_recorded_time": f"2026-09-28T00:0{ordinal}:10Z",
        "evidence_quality": "direct",
        "contradiction_or_missing_state": "none",
    }


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
            "failing_pod_uid",
            "owning_replicaset_uid",
            "owning_deployment_uid",
        ],
        "expected_required_causal_hops": [
            "commit_to_run",
            "run_to_image",
            "image_to_deployment",
            "deployment_to_replicaset",
            "replicaset_to_pod",
            "pod_to_failure",
        ],
        "actual_incident_id": "incident:1",
        "actual_snapshot_id": "snapshot:1",
        "actual_supported_hypotheses": [
            {
                "hypothesis_id": "hypothesis:supported",
                "rank": 1,
                "root_event_id": "change-event:golden",
                "cause": {
                    "cause_kind": "source_file_mutation",
                    "logical_change": "healthy_to_fail",
                    "semantic_level": "INITIATING_MUTATION",
                },
                "evidence_state": "supported_under_current_model",
                "support_qualified": True,
            }
        ],
        "actual_diagnostic_hypotheses": [
            {
                "hypothesis_id": "hypothesis:distractor",
                "rank": 1,
                "root_event_id": "change-event:distractor",
                "cause": None,
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
                "evidence_id": f"evidence:{ordinal}",
                "evidence_type": "provider_lineage",
                "source_reference": f"receipt:{ordinal}",
            }
            for ordinal in range(1, 7)
        ],
        "causal_path": [
            _causal_hop(1, "source_commit", "triggers", "actions_run"),
            _causal_hop(2, "actions_run", "produces", "immutable_image"),
            _causal_hop(3, "immutable_image", "used_by", "failing_deployment"),
            _causal_hop(4, "failing_deployment", "owns", "owning_replicaset"),
            _causal_hop(5, "owning_replicaset", "owns", "failing_pod"),
            _causal_hop(6, "failing_pod", "exhibits", "runtime_failure"),
        ],
        "unsupported_critical_hop_count": 0,
        "abstention_result": None,
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
        "pass_criteria_results": [
            {
                "criterion_id": criterion,
                "passed": True,
                "evidence_reference_ids": ["evidence:1"],
            }
            for criterion in (
                "provider_truth_and_cleanup_are_complete",
                "supported_top1_matches_frozen_expected_cause",
                "required_identity_chain_and_causal_hops_are_proven",
                "recovery_condition_is_verified",
            )
        ],
        "post_cleanup_fingerprint": "6" * 64,
        "temporal_audit": None,
        "status": status,
        "construction_blocked_reason": reason,
        "limitations": ["single controlled scenario"],
    }


def _receipt_for_scenario(scenario_id: str) -> dict[str, Any]:
    corpus = _load(CORPUS_PATH)
    truth = _load(GROUND_TRUTH_PATH)
    scenario = next(
        item for item in corpus["scenarios"] if item["scenario_id"] == scenario_id
    )
    expected = next(
        item
        for item in truth["ground_truth_records"]
        if item["scenario_id"] == scenario_id
    )
    receipt = _sample_receipt()
    receipt.update(
        {
            "scenario_id": scenario_id,
            "scenario_family": scenario["scenario_family"],
            "execution_class": scenario["execution_class"],
            "ground_truth_ref": {
                "ground_truth_id": expected["ground_truth_id"],
                "ground_truth_version": "cx0-golden-ground-truth-v1",
                "path": "evaluation/golden/cx0/golden_ground_truth_v1.json",
            },
            "expected_cause": expected["expected_supported_cause"],
            "expected_abstention": expected["expected_abstention"],
            "expected_affected_entities": expected["expected_affected_entities"],
            "expected_required_causal_hops": expected[
                "expected_required_causal_hops"
            ],
            "pass_criteria_results": [
                {
                    "criterion_id": criterion,
                    "passed": True,
                    "evidence_reference_ids": ["evidence:1"],
                }
                for criterion in scenario["pass_criteria"]
            ],
            "causal_path": [
                _causal_hop(
                    ordinal,
                    hop["from"],
                    hop.get("predicate", "related_to"),
                    hop["to"],
                )
                for ordinal, hop in enumerate(
                    scenario["expected_required_causal_hops"], start=1
                )
            ],
            "actual_incident_id": (
                "incident:1"
                if scenario["receipt_requirements"]["actual_incident_required"]
                else None
            ),
            "actual_snapshot_id": (
                "snapshot:1"
                if scenario["receipt_requirements"]["actual_snapshot_required"]
                else None
            ),
            "recovery_result": (
                receipt["recovery_result"]
                if expected["expected_recovery_condition"] is not None
                else None
            ),
        }
    )
    if expected["expected_abstention"]:
        receipt["actual_supported_hypotheses"] = []
        receipt["support_gate_result"] = {
            "policy_version": "causal-support-gate-v1",
            "state": "insufficient_candidate_specific_evidence",
            "supported_hypothesis_ids": [],
        }
        receipt["abstention_result"] = {
            "observed": True,
            "supported_projection_empty": True,
            "reason": "Frozen evidence does not support a causal conclusion.",
            "evidence_reference_ids": ["evidence:1"],
        }
        receipt["causal_path"] = []
    else:
        receipt["actual_supported_hypotheses"][0]["cause"] = expected[
            "expected_supported_cause"
        ]
    if scenario_id == "G-TIME-2":
        receipt["temporal_audit"] = {
            "valid_effective_time": "2026-09-28T00:01:00Z",
            "learned_recorded_time": "2026-09-28T01:01:00Z",
            "arrival_order_rewrites_provider_truth": False,
            "future_state_substitution_used": False,
            "historical_entity_identity_unchanged": True,
            "recomputation_performed": True,
            "prior_analysis_id": "causal-analysis:before",
            "prior_analysis_state": "completed_no_hypothesis",
            "revised_analysis_id": "causal-analysis:after",
            "revised_analysis_state": "completed",
        }
    return receipt


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
        "receipt_requirements",
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
        "unsupported_critical_hop_count",
        "abstention_result",
        "impact",
        "ownership",
        "response_guidance",
        "recovery_result",
        "cleanup_result",
        "pass_criteria_results",
        "post_cleanup_fingerprint",
        "temporal_audit",
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


def test_causal_hop_schema_requires_complete_machine_authority(
    receipt_schema: dict[str, Any],
) -> None:
    required = set(receipt_schema["$defs"]["causal_hop"]["required"])
    assert required == {
        "from",
        "to",
        "predicate",
        "relationship_id",
        "provenance_source",
        "evidence_reference_ids",
        "evidence_semantics",
        "valid_effective_time",
        "learned_recorded_time",
        "evidence_quality",
        "contradiction_or_missing_state",
    }


def test_semantic_validator_accepts_complete_positive_receipt() -> None:
    decision = validate_golden_receipt(_sample_receipt(), repository_root=ROOT)
    assert decision.valid is True
    assert decision.errors == ()


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        ("precondition_fingerprint", None, "precondition_fingerprint_missing"),
        ("infrastructure_fingerprint", None, "infrastructure_fingerprint_missing"),
        ("post_cleanup_fingerprint", None, "post_cleanup_fingerprint_missing"),
    ),
)
def test_pass_rejects_missing_authority(
    field: str, value: Any, error: str
) -> None:
    receipt = _sample_receipt()
    receipt[field] = value
    decision = validate_golden_receipt(receipt, repository_root=ROOT)
    assert decision.valid is False
    assert error in decision.errors


def test_pass_rejects_incomplete_cleanup() -> None:
    receipt = _sample_receipt()
    receipt["cleanup_result"]["completed"] = False
    decision = validate_golden_receipt(receipt, repository_root=ROOT)
    assert decision.valid is False
    assert "cleanup_incomplete" in decision.errors


def test_pass_rejects_changed_protected_control_plane() -> None:
    receipt = _sample_receipt()
    receipt["cleanup_result"]["protected_control_plane_unchanged"] = False
    decision = validate_golden_receipt(receipt, repository_root=ROOT)
    assert decision.valid is False
    assert "protected_control_plane_changed" in decision.errors


def test_positive_pass_rejects_empty_supported_projection() -> None:
    receipt = _sample_receipt()
    receipt["actual_supported_hypotheses"] = []
    decision = validate_golden_receipt(receipt, repository_root=ROOT)
    assert decision.valid is False
    assert "supported_top1_missing" in decision.errors


def test_positive_pass_rejects_wrong_supported_top1() -> None:
    receipt = _sample_receipt()
    receipt["actual_supported_hypotheses"][0]["cause"]["logical_change"] = (
        "unrelated_change"
    )
    decision = validate_golden_receipt(receipt, repository_root=ROOT)
    assert decision.valid is False
    assert "supported_top1_mismatch" in decision.errors


def test_positive_pass_rejects_missing_required_causal_hop() -> None:
    receipt = _sample_receipt()
    receipt["causal_path"] = receipt["causal_path"][:-1]
    decision = validate_golden_receipt(receipt, repository_root=ROOT)
    assert decision.valid is False
    assert any(
        error.startswith("required_causal_hop_missing:")
        for error in decision.errors
    )


def test_positive_pass_rejects_hop_without_provenance_or_evidence() -> None:
    receipt = _sample_receipt()
    receipt["causal_path"][0]["provenance_source"] = ""
    receipt["causal_path"][0]["evidence_reference_ids"] = []
    decision = validate_golden_receipt(receipt, repository_root=ROOT)
    assert decision.valid is False
    assert any(
        error.startswith("causal_hop_authority_incomplete:")
        for error in decision.errors
    )


def test_pass_rejects_receipt_expectation_mismatch() -> None:
    receipt = _sample_receipt()
    receipt["expected_affected_entities"] = ["invented_entity"]
    decision = validate_golden_receipt(receipt, repository_root=ROOT)
    assert decision.valid is False
    assert "expected_affected_entities_mismatch" in decision.errors


def test_expected_abstention_requires_audited_abstention_not_empty_by_accident() -> None:
    receipt = _receipt_for_scenario("G-ADV-2")
    receipt["abstention_result"] = None
    decision = validate_golden_receipt(receipt, repository_root=ROOT)
    assert decision.valid is False
    assert "abstention_result_missing" in decision.errors


def test_time_one_truth_is_independent_of_topo_snapshot(
    truth: dict[str, Any],
) -> None:
    record = next(
        item
        for item in truth["ground_truth_records"]
        if item["scenario_id"] == "G-TIME-1"
    )
    assert "pinned_topology_snapshot" not in record["truth_source_authorities"]
    assert "kubernetes_topology_observation_at_incident_boundary" in record[
        "truth_source_authorities"
    ]
    assert "kubernetes_uid_ownership_at_incident_boundary" in record[
        "truth_source_authorities"
    ]
    assert "provider_observation_timestamp" in record["truth_source_authorities"]


def test_ephemeral_one_freezes_historical_uid_contract(
    truth: dict[str, Any],
) -> None:
    record = next(
        item
        for item in truth["ground_truth_records"]
        if item["scenario_id"] == "G-EPH-1"
    )
    contract = record["historical_identity_contract"]
    assert contract and all(contract.values())
    assert contract["old_pod_uid_preserved_as_historical_truth"] is True
    assert contract["replacement_pod_uid_is_distinct"] is True
    assert contract["old_and_replacement_pods_not_falsely_merged"] is True
    assert contract["old_pod_identity_not_rewritten"] is True


def test_ephemeral_two_freezes_generation_and_image_mapping(
    truth: dict[str, Any],
) -> None:
    record = next(
        item
        for item in truth["ground_truth_records"]
        if item["scenario_id"] == "G-EPH-2"
    )
    contract = record["generation_mapping_contract"]
    assert contract and all(contract.values())
    assert contract["old_and_new_replicasets_remain_distinct"] is True
    assert contract[
        "immutable_image_digest_maps_to_correct_new_replicaset_and_pods"
    ] is True
    assert contract["cross_generation_causal_jump_forbidden"] is True


def test_time_two_freezes_bitemporal_and_revision_audit(
    truth: dict[str, Any],
) -> None:
    record = next(
        item
        for item in truth["ground_truth_records"]
        if item["scenario_id"] == "G-TIME-2"
    )
    contract = record["bitemporal_contract"]
    assert contract and all(contract.values())
    receipt = _receipt_for_scenario("G-TIME-2")
    decision = validate_golden_receipt(receipt, repository_root=ROOT)
    assert decision.valid is True


@pytest.mark.parametrize(
    "invalid_reason",
    (
        "harness_not_implemented",
        "provider_failure",
        "infrastructure_failure",
        "unexpected_product_output",
    ),
)
def test_construction_blocked_rejects_nonrepresentability_unrelated_failures(
    invalid_reason: str,
) -> None:
    receipt = _sample_receipt("CONSTRUCTION_BLOCKED")
    receipt["construction_blocked_reason"] = invalid_reason
    decision = validate_golden_receipt(receipt, repository_root=ROOT)
    assert decision.valid is False
    assert "construction_blocked_reason_not_representability_failure" in (
        decision.errors
    )


def test_gpos_source_and_namespace_scopes_are_separate(corpus: dict[str, Any]) -> None:
    scenario = next(
        item for item in corpus["scenarios"] if item["scenario_id"] == "G-POS-1"
    )
    authorized = set(scenario["authorized_mutation_classes"])
    assert "evaluation_fixture_repository_source_change" in authorized
    assert "provider_build_execution" in authorized
    assert "evaluation_namespace_workload_rollout" in authorized
    assert "evaluation_namespace_source_fixture_change" not in authorized
    assert "dedicated_evaluation_fixture_repository" in scenario["prerequisites"]


def test_durable_accepted_receipt_storage_is_frozen(
    authority: dict[str, Any],
) -> None:
    contract = authority["durable_accepted_receipts"]
    assert contract["tracked_release_evidence_path"] == (
        "docs/architecture/evaluation/receipts/cx0/"
    )
    assert contract["acceptance_requires_artifact_integrity_manifest"] is True
    assert contract["g6_binding_name"] == "GOLDEN_EVALUATION_RECEIPT_V1"
    text = (
        ROOT / "docs/architecture/evaluation/receipts/cx0/README.md"
    ).read_text(encoding="utf-8")
    assert "artifact-integrity-v1.json" in text
    assert "GOLDEN_EVALUATION_RECEIPT_V1" in text
    assert "evaluation/results/" in text
