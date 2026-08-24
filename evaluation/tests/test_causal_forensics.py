from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

from evaluation.causal_forensics import (
    FIRST_DIVERGENCE_CLASSIFICATIONS,
    VERSION_METADATA,
    build_forensic_bundle,
    capture_persistence_state,
    first_divergence,
    validate_forensic_bundle,
)
from evaluation.cause_fingerprint import (
    CAUSE_FINGERPRINT_VERSION,
    CAUSE_MATCH_VERSION,
    CauseFingerprint,
    compare_causes,
    expected_cause_fingerprint,
    fingerprints_from_change,
    fingerprints_from_event,
    value_hash,
)
from evaluation.contracts import ScenarioManifest, deterministic_json
from evaluation.product_diff_guard import assert_h3_r1_historical_product_scope
from evaluation.scenarios import manifest_path


ROOT = Path(__file__).resolve().parents[2]
GOOD_IMAGE = "nginx:1.27-alpine"
BAD_IMAGE = "registry.invalid/eval/image:run"
DEPLOYMENT_UID = "deployment-uid"
DEPLOYMENT_ID = f"k8s:cluster:deployment:{DEPLOYMENT_UID}"


def truth_inputs() -> tuple[dict, dict, dict]:
    manifest = {
        "scenario_version": "eval-1.scenario.v1",
        "causal_intent": {
            "root_entity": "root_deployment",
            "root_change": "root_deployment_image_change",
            "failure_mode": "ImagePullBackOff",
        },
        "expected_blast_radius": {"impact_truth": {}},
    }
    receipt = {
        "actions": [
            {
                "action_id": "run:1",
                "action_type": "causal_bad_image",
                "logical_target": "root_deployment",
                "provider_uid": DEPLOYMENT_UID,
                "before": {"generation": 2, "image": GOOD_IMAGE},
                "after": {"generation": 3, "image": BAD_IMAGE},
            }
        ]
    }
    provider = {
        "established": True,
        "objects": [
            {
                "logical_name": "root_deployment",
                "provider_kind": "Deployment",
                "uid": DEPLOYMENT_UID,
                "spec": {"images": [BAD_IMAGE]},
                "status": {"observedGeneration": 3},
            }
        ],
        "assertions": [{"passed": True, "reason": "ImagePullBackOff"}],
    }
    return manifest, receipt, provider


def structured_change() -> dict:
    return {
        "change_id": "change-1",
        "change_type": "entity_updated",
        "category": "scaling",
        "source_system": "snapshot-diff",
        "entity_id": DEPLOYMENT_ID,
        "entity_kind": "KubernetesDeployment",
        "changed_fields": {
            "properties.images": {
                "before": [GOOD_IMAGE],
                "after": [BAD_IMAGE],
            }
        },
        "before": {
            "kind": "KubernetesDeployment",
            "properties": {"uid": DEPLOYMENT_UID, "images": [GOOD_IMAGE]},
        },
        "after": {
            "kind": "KubernetesDeployment",
            "properties": {"uid": DEPLOYMENT_UID, "images": [BAD_IMAGE]},
        },
        "temporal": {"temporal_version": "tc3.v1"},
    }


def structured_event() -> dict:
    change = structured_change()
    return {
        "event_id": "event-1",
        "origin_change_id": "change-1",
        "title": "KubernetesDeployment updated",
        "kind": "scaling",
        "source": "topology_diff",
        "temporal": {"temporal_version": "tc3.v1"},
        "metadata": {
            **change,
            "entity_refs": [
                {
                    "entity_id": DEPLOYMENT_ID,
                    "kind": "KubernetesDeployment",
                }
            ],
        },
    }


