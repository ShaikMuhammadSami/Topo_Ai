from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

import pytest

import evaluation.lineage_broken_run_image as b2
from evaluation.artifact_integrity import verify_integrity_manifest
from evaluation.lineage_distractor_robustness import (
    copy_seed_database,
    sha256_file,
    validate_seed_database,
)


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "evaluation/lineage_broken_run_image.py"
TEST_MODULE = ROOT / "evaluation/tests/test_lineage_broken_run_image.py"
FROZEN_CONTRACT = (
    ROOT
    / "docs/architecture/evaluation"
    / "lineage-2b2-missing-run-image-contract-v1.md"
)
BASELINE_ROOT = ROOT / "docs/architecture/evaluation/baselines"


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _fresh_copy(tmp_path: Path, name: str = "scenario.db") -> Path:
    destination = tmp_path / name
    copy_seed_database(b2.DEFAULT_SEED_DB, destination)
    b2.reset_derived_analysis(destination)
    return destination


@pytest.fixture(scope="module")
def frozen_schema() -> dict:
    return b2.verify_contract_schema(b2.DEFAULT_SEED_DB)


@pytest.fixture(scope="module")
def measured_result(tmp_path_factory: pytest.TempPathFactory) -> dict:
    seed_before = sha256_file(b2.DEFAULT_SEED_DB)
    baselines_before = _tree_hashes(BASELINE_ROOT)
    contract_before = sha256_file(FROZEN_CONTRACT)
    result_root = tmp_path_factory.mktemp("lineage-2b2") / "result"
    result = b2.run_measurement(output_root=result_root)
    result["test_safety"] = {
        "seed_before": seed_before,
        "seed_after": sha256_file(b2.DEFAULT_SEED_DB),
        "baselines_before": baselines_before,
        "baselines_after": _tree_hashes(BASELINE_ROOT),
        "contract_before": contract_before,
        "contract_after": sha256_file(FROZEN_CONTRACT),
    }
    return result


def test_harness_and_contract_are_present() -> None:
    assert HARNESS.is_file()
    assert TEST_MODULE.is_file()
    assert FROZEN_CONTRACT.is_file()


def test_wrong_seed_hash_is_rejected() -> None:
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        validate_seed_database(b2.DEFAULT_SEED_DB, expected_sha256="0" * 64)


def test_seed_is_opened_immutable_and_read_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_connect = sqlite3.connect
    calls: list[tuple[str, bool]] = []

    def guarded_connect(database, *args, **kwargs):
        calls.append((str(database), bool(kwargs.get("uri"))))
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", guarded_connect)
    receipt = validate_seed_database(
        b2.DEFAULT_SEED_DB,
        expected_sha256=b2.EXPECTED_SEED_SHA256,
    )
    assert receipt["open_mode"] == "mode=ro&immutable=1; PRAGMA query_only=ON"
    assert calls == [(calls[0][0], True)]
    assert "mode=ro&immutable=1" in calls[0][0]


def test_scenario_copy_is_byte_identical_and_seed_safe(tmp_path: Path) -> None:
    seed_before = sha256_file(b2.DEFAULT_SEED_DB)
    destination = tmp_path / "copy.db"
    receipt = copy_seed_database(b2.DEFAULT_SEED_DB, destination)
    assert receipt["seed_sha256_before_copy"] == b2.EXPECTED_SEED_SHA256
    assert receipt["scenario_copy_sha256"] == b2.EXPECTED_SEED_SHA256
    connection = sqlite3.connect(destination)
    try:
        connection.execute("DELETE FROM causal_analyses")
        connection.commit()
    finally:
        connection.close()
    assert sha256_file(b2.DEFAULT_SEED_DB) == seed_before
    assert sha256_file(destination) != seed_before


def test_authority_classification_matches_frozen_contract(frozen_schema: dict) -> None:
    classification = b2.authority_classification(frozen_schema["inventory"])
    preserved = classification["authoritative_preserved"]
    assert classification["authoritative_removed_for_b2"] == {
        "build_artifact_evidence": b2.E1_ID
    }
    assert preserved["commit_run_relationship"] == b2.COMMIT_RUN_RELATIONSHIP_ID
    assert preserved["commit_run_evidence"] == b2.COMMIT_RUN_EVIDENCE_ID
    assert preserved["deployment_image_relationship"] == b2.DEPLOYMENT_IMAGE_RELATIONSHIP_ID
    assert preserved["pod_image_relationship"] == b2.POD_IMAGE_RELATIONSHIP_ID
    assert preserved["runtime_failure_signal"] == b2.GOLDEN_SIGNAL_ID
    assert classification["synthetic_authority"] is False


