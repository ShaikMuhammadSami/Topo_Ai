from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from evaluation.runtime_causal_observer import (
    ACCEPTED_WAITING_REASONS,
    RUNTIME_CAUSAL_RECEIPT_VERSION,
    image_digest_from_ref,
    namespace_for_run,
    render_deployment_template,
    require_safe_namespace,
    validate_runtime_causal_receipt,
    verify_local_cluster,
)
from evaluation.source_cause_match import (
    CausalVerdict,
    FirstDivergence,
    RootCauseLevel,
    SOURCE_CAUSE_MATCH_VERSION,
    audit_evidence_ledger,
    blank_topo_observation,
    cause_observation,
    deterministic_result_json,
    evaluate_source_cause,
    validate_source_cause_result,
)
from evaluation.source_mutation_truth import (
    FAIL_BYTES,
    HEALTHY_BYTES,
    source_mutation_from_local_git,
)
from evaluation.product_diff_guard import (
    assert_text_file_git_blob_id,
    assert_file_sha256,
    assert_historical_commit_excludes_paths,
)


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_CAUSAL_OBSERVATION_ACCEPTED_COMMIT = (
    "9318efe6a13eab9e3dc114df75edd5784dacfdf9"
)
RUN_ID = 32695735269
PARENT = "f9b152133a8075428766dd48b3f752b255ec5270"
FAILURE = "4149b194c4c4fdfdcd402a157c5336ad59dfdbbe"
REPOSITORY = "ShaikMuhammadSami/Topo_Ai"
REPOSITORY_ID = "1278498159"
DIGEST = "sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed"
IMAGE = f"ghcr.io/shaikmuhammadsami/topo_ai-topo-lineage-eval@{DIGEST}"
SOURCE_PATH = "evaluation/fixtures/lineage-image/runtime-mode.txt"
WORKFLOW = ROOT / ".github/workflows/topo-lineage-provider-fixture.yml"
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


def source_truth() -> dict[str, Any]:
    return source_mutation_from_local_git(
        repo_root=ROOT,
        repository_id=REPOSITORY_ID,
        repository=REPOSITORY,
        parent_commit_sha=PARENT,
        commit_sha=FAILURE,
    )


def runtime_receipt() -> dict[str, Any]:
    return {
        "schema_version": RUNTIME_CAUSAL_RECEIPT_VERSION,
        "experiment": {
            "run_id": RUN_ID,
            "source_parent_commit": PARENT,
            "source_failure_commit": FAILURE,
            "immutable_image_ref": IMAGE,
            "image_digest": DIGEST,
        },
        "kubernetes": {
            "context": "docker-desktop",
            "cluster": "docker-desktop",
            "namespace": namespace_for_run(RUN_ID),
            "namespace_uid": "namespace-uid",
            "deployment_name": "lineage-causal-fixture",
            "deployment_uid": "deployment-uid",
            "replicaset_name": "lineage-causal-fixture-rs",
            "replicaset_uid": "replicaset-uid",
            "pod_name": "lineage-causal-fixture-rs-pod",
            "pod_uid": "pod-uid",
        },
        "ownership": {
            "replicaset_owner_deployment_uid": "deployment-uid",
            "pod_owner_replicaset_uid": "replicaset-uid",
        },
        "container": {
            "name": "fixture",
            "image": IMAGE,
            "image_id": f"ghcr.io/shaikmuhammadsami/topo_ai-topo-lineage-eval@{DIGEST}",
            "restart_count": 2,
            "waiting_reason": "CrashLoopBackOff",
            "current_state": "waiting",
            "last_termination_reason": "Error",
            "last_termination_exit_code": 42,
            "last_termination_started_at": "2026-08-24T06:30:00Z",
            "last_termination_finished_at": "2026-08-24T06:30:00Z",
            "backoff_observation": {
                "source": "container_status_waiting",
                "reason": "CrashLoopBackOff",
                "event_uid": None,
                "event_count": None,
                "observed_at": None,
            },
        },
        "deployment_status": {
            "desired_replicas": 1,
            "ready_replicas": 0,
            "available_replicas": 0,
            "unavailable_replicas": 1,
        },
        "observation": {
            "started_at": "2026-08-24T06:29:00Z",
            "failure_confirmed_at": "2026-08-24T06:30:01Z",
            "captured_at": "2026-08-24T06:30:02Z",
            "timeout_seconds": 120,
        },
        "ground_truth": {
            "exact_image_identity_confirmed": True,
            "ownership_chain_confirmed": True,
            "failure_mechanism_confirmed": True,
            "runtime_manifestation_confirmed": True,
            "operational_impact_confirmed": True,
        },
        "topo_used_to_construct_truth": False,
    }