def complete_result() -> tuple[dict, dict]:
    manifest, receipt, provider = truth_inputs()
    event = structured_event()
    affected_id = "k8s:cluster:pod:pod-uid"
    relevance = {
        "candidate_event_id": "event-1",
        "candidate_entity_id": DEPLOYMENT_ID,
        "affected_entity_id": affected_id,
        "relevance_status": "semantic_path",
        "path_semantic": "control_ownership",
        "path_relationship_ids": ["relationship-1", "relationship-2"],
        "path_predicates": ["owns", "owns"],
        "path_traversal_directions": ["forward", "forward"],
        "topology_component": 0.65,
    }
    top = {
        "hypothesis_id": "hypothesis-1",
        "rank": 1,
        "root_event_id": "event-1",
        "root_title": "KubernetesDeployment updated",
        "affected_entity_id": affected_id,
        "score": 60.29,
        "chain": [
            {"node_type": "change_event", "node_id": "event|event-1"},
            {"node_type": "entity", "node_id": f"entity|{DEPLOYMENT_ID}"},
            {"node_type": "entity", "node_id": f"entity|{affected_id}"},
        ],
        "evidence_ledger": {
            "ledger_version": "tc4.v1",
            "snapshot_id": "snapshot-incident",
            "supporting": [
                {"evidence_id": "evidence-1", "claim_type": "source_change"},
                {"evidence_id": "evidence-2", "claim_type": "topology_path"},
            ],
            "contradicting": [],
            "missing": [],
        },
    }
    analysis = {
        "analysis_id": "analysis-1",
        "topology_snapshot_id": "snapshot-incident",
        "top_hypothesis": top,
        "hypotheses": [top],
        "candidate_selection_audit": [
            {
                "event_id": "event-1",
                "origin_change_id": "change-1",
                "raw_rank": 11,
                "raw_score": 55.14,
                "role": "observed_resource_mutation",
                "eligibility": "primary_eligible",
                "eligible_rank": 1,
                "selected_for_hypothesis": True,
                "policy_version": "causal-candidate-v1",
            }
        ],
        "candidate_relevance_audit": [relevance],
    }
    result = {
        "scenario_id": "synthetic-causal-audit",
        "run_id": "run-1",
        "topo_git_commit": "abcdef123456",
        "ground_truth": manifest,
        "execution_receipt": receipt,
        "provider_verification": provider,
        "environment": {"cluster": "test"},
        "metric_results": {
            "root_cause_top1_correct": False,
            "root_cause_top3_contains_truth": False,
        },
        "topo_observation": {
            "incident": {
                "incident_id": "incident-1",
                "topology_snapshot_id": "snapshot-incident",
            },
            "snapshot": {
                "snapshot_id": "snapshot-incident",
                "entities": [
                    {"id": DEPLOYMENT_ID, "kind": "KubernetesDeployment"},
                    {"id": affected_id, "kind": "KubernetesPod"},
                ],
            },
            "change_events": [event],
            "incident_change_analysis": {
                "candidates": [
                    {
                        "event": event,
                        "score": 55.14,
                        "minutes_before_incident": 0.09,
                    }
                ]
            },
            "causal_analysis": analysis,
        },
    }
    persistence = {
        "changes": [{"change_id": "change-1", "payload": structured_change()}],
        "change_events": [event],
        "change_entity_links": [],
        "causal_analyses": [
            {"analysis_id": "analysis-1", "payload": analysis}
        ],
    }
    return result, persistence


def expected() -> CauseFingerprint:
    return expected_cause_fingerprint(*truth_inputs())


def actual(**overrides) -> CauseFingerprint:
    values = {
        "provider": "kubernetes",
        "entity_kind": "Deployment",
        "canonical_entity_id": DEPLOYMENT_ID,
        "provider_native_entity_id": DEPLOYMENT_UID,
        "mutation_family": "field_change",
        "changed_field": "properties.images",
        "before_value_ref": GOOD_IMAGE,
        "before_value_hash": value_hash(GOOD_IMAGE),
        "after_value_ref": BAD_IMAGE,
        "after_value_hash": value_hash(BAD_IMAGE),
        "evidence_source": "test",
        "fingerprint_completeness": "complete",
    }
    values.update(overrides)
    return CauseFingerprint(**values)


def test_expected_fingerprint_derives_only_from_manifest_receipt_provider_truth():
    manifest, receipt, provider = truth_inputs()
    fingerprint = expected_cause_fingerprint(manifest, receipt, provider)
    assert fingerprint.provider_native_entity_id == DEPLOYMENT_UID
    assert fingerprint.changed_field == "spec.template.spec.containers[0].image"
    assert fingerprint.before_value_ref == GOOD_IMAGE
    assert fingerprint.after_value_ref == BAD_IMAGE
    assert fingerprint.evidence_source == (
        "scenario_intent+execution_receipt+provider_verification"
    )


def test_actual_fingerprint_does_not_backfill_missing_upstream_structure():
    fingerprints = fingerprints_from_change(
        {
            "change_id": "change-generic",
            "change_type": "entity_updated",
            "entity_id": DEPLOYMENT_ID,
            "entity_kind": "KubernetesDeployment",
            "title": "KubernetesDeployment updated",
        },
        evidence_source="normalized_change",
    )
    assert fingerprints[0].changed_field is None
    assert fingerprints[0].before_value_hash is None
    assert fingerprints[0].after_value_hash is None


def test_same_entity_field_and_values_match_exactly():
    assert compare_causes(expected(), actual()).status == "exact"


def test_same_entity_different_changed_field_is_not_exact():
    match = compare_causes(expected(), actual(changed_field="properties.replicas"))
    assert match.status == "entity_match_mutation_mismatch"


def test_same_changed_field_different_entity_is_not_exact():
    match = compare_causes(
        expected(), actual(provider_native_entity_id="other-deployment")
    )
    assert match.status == "mutation_match_entity_mismatch"


