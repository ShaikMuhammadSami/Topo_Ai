from __future__ import annotations

import copy
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest

from evaluation.contracts import (
    EvaluationResult,
    EvaluationStatus,
    ExecutionAction,
    ExecutionReceipt,
    ProviderObject,
    ProviderVerification,
    ScenarioManifest,
    TopoObservation,
    contract_dict,
    deterministic_json,
    validate_manifest,
)
from evaluation.evaluator import IndependentEvaluator
from evaluation.kubernetes import EVALUATION_LABEL, Kubectl
from evaluation.scenarios import manifest_path
from evaluation.topo_client import bounded_wait


ROOT = Path(__file__).resolve().parents[2]


def provider() -> ProviderVerification:
    values = [
        ("root_deployment", "Deployment", "sentinel-a-app", "uid-dep"),
        ("root_replicaset", "ReplicaSet", "sentinel-a-app-abc", "uid-rs"),
        ("root_pod", "Pod", "sentinel-a-app-abc-xyz", "uid-pod"),
        ("root_service", "Service", "sentinel-a-app", "uid-svc"),
    ]
    return ProviderVerification(
        verification_version="eval-1.provider.v1",
        source="kubernetes-api-via-kubectl",
        observed_at="2026-08-23T10:00:01+00:00",
        established=True,
        objects=[
            ProviderObject(
                logical_name=alias,
                provider_kind=kind,
                namespace="topo-eval-a-abcdef",
                name=name,
                uid=uid,
                observed_at="2026-08-23T10:00:01+00:00",
            )
            for alias, kind, name, uid in values
        ],
        assertions=[{"failure_observed_at": "2026-08-23T10:00:00+00:00", "passed": True}],
    )


def semantics(state: str = "supported_under_current_model") -> dict:
    return {
        "score_type": "heuristic_ranking",
        "calibration_status": "not_calibrated",
        "calibrated_probability": None,
        "evidence_state": state,
        "ranking_score": 87.0,
    }


def observation() -> TopoObservation:
    entities = [
        {"id": "e-dep", "external_id": "uid-dep", "kind": "KubernetesDeployment", "name": "sentinel-a-app", "properties": {"namespace": "topo-eval-a-abcdef"}},
        {"id": "e-rs", "external_id": "uid-rs", "kind": "KubernetesReplicaSet", "name": "sentinel-a-app-abc", "properties": {"namespace": "topo-eval-a-abcdef"}},
        {"id": "e-pod", "external_id": "uid-pod", "kind": "KubernetesPod", "name": "sentinel-a-app-abc-xyz", "properties": {"namespace": "topo-eval-a-abcdef"}},
        {"id": "e-svc", "external_id": "uid-svc", "kind": "KubernetesService", "name": "sentinel-a-app", "properties": {"namespace": "topo-eval-a-abcdef"}},
    ]
    relationships = [
        {"id": "r1", "source_entity_id": "e-dep", "target_entity_id": "e-rs", "relationship_type": "owns", "directed": True},
        {"id": "r2", "source_entity_id": "e-rs", "target_entity_id": "e-pod", "relationship_type": "owns", "directed": True},
        {"id": "r3", "source_entity_id": "e-svc", "target_entity_id": "e-pod", "relationship_type": "selects", "directed": True},
    ]
    top = {
        "hypothesis_id": "h1",
        "rank": 1,
        "root_event_id": "event-true",
        "root_source": "kubernetes",
        "root_title": "Deployment configuration changed",
        "affected_entity_id": "e-dep",
        "score": 87.0,
        "chain": [{"node_id": "node-dep", "node_type": "entity", "label": "deployment"}],
        "confidence_semantics": semantics(),
        "evidence_ledger": {
            "supporting": [
                {"claim_type": "topology_path", "entity_ids": ["e-dep", "e-rs", "e-pod"], "relationship_ids": ["r1", "r2"]}
            ],
            "contradicting": [],
            "missing": [],
        },
    }
    return TopoObservation(
        observation_version="eval-1.topo-observation.v1",
        captured_at="2026-08-23T10:00:05+00:00",
        incident={"incident_id": "inc-1", "affected_entity_id": "e-pod", "topology_snapshot_id": "snap-1", "occurrence_count": 1},
        incident_candidates=[{"incident_id": "inc-1"}],
        snapshot={"snapshot_id": "snap-1", "entities": entities, "relationships": relationships},
        causal_analysis={
            "analysis_id": "analysis-1",
            "top_hypothesis": top,
            "hypotheses": [top],
            "nodes": [{"node_id": "node-dep", "entity_id": "e-dep"}],
            "confidence_semantics": semantics(),
        },
        briefing={"incident_id": "inc-1"},
        blast_radius={"affected_entities": [{"entity_id": item} for item in ("e-pod", "e-rs", "e-dep")]},
        change_events=[{"event_id": "event-true", "title": "Deployment configuration changed", "entity_links": [{"entity_id": "e-dep"}]}],
        observed_times={
            "incident": "2026-08-23T10:00:02+00:00",
            "causal_analysis": "2026-08-23T10:00:03+00:00",
            "briefing": "2026-08-23T10:00:04+00:00",
        },
    )


