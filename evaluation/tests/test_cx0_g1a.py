from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from evaluation.cx0_g1a import (
    BASE_IMAGE_DIGEST,
    FIXTURE_IMAGE_REPOSITORY,
    FIXTURE_REPOSITORY,
    G1AContractError,
    HEALTHY_ACTIONS_RUN_ATTEMPT,
    HEALTHY_ACTIONS_RUN_ID,
    HEALTHY_FIXTURE_COMMIT,
    HEALTHY_IMAGE_DIGEST,
    HEALTHY_IMAGE_URI,
    MANIFEST_PATH,
    control_plane_fingerprint,
    recovery_command,
    validate_provider_receipt,
    validate_uid_chain,
    validate_workload_manifest,
)


def _receipt() -> dict[str, object]:
    return {
        "schema_version": "topoai-golden-provider-build-receipt-v1",
        "repository": FIXTURE_REPOSITORY,
        "workflow_name": "Build Golden Fixture Image",
        "workflow_file": ".github/workflows/build-image.yml",
        "run_id": HEALTHY_ACTIONS_RUN_ID,
        "run_attempt": HEALTHY_ACTIONS_RUN_ATTEMPT,
        "source_commit": HEALTHY_FIXTURE_COMMIT,
        "source_ref": "refs/heads/main",
        "image_repository": FIXTURE_IMAGE_REPOSITORY,
        "image_digest": HEALTHY_IMAGE_DIGEST,
        "image_uri_by_digest": HEALTHY_IMAGE_URI,
        "base_image_digest": BASE_IMAGE_DIGEST,
        "build_started_or_observed_utc": "2026-09-28T19:12:23Z",
        "build_completed_utc": "2026-09-28T19:12:42Z",
    }


def _resource(kind: str, uid: str, image: str = HEALTHY_IMAGE_URI) -> dict[str, object]:
    resource: dict[str, object] = {
        "apiVersion": "v1",
        "kind": kind,
        "metadata": {"name": kind.casefold(), "uid": uid},
        "spec": {},
    }
    if kind == "Deployment":
        resource["metadata"] = {"name": "topo-golden-fixture", "uid": uid, "generation": 1}
        resource["spec"] = {"template": {"spec": {"containers": [{"name": "fixture", "image": image}]}}}
    elif kind == "ReplicaSet":
        resource["metadata"] = {
            "name": "topo-golden-fixture-abc",
            "uid": uid,
            "ownerReferences": [{"controller": True, "kind": "Deployment", "uid": "deployment-uid"}],
        }
        resource["spec"] = {"template": {"spec": {"containers": [{"name": "fixture", "image": image}]}}}
    else:
        resource["metadata"] = {
            "name": "topo-golden-fixture-abc-12345",
            "uid": uid,
            "ownerReferences": [{"controller": True, "kind": "ReplicaSet", "uid": "replicaset-uid"}],
        }
        resource["spec"] = {"containers": [{"name": "fixture", "image": image}]}
    return resource


def test_manifest_is_exactly_the_isolated_healthy_workload() -> None:
    result = validate_workload_manifest(json.loads(MANIFEST_PATH.read_text(encoding="utf-8")))
    assert result == {
        "namespace": "topo-eval",
        "deployment": "topo-golden-fixture",
        "container": "fixture",
        "image": HEALTHY_IMAGE_URI,
    }


def test_manifest_has_no_secret_or_shared_control_plane_authority() -> None:
    text = MANIFEST_PATH.read_text(encoding="utf-8")
    assert '"imagePullSecrets"' not in text
    assert '"topo-system"' not in text
    assert '"kind": "ClusterRole"' not in text
    assert '"kind": "ClusterRoleBinding"' not in text
    assert '"kind": "Secret"' not in text


