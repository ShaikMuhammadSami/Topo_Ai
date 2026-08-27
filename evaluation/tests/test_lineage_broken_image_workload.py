from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

import pytest

from evaluation.artifact_integrity import verify_integrity_manifest
from evaluation.lineage_broken_image_workload import (
    CONTAINER_IMAGE_EVIDENCE_ID,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_SEED_DB,
    DEPLOYMENT_ENTITY_ID,
    DEPLOYMENT_IMAGE_RELATIONSHIP_ID,
    DEPLOYMENT_REPLICASET_RELATIONSHIP_ID,
    E1_ID,
    EXPECTED_SEED_SHA256,
    FIRST_DIVERGENCE_ORDER,
    GOLDEN_IMAGE_DIGEST,
    GOLDEN_IMAGE_REFERENCE,
    GOLDEN_INCIDENT_BOUNDARY,
    GOLDEN_SNAPSHOT_ID,
    IMAGE_ENTITY_ID,
    LAST_APPLIED_ANNOTATION,
    POD_ENTITY_ID,
    POD_IMAGE_RELATIONSHIP_ID,
    REPLICASET_POD_RELATIONSHIP_ID,
    RUN_IMAGE_EVIDENCE_ID,
    RUN_IMAGE_RELATIONSHIP_ID,
    RUNTIME_STATUS_DIGEST,
    ExperimentConstructionBlocked,
    _annotation_document,
    _assert_no_sqlite_transients,
    _connect,
    _scan_value,
    alternative_authority_scan,
    apply_b3_mutation,
    fabrication_scan,
    grade_taxonomy,
    inspect_database,
    pre_mutation_image_inventory,
    protected_fingerprints,
    recursive_coreference_scan,
    run_measurement,
    snapshot_identity_audit,
    validate_b3_construction,
    validate_control_precondition,
    verify_contract_schema,
)
from evaluation.lineage_broken_run_image import reset_derived_analysis
from evaluation.lineage_distractor_robustness import (
    copy_seed_database,
    sha256_file,
    validate_seed_database,
)


@pytest.fixture(scope="module")
def seed_inventory() -> dict:
    return inspect_database(DEFAULT_SEED_DB, read_only=True)


@pytest.fixture()
def isolated_copy(tmp_path: Path) -> Path:
    path = tmp_path / "scenario.db"
    copy_seed_database(DEFAULT_SEED_DB, path)
    return path


@pytest.fixture()
def cut_copy(isolated_copy: Path) -> tuple[Path, dict, dict]:
    reset = reset_derived_analysis(isolated_copy)
    mutation = apply_b3_mutation(isolated_copy)
    return isolated_copy, reset, mutation


@pytest.fixture(scope="module")
def measurement(tmp_path_factory: pytest.TempPathFactory) -> dict:
    return run_measurement(output_root=tmp_path_factory.mktemp("lineage-2b3") / "result")


def test_wrong_seed_hash_rejected() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        validate_seed_database(DEFAULT_SEED_DB, expected_sha256="0" * 64)


def test_seed_is_opened_immutable_and_query_only() -> None:
    connection = _connect(DEFAULT_SEED_DB, read_only=True)
    try:
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("DELETE FROM causal_analyses")
    finally:
        connection.close()


def test_copy_only_writes_leave_source_unchanged(isolated_copy: Path) -> None:
    before = sha256_file(DEFAULT_SEED_DB)
    reset_derived_analysis(isolated_copy)
    apply_b3_mutation(isolated_copy)
    assert sha256_file(DEFAULT_SEED_DB) == before == EXPECTED_SEED_SHA256
    assert sha256_file(isolated_copy) != before


def test_seed_checks_are_clean() -> None:
    receipt = validate_seed_database(DEFAULT_SEED_DB, expected_sha256=EXPECTED_SEED_SHA256)
    assert receipt["quick_check"] == "ok"
    assert receipt["integrity_check"] == "ok"
    assert receipt["open_mode"] == "mode=ro&immutable=1; PRAGMA query_only=ON"


