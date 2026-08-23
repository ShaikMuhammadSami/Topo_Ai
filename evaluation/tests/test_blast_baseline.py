from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from evaluation.contracts import ScenarioManifest, TopoObservation, validate_manifest
from evaluation.evaluator import IndependentEvaluator, blast_false_positive_path_attribution
from evaluation.kubernetes import Kubectl, SAFE_NAMESPACE
from evaluation.scenarios import manifest_path


ROOT = Path(__file__).resolve().parents[2]
SENTINEL_D_GIT_BLOB_SHA1 = "e7e2a8f4e2cde066bee209191ec27304a41193f7"


def _git_blob_sha1(path: Path) -> str:
    # Match Git's text normalization so the frozen blob is portable across
    # Windows CRLF and Unix LF worktrees.
    content = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()


def _blast_path_observation(relationships: list[dict] | None = None) -> TopoObservation:
    return TopoObservation(
        observation_version="eval-1.topo-observation.v1",
        captured_at="2026-08-23T10:00:00+00:00",
        incident={"topology_snapshot_id": "pinned-snapshot"},
        snapshot={
            "snapshot_id": "pinned-snapshot",
            "entities": [
                {"id": "failed", "kind": "KubernetesPod", "name": "failed"},
                {"id": "namespace", "kind": "KubernetesNamespace", "name": "eval"},
                {"id": "healthy-deployment", "kind": "KubernetesDeployment", "name": "healthy"},
            ],
            "relationships": relationships
            or [
                {
                    "id": "r-contains-failed",
                    "source_entity_id": "namespace",
                    "target_entity_id": "failed",
                    "relationship_type": "contains",
                    "directed": True,
                    "provenance": {"assertion_type": "observed"},
                },
                {
                    "id": "r-contains-healthy",
                    "source_entity_id": "namespace",
                    "target_entity_id": "healthy-deployment",
                    "relationship_type": "contains",
                    "directed": True,
                    "provenance": {"assertion_type": "observed"},
                },
            ],
        },
        blast_radius={
            "root_entity_id": "failed",
            "affected_entities": [
                {"entity_id": "failed", "relationship": None},
                {"entity_id": "namespace", "relationship": "contains"},
                {"entity_id": "healthy-deployment", "relationship": "contains"},
            ],
            "dependency_paths": [
                {"path": ["failed", "namespace"]},
                {"path": ["failed", "namespace", "healthy-deployment"]},
            ],
        },
    )


def test_all_permanent_blast_manifests_validate_and_keep_truth_independent():
    for scenario_id in ("blast-01", "blast-02", "blast-03"):
        manifest = ScenarioManifest.load(manifest_path(scenario_id))
        before = manifest.ground_truth_copy()
        TopoObservation(
            observation_version="eval-1.topo-observation.v1",
            captured_at="2026-08-23T10:00:00+00:00",
            blast_radius={"affected_entities": [{"entity_id": "Topo-cannot-rewrite-truth"}]},
        )
        assert manifest.ground_truth_copy() == before
        blast = before["expected_blast_radius"]
        assert set(blast["required_affected"]).isdisjoint(blast["explicitly_unaffected"])


def test_false_positive_path_attribution_is_deterministic_and_directional():
    manifest = ScenarioManifest.load(manifest_path("blast-01"))
    aliases = {
        "failed_pod": ["failed"],
        "scenario_namespace": ["namespace"],
        "healthy_deployment": ["healthy-deployment"],
    }
    first = blast_false_positive_path_attribution(
        manifest,
        _blast_path_observation(),
        aliases,
    )
    reversed_relationships = list(
        reversed(_blast_path_observation().snapshot["relationships"])
    )
    second = blast_false_positive_path_attribution(
        manifest,
        _blast_path_observation(reversed_relationships),
        aliases,
    )
    assert first == second
    healthy_path = next(
        item for item in first if item["false_positive_alias"] == "healthy_deployment"
    )
    assert [hop["relationship_id"] for hop in healthy_path["hops"]] == [
        "r-contains-failed",
        "r-contains-healthy",
    ]
    assert [hop["traversal_direction"] for hop in healthy_path["hops"]] == [
        "reverse",
        "forward",
    ]
    assert all(hop["predicate"] == "contains" for hop in healthy_path["hops"])