def test_accepted_provider_receipt_is_strictly_bound() -> None:
    result = validate_provider_receipt(
        _receipt(),
        expected_commit=HEALTHY_FIXTURE_COMMIT,
        expected_run_id=HEALTHY_ACTIONS_RUN_ID,
        expected_run_attempt=HEALTHY_ACTIONS_RUN_ATTEMPT,
        expected_image_digest=HEALTHY_IMAGE_DIGEST,
    )
    assert result["image_uri_by_digest"] == HEALTHY_IMAGE_URI


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("repository", "customer/repository"),
        ("source_commit", "0" * 40),
        ("run_id", 1),
        ("image_digest", "sha256:" + "0" * 64),
        ("image_uri_by_digest", FIXTURE_IMAGE_REPOSITORY + ":latest"),
    ),
)
def test_provider_receipt_rejects_authority_substitution(field: str, value: object) -> None:
    receipt = _receipt()
    receipt[field] = value
    with pytest.raises(G1AContractError):
        validate_provider_receipt(
            receipt,
            expected_commit=HEALTHY_FIXTURE_COMMIT,
            expected_run_id=HEALTHY_ACTIONS_RUN_ID,
            expected_run_attempt=HEALTHY_ACTIONS_RUN_ATTEMPT,
            expected_image_digest=HEALTHY_IMAGE_DIGEST,
        )


def test_uid_chain_requires_exact_controller_uids_and_digest() -> None:
    result = validate_uid_chain(
        _resource("Deployment", "deployment-uid"),
        _resource("ReplicaSet", "replicaset-uid"),
        _resource("Pod", "pod-uid"),
        expected_image_uri=HEALTHY_IMAGE_URI,
    )
    assert result["uid_owner_chain_exact"] is True
    assert result["deployment_uid"] == "deployment-uid"
    assert result["replica_set_uid"] == "replicaset-uid"
    assert result["pod_uid"] == "pod-uid"


def test_uid_chain_rejects_name_only_or_wrong_owner_identity() -> None:
    replica_set = _resource("ReplicaSet", "replicaset-uid")
    replica_set["metadata"]["ownerReferences"][0]["uid"] = "different-deployment-uid"
    with pytest.raises(G1AContractError):
        validate_uid_chain(
            _resource("Deployment", "deployment-uid"),
            replica_set,
            _resource("Pod", "pod-uid"),
            expected_image_uri=HEALTHY_IMAGE_URI,
        )


def test_uid_chain_rejects_tag_or_requested_digest_substitution() -> None:
    pod = _resource("Pod", "pod-uid")
    pod["spec"]["containers"][0]["image"] = FIXTURE_IMAGE_REPOSITORY + ":main"
    with pytest.raises(G1AContractError):
        validate_uid_chain(
            _resource("Deployment", "deployment-uid"),
            _resource("ReplicaSet", "replicaset-uid"),
            pod,
            expected_image_uri=HEALTHY_IMAGE_URI,
        )


def test_control_plane_fingerprint_is_order_independent_and_status_sensitive() -> None:
    deployments = [
        {
            "metadata": {"name": name, "uid": f"uid-{name}", "generation": 1},
            "spec": {"replicas": replicas, "template": {"spec": {"containers": [{"image": f"example/{name}@sha256:{'1' * 64}"}]}}},
            "status": {"observedGeneration": 1, "readyReplicas": replicas, "availableReplicas": replicas, "updatedReplicas": replicas},
        }
        for name, replicas in (("topo-backend", 2), ("topo-frontend", 2), ("topo-observer", 1))
    ]
    original = control_plane_fingerprint(deployments)
    assert control_plane_fingerprint(list(reversed(deployments))) == original
    changed = deepcopy(deployments)
    changed[0]["status"]["readyReplicas"] = 1
    assert control_plane_fingerprint(changed) != original


def test_recovery_command_is_fully_guarded_and_digest_pinned() -> None:
    command = recovery_command()
    assert "--context topo-golden" in command
    assert "-n topo-eval" in command
    assert "deployment/topo-golden-fixture" in command
    assert f"fixture={HEALTHY_IMAGE_URI}" in command
    assert "rollout undo" not in command
    assert ":latest" not in command


def test_g1a_adapter_does_not_import_product_causal_services() -> None:
    source = (Path(__file__).resolve().parents[1] / "cx0_g1a.py").read_text(encoding="utf-8")
    assert "backend.app" not in source
    assert "app.services" not in source
    assert "causal_support_gate" not in source
    assert "causal_hypothesis_projection" not in source
