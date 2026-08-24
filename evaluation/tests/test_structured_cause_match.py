from __future__ import annotations

import copy
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from evaluation.causal_forensics import first_divergence
from evaluation.cause_fingerprint import (
    CAUSE_FINGERPRINT_VERSION,
    CAUSE_MATCH_VERSION,
    CauseFingerprint,
    best_cause_match,
    compare_causes,
    expected_cause_fingerprint,
    expected_cause_fingerprints,
    fingerprints_from_event,
    value_hash,
)
from evaluation.contracts import (
    EvaluationResult,
    EvaluationStatus,
    ScenarioManifest,
    deterministic_json,
)
from evaluation.evaluator import (
    IndependentEvaluator,
    blast_false_positive_path_attribution,
)
from evaluation.evidence_semantics import NON_CAUSE_EVIDENCE_SEMANTICS_VERSION
from evaluation.product_diff_guard import assert_product_diff_scoped_to_h3_r1
from evaluation.scenarios import manifest_path
from evaluation.structured_cause_match import (
    assess_hypothesis_cause,
    evaluate_structured_root_causes,
)
from evaluation.tests.test_blast_baseline import (
    _blast_path_observation,
)
from evaluation.tests.test_contracts import (
    execution_receipt,
    observation,
    provider,
)
ROOT = Path(__file__).resolve().parents[2]
GOOD = "nginx:1.27-alpine"
BAD = "registry.invalid/eval/image:bad"
UID = "uid-dep"
ENTITY = f"k8s:cluster:deployment:{UID}"


def fingerprint(**overrides) -> CauseFingerprint:
    values = {
        "provider": "kubernetes",
        "entity_kind": "Deployment",
        "canonical_entity_id": ENTITY,
        "provider_native_entity_id": UID,
        "mutation_family": "field_change",
        "changed_field": "properties.images",
        "before_value_ref": GOOD,
        "before_value_hash": value_hash(GOOD),
        "after_value_ref": BAD,
        "after_value_hash": value_hash(BAD),
        "evidence_source": "test",
        "fingerprint_completeness": "complete",
    }
    values.update(overrides)
    return CauseFingerprint(**values)


def event(
    *,
    event_id: str = "event-true",
    field: str = "properties.images",
    before=GOOD,
    after=BAD,
    title: str = "KubernetesDeployment updated",
    entity_ids: list[str] | None = None,
) -> dict:
    ids = entity_ids or [ENTITY]
    return {
        "event_id": event_id,
        "origin_change_id": f"change-{event_id}",
        "title": title,
        "kind": "scaling",
        "metadata": {
            "change_type": "entity_updated",
            "entity_refs": [
                {"entity_id": entity_id, "kind": "KubernetesDeployment"}
                for entity_id in ids
            ],
            "changed_fields": {field: {"before": [before], "after": [after]}},
        },
    }


def hypothesis(
    *,
    rank: int = 1,
    event_id: str = "event-true",
    title: str = "KubernetesDeployment updated",
) -> dict:
    return {
        "hypothesis_id": f"hypothesis-{rank}",
        "rank": rank,
        "root_event_id": event_id,
        "root_title": title,
    }


def evaluate(topo=None, *, receipt=None, manifest=None):
    details: dict = {}
    result = IndependentEvaluator().evaluate(
        manifest or ScenarioManifest.load(manifest_path("sentinel-a")),
        provider(),
        topo or observation(),
        execution_receipt=receipt or execution_receipt(),
        cause_output=details,
    )
    return (*result, details)


def test_same_provider_native_entity_field_and_values_is_exact():
    assert compare_causes(fingerprint(), fingerprint()).status == "exact"


def test_same_entity_field_and_compatible_hashes_is_exact_without_value_refs():
    actual = fingerprint(before_value_ref=None, after_value_ref=None)
    assert compare_causes(fingerprint(), actual).status == "exact"


def test_same_entity_field_with_different_after_value_is_value_mismatch():
    actual = fingerprint(
        after_value_ref="different",
        after_value_hash=value_hash("different"),
    )
    assert compare_causes(fingerprint(), actual).status == "value_mismatch"


