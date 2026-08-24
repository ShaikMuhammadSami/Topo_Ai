from __future__ import annotations

import copy
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from evaluation.lineage_contracts import (
    LINEAGE_HOP_VERSION,
    LINEAGE_RESULT_VERSION,
    LineageResult,
    deterministic_json,
)
from evaluation.lineage_evaluator import HOP_SPECS, evaluate_lineage_chain, evaluate_lineage_hop
from evaluation.lineage_provider_truth import (
    contains_unredacted_secret_like_fields,
    container_image_canonical_id,
    github_commit_canonical_id,
    github_repository_canonical_id,
    github_workflow_run_canonical_id,
    kubernetes_canonical_id,
    kubernetes_signal_id,
    provider_identity,
    sanitize_provider_receipt,
)
from evaluation.product_diff_guard import assert_product_diff_scoped_to_h3_r1
from evaluation.lineage_runner import (
    NAMESPACE_PREFIX,
    RUN_LABEL,
    namespace_is_safe_for_cleanup,
)


ROOT = Path(__file__).resolve().parents[2]
REPO_ID = github_repository_canonical_id(
    api_url="https://api.github.com", repository_native_id="123"
)
COMMIT_SHA = "a" * 40
COMMIT_ID = github_commit_canonical_id(
    repository_canonical_id=REPO_ID, sha=COMMIT_SHA
)
RUN_ID = github_workflow_run_canonical_id(
    api_url="https://api.github.com", run_id="456"
)
DIGEST = "sha256:" + "b" * 64
IMAGE_ID = container_image_canonical_id(DIGEST)
DEPLOYMENT_ID = kubernetes_canonical_id(
    cluster="docker-desktop", kind="Deployment", uid="dep-uid"
)
RS_ID = kubernetes_canonical_id(
    cluster="docker-desktop", kind="ReplicaSet", uid="rs-uid"
)
POD_ID = kubernetes_canonical_id(
    cluster="docker-desktop", kind="Pod", uid="pod-uid"
)
SIGNAL_ID = kubernetes_signal_id(
    cluster="docker-desktop", event_uid="event-uid"
)


def identity(kind: str, native: str, canonical: str, **extra) -> dict:
    return provider_identity(
        provider="test",
        kind=kind,
        native_id=native,
        canonical_id=canonical,
        immutable_digest=extra.get("immutable_digest"),
    )


def provider_hops() -> dict[str, dict]:
    identities = {
        "repo": identity("GitRepository", "123", REPO_ID),
        "commit": identity("GitCommit", COMMIT_SHA, COMMIT_ID),
        "run": identity("GitHubWorkflowRun", "456", RUN_ID),
        "image": identity(
            "ContainerImage", DIGEST, IMAGE_ID, immutable_digest=DIGEST
        ),
        "deployment": identity("KubernetesDeployment", "dep-uid", DEPLOYMENT_ID),
        "rs": identity("KubernetesReplicaSet", "rs-uid", RS_ID),
        "pod": identity("KubernetesPod", "pod-uid", POD_ID),
        "signal": identity("RuntimeFailureSignal", "event-uid", SIGNAL_ID),
    }
    return {
        "H1": {
            "source_identity": identities["repo"],
            "target_identity": identities["commit"],
            "relationship_established": True,
            "source_time": None,
            "target_time": "2026-08-24T00:00:00Z",
            "evidence_references": {"github": "repo+commit"},
        },
        "H2": {
            "source_identity": identities["commit"],
            "target_identity": identities["run"],
            "relationship_established": True,
            "source_time": "2026-08-24T00:00:00Z",
            "target_time": "2026-08-24T00:00:03Z",
            "evidence_references": {"head_sha": COMMIT_SHA},
        },
        "H3": {
            "source_identity": identities["run"],
            "target_identity": identities["image"],
            "relationship_established": True,
            "source_time": "2026-08-24T00:00:03Z",
            "target_time": "2026-08-24T00:01:00Z",
            "immutable_artifact_proven": True,
            "evidence_references": {"attestation": "receipt-1"},
        },
        "H4": {
            "source_identity": identities["image"],
            "target_identity": identities["deployment"],
            "relationship_established": True,
            "source_time": "2026-08-24T00:01:00Z",
            "target_time": "2026-08-24T00:02:00Z",
            "immutable_artifact_proven": True,
            "evidence_references": {"deployment_uid": "dep-uid"},
        },
        "H5": {
            "source_identity": identities["deployment"],
            "target_identity": identities["rs"],
            "relationship_established": True,
            "source_time": "2026-08-24T00:02:00Z",
            "target_time": "2026-08-24T00:02:01Z",
            "evidence_references": {"owner_uid": "dep-uid"},
        },
        "H6": {
            "source_identity": identities["rs"],
            "target_identity": identities["pod"],
            "relationship_established": True,
            "source_time": "2026-08-24T00:02:01Z",
            "target_time": "2026-08-24T00:02:02Z",
            "evidence_references": {"owner_uid": "rs-uid"},
        },
        "H7": {
            "source_identity": identities["pod"],
            "target_identity": identities["signal"],
            "relationship_established": True,
            "source_time": "2026-08-24T00:02:02Z",
            "target_time": "2026-08-24T00:02:20Z",
            "accepted_failure_reasons": ["BackOff", "CrashLoopBackOff"],
            "evidence_references": {"event_uid": "event-uid"},
        },
    }