def test_snapshot_id_is_not_content_addressed() -> None:
    audit = snapshot_identity_audit()
    assert audit["constructor_observed"] is True
    assert audit["repository_persists_supplied_id"] is True
    assert audit["content_addressed"] is False
    assert audit["construction_blocked"] is False


def test_contract_schema_fails_if_snapshot_identity_is_nonseparable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "evaluation.lineage_broken_image_workload.snapshot_identity_audit",
        lambda: {"construction_blocked": True, "blocker_reason": "snapshot_identity_nonseparable"},
    )
    with pytest.raises(ExperimentConstructionBlocked, match="snapshot_identity_nonseparable"):
        verify_contract_schema(DEFAULT_SEED_DB)


def test_contract_schema_matches_frozen_seed() -> None:
    audit = verify_contract_schema(DEFAULT_SEED_DB)
    assert audit["status"] == "compatible"
    assert all(audit["checks"].values())


def test_control_and_b3_reset_are_identical(tmp_path: Path) -> None:
    paths = [tmp_path / "control.db", tmp_path / "b3.db"]
    for path in paths:
        copy_seed_database(DEFAULT_SEED_DB, path)
    resets = [reset_derived_analysis(path) for path in paths]
    assert resets[0] == resets[1]
    assert resets[0]["fresh_analysis_eligible"] is True
    assert resets[0]["authoritative_evidence_deleted"] is False


def test_reset_removes_old_analysis_and_cache(isolated_copy: Path) -> None:
    audit = reset_derived_analysis(isolated_copy)
    inventory = inspect_database(isolated_copy)
    assert audit["original_causal_analysis_ids"]
    assert inventory["causal_analysis_ids"] == []
    assert inventory["legacy_analysis_ids"] == []
    assert all(value is None for value in inventory["incident_analysis_cache"].values())


@pytest.mark.parametrize(
    "path,expected",
    [
        (("deployment_container", "image"), GOLDEN_IMAGE_REFERENCE),
        (("deployment_container", "image_identity", "requested_image", "digest"), GOLDEN_IMAGE_DIGEST),
        (("annotation", "image"), GOLDEN_IMAGE_REFERENCE),
        (("pod_container", "image"), GOLDEN_IMAGE_REFERENCE),
        (("pod_container", "image_id"), GOLDEN_IMAGE_REFERENCE),
        (("pod_container", "runtime_status_image"), RUNTIME_STATUS_DIGEST),
        (("relationships", "deployment_image", "id"), DEPLOYMENT_IMAGE_RELATIONSHIP_ID),
        (("relationships", "pod_image", "id"), POD_IMAGE_RELATIONSHIP_ID),
        (("evidence", "container_images", "id"), CONTAINER_IMAGE_EVIDENCE_ID),
    ],
)
def test_pre_mutation_inventory_contains_each_proof_surface(
    seed_inventory: dict,
    path: tuple[str, ...],
    expected: str,
) -> None:
    value = seed_inventory
    for key in path:
        value = value[key]
    assert value == expected


def test_pre_mutation_inventory_records_exact_annotation_path(seed_inventory: dict) -> None:
    inventory = pre_mutation_image_inventory(seed_inventory)
    assert inventory["annotation"]["valid_json"] is True
    assert inventory["annotation"]["path"] == "spec.template.spec.containers[name=fixture].image"


def test_annotation_parser_fails_closed_on_invalid_json() -> None:
    entity = {"properties": {"annotations": {LAST_APPLIED_ANNOTATION: "{"}}}
    with pytest.raises(ExperimentConstructionBlocked, match="annotation_authority_nonseparable"):
        _annotation_document(entity)


def test_annotation_cut_removes_only_affected_image(cut_copy: tuple[Path, dict, dict]) -> None:
    _, _, mutation = cut_copy
    before = mutation["annotation"]["unrelated_semantic_sha256_before"]
    after = mutation["annotation"]["unrelated_semantic_sha256_after"]
    assert mutation["annotation"]["operation"] == "member removed"
    assert mutation["annotation"]["replacement_value"] is None
    assert before == after
    assert mutation["annotation"]["preserved"] is True