def test_generic_deployment_title_without_structured_field_cannot_exact_match():
    fingerprints = fingerprints_from_event(
        {
            "event_id": "generic-event",
            "title": "KubernetesDeployment updated",
            "metadata": {
                "entity_id": DEPLOYMENT_ID,
                "entity_kind": "KubernetesDeployment",
            },
        },
        evidence_source="event",
    )
    assert compare_causes(expected(), fingerprints[0]).status == "insufficient_structure"


def test_partial_structured_representation_is_never_exact():
    partial = actual(before_value_hash=None, after_value_hash=None)
    assert compare_causes(expected(), partial).status == "compatible_partial"


def test_titles_are_not_inputs_to_cause_matching():
    first = fingerprints_from_event(
        {**structured_event(), "title": "arbitrary prose one"},
        evidence_source="event",
    )[0]
    second = fingerprints_from_event(
        {**structured_event(), "title": "unrelated words two"},
        evidence_source="event",
    )[0]
    assert compare_causes(expected(), first) == compare_causes(expected(), second)


def test_matcher_contains_no_fuzzy_llm_or_embedding_dependency():
    source = (ROOT / "evaluation/cause_fingerprint.py").read_text(encoding="utf-8").lower()
    assert "levenshtein" not in source
    assert "embedding" not in source
    assert "llm" not in source
    assert "title_contains" not in source


def test_first_divergence_returns_earliest_differing_layer():
    result = first_divergence(
        [
            {"layer": "intent", "truth_preserved": True},
            {
                "layer": "normalization",
                "truth_preserved": False,
                "classification": "NORMALIZATION_DEFECT",
                "reason": "lost field",
            },
            {
                "layer": "ranking",
                "truth_preserved": False,
                "classification": "RANKING_DISCRIMINATION_DEFECT",
            },
        ]
    )
    assert result["classification"] == "NORMALIZATION_DEFECT"
    assert result["layer_ordinal"] == 2


def test_downstream_mismatch_does_not_replace_earlier_divergence():
    verdicts = [
        {
            "layer": "event",
            "truth_preserved": False,
            "classification": "CHANGE_EVENT_DEFECT",
        },
        {
            "layer": "evaluator",
            "truth_preserved": False,
            "classification": "EVALUATOR_CAUSE_MATCH_DEFECT",
        },
    ]
    assert first_divergence(verdicts)["classification"] == "CHANGE_EVENT_DEFECT"


def test_identical_layer_chain_has_no_divergence():
    result = first_divergence(
        [
            {"layer": "intent", "truth_preserved": True},
            {"layer": "evaluator", "truth_preserved": True},
        ]
    )
    assert result["classification"] == "NO_DIVERGENCE_FOUND"


def test_all_required_first_divergence_values_are_versioned_and_available():
    assert "EVALUATOR_CAUSE_MATCH_DEFECT" in FIRST_DIVERGENCE_CLASSIFICATIONS
    assert "HYPOTHESIS_REPRESENTATION_DEFECT" in FIRST_DIVERGENCE_CLASSIFICATIONS
    assert "NO_DIVERGENCE_FOUND" in FIRST_DIVERGENCE_CLASSIFICATIONS


def test_product_commit_and_product_versions_serialize_in_bundle():
    result, persistence = complete_result()
    bundle = build_forensic_bundle(result, persistence)
    assert bundle["product_git_commit"] == "abcdef123456"
    assert bundle["versions"]["truth_contracts"]["TC-4"] == "tc4.v1"
    assert bundle["versions"]["product_reasoning"]["causal_rca"] == (
        "13c-causal-v1"
    )


def test_evaluation_contract_versions_serialize_in_bundle():
    result, persistence = complete_result()
    versions = build_forensic_bundle(result, persistence)["versions"]
    assert versions["evaluation_contracts"]["cause_fingerprint"] == (
        CAUSE_FINGERPRINT_VERSION
    )
    assert versions["evaluation_contracts"]["cause_match"] == CAUSE_MATCH_VERSION
    assert versions["evaluation_contracts"]["non_cause_evidence"] == (
        "non-cause-evidence-v1"
    )


def test_forensic_bundle_serialization_is_deterministic():
    result, persistence = complete_result()
    bundle = build_forensic_bundle(result, persistence)
    assert deterministic_json(bundle) == deterministic_json(bundle)
    assert json.loads(deterministic_json(bundle))["run_id"] == "run-1"


def test_forensic_tooling_does_not_import_product_reasoning_services():
    for path in (
        ROOT / "evaluation/cause_fingerprint.py",
        ROOT / "evaluation/causal_forensics.py",
    ):
        source = path.read_text(encoding="utf-8")
        assert "from app." not in source
        assert "import app." not in source