def entity(entity_id: str, kind: str, external_id: str, **properties) -> dict:
    return {
        "id": entity_id,
        "kind": kind,
        "external_id": external_id,
        "properties": properties,
    }


def relationship(
    rel_id: str,
    source: str,
    target: str,
    predicate: str,
    reference_types: tuple[str, ...],
    *,
    origin: str = "observed",
    completeness: str = "complete",
) -> dict:
    return {
        "id": rel_id,
        "source_entity_id": source,
        "target_entity_id": target,
        "relationship_type": predicate,
        "observed_at": "2026-08-24T00:03:00Z",
        "provenance": {
            "origin": origin,
            "source_component": "test-provider-linker",
            "source_references": [
                {"reference_type": item, "reference": f"ref:{item}"}
                for item in reference_types
            ],
            "linker_version": "test-linker:v1",
            "completeness": completeness,
        },
    }


def topo() -> dict:
    return {
        "snapshot_id": "snapshot-1",
        "incident_id": None,
        "pinned_snapshot_id": None,
        "entities": [
            entity(REPO_ID, "GitRepository", "123"),
            entity(COMMIT_ID, "GitCommit", COMMIT_SHA),
            entity(RUN_ID, "GitHubWorkflowRun", "456"),
            entity(IMAGE_ID, "ContainerImage", DIGEST, digest=DIGEST, immutable=True),
            entity(DEPLOYMENT_ID, "KubernetesDeployment", "dep-uid"),
            entity(RS_ID, "KubernetesReplicaSet", "rs-uid"),
            entity(POD_ID, "KubernetesPod", "pod-uid"),
        ],
        "relationships": [
            relationship("h1", REPO_ID, COMMIT_ID, "contains", ("github_repository_id", "git_commit_sha")),
            relationship("h2", COMMIT_ID, RUN_ID, "triggers", ("git_commit_sha", "github_workflow_run_id")),
            relationship("h3", RUN_ID, IMAGE_ID, "produces", ("github_workflow_run_id", "container_image_digest", "mapping_method"), origin="inferred"),
            relationship("h4", DEPLOYMENT_ID, IMAGE_ID, "uses", ("container_image_reference", "container_image_digest"), origin="derived"),
            relationship("h5", DEPLOYMENT_ID, RS_ID, "owns", ("kubernetes_owner_reference_uid",), origin="declared"),
            relationship("h6", RS_ID, POD_ID, "runs", ("kubernetes_owner_reference_uid",), origin="declared"),
        ],
        "signals": [
            {
                "signal_id": SIGNAL_ID,
                "reason": "BackOff",
                "involved_entity_id": POD_ID,
                "involved_object_uid": "pod-uid",
                "temporal": {
                    "source_event_at": "2026-08-24T00:02:20Z",
                    "observed_at": "2026-08-24T00:03:00Z",
                },
            }
        ],
    }


def spec(hop_id: str):
    return next(item for item in HOP_SPECS if item.hop_id == hop_id)


def status(hop_id: str, hops=None, observation=None) -> str:
    result = evaluate_lineage_hop(
        spec(hop_id),
        (hops or provider_hops())[hop_id],
        observation or topo(),
    )
    return result.evaluation["status"]


def test_repo_provider_identity_is_structural():
    assert provider_hops()["H1"]["source_identity"]["native_id"] == "123"
    assert status("H1") == "PROVEN"


def test_commit_sha_must_belong_to_expected_repository():
    hops = provider_hops()
    hops["H1"]["relationship_established"] = False
    assert status("H1", hops) == "INCONCLUSIVE"