def test_annotation_nonseparable_copy_fails_closed(isolated_copy: Path) -> None:
    reset_derived_analysis(isolated_copy)
    connection = sqlite3.connect(isolated_copy)
    try:
        row = connection.execute(
            "SELECT payload_json FROM topology_snapshots WHERE snapshot_id = ?",
            (GOLDEN_SNAPSHOT_ID,),
        ).fetchone()
        payload = json.loads(row[0])
        deployment = next(value for value in payload["entities"] if value["id"] == DEPLOYMENT_ENTITY_ID)
        deployment["properties"]["annotations"][LAST_APPLIED_ANNOTATION] = "not-json"
        with connection:
            connection.execute(
                "UPDATE topology_snapshots SET payload_json = ? WHERE snapshot_id = ?",
                (json.dumps(payload), GOLDEN_SNAPSHOT_ID),
            )
    finally:
        connection.close()
    with pytest.raises(ExperimentConstructionBlocked, match="annotation_authority_nonseparable"):
        apply_b3_mutation(isolated_copy)


@pytest.mark.parametrize(
    "entity_key,compatibility_keys,identity_keys",
    [
        ("deployment", ("image", "image_id", "runtime_status_image"), ("requested_image",)),
        ("pod", ("image", "image_id", "runtime_status_image"), ("requested_image", "runtime_image_id", "runtime_status_image")),
    ],
)
def test_b3_cut_uses_truthful_missing_representation(
    cut_copy: tuple[Path, dict, dict],
    entity_key: str,
    compatibility_keys: tuple[str, ...],
    identity_keys: tuple[str, ...],
) -> None:
    path, _, _ = cut_copy
    inventory = inspect_database(path)
    container = inventory[f"{entity_key}_container"]
    assert all(container[key] is None for key in compatibility_keys)
    identity = container["image_identity"]
    for key in identity_keys:
        assert identity[key]["capture_state"] == "missing"
        assert identity[key]["raw_value"] is None
        assert identity[key]["digest"] is None
    assert identity["resolved_artifact_identity"] is None
    assert identity["resolved_artifact_basis"] is None
    assert identity["identity_evidence_refs"] == []


def test_b3_cut_removes_edges_evidence_and_updates_counts(cut_copy: tuple[Path, dict, dict]) -> None:
    path, _, mutation = cut_copy
    inventory = inspect_database(path)
    assert mutation["relationships_removed"] == sorted([DEPLOYMENT_IMAGE_RELATIONSHIP_ID, POD_IMAGE_RELATIONSHIP_ID])
    assert inventory["relationships"]["deployment_image"] is None
    assert inventory["relationships"]["pod_image"] is None
    assert inventory["evidence"]["container_images"] is None
    assert inventory["snapshot_counts"]["record"] == {"entities": 9, "relationships": 10, "evidence": 4}
    assert inventory["snapshot_counts"]["payload"] == {"entities": 9, "relationships": 10, "evidence": 4}
    assert inventory["snapshot_counts"]["container_image_artifacts"] == {"count": 1, "relationships": 0}


@pytest.mark.parametrize(
    "surface",
    ["source_mutation", "e1", "run", "image", "deployment", "replicaset", "pod", "signal", "incident"],
)
def test_protected_entities_and_records_remain(cut_copy: tuple[Path, dict, dict], surface: str) -> None:
    path, _, _ = cut_copy
    inventory = inspect_database(path)
    value = inventory[surface] if surface in inventory else inventory["entities"][surface]
    assert value is not None


@pytest.mark.parametrize(
    "surface,expected_id",
    [
        ("commit_run", "rel:ebaedc357f11b3e70170"),
        ("run_image", RUN_IMAGE_RELATIONSHIP_ID),
        ("deployment_replicaset", DEPLOYMENT_REPLICASET_RELATIONSHIP_ID),
        ("replicaset_pod", REPLICASET_POD_RELATIONSHIP_ID),
    ],
)
def test_protected_relationships_remain(cut_copy: tuple[Path, dict, dict], surface: str, expected_id: str) -> None:
    path, _, _ = cut_copy
    assert inspect_database(path)["relationships"][surface]["id"] == expected_id


