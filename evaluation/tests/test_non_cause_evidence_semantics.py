from __future__ import annotations

import copy
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest

from evaluation.contracts import EvaluationResult, EvaluationStatus, ScenarioManifest
from evaluation.evaluator import IndependentEvaluator
from evaluation.evidence_semantics import (
    NON_CAUSE_EVIDENCE_SEMANTICS_VERSION,
    EvidenceInterpretation,
    interpret_explicit_non_cause_evidence,
)
from evaluation.scenarios import manifest_path
from evaluation.tests.test_contracts import execution_receipt, observation, provider


ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = "e-svc"
AFFECTED = "e-pod"
EVENT = "event-noncause"


def item(
    claim_type: str,
    *,
    entities: list[str] | None = None,
    relationships: list[str] | None = None,
    events: list[str] | None = None,
) -> dict:
    return {
        "evidence_id": f"evidence-{claim_type}",
        "claim_type": claim_type,
        "stance": "supporting",
        "entity_ids": entities or [],
        "relationship_ids": relationships or [],
        "change_event_ids": events or [],
        "source_references": [],
    }


def analysis(
    items: list[dict],
    *,
    relevance_status: str = "no_supported_path",
    path_entities: list[str] | None = None,
    path_relationships: list[str] | None = None,
) -> dict:
    return {
        "hypotheses": [
            {
                "hypothesis_id": "hypothesis-noncause",
                "rank": 2,
                "root_event_id": EVENT,
                "affected_entity_id": AFFECTED,
                "evidence_ledger": {
                    "supporting": copy.deepcopy(items),
                    "contradicting": [],
                    "missing": [],
                },
            }
        ],
        "candidate_relevance_audit": [
            {
                "candidate_event_id": EVENT,
                "candidate_entity_id": CANDIDATE,
                "affected_entity_id": AFFECTED,
                "relevance_status": relevance_status,
                "path_entity_ids": path_entities or [],
                "path_relationship_ids": path_relationships or [],
            }
        ],
    }


def interpret(items: list[dict], **kwargs):
    return interpret_explicit_non_cause_evidence(
        analysis=analysis(items, **kwargs),
        change_events=[
            {"event_id": EVENT, "links": [{"entity_id": CANDIDATE}]}
        ],
        non_cause_entity_ids=[CANDIDATE],
        affected_entity_ids=[AFFECTED],
    )


def evaluation_case(items: list[dict], **kwargs):
    manifest_value = ScenarioManifest.load(
        manifest_path("sentinel-a")
    ).ground_truth_copy()
    manifest_value["non_causes"] = ["root_service"]
    manifest_value["expected_evidence"]["forbidden_support"] = ["root_service"]
    manifest = ScenarioManifest(value=manifest_value)
    topo = observation()
    noncause_analysis = analysis(items, **kwargs)
    topo.causal_analysis["hypotheses"].extend(
        noncause_analysis["hypotheses"]
    )
    topo.causal_analysis["candidate_relevance_audit"] = noncause_analysis[
        "candidate_relevance_audit"
    ]
    topo.change_events.append(
        {"event_id": EVENT, "links": [{"entity_id": CANDIDATE}]}
    )
    return IndependentEvaluator().evaluate(
        manifest,
        provider(),
        topo,
        execution_receipt=execution_receipt(),
    )


def valid_result_payload() -> dict:
    result = EvaluationResult(
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
        execution_receipt={
            "receipt_version": "eval-1.execution.v1",
            "scenario_id": "sentinel-a",
            "run_id": "abcdef12",
            "namespace": "topo-eval-a-abcdef12",
            "started_at": "2026-08-23T10:00:00+00:00",
            "completed_at": "2026-08-23T10:00:05+00:00",
            "actions": [],
        },
        provider_verification=asdict(provider()),
        topo_observation=asdict(observation()),
        metric_results={},
        assertions=[],
        failures=[],
        warnings=[],
        overall_status=EvaluationStatus.PASS,
        evidence_semantics_version=NON_CAUSE_EVIDENCE_SEMANTICS_VERSION,
    )
    return result.as_dict()