def test_commit_actions_requires_exact_head_sha_relationship():
    hops = provider_hops()
    hops["H2"]["relationship_established"] = False
    assert status("H2", hops) == "INCONCLUSIVE"


def test_time_proximity_alone_cannot_prove_commit_actions():
    hops = provider_hops()
    hops["H2"]["relationship_established"] = False
    hops["H2"]["target_time"] = "2026-08-24T00:00:01Z"
    assert status("H2", hops) != "PROVEN"


def test_actions_image_requires_explicit_digest_evidence():
    hops = provider_hops()
    hops["H3"]["immutable_artifact_proven"] = False
    assert status("H3", hops) == "PARTIAL"


def test_mutable_tag_alone_is_partial():
    hops = provider_hops()
    hops["H3"]["target_identity"]["immutable_digest"] = None
    hops["H3"]["immutable_artifact_proven"] = False
    assert status("H3", hops) == "PARTIAL"


def test_image_digest_equality_is_immutable_identity():
    result = evaluate_lineage_hop(spec("H4"), provider_hops()["H4"], topo())
    assert result.evaluation["immutable_artifact_proven"] is True


def test_different_image_digest_is_wrong():
    hops = provider_hops()
    wrong = "sha256:" + "c" * 64
    hops["H4"]["source_identity"] = identity(
        "ContainerImage", wrong, container_image_canonical_id(wrong), immutable_digest=wrong
    )
    assert status("H4", hops) == "WRONG"


def test_image_deployment_requires_exact_digest_reference():
    observation = topo()
    observation["relationships"] = [item for item in observation["relationships"] if item["id"] != "h4"]
    assert status("H4", observation=observation) == "MISSING"


def test_deployment_uid_is_independent_from_display_name():
    observation = topo()
    deployment = next(item for item in observation["entities"] if item["id"] == DEPLOYMENT_ID)
    deployment["name"] = "arbitrary-display-name"
    assert status("H5", observation=observation) == "PROVEN"


def test_deployment_rs_requires_owner_reference_uid_match():
    assert status("H5") == "PROVEN"


def test_rs_pod_requires_owner_reference_uid_match():
    assert status("H6") == "PROVEN"


def test_wrong_owner_uid_is_wrong():
    hops = provider_hops()
    hops["H5"]["identity_conflict"] = True
    assert status("H5", hops) == "WRONG"


def test_pod_failure_uses_structured_provider_state():
    assert status("H7") == "PROVEN"


def test_pod_display_text_alone_is_insufficient_for_failure_proof():
    hops = provider_hops()
    hops["H7"]["target_identity"] = None
    assert status("H7", hops) != "PROVEN"


def test_each_hop_preserves_provider_evidence_independently():
    hop = provider_hops()["H2"]
    result = evaluate_lineage_hop(spec("H2"), hop, topo())
    assert result.provider_truth["evidence_references"] == {"head_sha": COMMIT_SHA}


def test_topo_cannot_define_expected_provider_lineage():
    observation = topo()
    observation["expected_provider_identity"] = {"native_id": "forged"}
    assert status("H1", observation=observation) == "PROVEN"


def test_provider_hop_with_missing_topo_edge_is_missing():
    observation = topo()
    observation["relationships"] = []
    assert status("H2", observation=observation) == "MISSING"


def test_correct_edge_missing_provenance_is_partial():
    observation = topo()
    next(item for item in observation["relationships"] if item["id"] == "h2")["provenance"] = {}
    assert status("H2", observation=observation) == "PARTIAL"


def test_wrong_edge_direction_is_wrong():
    observation = topo()
    edge = next(item for item in observation["relationships"] if item["id"] == "h2")
    edge["source_entity_id"], edge["target_entity_id"] = edge["target_entity_id"], edge["source_entity_id"]
    assert status("H2", observation=observation) == "WRONG"


def test_missing_required_source_reference_is_partial():
    observation = topo()
    edge = next(item for item in observation["relationships"] if item["id"] == "h5")
    edge["provenance"]["source_references"] = []
    assert status("H5", observation=observation) == "PARTIAL"


def test_tc2_origin_and_completeness_are_preserved():
    result = evaluate_lineage_hop(spec("H5"), provider_hops()["H5"], topo())
    assert result.topo_observation["provenance"]["origin"] == "declared"
    assert result.topo_observation["provenance"]["completeness"] == "complete"