def test_provider_run_image_evidence_remains(cut_copy: tuple[Path, dict, dict]) -> None:
    path, _, _ = cut_copy
    assert inspect_database(path)["evidence"]["run_image"]["id"] == RUN_IMAGE_EVIDENCE_ID


@pytest.mark.parametrize(
    "value,expected_type",
    [
        ({"nested": GOLDEN_IMAGE_DIGEST}, "golden_digest"),
        ([GOLDEN_IMAGE_REFERENCE], "golden_image_reference"),
        (json.dumps({"image": GOLDEN_IMAGE_REFERENCE}), "golden_image_reference"),
        ({"target": IMAGE_ENTITY_ID}, "image_entity_id"),
    ],
)
def test_recursive_scan_detects_nested_and_serialized_coreferences(value: object, expected_type: str) -> None:
    assert any(match["match_type"] == expected_type for match in _scan_value(value))


def test_scoped_scan_does_not_reject_protected_build_surfaces(cut_copy: tuple[Path, dict, dict]) -> None:
    path, _, _ = cut_copy
    inventory = inspect_database(path)
    assert GOLDEN_IMAGE_DIGEST in json.dumps(inventory["e1"], sort_keys=True)
    assert GOLDEN_IMAGE_DIGEST in json.dumps(inventory["entities"]["image"], sort_keys=True)
    assert GOLDEN_IMAGE_DIGEST in json.dumps(inventory["relationships"]["run_image"], sort_keys=True)
    assert recursive_coreference_scan(inventory)["count"] == 0


def test_alternative_authority_is_absent_after_cut(cut_copy: tuple[Path, dict, dict]) -> None:
    path, _, _ = cut_copy
    assert alternative_authority_scan(inspect_database(path)) == {"count": 0, "relationship_ids": []}


def test_valid_b3_construction_passes(cut_copy: tuple[Path, dict, dict]) -> None:
    path, _, _ = cut_copy
    construction = validate_b3_construction(inspect_database(path))
    assert construction["valid"] is True
    assert construction["broken_hop_present"] is False
    assert all(construction["required_present"].values())
    assert all(construction["required_absent"].values())


@pytest.mark.parametrize(
    "case",
    [
        "deployment_edge",
        "pod_edge",
        "deployment_requested",
        "pod_runtime_id",
        "annotation",
        "evidence",
        "stale_analysis",
        "missing_e1",
        "missing_run_image",
        "missing_owner_chain",
        "missing_failure",
    ],
)
def test_construction_fails_when_required_boundary_or_protected_truth_is_wrong(
    cut_copy: tuple[Path, dict, dict], seed_inventory: dict, case: str
) -> None:
    path, _, _ = cut_copy
    inventory = copy.deepcopy(inspect_database(path))
    if case == "deployment_edge":
        inventory["relationships"]["deployment_image"] = seed_inventory["relationships"]["deployment_image"]
    elif case == "pod_edge":
        inventory["relationships"]["pod_image"] = seed_inventory["relationships"]["pod_image"]
    elif case == "deployment_requested":
        inventory["deployment_container"]["image"] = GOLDEN_IMAGE_REFERENCE
        inventory["entities"]["deployment"]["properties"]["containers"][0]["image"] = GOLDEN_IMAGE_REFERENCE
    elif case == "pod_runtime_id":
        inventory["pod_container"]["image_id"] = GOLDEN_IMAGE_REFERENCE
        inventory["entities"]["pod"]["properties"]["containers"][0]["image_id"] = GOLDEN_IMAGE_REFERENCE
    elif case == "annotation":
        inventory["annotation"]["image"] = GOLDEN_IMAGE_REFERENCE
        inventory["entities"]["deployment"] = seed_inventory["entities"]["deployment"]
    elif case == "evidence":
        inventory["evidence"]["container_images"] = seed_inventory["evidence"]["container_images"]
    elif case == "stale_analysis":
        inventory["causal_analysis_ids"] = ["stale"]
    elif case == "missing_e1":
        inventory["e1"] = None
    elif case == "missing_run_image":
        inventory["relationships"]["run_image"] = None
    elif case == "missing_owner_chain":
        inventory["relationships"]["replicaset_pod"] = None
    elif case == "missing_failure":
        inventory["signal"] = None
    assert validate_b3_construction(inventory)["valid"] is False