def assert_schema_valid(payload: dict, tmp_path: Path) -> None:
    payload_path = tmp_path / "result.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    schema_path = ROOT / "docs/architecture/evaluation/evaluation-result.schema.json"
    command = (
        f"Get-Content -LiteralPath '{payload_path}' -Raw | "
        f"Test-Json -SchemaFile '{schema_path}'"
    )
    completed = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stdout.strip() == "True"


@pytest.mark.parametrize(
    "claim,entities",
    [
        ("source_change", []),
        ("identity_resolution", [CANDIDATE]),
        ("temporal_precedence", []),
    ],
)
def test_candidate_local_claims_are_candidate_facts(claim, entities):
    summary = interpret([item(claim, entities=entities, events=[EVENT])])
    assert summary.candidate_fact_count == 1
    assert summary.false_causal_support_count == 0


def test_runtime_failure_on_affected_entity_is_effect_evidence():
    summary = interpret([item("runtime_failure", entities=[AFFECTED])])
    assert summary.effect_evidence_count == 1
    assert summary.false_causal_support_count == 0


def test_runtime_failure_on_candidate_is_candidate_fact():
    summary = interpret([item("runtime_failure", entities=[CANDIDATE])])
    assert summary.candidate_fact_count == 1
    assert summary.false_causal_support_count == 0


def test_candidate_local_entity_linkage_is_candidate_fact():
    summary = interpret(
        [item("entity_linkage", entities=[CANDIDATE], events=[EVENT])]
    )
    assert summary.candidate_fact_count == 1
    assert summary.false_causal_support_count == 0


def test_cross_entity_linkage_is_causal_connectivity():
    summary = interpret(
        [
            item(
                "entity_linkage",
                entities=[CANDIDATE, AFFECTED],
                events=[EVENT],
            )
        ]
    )
    assert summary.false_causal_support_count == 1
    assert summary.interpretations[0].interpretation == (
        EvidenceInterpretation.CAUSAL_CONNECTIVITY
    )


def test_event_to_affected_linkage_is_causal_connectivity():
    summary = interpret(
        [item("entity_linkage", entities=[AFFECTED], events=[EVENT])]
    )
    assert summary.false_causal_support_count == 1


def test_topology_path_candidate_to_affected_is_causal_connectivity():
    summary = interpret(
        [
            item(
                "topology_path",
                entities=[CANDIDATE, AFFECTED],
                relationships=["relationship-path"],
            )
        ]
    )
    assert summary.false_causal_support_count == 1


def test_relationship_provenance_on_selected_path_is_causal_connectivity():
    summary = interpret(
        [
            item(
                "relationship_provenance",
                entities=[CANDIDATE],
                relationships=["relationship-path"],
            )
        ],
        relevance_status="semantic_path",
        path_entities=[CANDIDATE, AFFECTED],
        path_relationships=["relationship-path"],
    )
    assert summary.false_causal_support_count == 1


def test_candidate_local_relationship_provenance_is_not_causal():
    summary = interpret(
        [item("relationship_provenance", entities=[CANDIDATE])]
    )
    assert summary.candidate_fact_count == 1
    assert summary.false_causal_support_count == 0


def test_unscoped_relationship_provenance_is_ambiguous_not_causal():
    summary = interpret(
        [item("relationship_provenance", relationships=["unselected"])]
    )
    assert summary.ambiguous_support_count == 1
    assert summary.false_causal_support_count == 0


def test_artifact_lineage_bridging_candidate_and_effect_is_causal():
    summary = interpret(
        [item("artifact_provenance", entities=[CANDIDATE, AFFECTED])]
    )
    assert summary.lineage_evidence_count == 1
    assert summary.false_causal_support_count == 1


def test_candidate_local_artifact_lineage_is_not_causal():
    summary = interpret(
        [item("artifact_provenance", entities=[CANDIDATE])]
    )
    assert summary.lineage_evidence_count == 1
    assert summary.false_causal_support_count == 0