def test_first_broken_hop_picks_earliest_incomplete():
    observation = topo()
    observation["relationships"] = [item for item in observation["relationships"] if item["id"] != "h2"]
    result = evaluate_lineage_chain(provider_hops(), observation)
    assert result["first_broken_hop"] == "H2_COMMIT_ACTIONS"


def test_later_proven_hops_do_not_hide_earlier_missing_hop():
    observation = topo()
    observation["relationships"] = [item for item in observation["relationships"] if item["id"] != "h1"]
    result = evaluate_lineage_chain(provider_hops(), observation)
    assert result["first_broken_hop_id"] == "H1"
    assert result["commercial_proof_status"]["runtime_failure_proven"] is True


def test_all_proven_gives_no_broken_hop():
    result = evaluate_lineage_chain(provider_hops(), topo())
    assert result["first_broken_hop"] == "NO_BROKEN_HOP"
    assert result["lineage_complete"] is True


def test_provider_prerequisite_unavailable_is_explicitly_blocked():
    hops = provider_hops()
    hops["H3"] = {"status": "PROVIDER_PREREQUISITE_BLOCKED", "reason": "no digest-producing run"}
    result = evaluate_lineage_chain(hops, topo())
    assert result["first_broken_hop"] == "PROVIDER_PREREQUISITE_BLOCKED"
    assert result["first_broken_hop_id"] == "H3"


def test_no_fuzzy_identity_matching():
    observation = topo()
    observation["entities"][0]["id"] = REPO_ID + "-similar"
    observation["entities"][0]["external_id"] = "1234"
    assert status("H1", observation=observation) == "WRONG"


@pytest.mark.parametrize("forbidden", ["llm", "openai", "embedding"])
def test_evaluator_has_no_llm_or_embeddings(forbidden):
    source = (ROOT / "evaluation/lineage_evaluator.py").read_text(encoding="utf-8").lower()
    assert forbidden not in source


def test_mutable_tag_is_not_immutable_digest():
    assert container_image_canonical_id("repo/app:latest") != IMAGE_ID


def test_source_lineage_is_separate_from_causal_attribution():
    fields = LineageResult.__dataclass_fields__
    assert "lineage_complete" in fields
    assert "source_change_causally_proven" in fields


def test_provider_and_topo_times_remain_separate():
    result = evaluate_lineage_hop(spec("H2"), provider_hops()["H2"], topo())
    assert result.provider_truth["source_time"] == "2026-08-24T00:00:00Z"
    assert result.topo_observation["relationship_observed_at"] == "2026-08-24T00:03:00Z"


def test_small_provider_clock_skew_is_tolerated():
    hops = provider_hops()
    hops["H2"]["source_time"] = "2026-08-24T00:04:00Z"
    hops["H2"]["target_time"] = "2026-08-24T00:00:00Z"
    assert status("H2", hops) == "PROVEN"


def test_large_provider_time_inversion_is_partial():
    hops = provider_hops()
    hops["H2"]["source_time"] = "2026-08-24T00:06:00Z"
    hops["H2"]["target_time"] = "2026-08-24T00:00:00Z"
    assert status("H2", hops) == "PARTIAL"


def test_latest_topology_cannot_replace_incident_pin():
    observation = topo()
    observation.update({"incident_id": "incident-1", "pinned_snapshot_id": "snapshot-old", "snapshot_id": "snapshot-latest"})
    with pytest.raises(ValueError, match="exact pinned snapshot"):
        evaluate_lineage_chain(provider_hops(), observation)


def test_exact_incident_pin_is_accepted():
    observation = topo()
    observation.update({"incident_id": "incident-1", "pinned_snapshot_id": "snapshot-1"})
    assert evaluate_lineage_chain(provider_hops(), observation)["lineage_complete"] is True


def test_result_serialization_is_deterministic():
    value = {"z": [2, 1], "a": {"b": True}}
    assert deterministic_json(value) == deterministic_json(copy.deepcopy(value))


def test_result_schema_declares_required_contract():
    schema = json.loads((ROOT / "docs/architecture/evaluation/lineage-result.schema.json").read_text(encoding="utf-8"))
    assert schema["$schema"].endswith("2020-12/schema")
    assert {"hop_results", "first_broken_hop", "lineage_complete"}.issubset(schema["required"])


def test_secret_shaped_fields_are_redacted():
    value = {"token": "secret", "nested": {"download_url": "https://example.test/file?signature=secret&safe=yes"}}
    safe = sanitize_provider_receipt(value)
    assert safe["token"] == "[REDACTED]"
    assert "secret" not in safe["nested"]["download_url"]
    assert contains_unredacted_secret_like_fields(safe) is False