def test_same_entity_with_different_known_field_is_mutation_mismatch():
    actual = fingerprint(changed_field="properties.replicas")
    assert compare_causes(fingerprint(), actual).status == (
        "entity_match_mutation_mismatch"
    )


def test_same_mutation_with_different_provider_native_entity_is_entity_mismatch():
    actual = fingerprint(provider_native_entity_id="different-uid")
    assert compare_causes(fingerprint(), actual).status == (
        "mutation_match_entity_mismatch"
    )


def test_ca0_generic_title_with_exact_structure_passes_top1():
    topo = observation()
    topo.causal_analysis["top_hypothesis"]["root_title"] = (
        "KubernetesDeployment updated"
    )
    topo.causal_analysis["hypotheses"][0]["root_title"] = (
        "KubernetesDeployment updated"
    )
    topo.change_events[0]["title"] = "KubernetesDeployment updated"
    status, metrics, _, failures, details = evaluate(topo)
    assert status == EvaluationStatus.PASS
    assert not failures
    assert metrics["root_cause_top1_correct"] is True
    assert details["top1_cause_match"]["status"] == "exact"


def test_perfect_title_with_structured_value_mismatch_fails_top1():
    topo = observation()
    topo.change_events[0] = event(
        after="registry.invalid/eval/image:different",
        title="Deployment configuration changed",
    )
    status, metrics, _, _, details = evaluate(topo)
    assert status == EvaluationStatus.FAIL
    assert metrics["root_cause_title_match"] is True
    assert metrics["root_cause_top1_correct"] is False
    assert details["top1_cause_match"]["status"] == "value_mismatch"


def test_title_never_overrides_structured_mutation_mismatch():
    topo = observation()
    topo.change_events[0] = event(
        field="properties.replicas",
        before=2,
        after=3,
        title="Deployment configuration changed",
    )
    _, metrics, _, _, details = evaluate(topo)
    assert metrics["root_cause_title_match"] is True
    assert metrics["root_cause_top1_correct"] is False
    assert details["top1_cause_match"]["status"] == (
        "entity_match_mutation_mismatch"
    )


def test_top3_succeeds_when_rank2_structurally_matches_truth():
    topo = observation()
    true = topo.causal_analysis["hypotheses"][0]
    true["rank"] = 2
    wrong = copy.deepcopy(true)
    wrong.update(
        {"rank": 1, "hypothesis_id": "wrong", "root_event_id": "wrong-event"}
    )
    topo.causal_analysis["hypotheses"] = [wrong, true]
    topo.causal_analysis["top_hypothesis"] = wrong
    topo.change_events.append(
        event(event_id="wrong-event", field="properties.replicas", before=2, after=3)
    )
    status, metrics, _, _, details = evaluate(topo)
    assert status == EvaluationStatus.FAIL
    assert metrics["root_cause_top1_correct"] is False
    assert metrics["root_cause_top3_contains_truth"] is True
    assert details["top3_cause_matches"][1]["correct"] is True


def test_top3_fails_when_all_three_structurally_differ():
    topo = observation()
    hypotheses = [
        hypothesis(rank=rank, event_id=f"wrong-{rank}") for rank in (1, 2, 3)
    ]
    topo.causal_analysis["hypotheses"] = hypotheses
    topo.causal_analysis["top_hypothesis"] = hypotheses[0]
    topo.change_events = [
        event(
            event_id=f"wrong-{rank}",
            field="properties.replicas",
            before=rank,
            after=rank + 1,
        )
        for rank in (1, 2, 3)
    ]
    _, metrics, _, _, details = evaluate(topo)
    assert metrics["root_cause_top3_contains_truth"] is False
    assert all(item["correct"] is False for item in details["top3_cause_matches"])