def test_manifest_truth_remains_independent_from_actual_fingerprints():
    manifest = ScenarioManifest.load(manifest_path("blast-01"))
    before = manifest.ground_truth_copy()
    fingerprints_from_change(structured_change(), evidence_source="actual")
    assert manifest.ground_truth_copy() == before


def test_forensic_tooling_has_no_scenario_specific_outcome_override():
    content = "\n".join(
        (ROOT / path).read_text(encoding="utf-8").lower()
        for path in (
            "evaluation/cause_fingerprint.py",
            "evaluation/causal_forensics.py",
        )
    )
    assert "blast-01" not in content
    assert "blast-03" not in content


def test_build_bundle_requires_no_old_ignored_artifact():
    result, persistence = complete_result()
    bundle = build_forensic_bundle(result, persistence)
    assert bundle["first_divergence"]["classification"] == (
        "EVALUATOR_CAUSE_MATCH_DEFECT"
    )
    assert bundle["root_event_reference_match"]["status"] == "exact"


def test_regenerated_current_model_sqlite_state_is_captured(tmp_path):
    database = tmp_path / "current-model.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE changes (
            change_id TEXT PRIMARY KEY, namespace TEXT, payload_json TEXT
        );
        CREATE TABLE change_events (
            event_id TEXT PRIMARY KEY, namespace TEXT, origin_change_id TEXT,
            metadata_json TEXT, raw_payload_json TEXT
        );
        CREATE TABLE change_entity_links (
            link_id TEXT PRIMARY KEY, event_id TEXT, entity_id TEXT
        );
        CREATE TABLE causal_analyses (
            analysis_id TEXT PRIMARY KEY, incident_id TEXT, generated_at TEXT,
            payload_json TEXT
        );
        """
    )
    connection.execute(
        "INSERT INTO changes VALUES (?, ?, ?)",
        ("change-1", "eval-ns", json.dumps(structured_change())),
    )
    connection.execute(
        "INSERT INTO change_events VALUES (?, ?, ?, ?, ?)",
        ("event-1", "eval-ns", "change-1", json.dumps({}), json.dumps({})),
    )
    connection.execute(
        "INSERT INTO change_entity_links VALUES (?, ?, ?)",
        ("link-1", "event-1", DEPLOYMENT_ID),
    )
    connection.execute(
        "INSERT INTO causal_analyses VALUES (?, ?, ?, ?)",
        ("analysis-1", "incident-1", "2026-08-24T00:00:00Z", json.dumps({})),
    )
    connection.commit()
    connection.close()

    state = capture_persistence_state(
        database, namespace="eval-ns", incident_id="incident-1"
    )
    assert state["changes"][0]["payload"]["change_id"] == "change-1"
    assert state["change_events"][0]["metadata"] == {}
    assert state["change_entity_links"][0]["entity_id"] == DEPLOYMENT_ID
    assert state["causal_analyses"][0]["analysis_id"] == "analysis-1"


def test_bundle_keeps_generic_title_separate_from_exact_root_event_reference():
    result, persistence = complete_result()
    bundle = build_forensic_bundle(result, persistence)
    assert bundle["root_hypothesis"]["root_title"] == (
        "KubernetesDeployment updated"
    )
    assert bundle["root_hypothesis_direct_fingerprint"]["changed_field"] is None
    assert bundle["root_event_reference_match"]["status"] == "exact"


def test_bundle_uses_pinned_incident_topology_and_tc3_time():
    result, persistence = complete_result()
    historical = build_forensic_bundle(result, persistence)["historical_correctness"]
    assert historical["uses_incident_pinned_topology"] is True
    assert historical["temporal_version"] == "tc3.v1"


def test_h3_r1_historical_product_scope_remains_frozen_after_ca0():
    assert_h3_r1_historical_product_scope(ROOT)


def test_version_metadata_has_separate_product_and_evaluation_families():
    assert set(VERSION_METADATA) == {
        "truth_contracts",
        "product_reasoning",
        "evaluation_contracts",
    }
    assert VERSION_METADATA["product_reasoning"]["causal_candidate"] == (
        "causal-candidate-v1"
    )
    assert VERSION_METADATA["evaluation_contracts"]["cause_match"] == (
        "eval-cause-match-v1"
    )


def test_forensic_bundle_validates_against_machine_readable_schema():
    result, persistence = complete_result()
    bundle = build_forensic_bundle(result, persistence)
    schema = json.loads(
        (
            ROOT
            / "docs/architecture/evaluation/cause-forensic-bundle.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert schema["$schema"].endswith("2020-12/schema")
    assert set(schema["required"]).issubset(bundle)
    validate_forensic_bundle(bundle)