def test_event_lineage_feeding_selected_path_is_causal():
    summary = interpret(
        [item("event_lineage", events=[EVENT])],
        relevance_status="semantic_path",
        path_entities=[CANDIDATE, AFFECTED],
        path_relationships=["relationship-path"],
    )
    assert summary.lineage_evidence_count == 1
    assert summary.false_causal_support_count == 1


def test_candidate_local_event_lineage_is_not_causal():
    summary = interpret([item("event_lineage", events=[EVENT])])
    assert summary.lineage_evidence_count == 1
    assert summary.false_causal_support_count == 0


def test_unscoped_event_lineage_is_ambiguous_not_causal():
    summary = interpret([item("event_lineage", events=["another-event"])])
    assert summary.ambiguous_support_count == 1
    assert summary.false_causal_support_count == 0


def test_required_true_local_facts_fixture_passes_explicit_noncause_assertion():
    facts = [
        item("source_change", events=[EVENT]),
        item("identity_resolution", entities=[CANDIDATE], events=[EVENT]),
        item("temporal_precedence", events=[EVENT]),
        item("entity_linkage", entities=[CANDIDATE], events=[EVENT]),
        item("runtime_failure", entities=[AFFECTED]),
    ]
    status, metrics, assertions, failures = evaluation_case(facts)
    assert status == EvaluationStatus.PASS
    assert metrics["explicit_non_cause_supporting_fact_count"] == 4
    assert metrics["explicit_non_cause_effect_evidence_count"] == 1
    assert metrics["explicit_non_cause_false_causal_support_count"] == 0
    assert next(a for a in assertions if a["name"] == "noncause_support")[
        "passed"
    ]
    assert not failures


def test_effect_fact_only_passes_explicit_noncause_assertion():
    status, metrics, _, _ = evaluation_case(
        [item("runtime_failure", entities=[AFFECTED])]
    )
    assert status == EvaluationStatus.PASS
    assert metrics["explicit_non_cause_false_causal_support_count"] == 0


def test_required_false_causal_path_fixture_fails():
    facts = [
        item("source_change", events=[EVENT]),
        item("identity_resolution", entities=[CANDIDATE], events=[EVENT]),
        item("temporal_precedence", events=[EVENT]),
        item("entity_linkage", entities=[CANDIDATE], events=[EVENT]),
        item("runtime_failure", entities=[AFFECTED]),
        item(
            "topology_path",
            entities=[CANDIDATE, AFFECTED],
            relationships=["relationship-path"],
        ),
        item(
            "relationship_provenance",
            entities=[CANDIDATE, AFFECTED],
            relationships=["relationship-path"],
        ),
    ]
    status, metrics, assertions, _ = evaluation_case(
        facts,
        relevance_status="semantic_path",
        path_entities=[CANDIDATE, AFFECTED],
        path_relationships=["relationship-path"],
    )
    assert status == EvaluationStatus.FAIL
    assert metrics["explicit_non_cause_false_causal_support_count"] == 2
    assert not next(a for a in assertions if a["name"] == "noncause_support")[
        "passed"
    ]


def test_causal_relationship_provenance_drives_failure():
    status, metrics, _, _ = evaluation_case(
        [
            item(
                "relationship_provenance",
                entities=[CANDIDATE],
                relationships=["relationship-path"],
            )
        ],
        relevance_status="semantic_path",
        path_entities=[CANDIDATE, AFFECTED],
        path_relationships=["relationship-path"],
    )
    assert status == EvaluationStatus.FAIL
    assert metrics["explicit_non_cause_false_causal_support_count"] == 1


def test_ambiguous_material_evidence_makes_scenario_inconclusive():
    status, metrics, assertions, failures = evaluation_case(
        [item("future_claim", entities=[CANDIDATE])]
    )
    assert status == EvaluationStatus.INCONCLUSIVE
    assert metrics["explicit_non_cause_ambiguous_support_count"] == 1
    assert next(
        a for a in assertions if a["name"] == "noncause_evidence_classifiable"
    )["passed"] is False
    assert any(failure["category"] == "INCONCLUSIVE" for failure in failures)