def test_insufficient_structure_makes_required_cause_inconclusive():
    topo = observation()
    topo.change_events[0] = {
        "event_id": "event-true",
        "title": "Deployment configuration changed",
        "metadata": {},
    }
    status, metrics, _, failures, details = evaluate(topo)
    assert status == EvaluationStatus.INCONCLUSIVE
    assert metrics["root_cause_top1_correct"] is None
    assert details["cause_match_status"] == "inconclusive"
    assert any(item["category"] == "INCONCLUSIVE" for item in failures)


def test_ambiguous_entity_identity_is_inconclusive():
    expected = fingerprint(
        canonical_entity_id=None,
        provider_native_entity_id=None,
        fingerprint_completeness="partial",
    )
    result = assess_hypothesis_cause(
        [expected],
        hypothesis(),
        [
            event(
                entity_ids=[
                    "k8s:cluster:deployment:uid-one",
                    "k8s:cluster:deployment:uid-two",
                ]
            )
        ],
        alternatives_explicit=False,
    )
    assert result["status"] == "ambiguous"
    assert result["correct"] is None


def test_explicit_alternative_expected_cause_can_satisfy_outcome():
    manifest = {
        "causal_intent": {
            "root_entity": "primary",
            "root_change": "deployment_image_change",
        },
        "expected_behavior": {
            "should_abstain": False,
            "accepted_top_causes": [
                {"entity_alias": "primary", "title_contains_all": []},
                {"entity_alias": "alternative", "title_contains_all": []},
            ],
        },
    }
    receipt = {
        "actions": [
            {
                "action_type": "causal_bad_image",
                "logical_target": alias,
                "provider_uid": uid,
                "before": {"image": GOOD},
                "after": {"image": BAD},
            }
            for alias, uid in (("primary", "uid-one"), ("alternative", "uid-two"))
        ]
    }
    provider_truth = {
        "objects": [
            {
                "logical_name": alias,
                "provider_kind": "Deployment",
                "uid": uid,
            }
            for alias, uid in (("primary", "uid-one"), ("alternative", "uid-two"))
        ]
    }
    actual_event = event(entity_ids=["k8s:cluster:deployment:uid-two"])
    result = evaluate_structured_root_causes(
        manifest,
        receipt,
        provider_truth,
        {
            "causal_analysis": {"hypotheses": [hypothesis()]},
            "change_events": [actual_event],
        },
    )
    assert len(result["expected_cause_fingerprints"]) == 2
    assert result["root_cause_top1_correct"] is True


def test_provider_and_topo_image_fields_map_deterministically():
    expected = fingerprint(changed_field="spec.template.spec.containers[0].image")
    assert compare_causes(expected, fingerprint()).status == "exact"


def test_unknown_cross_representation_field_is_insufficient_not_fuzzy():
    expected = fingerprint(changed_field="spec.template.spec.containers[0].image")
    actual = fingerprint(changed_field="unknown.pretty.image.description")
    assert compare_causes(expected, actual).status == "insufficient_structure"


def test_image_digest_equality_is_exact():
    digest = "registry.example/app@sha256:" + "a" * 64
    left = fingerprint(
        before_value_ref=digest,
        before_value_hash=value_hash(digest),
        after_value_ref=digest,
        after_value_hash=value_hash(digest),
    )
    right = copy.deepcopy(left)
    assert compare_causes(left, right).status == "exact"


def test_image_reference_and_tag_hashing_is_deterministic():
    assert value_hash("registry.example/app:v1") == value_hash(
        "registry.example/app:v1"
    )
    assert value_hash("registry.example/app:v1") != value_hash(
        "registry.example/app:v2"
    )


def test_canonical_json_hashing_ignores_object_key_order():
    assert value_hash({"b": 2, "a": 1}) == value_hash({"a": 1, "b": 2})


def test_root_event_id_resolves_serialized_actual_cause():
    result = assess_hypothesis_cause(
        [fingerprint()], hypothesis(), [event()], alternatives_explicit=False
    )
    assert result["root_event_id"] == "event-true"
    assert result["actual_event_resolution"] == "topo_observation.change_events"
    assert result["correct"] is True