def test_intentional_fields_are_excluded_from_protected_fingerprints(cut_copy: tuple[Path, dict, dict]) -> None:
    _, _, mutation = cut_copy
    fingerprints = mutation["protected_fingerprints"]
    assert fingerprints["before"] == fingerprints["after"]
    assert fingerprints["changed"] == []
    assert fingerprints["preserved"] is True


@pytest.mark.parametrize(
    "fingerprint",
    [
        "source_mutation",
        "commit_run",
        "e1",
        "run_image",
        "run_image_provider_evidence",
        "container_image",
        "deployment_non_image",
        "replicaset",
        "pod_non_image",
        "owner_chain",
        "runtime_failure",
        "incident_pin",
        "annotation_unrelated_semantics",
    ],
)
def test_each_protected_fingerprint_is_unchanged(cut_copy: tuple[Path, dict, dict], fingerprint: str) -> None:
    _, _, mutation = cut_copy
    assert mutation["protected_fingerprints"]["before"][fingerprint] == mutation["protected_fingerprints"]["after"][fingerprint]


def test_control_precondition_is_intact(seed_inventory: dict) -> None:
    assert validate_control_precondition(seed_inventory)["valid"] is True


def test_control_fresh_golden_reproduction(measurement: dict) -> None:
    grade = measurement["control"]["grade"]
    diagnostics = measurement["control"]["diagnostics"]
    assert grade["golden_reproduction"] is True
    assert grade["old_analysis_reused"] is False
    assert diagnostics["exact_path_b_admitted"] is True
    assert diagnostics["source_supported"] is True
    assert diagnostics["most_specific_supported_semantic_level"] == "INITIATING_MUTATION"


def test_b3_product_abstains_without_image_workload_proof(measurement: dict) -> None:
    diagnostics = measurement["b3_repeats"][0]["diagnostics"]
    assert diagnostics["golden_raw_candidate_discovered"] is False
    assert diagnostics["ordinary_path_a_admitted"] is False
    assert diagnostics["exact_path_b_admitted"] is False
    assert diagnostics["sc2"]["status"] == "incomplete"
    assert diagnostics["sc2"]["reason"] == "immutable_image_missing"
    assert diagnostics["source_supported"] is False
    assert diagnostics["supported_projection"] == []
    assert diagnostics["supported_top1"] is None
    assert diagnostics["most_specific_supported_semantic_level"] == "NONE"


def test_b3_does_not_fabricate_image_workload_provenance(measurement: dict) -> None:
    first = measurement["b3_repeats"][0]
    assert first["fabrication"] == {"count": 0, "surfaces": []}
    assert first["unsafe_specificity"] == {"count": 0, "surfaces": []}


def test_missing_evidence_is_not_treated_as_contradiction(measurement: dict) -> None:
    audit = measurement["b3_repeats"][0]["evidence_semantics"]
    assert audit["degraded"] is False
    assert audit["missing_is_not_contradiction"] is True


@pytest.mark.parametrize(
    "expected,kwargs",
    [
        ("BROKEN_HOP_STILL_PRESENT", {"broken": True}),
        ("FABRICATED_IMAGE_WORKLOAD_PROVENANCE", {"fabricated": True}),
        ("SOURCE_CAUSE_FALSELY_SUPPORTED", {"supported": True}),
        ("UNSAFE_SOURCE_SPECIFICITY_PRESERVED", {"unsafe": True}),
        ("VALID_PRESERVED_EVIDENCE_CORRUPTED", {"corrupted": True}),
        ("EVIDENCE_SEMANTICS_DEGRADED", {"degraded": True}),
        ("NONDETERMINISTIC_RESULT", {"deterministic": False}),
        ("NO_DIVERGENCE", {}),
    ],
)
def test_frozen_taxonomy_priority(expected: str, kwargs: dict) -> None:
    assert FIRST_DIVERGENCE_ORDER.index(expected) >= 0
    result = grade_taxonomy(
        construction={"broken_hop_present": kwargs.get("broken", False)},
        fabrication={"count": int(kwargs.get("fabricated", False))},
        source_supported=kwargs.get("supported", False),
        unsafe={"count": int(kwargs.get("unsafe", False))},
        protected_corrupted=kwargs.get("corrupted", False),
        evidence_degraded=kwargs.get("degraded", False),
        deterministic=kwargs.get("deterministic", True),
    )
    assert result == expected