def test_reset_is_symmetric_and_only_removes_derived_state(tmp_path: Path) -> None:
    audits = []
    authority_before = []
    authority_after = []
    for index in range(2):
        path = tmp_path / f"copy-{index}.db"
        copy_seed_database(b2.DEFAULT_SEED_DB, path)
        before = b2.inspect_database(path, read_only=False)
        authority_before.append(b2.protected_evidence_fingerprints(before))
        audits.append(b2.reset_derived_analysis(path))
        after = b2.inspect_database(path, read_only=False)
        authority_after.append(b2.protected_evidence_fingerprints(after))
    assert audits[0] == audits[1]
    assert authority_before == authority_after
    assert all(audit["fresh_analysis_eligible"] for audit in audits)
    assert all(audit["authoritative_evidence_deleted"] is False for audit in audits)
    assert all(audit["original_causal_analysis_ids"] == [b2.OLD_ANALYSIS_ID] for audit in audits)


def test_b2_mutation_removes_only_the_broken_hop(tmp_path: Path) -> None:
    database = _fresh_copy(tmp_path)
    mutation = b2.apply_b2_mutation(database)
    inventory = b2.inspect_database(database, read_only=False)
    assert mutation["authoritative_cut"] == {
        "deleted_build_artifact_evidence": [b2.E1_ID]
    }
    assert inventory["e1_count"] == 0
    assert inventory["run_image_relationship_ids"] == []
    assert inventory["run_image_evidence_ids"] == []
    assert inventory["exact_provider_associations"] == []
    assert inventory["build_lineage_metadata"] == {
        "evidence_records_considered": 0,
        "relationship_count": 0,
        "unresolved_evidence_count": 0,
    }
    assert all(inventory["present"].values())
    assert mutation["protected_fingerprints"]["unchanged"] is True
    assert mutation["protected_fingerprints"]["changed"] == []
    assert b2.validate_b2_construction(inventory)["valid"] is True


@pytest.mark.parametrize(
    ("surface", "mutator"),
    (
        (
            "E1",
            lambda value: (
                value.update(e1_count=1),
                value["absent"].update(e1=False),
            ),
        ),
        (
            "Run -> Image relationship",
            lambda value: (
                value.update(run_image_relationship_ids=[b2.RUN_IMAGE_RELATIONSHIP_ID]),
                value["absent"].update(run_image_relationship=False),
            ),
        ),
        (
            "alternative provider authority",
            lambda value: (
                value.update(exact_provider_associations=[{"evidence_id": "alternative"}]),
                value["absent"].update(exact_provider_association=False),
            ),
        ),
    ),
)
def test_construction_fails_if_run_image_authority_survives(
    tmp_path: Path, surface: str, mutator
) -> None:
    database = _fresh_copy(tmp_path)
    b2.apply_b2_mutation(database)
    inventory = copy.deepcopy(b2.inspect_database(database, read_only=False))
    mutator(inventory)
    result = b2.validate_b2_construction(inventory)
    assert result["valid"] is False, surface
    assert result["broken_hop_present"] is True


@pytest.mark.parametrize(
    "required",
    (
        "commit_run_relationship",
        "deployment_image",
        "pod_image",
        "runtime_failure",
        "source_mutation",
        "container_image",
        "deployment_replicaset_owner",
        "replicaset_pod_owner",
    ),
)
def test_construction_fails_when_protected_truth_disappears(
    tmp_path: Path, required: str
) -> None:
    database = _fresh_copy(tmp_path)
    b2.apply_b2_mutation(database)
    inventory = copy.deepcopy(b2.inspect_database(database, read_only=False))
    inventory["present"][required] = False
    result = b2.validate_b2_construction(inventory)
    assert result["valid"] is False
    assert result["protected_present"] is False