def test_generic_root_title_does_not_change_structured_result():
    generic = assess_hypothesis_cause(
        [fingerprint()], hypothesis(title="KubernetesDeployment updated"), [event()], alternatives_explicit=False
    )
    specific = assess_hypothesis_cause(
        [fingerprint()], hypothesis(title="Deployment configuration changed"), [event()], alternatives_explicit=False
    )
    assert generic["status"] == specific["status"] == "exact"


def test_presentation_warning_coexists_with_structured_pass():
    topo = observation()
    topo.causal_analysis["hypotheses"][0]["root_title"] = (
        "KubernetesDeployment updated"
    )
    topo.causal_analysis["top_hypothesis"]["root_title"] = (
        "KubernetesDeployment updated"
    )
    topo.change_events[0]["title"] = "KubernetesDeployment updated"
    status, metrics, _, _, details = evaluate(topo)
    assert status == EvaluationStatus.PASS
    assert metrics["cause_presentation_generic"] is True
    assert details["diagnostics"]["presentation_warning"]


def test_authoritative_matcher_contains_no_fuzzy_title_tokens():
    source = (ROOT / "evaluation/structured_cause_match.py").read_text(
        encoding="utf-8"
    ).lower()
    assert "title_contains_all" not in source
    assert "levenshtein" not in source


def test_authoritative_matcher_has_no_llm_dependency():
    source = (ROOT / "evaluation/structured_cause_match.py").read_text(
        encoding="utf-8"
    ).lower()
    assert "llm" not in source
    assert "openai" not in source


def test_authoritative_matcher_has_no_embedding_dependency():
    source = (ROOT / "evaluation/structured_cause_match.py").read_text(
        encoding="utf-8"
    ).lower()
    assert "embedding" not in source


def test_expected_fingerprint_does_not_accept_topo_output():
    manifest = ScenarioManifest.load(manifest_path("sentinel-a")).ground_truth_copy()
    expected = expected_cause_fingerprint(
        manifest, execution_receipt(), asdict(provider())
    )
    topo = asdict(observation())
    topo["change_events"][0]["metadata"]["changed_fields"] = {
        "properties.replicas": {"before": 2, "after": 3}
    }
    assert expected.changed_field == "spec.template.spec.containers[0].image"
    assert expected.after_value_hash == value_hash(BAD)


def test_expected_fingerprint_prefers_provider_observed_after_state():
    manifest = ScenarioManifest.load(manifest_path("sentinel-a")).ground_truth_copy()
    receipt = execution_receipt()
    receipt["actions"][0]["after"]["image"] = "receipt-only-value"
    expected = expected_cause_fingerprint(manifest, receipt, asdict(provider()))
    assert expected.after_value_ref == BAD
    assert expected.after_value_hash == value_hash(BAD)


def test_evaluation_cannot_mutate_manifest_truth():
    manifest = ScenarioManifest.load(manifest_path("sentinel-a"))
    before = manifest.ground_truth_copy()
    evaluate(manifest=manifest)
    assert manifest.ground_truth_copy() == before


def test_ca0_forensic_best_match_behavior_remains_exact():
    actuals = fingerprints_from_event(event(), evidence_source="forensic")
    _, match = best_cause_match(fingerprint(), actuals)
    assert match.status == "exact"


def test_first_divergence_tooling_still_returns_earliest_layer():
    result = first_divergence(
        [
            {"layer": "intent", "truth_preserved": True},
            {
                "layer": "evaluator",
                "truth_preserved": False,
                "classification": "EVALUATOR_CAUSE_MATCH_DEFECT",
            },
        ]
    )
    assert result["classification"] == "EVALUATOR_CAUSE_MATCH_DEFECT"


def test_non_cause_evidence_version_is_unchanged():
    assert NON_CAUSE_EVIDENCE_SEMANTICS_VERSION == "non-cause-evidence-v1"


def test_blast_path_attribution_semantics_remain_directional():
    manifest = ScenarioManifest.load(manifest_path("blast-01"))
    aliases = {
        "failed_pod": ["failed"],
        "scenario_namespace": ["namespace"],
        "healthy_deployment": ["healthy-deployment"],
    }
    paths = blast_false_positive_path_attribution(
        manifest, _blast_path_observation(), aliases
    )
    healthy = next(
        item for item in paths if item["false_positive_alias"] == "healthy_deployment"
    )
    assert [hop["traversal_direction"] for hop in healthy["hops"]] == [
        "reverse",
        "forward",
    ]