def exact_cause(*, evidence_chain_complete: bool = True) -> dict[str, Any]:
    source = source_truth()
    return cause_observation(
        semantic_level=RootCauseLevel.INITIATING_MUTATION,
        supported=True,
        root_event_id="event-failure-commit",
        confidence=0.91,
        repository=source["repository"],
        parent_commit_sha=source["parent_commit_sha"],
        commit_sha=source["commit_sha"],
        file_path=source["file_path"],
        before_hash=source["before_hash"],
        after_hash=source["after_hash"],
        before_semantic_value=source["before_semantic_value"],
        after_semantic_value=source["after_semantic_value"],
        run_id=RUN_ID,
        image_digest=DIGEST,
        evidence_chain_complete=evidence_chain_complete,
    )


def complete_topo_observation() -> dict[str, Any]:
    source = source_truth()
    value = blank_topo_observation(run_id=RUN_ID)
    value["source_change"] = {
        "present": True,
        **{field: source[field] for field in (
            "repository",
            "parent_commit_sha",
            "commit_sha",
            "file_path",
            "before_hash",
            "after_hash",
            "before_semantic_value",
            "after_semantic_value",
        )},
    }
    for name in value["entities"]:
        value["entities"][name] = {
            "present": True,
            "entity_id": f"entity-{name}",
            "provider_identity": {},
        }
    value["entities"]["actions_run"]["provider_identity"] = {
        "run_id": RUN_ID,
        "run_attempt": 1,
    }
    value["entities"]["image"]["provider_identity"] = {
        "image_digest": DIGEST
    }
    value["entities"]["deployment"]["provider_identity"] = {
        "uid": "deployment-uid"
    }
    value["entities"]["replicaset"]["provider_identity"] = {
        "uid": "replicaset-uid"
    }
    value["entities"]["pod"]["provider_identity"] = {"uid": "pod-uid"}
    for name in value["relationships"]:
        value["relationships"][name] = {
            "present": True,
            "relationship_id": f"relationship-{name}",
            "predicate": "connected",
        }
    value["runtime"] = {
        "pod_failure_present": True,
        "exit_code": 42,
        "restart_count": 2,
        "backoff_reason": "CrashLoopBackOff",
        "desired_replicas": 1,
        "ready_replicas": 0,
        "available_replicas": 0,
    }
    value["incident"] = {
        "present": True,
        "incident_id": "incident-lineage-1c",
        "first_failure_signal_id": "signal-lineage-1c",
        "boundary_time": "2026-08-24T06:30:01Z",
        "pinned_topology_id": "snapshot-lineage-1c",
        "snapshot_effective_time": "2026-08-24T06:30:00Z",
        "pin_temporally_valid": True,
        "affected_entity_id": "entity-pod",
        "affected_entity_kind": "KubernetesPod",
        "affected_entity_matches_runtime": True,
        "analysis_state": "complete",
    }
    cause = exact_cause()
    value["causal"] = {
        "candidate_present": True,
        "relevance_path_present": True,
        "top1": cause,
        "top3": [cause],
        "evidence_ledger": {
            "supporting": [
                {"evidence_id": "evidence-source-lineage", "truth_status": "supported"}
            ],
            "contradicting": [],
            "unknown": [],
            "missing": [],
        },
    }
    return value