def evaluate(manifest: ScenarioManifest | None = None, truth: ProviderVerification | None = None, topo: TopoObservation | None = None):
    return IndependentEvaluator().evaluate(
        manifest or ScenarioManifest.load(manifest_path("sentinel-a")),
        truth or provider(),
        topo or observation(),
    )


def altered_manifest(mutator) -> ScenarioManifest:
    value = ScenarioManifest.load(manifest_path("sentinel-a")).ground_truth_copy()
    mutator(value)
    validate_manifest(value)
    return ScenarioManifest(value=value)


def test_all_manifests_validate_and_use_stable_aliases():
    for scenario in ("sentinel-a", "sentinel-b", "sentinel-c", "sentinel-d"):
        manifest = ScenarioManifest.load(manifest_path(scenario))
        assert manifest.scenario_id == scenario
        assert all("uid" not in alias.lower() for alias in manifest.aliases)


def test_machine_readable_schemas_are_valid_json_and_cover_contracts():
    manifest_schema = json.loads((ROOT / "docs/architecture/evaluation/scenario-manifest.schema.json").read_text())
    result_schema = json.loads((ROOT / "docs/architecture/evaluation/evaluation-result.schema.json").read_text())
    assert manifest_schema["$schema"].endswith("2020-12/schema")
    assert set(manifest_schema["required"]) == set(ScenarioManifest.load(manifest_path("sentinel-a")).value)
    assert "overall_status" in result_schema["required"]


def test_manifest_rejects_unknown_alias_and_probability():
    value = ScenarioManifest.load(manifest_path("sentinel-a")).ground_truth_copy()
    value["non_causes"] = ["missing_alias"]
    with pytest.raises(ValueError, match="Unknown logical aliases"):
        validate_manifest(value)
    value["non_causes"] = []
    value["expected_confidence_semantics"]["calibrated_probability"] = 0.8
    with pytest.raises(ValueError, match="probability"):
        validate_manifest(value)


def test_execution_and_provider_serialization_keep_provider_ids_separate():
    receipt = ExecutionReceipt(
        receipt_version="eval-1.execution.v1",
        scenario_id="sentinel-a",
        run_id="abcdef12",
        namespace="topo-eval-a-abcdef12",
        started_at="2026-08-23T10:00:00+00:00",
        actions=[
            ExecutionAction("a1", "causal_bad_image", "root_deployment", "provider-uid", "2026-08-23T10:00:00+00:00", {"image": "good"}, {"image": "bad"})
        ],
    )
    assert contract_dict(receipt)["actions"][0]["provider_uid"] == "provider-uid"
    assert asdict(provider())["objects"][0]["uid"].startswith("uid-")
    assert "e-dep" not in deterministic_json(asdict(provider()))


def test_complete_supported_result_passes_and_calculates_latencies():
    status, metrics, _, failures = evaluate()
    assert status == EvaluationStatus.PASS
    assert not failures
    assert metrics["root_cause_top1_correct"] is True
    assert metrics["root_cause_top3_contains_truth"] is True
    assert metrics["identity_correct"] is True
    assert metrics["time_to_incident"] == 2.0
    assert metrics["time_to_persisted_rca"] == 3.0
    assert metrics["time_to_useful_briefing"] == 4.0


def test_top1_wrong_but_top3_contains_truth_is_product_failure():
    topo = observation()
    true = topo.causal_analysis["hypotheses"][0]
    wrong = copy.deepcopy(true)
    wrong.update({"hypothesis_id": "wrong", "rank": 1, "root_event_id": "wrong-event", "root_title": "unrelated config change"})
    true["rank"] = 2
    topo.causal_analysis["hypotheses"] = [wrong, true]
    topo.causal_analysis["top_hypothesis"] = wrong
    status, metrics, _, _ = evaluate(topo=topo)
    assert status == EvaluationStatus.FAIL
    assert metrics["root_cause_top1_correct"] is False
    assert metrics["root_cause_top3_contains_truth"] is True