def test_mutation_fails_closed_if_protected_fingerprint_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _fresh_copy(tmp_path)
    original = b2.protected_evidence_fingerprints
    calls = 0

    def changed_after(inventory):
        nonlocal calls
        calls += 1
        values = original(inventory)
        if calls == 2:
            values["runtime_failure"] = "corrupted"
        return values

    monkeypatch.setattr(b2, "protected_evidence_fingerprints", changed_after)
    with pytest.raises(
        b2.ExperimentConstructionBlocked,
        match="counterfactual_would_corrupt_preserved_truth",
    ):
        b2.apply_b2_mutation(database)


def test_fabrication_scan_detects_surviving_product_surfaces(tmp_path: Path) -> None:
    database = _fresh_copy(tmp_path)
    result = b2.fabrication_scan(database, {"hypotheses": []})
    assert result["count"] >= 3
    assert "build_artifact_evidence.exact_run_image" in result["surfaces"]


def test_unsafe_source_specificity_scan_covers_multiple_surfaces() -> None:
    hypothesis_id = "source-hypothesis"
    analysis = {
        "supported_hypothesis_ids": [hypothesis_id],
        "hypotheses": [
            {
                "hypothesis_id": hypothesis_id,
                "root_event_id": b2.GOLDEN_EVENT_ID,
                "confidence_semantics": {
                    "evidence_state": "supported_under_current_model"
                },
                "support_gate": {"support_state": "supported_under_current_model"},
            }
        ],
    }
    result = b2.unsafe_specificity_scan(analysis)
    assert result["count"] == 3


def test_diagnostic_source_suspicion_and_empty_support_are_allowed() -> None:
    taxonomy = b2.grade_taxonomy(
        construction={"broken_hop_present": False},
        fabrication={"count": 0},
        source_supported=False,
        unsafe={"count": 0},
        protected_corrupted=False,
        evidence_degraded=False,
        deterministic=True,
    )
    assert taxonomy == "NO_DIVERGENCE"


def test_missing_evidence_is_not_contradiction() -> None:
    audit = b2.evidence_semantics_audit(
        {
            "hypotheses": [
                {
                    "evidence_ledger": {
                        "supporting": [],
                        "contradicting": [],
                        "missing": [
                            {
                                "claim_type": "provider_build_provenance",
                                "expectation_basis": "exact lineage candidate",
                                "quality": "unknown",
                            }
                        ],
                    }
                }
            ]
        }
    )
    assert audit["degraded"] is False
    assert audit["missing_is_not_contradiction"] is True


@pytest.mark.parametrize(
    "expected",
    b2.FIRST_DIVERGENCE_ORDER,
)
def test_taxonomy_priority_is_frozen(expected: str) -> None:
    position = b2.FIRST_DIVERGENCE_ORDER.index(expected)
    active = set(b2.FIRST_DIVERGENCE_ORDER[position:-1])
    result = b2.grade_taxonomy(
        construction={"broken_hop_present": "BROKEN_HOP_STILL_PRESENT" in active},
        fabrication={"count": int("FABRICATED_RUN_IMAGE_PROVENANCE" in active)},
        source_supported="SOURCE_CAUSE_FALSELY_SUPPORTED" in active,
        unsafe={"count": int("UNSAFE_SOURCE_SPECIFICITY_PRESERVED" in active)},
        protected_corrupted="VALID_PRESERVED_EVIDENCE_CORRUPTED" in active,
        evidence_degraded="EVIDENCE_SEMANTICS_DEGRADED" in active,
        deterministic="NONDETERMINISTIC_RESULT" not in active,
    )
    assert result == expected


def test_normalization_excludes_only_declared_volatile_fields() -> None:
    common = {
        "construction": {"valid": True},
        "fabrication": {"count": 0},
        "unsafe": {"count": 0},
        "evidence_semantics": {"degraded": False},
        "protected_fingerprints": {"unchanged": True},
    }
    first = b2.normalized_semantic_output(
        diagnostics={
            "analysis_id": "deterministic-a",
            "generated_at": "2026-08-27T00:00:00Z",
            "final_score": 0.4,
        },
        **common,
    )
    second = b2.normalized_semantic_output(
        diagnostics={
            "analysis_id": "deterministic-a",
            "generated_at": "2026-08-27T00:01:00Z",
            "final_score": 0.4,
        },
        **common,
    )
    changed_identity = b2.normalized_semantic_output(
        diagnostics={
            "analysis_id": "deterministic-b",
            "generated_at": "2026-08-27T00:01:00Z",
            "final_score": 0.4,
        },
        **common,
    )
    changed_score = b2.normalized_semantic_output(
        diagnostics={
            "analysis_id": "deterministic-a",
            "generated_at": "2026-08-27T00:01:00Z",
            "final_score": 0.5,
        },
        **common,
    )
    assert b2.VOLATILE_ANALYSIS_FIELDS == ("generated_at",)
    assert b2._semantic_sha256(first) == b2._semantic_sha256(second)
    assert b2._semantic_sha256(first) != b2._semantic_sha256(changed_identity)
    assert b2._semantic_sha256(first) != b2._semantic_sha256(changed_score)