def evaluate(value: dict[str, Any] | None = None) -> dict[str, Any]:
    return evaluate_source_cause(
        source_truth(), runtime_receipt(), value or complete_topo_observation()
    )


def _is_type(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }[expected]


def validate_json_schema(value: Any, schema: dict[str, Any], root: dict[str, Any]) -> None:
    if "$ref" in schema:
        target: Any = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        validate_json_schema(value, target, root)
        return
    if "oneOf" in schema:
        matches = 0
        for candidate in schema["oneOf"]:
            try:
                validate_json_schema(value, candidate, root)
            except AssertionError:
                continue
            matches += 1
        assert matches == 1
        return
    if "const" in schema:
        assert value == schema["const"]
    if "enum" in schema:
        assert value in schema["enum"]
    if "type" in schema:
        accepted = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        assert any(_is_type(value, item) for item in accepted)
    if isinstance(value, dict):
        assert set(schema.get("required") or []).issubset(value)
        properties = schema.get("properties") or {}
        if schema.get("additionalProperties") is False:
            assert set(value).issubset(properties)
        for key, item in value.items():
            if key in properties:
                validate_json_schema(item, properties[key], root)
    if isinstance(value, list):
        if "minItems" in schema:
            assert len(value) >= schema["minItems"]
        if "maxItems" in schema:
            assert len(value) <= schema["maxItems"]
        if "items" in schema:
            for item in value:
                validate_json_schema(item, schema["items"], root)
    if isinstance(value, str):
        if "minLength" in schema:
            assert len(value) >= schema["minLength"]
        if "pattern" in schema:
            assert re.fullmatch(schema["pattern"], value)
        if schema.get("format") == "date-time":
            datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema:
            assert value >= schema["minimum"]
        if "maximum" in schema:
            assert value <= schema["maximum"]


def test_frozen_parent_sha_format():
    assert re.fullmatch(r"[0-9a-f]{40}", PARENT)


def test_frozen_failure_sha_format():
    assert re.fullmatch(r"[0-9a-f]{40}", FAILURE)