def test_false_positive_metrics_count_predicates_and_path_patterns():
    manifest = ScenarioManifest.load(manifest_path("blast-01"))
    aliases = {
        "failed_pod": ["failed"],
        "scenario_namespace": ["namespace"],
        "healthy_deployment": ["healthy-deployment"],
    }
    paths = blast_false_positive_path_attribution(
        manifest,
        _blast_path_observation(),
        aliases,
    )
    predicate_count = sum(
        1 for path in paths for hop in path["hops"] if hop["predicate"] == "contains"
    )
    patterns = [
        " > ".join(
            f"{hop['predicate']}:{hop['traversal_direction']}" for hop in path["hops"]
        )
        for path in paths
    ]
    assert predicate_count == 3
    assert "contains:reverse > contains:forward" in patterns


def test_structural_context_cannot_automatically_become_impact():
    value = ScenarioManifest.load(manifest_path("blast-01")).ground_truth_copy()
    value["expected_blast_radius"]["required_affected"].append("scenario_namespace")
    value["expected_blast_radius"]["explicitly_unaffected"].remove("scenario_namespace")
    with pytest.raises(ValueError, match="required_affected"):
        validate_manifest(value)


def test_impact_truth_classes_must_be_disjoint():
    value = ScenarioManifest.load(manifest_path("blast-01")).ground_truth_copy()
    value["expected_blast_radius"]["impact_truth"]["unaffected"].append("failed_pod")
    with pytest.raises(ValueError, match="disjoint"):
        validate_manifest(value)


def test_partial_backend_truth_keeps_ready_service_and_sibling_unaffected():
    blast = ScenarioManifest.load(manifest_path("blast-02")).value["expected_blast_radius"]
    assert blast["impact_truth"]["operationally_impacted"] == []
    assert "root_service" in blast["impact_truth"]["unaffected"]
    assert "healthy_pod" in blast["impact_truth"]["unaffected"]
    assert "root_service" not in blast["required_affected"]
    assert "healthy_pod" not in blast["required_affected"]


def test_zero_ready_endpoint_truth_marks_service_impacted():
    blast = ScenarioManifest.load(manifest_path("blast-03")).value["expected_blast_radius"]
    assert blast["impact_truth"]["operationally_impacted"] == ["root_service"]
    assert "root_service" in blast["required_affected"]


def test_provider_endpoint_slice_readiness_is_captured_without_topo():
    class ProviderOnlyKubectl(Kubectl):
        def get(self, kind, name=None, **kwargs):
            if kind == "service":
                return {
                    "metadata": {"uid": "service-uid"},
                    "spec": {"selector": {"app": "partial-backend"}},
                }
            if kind == "endpointslices":
                return {
                    "items": [
                        {
                            "metadata": {"name": "slice-a", "uid": "slice-uid"},
                            "endpoints": [
                                {
                                    "addresses": ["10.0.0.2"],
                                    "conditions": {"ready": True},
                                    "targetRef": {"kind": "Pod", "name": "healthy", "uid": "healthy-uid"},
                                },
                                {
                                    "addresses": ["10.0.0.3"],
                                    "conditions": {"ready": False},
                                    "targetRef": {"kind": "Pod", "name": "failed", "uid": "failed-uid"},
                                },
                            ],
                        }
                    ]
                }
            raise AssertionError(f"Unexpected provider query: {kind}")

    truth = ProviderOnlyKubectl().service_endpoint_truth("provider-namespace", "service")
    assert truth["selector"] == {"app": "partial-backend"}
    assert truth["ready_endpoint_count"] == 1
    assert truth["ready_target_uids"] == ["healthy-uid"]
    assert truth["endpoint_slices"][0]["uid"] == "slice-uid"