@pytest.mark.parametrize("affected_id,resolved,correct", [(None, False, False), ("e-other", True, False), ("e-pod", True, True)])
def test_identity_correct_wrong_and_unresolved(affected_id, resolved, correct):
    topo = observation()
    topo.incident["affected_entity_id"] = affected_id
    _, metrics, _, _ = evaluate(topo=topo)
    assert metrics["identity_resolved"] is resolved
    assert metrics["identity_correct"] is correct


def test_required_optional_and_forbidden_path_semantics():
    status, metrics, _, _ = evaluate()
    assert status == EvaluationStatus.PASS
    assert metrics["causal_path_required_hops_present"] is True
    manifest = altered_manifest(
        lambda value: value["expected_path"]["forbidden_hops"].append(
            {"from": "root_deployment", "predicate": "owns", "to": "root_replicaset"}
        )
    )
    status, metrics, _, _ = evaluate(manifest=manifest)
    assert status == EvaluationStatus.FAIL
    assert metrics["causal_path_forbidden_hops_absent"] is False


def test_blast_precision_recall_and_zero_denominator():
    topo = observation()
    topo.blast_radius["affected_entities"] = [{"entity_id": "e-pod"}, {"entity_id": "e-rs"}]
    _, metrics, _, _ = evaluate(topo=topo)
    assert metrics["blast_radius_true_positive_count"] == 2
    assert metrics["blast_radius_false_negative_count"] == 1
    assert metrics["blast_radius_recall"] == pytest.approx(2 / 3)
    empty = altered_manifest(
        lambda value: value["expected_blast_radius"].update(required_affected=[], explicitly_unaffected=[])
    )
    topo.blast_radius["affected_entities"] = []
    _, metrics, _, _ = evaluate(manifest=empty, topo=topo)
    assert metrics["blast_radius_precision"] is None
    assert metrics["blast_radius_recall"] is None


def test_provider_truth_disagreement_is_not_rewritten_from_topo():
    truth = provider()
    original = asdict(truth)
    truth.objects[2] = ProviderObject(
        logical_name="root_pod",
        provider_kind="Pod",
        namespace="topo-eval-a-abcdef",
        name="different-real-pod",
        uid="different-provider-uid",
        observed_at="2026-08-23T10:00:01+00:00",
    )
    status, metrics, _, _ = evaluate(truth=truth)
    assert status == EvaluationStatus.FAIL
    assert metrics["identity_correct"] is False
    assert original["objects"][2]["uid"] == "uid-pod"


def test_ground_truth_is_immutable_across_topo_changes_and_missing_output():
    manifest = ScenarioManifest.load(manifest_path("sentinel-a"))
    expected = manifest.ground_truth_copy()
    topo = observation()
    topo.causal_analysis["hypotheses"][0]["root_title"] = "wrong"
    evaluate(manifest=manifest, topo=topo)
    assert manifest.ground_truth_copy() == expected
    evaluate(manifest=manifest, topo=TopoObservation("eval-1.topo-observation.v1", "2026-08-23T10:00:00+00:00"))
    assert manifest.ground_truth_copy() == expected


def test_provider_failure_is_harness_error_and_missing_identity_is_inconclusive():
    invalid = provider()
    invalid.established = False
    status, _, _, failures = evaluate(truth=invalid)
    assert status == EvaluationStatus.HARNESS_ERROR
    assert failures[0]["category"] == "HARNESS"
    missing = provider()
    missing.objects = [item for item in missing.objects if item.logical_name != "root_deployment"]
    status, _, _, failures = evaluate(truth=missing)
    assert status == EvaluationStatus.INCONCLUSIVE
    assert failures[0]["category"] == "INCONCLUSIVE"


def test_explicit_noncause_support_counts_unsupported_critical_claim():
    manifest_value = ScenarioManifest.load(manifest_path("sentinel-a")).ground_truth_copy()
    manifest_value["non_causes"] = ["root_service"]
    manifest_value["expected_evidence"]["forbidden_support"] = ["root_service"]
    manifest = ScenarioManifest(value=manifest_value)
    topo = observation()
    topo.causal_analysis["hypotheses"][0]["evidence_ledger"]["supporting"].append(
        {"claim_type": "entity_linkage", "entity_ids": ["e-svc"], "relationship_ids": []}
    )
    status, metrics, _, _ = evaluate(manifest=manifest, topo=topo)
    assert status == EvaluationStatus.FAIL
    assert metrics["explicit_non_cause_supported_count"] == 1
    assert metrics["unsupported_critical_claim_count"] == 1


