from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / "scripts/cloud/cx0/kubernetes_reproducibility_contract.py"
MANIFEST_ROOT = ROOT / "infrastructure/kubernetes/golden"
BACKEND_IMAGE = (
    "297361542190.dkr.ecr.us-east-1.amazonaws.com/topo-golden/topo@"
    "sha256:ef4731bc03aab04bdabd8b525a27f4c765c860e11a553aca66ac20650feeb56b"
)

SPEC = importlib.util.spec_from_file_location("cx0_kubernetes_contract", CONTRACT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load Kubernetes reproducibility contract")
CONTRACT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CONTRACT
SPEC.loader.exec_module(CONTRACT)


def source_contract() -> dict[str, object]:
    return CONTRACT.load_source_contract(MANIFEST_ROOT, BACKEND_IMAGE)


def matching_live(source: dict[str, object]) -> dict[str, object]:
    deployments = copy.deepcopy(source["deployments"])
    services = copy.deepcopy(source["services"])
    for item in [*deployments, *services]:
        item.pop("kind", None)
        item["metadata"]["uid"] = "runtime-only-uid"
        item["metadata"]["resourceVersion"] = "987654"
        item["status"] = {"runtime": "ignored"}
    return {"deployments": deployments, "services": services}


class Cx0KubernetesReconciliationTests(unittest.TestCase):
    def test_identical_semantics_ignore_runtime_identity_and_status(self) -> None:
        source = source_contract()
        result = CONTRACT.compare_contracts(source, matching_live(source))
        self.assertEqual("MATCH", result["classification"])
        self.assertEqual([], result["difference_paths"])
        self.assertIn("uid", result["runtime_generated_fields_excluded"])

    def test_immutable_image_digest_mismatch_is_codified_differently(self) -> None:
        source = source_contract()
        live = matching_live(source)
        backend = next(
            item for item in live["deployments"]
            if item["metadata"]["name"] == "topo-backend"
        )
        backend["pod_template"]["containers"][0]["image"] = (
            "297361542190.dkr.ecr.us-east-1.amazonaws.com/topo-golden/topo@"
            "sha256:" + "f" * 64
        )
        result = CONTRACT.compare_contracts(source, live)
        self.assertEqual("CODIFIED_DIFFERENTLY", result["classification"])
        self.assertTrue(any(path.endswith(".image") for path in result["difference_paths"]))

    def test_required_service_spec_mismatch_is_codified_differently(self) -> None:
        source = source_contract()
        live = matching_live(source)
        edge = next(
            item for item in live["services"]
            if item["metadata"]["name"] == "topo-backend-edge"
        )
        edge["ports"][0]["node_port"] = 32099
        result = CONTRACT.compare_contracts(source, live)
        self.assertEqual("CODIFIED_DIFFERENTLY", result["classification"])
        self.assertTrue(any("node_port" in path for path in result["difference_paths"]))

    def test_required_live_workload_without_source_is_live_only_required(self) -> None:
        source = source_contract()
        live = matching_live(source)
        extra = copy.deepcopy(live["deployments"][0])
        extra["metadata"]["name"] = "topo-live-only"
        live["deployments"].append(extra)
        result = CONTRACT.compare_contracts(source, live)
        self.assertEqual("LIVE_ONLY_REQUIRED", result["classification"])
        self.assertTrue(any("topo-live-only" in item for item in result["live_only_required_objects"]))

    def test_unresolved_required_image_is_unknown_required(self) -> None:
        source = source_contract()
        live = matching_live(source)
        live["deployments"][0]["pod_template"]["containers"][0]["image"] = None
        result = CONTRACT.compare_contracts(source, live)
        self.assertEqual("UNKNOWN_REQUIRED", result["classification"])
        self.assertTrue(any(path.endswith(".image") for path in result["unresolved_required_paths"]))

    def test_current_replica_shape_false_positive_is_match_only_on_semantic_agreement(self) -> None:
        source = source_contract()
        live = matching_live(source)
        replicas = {
            item["metadata"]["name"]: item["replicas"]
            for item in live["deployments"]
        }
        self.assertEqual(
            {"topo-backend": 2, "topo-frontend": 2, "topo-observer": 1},
            replicas,
        )
        result = CONTRACT.compare_contracts(source, live)
        self.assertEqual("MATCH", result["classification"])
        changed = copy.deepcopy(live)
        changed["deployments"][0]["pod_template"]["service_account_name"] = "wrong"
        self.assertEqual(
            "CODIFIED_DIFFERENTLY",
            CONTRACT.compare_contracts(source, changed)["classification"],
        )

    def test_source_contract_never_contains_secret_values(self) -> None:
        source = source_contract()
        rendered = str(source)
        self.assertFalse(source["secret_values_emitted"])
        self.assertNotIn("database-url=", rendered)
        self.assertNotIn("agent-token=", rendered)
        self.assertIn("secretKeyRef", rendered)


if __name__ == "__main__":
    unittest.main()