def test_recreate_strategy_explicitly_removes_rolling_update():
    class CapturingKubectl(Kubectl):
        def __init__(self):
            super().__init__()
            self.arguments = None

        def run(self, *args, **kwargs):
            self.arguments = args
            return ""

        def get(self, *args, **kwargs):
            return {"metadata": {"name": "workload"}}

    kubectl = CapturingKubectl()
    kubectl.use_recreate_strategy("eval", "workload")
    patch = json.loads(kubectl.arguments[kubectl.arguments.index("-p") + 1])
    assert patch["spec"]["strategy"] == {
        "type": "Recreate",
        "rollingUpdate": None,
    }


def test_partial_failure_probe_uses_pod_scoped_persistent_state():
    class CapturingKubectl(Kubectl):
        def __init__(self):
            super().__init__()
            self.arguments = None

        def run(self, *args, **kwargs):
            self.arguments = args
            return ""

        def get(self, *args, **kwargs):
            return {
                "metadata": {"name": "workload"},
                "spec": {"template": {"spec": {"containers": [{"name": "nginx"}]}}},
            }

    kubectl = CapturingKubectl()
    kubectl.configure_persistent_failure_probe("eval", "workload")
    patch = json.loads(kubectl.arguments[kubectl.arguments.index("-p") + 1])
    pod_spec = patch["spec"]["template"]["spec"]
    assert pod_spec["volumes"] == [{"name": "topo-eval-state", "emptyDir": {}}]
    assert pod_spec["containers"][0]["livenessProbe"]["exec"]["command"][-1] == (
        "test ! -f /topo-eval-state/fail"
    )


def test_blast_metric_zero_denominators_are_explicitly_undefined():
    value = ScenarioManifest.load(manifest_path("blast-01")).ground_truth_copy()
    value["expected_blast_radius"] = {
        "required_affected": [],
        "explicitly_unaffected": [],
    }
    metrics = IndependentEvaluator._blast_metrics(
        ScenarioManifest(value=value),
        TopoObservation(
            observation_version="eval-1.topo-observation.v1",
            captured_at="2026-08-23T10:00:00+00:00",
            blast_radius={"affected_entities": []},
        ),
        {},
    )
    assert metrics["blast_radius_precision"] is None
    assert metrics["blast_radius_recall"] is None


def test_sentinel_d_manifest_remains_byte_for_byte_unchanged():
    assert _git_blob_sha1(manifest_path("sentinel-d")) == SENTINEL_D_GIT_BLOB_SHA1


def test_blast_namespaces_retain_exact_cleanup_guard():
    assert SAFE_NAMESPACE.fullmatch("topo-eval-blast-01-abcdef12")
    assert SAFE_NAMESPACE.fullmatch("topo-eval-blast-02-abcdef12")
    assert SAFE_NAMESPACE.fullmatch("topo-eval-blast-03-abcdef12")
    assert not SAFE_NAMESPACE.fullmatch("topo-eval-blast-99-abcdef12")
    assert not SAFE_NAMESPACE.fullmatch("production")


def test_result_schema_allows_structured_attribution_metrics():
    schema = json.loads(
        (ROOT / "docs/architecture/evaluation/evaluation-result.schema.json").read_text()
    )
    allowed = schema["properties"]["metric_results"]["additionalProperties"]["type"]
    assert "array" in allowed
    assert "object" in allowed


def test_no_blast_scenario_special_cases_exist_in_product_code():
    forbidden = ("blast-01", "blast-02", "blast-03", "topo-eval-blast")
    product_roots = (
        ROOT / "backend/app",
        ROOT / "agent/src",
        ROOT / "frontend",
        ROOT / "cli/src",
    )
    hits: list[str] = []
    for product_root in product_roots:
        for path in product_root.rglob("*"):
            if not path.is_file() or any(
                part in {"node_modules", ".next", "__pycache__"} for part in path.parts
            ):
                continue
            try:
                content = path.read_text(encoding="utf-8").lower()
            except (OSError, UnicodeDecodeError):
                continue
            for token in forbidden:
                if token in content:
                    hits.append(f"{path.relative_to(ROOT)}:{token}")
    assert hits == []