def test_full_control_recomputes_and_reproduces_golden_source(measured_result: dict) -> None:
    control = measured_result["control"]
    diagnostics = control["diagnostics"]
    assert control["grade"]["golden_reproduction"] is True
    assert control["grade"]["fresh_execution"]["record_existed_before_call"] is False
    assert control["grade"]["fresh_execution"]["persisted_record_count"] == 1
    assert diagnostics["exact_path_b_admitted"] is True
    assert diagnostics["source_supported"] is True
    assert diagnostics["most_specific_supported_semantic_level"] == "INITIATING_MUTATION"


def test_full_b2_is_valid_safe_and_deterministic(measured_result: dict) -> None:
    aggregate = measured_result["aggregate"]
    assert aggregate["construction_valid_repetitions"] == 3
    assert aggregate["reset_symmetry"] is True
    assert aggregate["determinism"]["identical"] is True
    assert len(set(aggregate["determinism"]["hashes"])) == 1
    assert aggregate["taxonomy_result"] == "NO_DIVERGENCE"
    assert aggregate["overall_verdict"] == "ROBUST_IN_MEASURED_MATRIX"
    assert aggregate["source_specificity_reduced_safely"] is True
    assert aggregate["fabricated_run_image_count"] == 0
    assert aggregate["unsafe_source_specificity_count"] == 0


def test_full_b2_preserves_truth_and_abstains_from_source_support(
    measured_result: dict,
) -> None:
    assert measured_result["aggregate"]["preserved_truth"] == {
        "commit_run": True,
        "image_workload": True,
        "runtime_failure": True,
    }
    for repeat in measured_result["b2_repeats"]:
        diagnostics = repeat["diagnostics"]
        assert repeat["execution"]["record_existed_before_call"] is False
        assert repeat["execution"]["persisted_record_count"] == 1
        assert diagnostics["source_supported"] is False
        assert diagnostics["exact_path_b_admitted"] is False
        assert diagnostics["supported_projection"] == []
        assert diagnostics["most_specific_supported_semantic_level"] == "NONE"
        assert repeat["fabrication"]["count"] == 0
        assert repeat["unsafe_specificity"]["count"] == 0
        assert repeat["protected_corrupted"] is False
        assert repeat["evidence_semantics"]["degraded"] is False


def test_seed_contract_and_historical_baselines_remain_unchanged(
    measured_result: dict,
) -> None:
    safety = measured_result["test_safety"]
    assert safety["seed_before"] == safety["seed_after"] == b2.EXPECTED_SEED_SHA256
    assert safety["baselines_before"] == safety["baselines_after"]
    assert safety["contract_before"] == safety["contract_after"]


def test_eai_is_generated_last_and_verifies(measured_result: dict) -> None:
    root = Path(measured_result["output_root"])
    eai = measured_result["eai"]
    verification = verify_integrity_manifest(root)
    manifest_path = root / "artifact-integrity-v1.json"
    ordinary_files = [path for path in root.rglob("*") if path.is_file() and path != manifest_path]
    assert eai["contract"] == "evaluation-artifact-integrity-v1"
    assert eai["verification"]["status"] == "verified"
    assert verification.tree_sha256 == eai["tree_sha256"]
    assert verification.included_file_count == eai["included_file_count"]
    assert all(path.stat().st_mtime_ns <= manifest_path.stat().st_mtime_ns for path in ordinary_files)
    assert measured_result["sqlite_transient_files"] == []


def test_measurement_result_root_fails_closed(measured_result: dict) -> None:
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        b2.run_measurement(output_root=Path(measured_result["output_root"]))