def test_unredacted_signed_url_is_detected():
    assert contains_unredacted_secret_like_fields({"url": "https://example.test/x?token=unsafe"}) is True


def test_evaluator_imports_no_product_reasoning_services():
    for filename in ("lineage_contracts.py", "lineage_provider_truth.py", "lineage_evaluator.py"):
        source = (ROOT / "evaluation" / filename).read_text(encoding="utf-8")
        assert "from app." not in source
        assert "import app." not in source


def test_lineage_tooling_has_no_scenario_specific_product_override():
    source = "\n".join(
        (ROOT / "evaluation" / filename).read_text(encoding="utf-8").lower()
        for filename in ("lineage_contracts.py", "lineage_provider_truth.py", "lineage_evaluator.py")
    )
    assert "sentinel-a" not in source
    assert "blast-01" not in source


def test_lineage_scenario_id_does_not_appear_in_product_code():
    completed = subprocess.run(
        ["rg", "-l", "lineage-source-to-runtime-v1|topo-eval-lineage", "backend/app", "backend/tests", "agent/src", "frontend", "cli/src"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.stdout.strip() == ""


def test_product_diff_is_scoped_to_h3_r1_after_lineage_baseline():
    assert_product_diff_scoped_to_h3_r1(ROOT)


def test_h6_accepts_current_direct_collector_runs_predicate():
    assert status("H6") == "PROVEN"


def test_h6_accepts_agent_inventory_owns_predicate():
    observation = topo()
    edge = next(item for item in observation["relationships"] if item["id"] == "h6")
    edge["relationship_type"] = "owns"
    assert status("H6", observation=observation) == "PROVEN"


def test_lineage_complete_requires_all_seven_hops():
    hops = provider_hops()
    hops["H3"]["immutable_artifact_proven"] = False
    result = evaluate_lineage_chain(hops, topo())
    assert result["lineage_complete"] is False
    assert result["immutable_artifact_chain_complete"] is False


def test_commercial_status_is_boolean_and_non_marketing():
    result = evaluate_lineage_chain(provider_hops(), topo())
    assert all(type(value) is bool for value in result["commercial_proof_status"].values())


def test_cleanup_requires_exact_namespace_and_label():
    run_id = "abc12345"
    namespace = {"metadata": {"name": f"{NAMESPACE_PREFIX}{run_id}", "labels": {RUN_LABEL: run_id}}}
    assert namespace_is_safe_for_cleanup(namespace, run_id) is True


@pytest.mark.parametrize(
    "namespace",
    [
        {"metadata": {"name": "default", "labels": {RUN_LABEL: "abc12345"}}},
        {"metadata": {"name": f"{NAMESPACE_PREFIX}abc12345", "labels": {}}},
        {"metadata": {"name": f"{NAMESPACE_PREFIX}abc12345", "labels": {RUN_LABEL: "other"}}},
    ],
)
def test_cleanup_rejects_unsafe_namespace(namespace):
    assert namespace_is_safe_for_cleanup(namespace, "abc12345") is False


def test_contract_versions_are_explicit():
    assert LINEAGE_HOP_VERSION == "eval-lineage-hop-v1"
    assert LINEAGE_RESULT_VERSION == "eval-lineage-result-v1"


def test_provider_identity_builder_does_not_read_topo():
    built = provider_identity(provider="github", kind="GitCommit", native_id=COMMIT_SHA, canonical_id=COMMIT_ID)
    assert set(built) == {"provider", "kind", "native_id", "canonical_id", "name", "scope", "immutable_digest"}


def test_provider_blocked_hop_does_not_claim_artifact_identity():
    hops = provider_hops()
    hops["H3"] = {"status": "PROVIDER_PREREQUISITE_BLOCKED", "reason": "no provider artifact"}
    result = evaluate_lineage_hop(spec("H3"), hops["H3"], topo())
    assert result.evaluation["immutable_artifact_proven"] is None
    assert result.evaluation["status"] == "PROVIDER_PREREQUISITE_BLOCKED"


def test_provider_evidence_is_not_mutated_by_evaluation():
    hops = provider_hops()
    before = copy.deepcopy(hops)
    evaluate_lineage_chain(hops, topo())
    assert hops == before


def test_generated_timestamp_is_timezone_aware_example():
    assert datetime.now(timezone.utc).tzinfo is timezone.utc
