from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from evaluation.h3_observation import (
    H3FirstDivergence,
    H3Status,
    build_h3_result,
    evaluate_h3,
    load_provider_receipt,
    observe_topo_snapshot,
    provider_expected_from_receipt,
    serialize_h3_result,
    validate_provider_receipt,
)
from evaluation.lineage_provider_truth import contains_unredacted_secret_like_fields
from evaluation.product_diff_guard import assert_h3_r1_historical_product_scope


ROOT = Path(__file__).resolve().parents[2]
RECEIPT = (
    ROOT
    / "evaluation/results/provider-receipts/32688747741-1"
    / "topo-lineage-provider-receipt.json"
)
SCHEMA = ROOT / "docs/architecture/evaluation/h3-observation-result.schema.json"
WORKFLOW = ROOT / ".github/workflows/topo-lineage-provider-fixture.yml"
RUNNER = ROOT / "evaluation/h3_runner.py"
EVALUATOR = ROOT / "evaluation/h3_observation.py"

RECEIPT_SHA256 = "7903be83d443a81f382fe08bc8458bc8b1ac6fc3e8858c50b4d2cb07edd3cec3"
WORKFLOW_SHA256 = "145a10245d575e02a756be018aaa25c2eabd1d39cde82b43aebd0d605d951903"
PERMANENT_MANIFEST_HASHES = {
    "blast-01.json": "2f292f5ee1c116d2c2c832bc2165a61bc13dedc5",
    "blast-02.json": "695d0feda176f26c7e601a57060f4ad0d29310a9",
    "blast-03.json": "0f9974a4a5f4a08d6b01d2e02be319698175f6c1",
    "sentinel-a.json": "599ba19827d5097fded3f52264cad8dd35abb839",
    "sentinel-b.json": "f404607eaca904baac362edb2365fa53652565fe",
    "sentinel-c.json": "9bb3c201b190708224770a30ec9c23939623f683",
    "sentinel-d.json": "e7e2a8f4e2cde066bee209191ec27304a41193f7",
}


def receipt() -> dict[str, Any]:
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def expected() -> dict[str, Any]:
    return provider_expected_from_receipt(
        receipt(),
        github_verification={
            "run_timestamps": {
                "created_at": "2026-08-24T04:05:58Z",
                "run_started_at": "2026-08-24T04:05:58Z",
                "updated_at": "2026-08-24T04:06:38Z",
            }
        },
    )


def complete_observation() -> dict[str, Any]:
    item = expected()
    return {
        "snapshot_id": "snapshot:h3:test",
        "snapshot_collected_at": "2026-08-24T04:07:00Z",
        "context": {
            "repository_entity_present": True,
            "commit_entity_present": True,
            "workflow_name_match": True,
            "commit_run_trigger_present": True,
        },
        "topo_run_entity": {
            "present": True,
            "canonical_entity_id": item["run_canonical_entity_id"],
            "entity_kind": "GitHubWorkflowRun",
            "provider_native_id": item["run_id"],
            "aliases": [],
            "source_system": "github-actions",
            "properties": {
                "run_id": item["run_id"],
                "run_attempt": item["run_attempt"],
                "run_number": item["run_number"],
                "head_sha": item["commit_sha"],
                "workflow_name": item["workflow_name"],
            },
            "repository_scope_match": True,
            "repository_scope_source_references": [],
            "observed_at": "2026-08-24T04:06:38Z",
            "temporal": None,
        },
        "topo_image_entity": {
            "present": True,
            "canonical_entity_id": item["image_canonical_entity_id"],
            "entity_kind": "ContainerImage",
            "provider_native_id": item["image_digest"],
            "aliases": [],
            "source_system": "kubernetes",
            "immutable_digest": item["image_digest"],
            "properties": {
                "repository": item["image_repository"],
                "tag": None,
                "digest": item["image_digest"],
                "immutable": True,
            },
            "observed_at": "2026-08-24T04:07:00Z",
            "temporal": None,
        },
        "topo_relationship": {
            "present": True,
            "relationship_id": "relationship:h3:test",
            "predicate": "produces",
            "stored_source_entity_id": item["run_canonical_entity_id"],
            "stored_target_entity_id": item["image_canonical_entity_id"],
            "directed": True,
            "origin": "inferred",
            "source_system": "github-actions",
            "source_component": "backend.app.services.github_actions_graph",
            "source_references": [
                {
                    "reference_type": "github_workflow_run_id",
                    "reference": item["run_id"],
                    "source_system": "github-actions",
                },
                {
                    "reference_type": "container_image_digest",
                    "reference": item["image_digest"],
                    "source_system": "kubernetes",
                },
            ],
            "linker_version": "github-actions-artifact-linker:v1",
            "completeness": "complete",
            "confidence": 0.99,
            "confidence_semantics": "heuristic_score",
            "observed_at": "2026-08-24T04:07:00Z",
            "temporal": {
                "temporal_version": "tc3.v1",
                "effective_at": "2026-08-24T04:06:38Z",
                "observed_at": "2026-08-24T04:07:00Z",
                "time_origin": "topo_observed",
                "time_quality": "exact",
                "status": "complete",
            },
        },
    }