def test_three_repetitions_are_semantically_deterministic(measurement: dict) -> None:
    determinism = measurement["aggregate"]["determinism"]
    assert determinism["identical"] is True
    assert len(determinism["hashes"]) == 3
    assert len(set(determinism["hashes"])) == 1


def test_only_declared_volatile_fields_are_normalized(measurement: dict) -> None:
    assert measurement["manifest"]["volatile_fields_normalized"] == ["generated_at", "temporary_copy_path"]
    assert all(value["diagnostics"]["analysis_id"] for value in measurement["b3_repeats"])


def test_measurement_verdict_is_robust_no_divergence(measurement: dict) -> None:
    assert measurement["aggregate"]["taxonomy_result"] == "NO_DIVERGENCE"
    assert measurement["aggregate"]["overall_verdict"] == "ROBUST_IN_MEASURED_MATRIX"
    assert measurement["aggregate"]["source_specificity_reduced_safely"] is True


def test_eai_manifest_is_generated_last_and_verifies(measurement: dict) -> None:
    eai = measurement["eai"]
    assert eai["generated_after_ordinary_artifacts"] is True
    assert eai["verification"]["status"] == "verified"
    verified = verify_integrity_manifest(Path(measurement["output_root"]))
    assert verified.tree_sha256 == eai["tree_sha256"]


def test_result_has_no_sqlite_transients(measurement: dict) -> None:
    assert measurement["sqlite_transient_files"] == []
    assert _assert_no_sqlite_transients(Path(measurement["output_root"])) == []


def test_result_artifacts_are_under_ignored_result_root(measurement: dict) -> None:
    output = Path(measurement["output_root"])
    assert (output / "aggregate.json").is_file()
    assert (output / "artifact-hashes.json").is_file()
    assert (output / "artifact-integrity-v1.json").is_file()
    assert DEFAULT_OUTPUT_ROOT.as_posix().endswith("evaluation/results/lineage/adversarial/lineage-2b-missing-image-workload")


def test_source_seed_is_unchanged_after_measurement(measurement: dict) -> None:
    assert measurement["aggregate"]["seed_post_run"]["sha256"] == EXPECTED_SEED_SHA256
    assert sha256_file(DEFAULT_SEED_DB) == EXPECTED_SEED_SHA256


def test_measurement_is_offline_and_product_unchanged(measurement: dict) -> None:
    manifest = measurement["manifest"]
    assert manifest["offline"] is True
    assert manifest["product_code_modified"] is False
    assert manifest["product_hints"] is False


def test_fabrication_scan_detects_a_product_claim_path() -> None:
    analysis = {
        "candidate_relevance_audit": [{
            "candidate_event_id": "change-event:20a8946c8c445153d85c90ee2166d487",
            "topology_path": [IMAGE_ENTITY_ID, POD_ENTITY_ID],
        }],
        "hypotheses": [],
    }
    result = fabrication_scan(analysis)
    assert result["count"] == 1
    assert result["surfaces"] == ["candidate_relevance_audit[0].topology_path"]


def test_historical_accepted_paths_are_not_result_targets() -> None:
    forbidden = {
        "lineage-2b-missing-run-image",
        "lineage-2a-final-clean-distractor-robustness-baseline.md",
        "lineage-1-final-proven-source-to-runtime-causal-baseline.md",
    }
    assert DEFAULT_OUTPUT_ROOT.name == "lineage-2b-missing-image-workload"
    assert DEFAULT_OUTPUT_ROOT.name not in forbidden