def test_result_serialization_with_structured_metadata_is_deterministic():
    _, metrics, assertions, failures, details = evaluate()
    result = EvaluationResult(
        result_version="eval-1.result.v1",
        harness_version="eval-1.v1",
        run_id="abcdef12",
        scenario_id="sentinel-a",
        topo_git_commit="abcdef0",
        started_at="2026-08-23T10:00:00+00:00",
        completed_at="2026-08-23T10:00:05+00:00",
        environment={},
        ground_truth=ScenarioManifest.load(manifest_path("sentinel-a")).ground_truth_copy(),
        execution_receipt=execution_receipt(),
        provider_verification=asdict(provider()),
        topo_observation=asdict(observation()),
        metric_results=metrics,
        assertions=assertions,
        failures=failures,
        warnings=[],
        overall_status=EvaluationStatus.PASS,
        evidence_semantics_version=NON_CAUSE_EVIDENCE_SEMANTICS_VERSION,
        cause_fingerprint_version=CAUSE_FINGERPRINT_VERSION,
        cause_match_version=CAUSE_MATCH_VERSION,
        cause_match_status=details["cause_match_status"],
        expected_cause_fingerprints=details["expected_cause_fingerprints"],
        top1_actual_cause_fingerprint=details["top1_actual_cause_fingerprint"],
        top1_cause_match=details["top1_cause_match"],
        top3_cause_matches=details["top3_cause_matches"],
        cause_match_diagnostics=details["diagnostics"],
    )
    assert result.to_json() == result.to_json()
    assert json.loads(result.to_json())["cause_match_version"] == CAUSE_MATCH_VERSION


def test_current_result_validates_against_schema(tmp_path):
    _, metrics, assertions, failures, details = evaluate()
    payload = EvaluationResult(
        result_version="eval-1.result.v1",
        harness_version="eval-1.v1",
        run_id="abcdef12",
        scenario_id="sentinel-a",
        topo_git_commit="abcdef0",
        started_at="2026-08-23T10:00:00+00:00",
        completed_at="2026-08-23T10:00:05+00:00",
        environment={},
        ground_truth=ScenarioManifest.load(manifest_path("sentinel-a")).ground_truth_copy(),
        execution_receipt=execution_receipt(),
        provider_verification=asdict(provider()),
        topo_observation=asdict(observation()),
        metric_results=metrics,
        assertions=assertions,
        failures=failures,
        warnings=[],
        overall_status=EvaluationStatus.PASS,
        evidence_semantics_version=NON_CAUSE_EVIDENCE_SEMANTICS_VERSION,
        cause_fingerprint_version=CAUSE_FINGERPRINT_VERSION,
        cause_match_version=CAUSE_MATCH_VERSION,
        cause_match_status=details["cause_match_status"],
        expected_cause_fingerprints=details["expected_cause_fingerprints"],
        top1_actual_cause_fingerprint=details["top1_actual_cause_fingerprint"],
        top1_cause_match=details["top1_cause_match"],
        top3_cause_matches=details["top3_cause_matches"],
        cause_match_diagnostics=details["diagnostics"],
    ).as_dict()
    payload_path = tmp_path / "result.json"
    payload_path.write_text(deterministic_json(payload), encoding="utf-8")
    schema = ROOT / "docs/architecture/evaluation/evaluation-result.schema.json"
    command = (
        f"Get-Content -LiteralPath '{payload_path}' -Raw | "
        f"Test-Json -SchemaFile '{schema}'"
    )
    completed = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stdout.strip() == "True"