def test_abstention_and_false_certainty_are_bounded_by_manifest():
    def make_abstention(value):
        value["expected_behavior"]["should_abstain"] = True
        value["expected_behavior"]["accepted_top_causes"] = []
        value["expected_path"].update(required_hops=[], optional_hops=[], forbidden_hops=[])
        value["expected_blast_radius"].update(required_affected=[], explicitly_unaffected=[])
        value["expected_evidence"]["expected_missing"] = ["source_change"]

    manifest = altered_manifest(make_abstention)
    topo = observation()
    topo.causal_analysis["hypotheses"] = []
    topo.causal_analysis["top_hypothesis"] = None
    topo.causal_analysis["confidence_semantics"] = semantics("insufficient_evidence")
    topo.blast_radius["affected_entities"] = []
    status, metrics, _, _ = evaluate(manifest=manifest, topo=topo)
    assert status == EvaluationStatus.PASS
    assert metrics["abstention_correct"] is True
    assert metrics["false_certainty"] is False
    certain = observation()
    status, metrics, _, _ = evaluate(manifest=manifest, topo=certain)
    assert status == EvaluationStatus.FAIL
    assert metrics["false_certainty"] is True


def test_tc5_probability_null_invariant_fails_on_probability():
    topo = observation()
    topo.causal_analysis["confidence_semantics"]["calibrated_probability"] = 0.87
    status, metrics, _, _ = evaluate(topo=topo)
    assert status == EvaluationStatus.FAIL
    assert metrics["tc5_probability_null_invariant"] is False


def test_result_artifact_serialization_is_deterministic():
    result = EvaluationResult(
        result_version="eval-1.result.v1",
        harness_version="eval-1.v1",
        run_id="abcdef12",
        scenario_id="sentinel-a",
        topo_git_commit="abcdef0",
        started_at="2026-08-23T10:00:00+00:00",
        completed_at="2026-08-23T10:00:05+00:00",
        environment={"z": 1, "a": 2},
        ground_truth={},
        execution_receipt={},
        provider_verification={},
        topo_observation={},
        metric_results={},
        assertions=[],
        failures=[],
        warnings=[],
        overall_status=EvaluationStatus.PASS,
    )
    assert result.to_json() == result.to_json()
    assert result.to_json().index('"a"') < result.to_json().index('"z"')
    assert json.loads(result.to_json())["overall_status"] == "PASS"


def test_generated_result_directory_is_ignored():
    completed = subprocess.run(
        ["git", "check-ignore", "evaluation/results/disposable.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0


def test_cleanup_namespace_guard_rejects_unsafe_name_and_wrong_label():
    kubectl = Kubectl()
    with pytest.raises(ValueError, match="unsafe namespace"):
        kubectl.cleanup_namespace("production", "abcdef12")

    class WrongLabelKubectl(Kubectl):
        def get(self, *args, **kwargs):
            return {"metadata": {"labels": {EVALUATION_LABEL: "someone-else"}}}

    with pytest.raises(ValueError, match="Refusing cleanup"):
        WrongLabelKubectl().cleanup_namespace("topo-eval-a-abcdef", "abcdef12")


def test_bounded_wait_times_out_without_infinite_polling():
    now = [0.0]

    def clock():
        return now[0]

    def sleep(seconds):
        now[0] += seconds

    with pytest.raises(TimeoutError):
        bounded_wait(lambda: False, bool, timeout_seconds=2, interval_seconds=1, clock=clock, sleeper=sleep)
    assert now[0] == 3


def test_no_product_special_cases():
    forbidden = ("sentinel-a", "sentinel-b", "sentinel-c", "sentinel-d", "topo-eval")
    product_roots = (ROOT / "backend/app", ROOT / "agent/src", ROOT / "frontend", ROOT / "cli/src")
    hits = []
    for product_root in product_roots:
        for path in product_root.rglob("*"):
            if not path.is_file() or any(part in {"node_modules", ".next", "__pycache__"} for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8").lower()
            except (UnicodeDecodeError, OSError):
                continue
            for token in forbidden:
                if token in text:
                    hits.append(f"{path.relative_to(ROOT)}:{token}")
    assert hits == []