def test_failure_commit_has_exact_direct_parent():
    parents = subprocess.run(
        ["git", "rev-list", "--parents", "-n", "1", FAILURE],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip().split()
    assert parents == [FAILURE, PARENT]


def test_failure_commit_changes_exactly_one_file():
    changed = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", PARENT, FAILURE, "--"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert changed == [SOURCE_PATH]


def test_source_path_matches_exactly():
    assert source_truth()["file_path"] == SOURCE_PATH


def test_source_blob_hashes_are_exact():
    truth = source_truth()
    assert truth["before_hash"] == hashlib.sha256(HEALTHY_BYTES).hexdigest()
    assert truth["after_hash"] == hashlib.sha256(FAIL_BYTES).hexdigest()


def test_source_semantics_are_exact_healthy_to_fail():
    truth = source_truth()
    assert (truth["before_semantic_value"], truth["after_semantic_value"]) == (
        "healthy",
        "fail",
    )


def test_expected_failure_mechanism_is_exit_42():
    assert source_truth()["expected_failure_mechanism"]["exit_code"] == 42


def test_runtime_receipt_contract_is_strict():
    value = runtime_receipt()
    validate_runtime_causal_receipt(value)
    value["unexpected"] = True
    with pytest.raises(ValueError, match="fields do not match"):
        validate_runtime_causal_receipt(value)


def test_exact_immutable_digest_is_required():
    assert image_digest_from_ref(IMAGE) == DIGEST


@pytest.mark.parametrize("mutable", ["repo/image:latest", "repo/image:run-1", "repo/image"])
def test_mutable_tag_cannot_satisfy_artifact_identity(mutable: str):
    with pytest.raises(ValueError, match="immutable"):
        image_digest_from_ref(mutable)


@pytest.mark.parametrize("field", ["deployment_uid", "replicaset_uid", "pod_uid"])
def test_runtime_provider_uid_is_required(field: str):
    value = runtime_receipt()
    value["kubernetes"][field] = None
    with pytest.raises(ValueError, match=field):
        validate_runtime_causal_receipt(value)


def test_owner_reference_chain_is_exact():
    validate_runtime_causal_receipt(runtime_receipt())


@pytest.mark.parametrize(
    "field",
    ["replicaset_owner_deployment_uid", "pod_owner_replicaset_uid"],
)
def test_wrong_owner_uid_invalidates_chain(field: str):
    value = runtime_receipt()
    value["ownership"][field] = "wrong-owner"
    with pytest.raises(ValueError, match="owner-reference"):
        validate_runtime_causal_receipt(value)


def test_exit_code_other_than_42_invalidates_experiment():
    value = runtime_receipt()
    value["container"]["last_termination_exit_code"] = 1
    with pytest.raises(ValueError, match="exit code 42"):
        validate_runtime_causal_receipt(value)


def test_restart_count_zero_is_insufficient():
    value = runtime_receipt()
    value["container"]["restart_count"] = 0
    with pytest.raises(ValueError, match="At least one"):
        validate_runtime_causal_receipt(value)


@pytest.mark.parametrize("reason", sorted(ACCEPTED_WAITING_REASONS))
def test_structured_backoff_reason_is_accepted(reason: str):
    value = runtime_receipt()
    value["container"]["backoff_observation"]["reason"] = reason
    validate_runtime_causal_receipt(value)


def test_non_backoff_reason_is_rejected():
    value = runtime_receipt()
    value["container"]["backoff_observation"]["reason"] = "Running"
    with pytest.raises(ValueError, match="backoff"):
        validate_runtime_causal_receipt(value)


@pytest.mark.parametrize(
    "field,bad",
    [("desired_replicas", 2), ("ready_replicas", 1), ("available_replicas", 1)],
)
def test_operational_impact_requires_one_zero_zero(field: str, bad: int):
    value = runtime_receipt()
    value["deployment_status"][field] = bad
    with pytest.raises(ValueError, match="replica"):
        validate_runtime_causal_receipt(value)


def test_source_truth_is_independent_of_topo():
    assert source_truth()["topo_output_used"] is False


def test_runtime_truth_is_independent_of_topo():
    assert runtime_receipt()["topo_used_to_construct_truth"] is False


def test_exact_level_one_top1_with_complete_evidence_is_proven():
    result = evaluate()
    assert result["verdict"] == CausalVerdict.PROVEN.value
    assert result["first_internal_divergence"] == FirstDivergence.NO_DIVERGENCE.value


def test_exact_source_mutation_in_top3_only_is_partial():
    value = complete_topo_observation()
    lower = cause_observation(
        semantic_level=RootCauseLevel.RUNTIME_MANIFESTATION,
        supported=True,
        root_event_id="pod-crash",
        confidence=0.8,
        evidence_chain_complete=True,
    )
    value["causal"]["top1"] = lower
    value["causal"]["top3"] = [lower, exact_cause()]
    assert evaluate(value)["verdict"] == CausalVerdict.PARTIAL.value


def test_exact_commit_and_image_only_is_partial():
    value = complete_topo_observation()
    value["causal"]["top1"] = cause_observation(
        semantic_level=RootCauseLevel.INITIATING_MUTATION,
        supported=True,
        commit_sha=FAILURE,
        image_digest=DIGEST,
        evidence_chain_complete=True,
    )
    value["causal"]["top3"] = [value["causal"]["top1"]]
    assert evaluate(value)["verdict"] == CausalVerdict.PARTIAL.value


@pytest.mark.parametrize(
    "level",
    [
        RootCauseLevel.FAILURE_MECHANISM,
        RootCauseLevel.RUNTIME_MANIFESTATION,
        RootCauseLevel.OPERATIONAL_IMPACT,
    ],
)
def test_lower_semantic_level_is_partial(level: RootCauseLevel):
    value = complete_topo_observation()
    value["causal"]["top1"] = cause_observation(
        semantic_level=level,
        supported=True,
        evidence_chain_complete=True,
    )
    value["causal"]["top3"] = [value["causal"]["top1"]]
    result = evaluate(value)
    assert result["verdict"] == CausalVerdict.PARTIAL.value
    assert result["first_internal_divergence"] == (
        FirstDivergence.ROOT_CAUSE_LOWER_SEMANTIC_LEVEL.value
    )


@pytest.mark.parametrize(
    "field,bad",
    [("file_path", "different/file.txt"), ("commit_sha", "a" * 40)],
)
def test_different_source_mutation_is_wrong(field: str, bad: str):
    value = complete_topo_observation()
    cause = exact_cause()
    cause[field] = bad
    value["causal"]["top1"] = cause
    value["causal"]["top3"] = [cause]
    assert evaluate(value)["verdict"] == CausalVerdict.WRONG.value


def test_missing_source_ingestion_is_missing_at_first_divergence():
    value = complete_topo_observation()
    value["source_change"] = blank_topo_observation(run_id=RUN_ID)["source_change"]
    result = evaluate(value)
    assert result["verdict"] == CausalVerdict.MISSING.value
    assert result["first_internal_divergence"] == (
        FirstDivergence.SOURCE_CHANGE_NOT_INGESTED.value
    )


@pytest.mark.parametrize(
    "relationship,divergence",
    [
        ("actions_image", FirstDivergence.RUN_IMAGE_LINK_MISSING),
        ("image_deployment", FirstDivergence.IMAGE_DEPLOYMENT_LINK_MISSING),
        ("deployment_replicaset", FirstDivergence.DEPLOYMENT_RS_LINK_MISSING),
        ("replicaset_pod", FirstDivergence.RS_POD_LINK_MISSING),
    ],
)
def test_missing_lineage_hop_is_earliest_divergence(
    relationship: str, divergence: FirstDivergence
):
    value = complete_topo_observation()
    value["relationships"][relationship]["present"] = False
    result = evaluate(value)
    assert result["verdict"] == CausalVerdict.MISSING.value
    assert result["first_internal_divergence"] == divergence.value


def test_missing_pod_failure_evidence_is_detected():
    value = complete_topo_observation()
    value["runtime"]["pod_failure_present"] = False
    result = evaluate(value)
    assert result["first_internal_divergence"] == (
        FirstDivergence.POD_FAILURE_EVIDENCE_MISSING.value
    )


def test_no_incident_is_detected():
    value = complete_topo_observation()
    value["incident"]["present"] = False
    result = evaluate(value)
    assert result["first_internal_divergence"] == FirstDivergence.INCIDENT_NOT_CREATED.value


def test_future_or_invalid_incident_pin_is_detected():
    value = complete_topo_observation()
    value["incident"]["pin_temporally_valid"] = False
    result = evaluate(value)
    assert result["first_internal_divergence"] == FirstDivergence.INCIDENT_PIN_INVALID.value


def test_missing_causal_candidate_is_detected():
    value = complete_topo_observation()
    value["causal"]["candidate_present"] = False
    result = evaluate(value)
    assert result["first_internal_divergence"] == FirstDivergence.CAUSAL_CANDIDATE_MISSING.value


def test_missing_causal_relevance_path_is_detected():
    value = complete_topo_observation()
    value["causal"]["relevance_path_present"] = False
    result = evaluate(value)
    assert result["first_internal_divergence"] == FirstDivergence.CAUSAL_RELEVANCE_PATH_MISSING.value


def test_incomplete_evidence_chain_is_partial_and_detected():
    value = complete_topo_observation()
    cause = exact_cause(evidence_chain_complete=False)
    value["causal"]["top1"] = cause
    value["causal"]["top3"] = [cause]
    result = evaluate(value)
    assert result["verdict"] == CausalVerdict.PARTIAL.value
    assert result["first_internal_divergence"] == FirstDivergence.EVIDENCE_CHAIN_INCOMPLETE.value


def test_abstention_is_represented_distinctly():
    value = complete_topo_observation()
    abstained = cause_observation(
        semantic_level=RootCauseLevel.ABSTAINED,
        supported=False,
    )
    value["causal"]["top1"] = abstained
    value["causal"]["top3"] = [abstained]
    result = evaluate(value)
    assert result["abstained"] is True
    assert result["verdict"] == CausalVerdict.MISSING.value


@pytest.mark.parametrize(
    "forbidden",
    ["root_title", "fuzzywuzzy", "rapidfuzz", "sentence_transformers", "openai"],
)
def test_source_cause_evaluator_contains_no_forbidden_matcher(forbidden: str):
    source = (ROOT / "evaluation/source_cause_match.py").read_text(
        encoding="utf-8"
    ).lower()
    assert forbidden not in source


def test_evaluator_diagnostics_confirm_no_similarity_or_llm_authority():
    diagnostics = evaluate()["diagnostics"]
    assert diagnostics["title_token_matching_used"] is False
    assert diagnostics["fuzzy_matching_used"] is False
    assert diagnostics["embeddings_used"] is False
    assert diagnostics["llm_used"] is False


def test_evaluator_imports_no_product_reasoning_module():
    source = (ROOT / "evaluation/source_cause_match.py").read_text(encoding="utf-8")
    assert "backend.app" not in source
    assert "causal_candidate_policy" not in source
    assert "causal_relevance_policy" not in source


def test_unknown_evidence_is_not_contradiction():
    audit = audit_evidence_ledger(
        {
            "supporting": [],
            "contradicting": [
                {"evidence_id": "unknown-1", "truth_status": "unknown"}
            ],
            "unknown": [],
            "missing": [],
        }
    )
    assert audit["unknown_count"] == 1
    assert audit["contradicting_count"] == 0


def test_missing_evidence_requires_expectation_basis():
    with pytest.raises(ValueError, match="expectation basis"):
        audit_evidence_ledger(
            {
                "supporting": [],
                "contradicting": [],
                "unknown": [],
                "missing": [{"evidence_id": "missing-1"}],
            }
        )


def test_result_serialization_is_deterministic():
    result = evaluate()
    assert deterministic_result_json(result) == deterministic_result_json(result)


def test_runtime_schema_validates_complete_receipt():
    schema = json.loads(
        (ROOT / "docs/architecture/evaluation/runtime-causal-receipt.schema.json").read_text()
    )
    validate_json_schema(runtime_receipt(), schema, schema)


def test_source_cause_schema_validates_complete_result():
    result = evaluate()
    schema = json.loads(
        (ROOT / "docs/architecture/evaluation/source-cause-match.schema.json").read_text()
    )
    validate_json_schema(result, schema, schema)


def test_schema_versions_are_frozen():
    runtime_schema = json.loads(
        (ROOT / "docs/architecture/evaluation/runtime-causal-receipt.schema.json").read_text()
    )
    source_schema = json.loads(
        (ROOT / "docs/architecture/evaluation/source-cause-match.schema.json").read_text()
    )
    assert runtime_schema["properties"]["schema_version"]["const"] == RUNTIME_CAUSAL_RECEIPT_VERSION
    assert source_schema["properties"]["schema_version"]["const"] == SOURCE_CAUSE_MATCH_VERSION


def test_runtime_causal_observation_commit_changed_no_product_paths():
    assert_historical_commit_excludes_paths(
        ROOT,
        name="LINEAGE-1C runtime causal observation",
        commit=RUNTIME_CAUSAL_OBSERVATION_ACCEPTED_COMMIT,
    )


@pytest.mark.parametrize("name,expected", sorted(PERMANENT_MANIFEST_HASHES.items()))
def test_permanent_manifest_is_unchanged(name: str, expected: str):
    assert_text_file_git_blob_id(ROOT / "evaluation/manifests" / name, expected)


def test_frozen_h3_workflow_is_unchanged():
    assert_file_sha256(WORKFLOW, WORKFLOW_SHA256)


def test_failure_branch_still_points_to_frozen_commit():
    actual = subprocess.run(
        ["git", "rev-parse", "evaluation/lineage-1-failure-run-v1"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert actual == FAILURE


def test_evaluation_tooling_cannot_rerun_provider_workflow():
    text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (
            ROOT / "evaluation/runtime_causal_observer.py",
            ROOT / "evaluation/source_cause_match.py",
        )
    )
    assert "gh workflow run" not in text
    assert "workflow_dispatch" not in text
    assert "build-push" not in text


def test_cleanup_guard_requires_exact_namespace_prefix():
    with pytest.raises(ValueError):
        require_safe_namespace("default", RUN_ID, {"topo.ai/evaluation-run": str(RUN_ID)})


def test_cleanup_guard_requires_exact_run_label():
    with pytest.raises(ValueError, match="label"):
        require_safe_namespace(namespace_for_run(RUN_ID), RUN_ID, {"topo.ai/evaluation-run": "wrong"})


def test_local_cluster_safety_accepts_only_docker_desktop_loopback_kind_nodes():
    result = verify_local_cluster(
        context="docker-desktop",
        cluster="docker-desktop",
        server="https://127.0.0.1:6443",
        nodes=[{"metadata": {"name": "desktop-worker"}, "spec": {"providerID": "kind://docker/desktop/desktop-worker"}}],
    )
    assert result["safe"] is True


@pytest.mark.parametrize(
    "context,cluster,server,provider",
    [
        ("production", "production", "https://10.0.0.1", "aws:///node"),
        ("docker-desktop", "docker-desktop", "https://remote.example", "kind://docker/desktop/node"),
        ("docker-desktop", "docker-desktop", "https://127.0.0.1", "aws:///node"),
    ],
)
def test_local_cluster_safety_rejects_unknown_or_remote_cluster(
    context: str, cluster: str, server: str, provider: str
):
    with pytest.raises(ValueError, match="INCONCLUSIVE_LOCAL_CLUSTER_SAFETY"):
        verify_local_cluster(
            context=context,
            cluster=cluster,
            server=server,
            nodes=[{"metadata": {"name": "node"}, "spec": {"providerID": provider}}],
        )


def test_deployment_template_renders_only_frozen_placeholders():
    template = (ROOT / "evaluation/fixtures/lineage-causal/deployment.yaml").read_text()
    rendered = render_deployment_template(template, run_id=RUN_ID, immutable_image_ref=IMAGE)
    assert "__RUN_ID__" not in rendered
    assert "__IMMUTABLE_IMAGE_REF__" not in rendered
    assert namespace_for_run(RUN_ID) in rendered
    assert IMAGE in rendered
    assert "command:" not in rendered
    assert "args:" not in rendered
    assert "env:" not in rendered
    documents = list(yaml.safe_load_all(rendered))
    assert all(
        document["metadata"]["labels"]["topo.ai/evaluation-run"] == str(RUN_ID)
        for document in documents
    )


def test_mutable_image_cannot_render_deployment():
    template = (ROOT / "evaluation/fixtures/lineage-causal/deployment.yaml").read_text()
    with pytest.raises(ValueError, match="immutable"):
        render_deployment_template(template, run_id=RUN_ID, immutable_image_ref="repo/image:latest")


def test_observation_matrix_contains_all_required_dimensions():
    dimensions = {item["dimension"] for item in evaluate()["observation_matrix"]}
    assert {
        "Repository",
        "Parent commit",
        "Failure commit",
        "Changed file",
        "Commit -> Actions",
        "Actions -> Image",
        "Image -> Deployment",
        "Deployment -> ReplicaSet",
        "ReplicaSet -> Pod",
        "Pod failure",
        "Incident",
        "Pinned topology",
        "Causal candidate",
        "Causal relevance path",
        "Top1 root cause",
        "Top3 supported causes",
        "TC4 evidence ledger",
        "Root-cause semantic level",
    }.issubset(dimensions)


def test_result_validator_rejects_unknown_fields():
    result = evaluate()
    result["unexpected"] = True
    with pytest.raises(ValueError, match="fields do not match"):
        validate_source_cause_result(result)