def test_old_result_without_structured_fields_remains_schema_compatible(tmp_path):
    _, metrics, assertions, failures, details = evaluate()
    payload = EvaluationResult(
        result_version="eval-1.result.v1",
        harness_version="eval-1.v1",
        run_id="abcdef12",
        scenario_id="sentinel-a",
        topo_git_commit="abcdef0",
        started_at="2026-08-23T10:00:00+00:00",
        completed_at="2026-08-23T10:00:05+00:00",
        environment={},
        ground_truth=ScenarioManifest.load(
            manifest_path("sentinel-a")
        ).ground_truth_copy(),
        execution_receipt=execution_receipt(),
        provider_verification=asdict(provider()),
        topo_observation=asdict(observation()),
        metric_results=metrics,
        assertions=assertions,
        failures=failures,
        warnings=[],
        overall_status=EvaluationStatus.PASS,
        evidence_semantics_version=NON_CAUSE_EVIDENCE_SEMANTICS_VERSION,
        cause_fingerprint_version=CAUSE_FINGERPRINT_VERSION,
        cause_match_version=CAUSE_MATCH_VERSION,
        cause_match_status=details["cause_match_status"],
        expected_cause_fingerprints=details["expected_cause_fingerprints"],
        top1_actual_cause_fingerprint=details["top1_actual_cause_fingerprint"],
        top1_cause_match=details["top1_cause_match"],
        top3_cause_matches=details["top3_cause_matches"],
        cause_match_diagnostics=details["diagnostics"],
    ).as_dict()
    for field in (
        "cause_fingerprint_version",
        "cause_match_version",
        "cause_match_status",
        "expected_cause_fingerprints",
        "top1_actual_cause_fingerprint",
        "top1_cause_match",
        "top3_cause_matches",
        "cause_match_diagnostics",
    ):
        payload.pop(field)
    schema = ROOT / "docs/architecture/evaluation/evaluation-result.schema.json"
    payload_path = tmp_path / "old.json"
    payload_path.write_text(deterministic_json(payload), encoding="utf-8")
    command = (
        f"Get-Content -LiteralPath '{payload_path}' -Raw | "
        f"Test-Json -SchemaFile '{schema}'"
    )
    completed = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stdout.strip() == "True"


def test_evaluator_imports_no_product_reasoning_implementation():
    source = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "evaluation/evaluator.py",
            "evaluation/structured_cause_match.py",
            "evaluation/cause_fingerprint.py",
        )
    )
    forbidden = (
        "app.services.causal_rca",
        "causal_candidate_policy",
        "causal_relevance_policy",
        "blast_impact_policy",
        "causal_evidence_ledger",
    )
    assert not any(value in source for value in forbidden)


def test_no_scenario_specific_structured_match_override():
    source = "\n".join(
        (ROOT / path).read_text(encoding="utf-8").lower()
        for path in (
            "evaluation/structured_cause_match.py",
            "evaluation/cause_fingerprint.py",
        )
    )
    assert all(
        scenario not in source
        for scenario in (
            "sentinel-a",
            "sentinel-b",
            "sentinel-c",
            "sentinel-d",
            "blast-01",
            "blast-02",
            "blast-03",
        )
    )


def test_product_diff_is_scoped_to_h3_r1_after_eval_1_2():
    assert_product_diff_scoped_to_h3_r1(ROOT)


def test_all_manifest_hashes_remain_frozen():
    expected_hashes = {
        "sentinel-a": "599ba19827d5097fded3f52264cad8dd35abb839",
        "sentinel-b": "f404607eaca904baac362edb2365fa53652565fe",
        "sentinel-c": "9bb3c201b190708224770a30ec9c23939623f683",
        "sentinel-d": "e7e2a8f4e2cde066bee209191ec27304a41193f7",
        "blast-01": "2f292f5ee1c116d2c2c832bc2165a61bc13dedc5",
        "blast-02": "695d0feda176f26c7e601a57060f4ad0d29310a9",
        "blast-03": "0f9974a4a5f4a08d6b01d2e02be319698175f6c1",
    }
    for scenario, expected_hash in expected_hashes.items():
        completed = subprocess.run(
            ["git", "hash-object", str(manifest_path(scenario))],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        assert completed.stdout.strip() == expected_hash