def evaluate(observation: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return evaluate_h3(expected(), observation, **kwargs)


def assert_divergence(
    observation: dict[str, Any], status: H3Status, divergence: H3FirstDivergence
) -> None:
    result = evaluate(observation)
    assert result["status"] == status.value
    assert result["first_divergence"] == divergence.value


def test_real_provider_receipt_validates():
    assert load_provider_receipt(RECEIPT)["run_id"] == 32688747741


def test_real_provider_receipt_hash_is_frozen():
    assert hashlib.sha256(RECEIPT.read_bytes()).hexdigest() == RECEIPT_SHA256


def test_expected_run_identity_includes_repository_run_and_attempt():
    item = expected()
    assert item["repository"] == "ShaikMuhammadSami/Topo_Ai"
    assert item["run_id"] == "32688747741"
    assert item["run_attempt"] == 1


def test_same_commit_but_different_run_id_does_not_match():
    observation = complete_observation()
    observation["topo_run_entity"]["canonical_entity_id"] = (
        "github:api.github.com:workflow-run:32688747742"
    )
    observation["topo_run_entity"]["provider_native_id"] = "32688747742"
    observation["topo_run_entity"]["properties"]["run_id"] = "32688747742"
    assert_divergence(
        observation, H3Status.WRONG, H3FirstDivergence.ACTIONS_RUN_IDENTITY_WRONG
    )


def test_same_run_id_but_different_attempt_does_not_match():
    observation = complete_observation()
    observation["topo_run_entity"]["properties"]["run_attempt"] = 2
    assert_divergence(
        observation, H3Status.WRONG, H3FirstDivergence.ACTIONS_RUN_IDENTITY_WRONG
    )


def test_repository_scope_is_required_for_run_identity():
    observation = complete_observation()
    observation["topo_run_entity"]["repository_scope_match"] = False
    assert_divergence(
        observation, H3Status.WRONG, H3FirstDivergence.ACTIONS_RUN_IDENTITY_WRONG
    )


def test_image_digest_is_authoritative_identity():
    item = expected()
    assert item["image_canonical_entity_id"].endswith(item["image_digest"])
    assert item["image_tag"] not in item["image_canonical_entity_id"]


def test_mutable_tag_alone_is_not_proven():
    observation = complete_observation()
    image = observation["topo_image_entity"]
    image["canonical_entity_id"] = f"artifact:container-image:{expected()['image_tag']}"
    image["provider_native_id"] = expected()["image_tag"]
    image["immutable_digest"] = None
    image["properties"] = {"tag": expected()["image_tag"], "immutable": False}
    assert_divergence(
        observation, H3Status.WRONG, H3FirstDivergence.IMAGE_DIGEST_IDENTITY_WRONG
    )


def test_exact_digest_identity_succeeds():
    result = evaluate(complete_observation())
    assert result["image_identity_match"] is True


def test_wrong_digest_is_wrong():
    observation = complete_observation()
    wrong = "sha256:" + "0" * 64
    image = observation["topo_image_entity"]
    image["canonical_entity_id"] = f"artifact:container-image:{wrong}"
    image["provider_native_id"] = wrong
    image["immutable_digest"] = wrong
    image["properties"]["digest"] = wrong
    assert_divergence(
        observation, H3Status.WRONG, H3FirstDivergence.IMAGE_DIGEST_IDENTITY_WRONG
    )


def test_missing_run_entity_is_first_divergence():
    observation = complete_observation()
    observation["topo_run_entity"]["present"] = False
    assert_divergence(
        observation, H3Status.MISSING, H3FirstDivergence.ACTIONS_RUN_ENTITY_MISSING
    )


def test_wrong_run_identity_is_first_divergence():
    observation = complete_observation()
    observation["topo_run_entity"]["entity_kind"] = "GitCommit"
    assert_divergence(
        observation, H3Status.WRONG, H3FirstDivergence.ACTIONS_RUN_IDENTITY_WRONG
    )


def test_missing_image_entity_is_first_divergence():
    observation = complete_observation()
    observation["topo_image_entity"]["present"] = False
    assert_divergence(
        observation, H3Status.MISSING, H3FirstDivergence.IMAGE_ENTITY_MISSING
    )


def test_wrong_image_identity_is_first_divergence():
    observation = complete_observation()
    observation["topo_image_entity"]["properties"]["digest"] = "sha256:" + "f" * 64
    assert_divergence(
        observation, H3Status.WRONG, H3FirstDivergence.IMAGE_DIGEST_IDENTITY_WRONG
    )


def test_both_entities_without_edge_is_missing():
    observation = complete_observation()
    observation["topo_relationship"]["present"] = False
    assert_divergence(
        observation,
        H3Status.MISSING,
        H3FirstDivergence.RUN_IMAGE_RELATIONSHIP_MISSING,
    )


def test_wrong_predicate_is_detected():
    observation = complete_observation()
    observation["topo_relationship"]["predicate"] = "uses"
    assert_divergence(
        observation, H3Status.WRONG, H3FirstDivergence.RUN_IMAGE_PREDICATE_WRONG
    )


def test_wrong_direction_is_detected():
    observation = complete_observation()
    relation = observation["topo_relationship"]
    relation["stored_source_entity_id"], relation["stored_target_entity_id"] = (
        relation["stored_target_entity_id"],
        relation["stored_source_entity_id"],
    )
    assert_divergence(
        observation, H3Status.WRONG, H3FirstDivergence.RUN_IMAGE_DIRECTION_WRONG
    )


@pytest.mark.parametrize("missing", ["origin", "source_component", "linker_version"])
def test_incomplete_provenance_is_partial(missing: str):
    observation = complete_observation()
    observation["topo_relationship"][missing] = None
    assert_divergence(
        observation,
        H3Status.PARTIAL,
        H3FirstDivergence.RUN_IMAGE_PROVENANCE_INCOMPLETE,
    )


def test_partial_provenance_completeness_is_partial():
    observation = complete_observation()
    observation["topo_relationship"]["completeness"] = "partial"
    assert_divergence(
        observation,
        H3Status.PARTIAL,
        H3FirstDivergence.RUN_IMAGE_PROVENANCE_INCOMPLETE,
    )


def test_missing_run_source_reference_is_partial():
    observation = complete_observation()
    observation["topo_relationship"]["source_references"] = [
        observation["topo_relationship"]["source_references"][1]
    ]
    assert_divergence(
        observation,
        H3Status.PARTIAL,
        H3FirstDivergence.RUN_IMAGE_SOURCE_REFERENCE_INCOMPLETE,
    )


def test_missing_digest_source_reference_is_partial():
    observation = complete_observation()
    observation["topo_relationship"]["source_references"] = [
        observation["topo_relationship"]["source_references"][0]
    ]
    assert_divergence(
        observation,
        H3Status.PARTIAL,
        H3FirstDivergence.RUN_IMAGE_SOURCE_REFERENCE_INCOMPLETE,
    )


def test_incomplete_temporal_metadata_is_partial():
    observation = complete_observation()
    observation["topo_relationship"]["temporal"] = None
    assert_divergence(
        observation,
        H3Status.PARTIAL,
        H3FirstDivergence.RUN_IMAGE_TEMPORAL_INCOMPLETE,
    )


def test_exact_edge_provenance_refs_and_time_is_proven():
    result = evaluate(complete_observation())
    assert result["status"] == H3Status.PROVEN.value
    assert result["first_divergence"] == H3FirstDivergence.NO_DIVERGENCE.value


def test_entity_failure_precedes_edge_failure():
    observation = complete_observation()
    observation["topo_image_entity"]["present"] = False
    observation["topo_relationship"]["present"] = False
    assert_divergence(
        observation, H3Status.MISSING, H3FirstDivergence.IMAGE_ENTITY_MISSING
    )


def test_later_errors_do_not_replace_earlier_run_divergence():
    observation = complete_observation()
    observation["topo_run_entity"]["present"] = False
    observation["topo_image_entity"]["present"] = False
    observation["topo_relationship"]["predicate"] = "depends_on"
    assert_divergence(
        observation, H3Status.MISSING, H3FirstDivergence.ACTIONS_RUN_ENTITY_MISSING
    )


def test_provider_access_unavailable_is_inconclusive():
    result = evaluate(
        complete_observation(), topo_provider_access_available=False
    )
    assert result["status"] == H3Status.INCONCLUSIVE.value
    assert (
        result["first_divergence"]
        == H3FirstDivergence.TOPO_PROVIDER_ACCESS_UNAVAILABLE.value
    )


def test_provider_expected_truth_is_explicitly_receipt_sourced():
    assert expected()["truth_source"] == "accepted_provider_receipt"


def test_provider_expected_builder_has_no_topo_argument():
    source = EVALUATOR.read_text(encoding="utf-8")
    signature = source.split("def provider_expected_from_receipt", 1)[1].split(") ->", 1)[0]
    assert "topo" not in signature.lower()


def test_provider_receipt_is_not_product_ingestion_shortcut():
    source = RUNNER.read_text(encoding="utf-8")
    exercise = source.split("def _exercise_product_path", 1)[1].split(
        "def run_h3_observation", 1
    )[0]
    assert "receipt" not in exercise
    assert "provider_payloads" in exercise


def test_post_repair_runner_uses_general_product_provider_evidence_path():
    source = RUNNER.read_text(encoding="utf-8")
    exercise = source.split("def _exercise_product_path", 1)[1].split(
        "def run_h3_observation", 1
    )[0]
    assert "GitHubConnector" in exercise
    assert "enrich_snapshot_with_github_actions_provider_evidence" in exercise
    assert "reconcile_build_artifact_lineage" not in exercise


def test_tag_cannot_substitute_for_digest():
    assert expected()["image_tag"] != expected()["image_digest"]


def test_digest_is_not_inferred_from_timestamps():
    source = EVALUATOR.read_text(encoding="utf-8")
    assert "hashlib" not in source
    assert receipt()["built_at"] is None


def test_no_fuzzy_matching_in_evaluator():
    source = EVALUATOR.read_text(encoding="utf-8").lower()
    for forbidden in ("difflib", "levenshtein", "fuzzywuzzy"):
        assert forbidden not in source


def test_no_llm_or_embedding_dependency():
    source = (EVALUATOR.read_text(encoding="utf-8") + RUNNER.read_text(encoding="utf-8")).lower()
    for forbidden in ("llm_client", "openai", "embedding"):
        assert forbidden not in source


def test_product_reasoning_services_are_not_imported_by_evaluator():
    source = EVALUATOR.read_text(encoding="utf-8")
    assert "from app." not in source
    assert "import app." not in source


def test_provider_and_topo_time_are_structurally_separate():
    item = expected()
    observation = complete_observation()
    assert "provider_run_timestamps" in item
    assert "observed_at" in observation["topo_relationship"]


def test_built_at_null_is_supported():
    value = receipt()
    assert value["built_at"] is None
    validate_provider_receipt(value)


def test_secret_like_values_are_redacted_from_result():
    result = build_h3_result(
        provider_expected=expected(),
        provider_verification={"authorization": "unsafe"},
        ingestion_exercise={"receipt_used_as_product_input": False},
        observation=complete_observation(),
        evaluation=evaluate(complete_observation()),
        observed_at="2026-08-24T04:07:00Z",
        product_git_commit="a" * 40,
    )
    assert result["provider_verification"]["authorization"] == "[REDACTED]"
    assert contains_unredacted_secret_like_fields(result) is False


def test_result_serialization_is_deterministic():
    value = {"z": 1, "a": {"b": 2}}
    assert serialize_h3_result(value) == serialize_h3_result(copy.deepcopy(value))
    assert serialize_h3_result(value).index('"a"') < serialize_h3_result(value).index('"z"')


def _validate_result_shape(result: dict[str, Any], schema: dict[str, Any]) -> None:
    assert result["schema_version"] == schema["properties"]["schema_version"]["const"]
    assert set(schema["required"]).issubset(result)
    status = schema["properties"]["evaluation"]["properties"]["status"]["enum"]
    divergence = schema["properties"]["evaluation"]["properties"]["first_divergence"]["enum"]
    assert result["evaluation"]["status"] in status
    assert result["evaluation"]["first_divergence"] in divergence
    assert re.fullmatch(r"[0-9a-f]{40}", result["product_git_commit"])


def test_h3_result_schema_validates_representative_result_shape():
    result = build_h3_result(
        provider_expected=expected(),
        provider_verification={},
        ingestion_exercise={
            "mode": "test",
            "receipt_used_as_product_input": False,
            "kubernetes_materialization_required": True,
            "product_code_changed": False,
        },
        observation=complete_observation(),
        evaluation=evaluate(complete_observation()),
        observed_at="2026-08-24T04:07:00Z",
        product_git_commit="a" * 40,
    )
    _validate_result_shape(result, json.loads(SCHEMA.read_text(encoding="utf-8")))


def test_observer_extracts_exact_entities_and_relationship():
    item = expected()
    observation = complete_observation()
    snapshot = {
        "snapshot_id": observation["snapshot_id"],
        "collected_at": observation["snapshot_collected_at"],
        "entities": [
            {
                "id": item["repository_canonical_entity_id"],
                "kind": "GitRepository",
                "properties": {},
            },
            {
                "id": item["commit_canonical_entity_id"],
                "kind": "GitCommit",
                "properties": {},
            },
            {
                "id": item["run_canonical_entity_id"],
                "kind": "GitHubWorkflowRun",
                "external_id": item["run_id"],
                "source_system": "github-actions",
                "properties": observation["topo_run_entity"]["properties"],
            },
            {
                "id": item["image_canonical_entity_id"],
                "kind": "ContainerImage",
                "external_id": item["image_digest"],
                "source_system": "kubernetes",
                "properties": observation["topo_image_entity"]["properties"],
            },
        ],
        "relationships": [
            {
                "id": "repo-run",
                "source_entity_id": item["repository_canonical_entity_id"],
                "target_entity_id": item["run_canonical_entity_id"],
                "relationship_type": "contains",
                "provenance": {"source_references": []},
            },
            {
                "id": "commit-run",
                "source_entity_id": item["commit_canonical_entity_id"],
                "target_entity_id": item["run_canonical_entity_id"],
                "relationship_type": "triggers",
            },
            {
                "id": "run-image",
                "source_entity_id": item["run_canonical_entity_id"],
                "target_entity_id": item["image_canonical_entity_id"],
                "relationship_type": "produces",
                "directed": True,
                "provenance": {
                    "origin": "inferred",
                    "source_component": "component",
                    "source_references": [],
                    "linker_version": "v1",
                    "completeness": "complete",
                },
            },
        ],
    }
    extracted = observe_topo_snapshot(snapshot, item)
    assert extracted["topo_run_entity"]["repository_scope_match"] is True
    assert extracted["topo_image_entity"]["immutable_digest"] == item["image_digest"]
    assert extracted["topo_relationship"]["predicate"] == "produces"


def test_no_scenario_specific_provider_values_in_product_paths():
    needles = ("32688747741", "ebd9da90b6d9d4366f1349ba18106792")
    for path in (ROOT / "backend/app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not any(needle in text for needle in needles), path


def test_h3_r1_historical_product_scope_remains_exact():
    assert_h3_r1_historical_product_scope(ROOT)


def test_provider_workflow_remains_frozen():
    assert hashlib.sha256(WORKFLOW.read_bytes()).hexdigest() == WORKFLOW_SHA256


@pytest.mark.parametrize("name,expected_hash", sorted(PERMANENT_MANIFEST_HASHES.items()))
def test_permanent_manifest_remains_unchanged(name: str, expected_hash: str):
    path = ROOT / "evaluation/manifests" / name
    actual = subprocess.run(
        ["git", "hash-object", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert actual == expected_hash