def test_legacy_raw_count_is_preserved_but_does_not_drive_failure():
    status, metrics, _, _ = evaluation_case(
        [item("identity_resolution", entities=[CANDIDATE], events=[EVENT])]
    )
    assert status == EvaluationStatus.PASS
    assert metrics["explicit_non_cause_supported_count"] == 1
    assert metrics["unsupported_critical_claim_count"] == 1
    assert metrics["explicit_non_cause_false_causal_support_count"] == 0


def test_false_causal_metric_not_raw_metric_drives_assertion():
    status, metrics, assertions, _ = evaluation_case(
        [item("entity_linkage", entities=[CANDIDATE], events=[EVENT])]
    )
    assert metrics["explicit_non_cause_supported_count"] == 1
    assert metrics["explicit_non_cause_false_causal_support_count"] == 0
    assert status == EvaluationStatus.PASS
    assert next(a for a in assertions if a["name"] == "noncause_support")[
        "passed"
    ]


def test_interpretation_is_deterministic_across_input_order():
    values = [
        item("identity_resolution", entities=[CANDIDATE]),
        item("runtime_failure", entities=[AFFECTED]),
        item("source_change", events=[EVENT]),
    ]
    left = interpret(values).metrics()
    right = interpret(list(reversed(values))).metrics()
    assert left == right


def test_sut_output_cannot_mutate_manifest_ground_truth():
    manifest = ScenarioManifest.load(manifest_path("sentinel-a"))
    before = manifest.ground_truth_copy()
    evaluation_case([item("source_change", events=[EVENT])])
    assert manifest.ground_truth_copy() == before


def test_manifest_truth_is_independent_of_interpreter_inputs():
    manifest = ScenarioManifest.load(manifest_path("sentinel-b"))
    before = manifest.ground_truth_copy()
    interpret([item("topology_path", entities=[CANDIDATE, AFFECTED])])
    assert manifest.ground_truth_copy() == before


def test_evaluator_evidence_semantics_has_no_product_reasoning_imports():
    source = (ROOT / "evaluation/evidence_semantics.py").read_text(
        encoding="utf-8"
    )
    forbidden = (
        "backend.app.services.causal_rca",
        "backend.app.services.causal_evidence_ledger",
        "causal_relevance_policy",
        "causal_candidate_policy",
    )
    assert not any(value in source for value in forbidden)


def test_result_serialization_persists_semantics_version_deterministically():
    result = EvaluationResult(
        result_version="eval-1.result.v1",
        harness_version="eval-1.v1",
        run_id="abcdef12",
        scenario_id="sentinel-a",
        topo_git_commit="abcdef0",
        started_at="2026-08-23T10:00:00+00:00",
        completed_at="2026-08-23T10:00:05+00:00",
        environment={},
        ground_truth={},
        execution_receipt={},
        provider_verification={},
        topo_observation={},
        metric_results={},
        assertions=[],
        failures=[],
        warnings=[],
        overall_status=EvaluationStatus.PASS,
        evidence_semantics_version=NON_CAUSE_EVIDENCE_SEMANTICS_VERSION,
    )
    assert result.to_json() == result.to_json()
    assert json.loads(result.to_json())["evidence_semantics_version"] == (
        NON_CAUSE_EVIDENCE_SEMANTICS_VERSION
    )


def test_old_eval_result_without_semantics_version_still_validates(tmp_path):
    payload = valid_result_payload()
    payload.pop("evidence_semantics_version", None)
    assert_schema_valid(payload, tmp_path)


def test_new_result_schema_accepts_evidence_semantics_version(tmp_path):
    payload = valid_result_payload()
    payload["evidence_semantics_version"] = (
        NON_CAUSE_EVIDENCE_SEMANTICS_VERSION
    )
    assert_schema_valid(payload, tmp_path)


def test_classifier_contains_no_scenario_specific_special_cases():
    source = (ROOT / "evaluation/evidence_semantics.py").read_text(
        encoding="utf-8"
    ).lower()
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


def test_product_paths_have_no_worktree_diff():
    completed = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--",
            "backend/app",
            "backend/tests",
            "agent/src",
            "frontend",
            "cli/src",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert not completed.stdout.strip()
