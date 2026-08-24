from __future__ import annotations

import copy
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from evaluation.oci_artifact_identity import (
    DescriptorRole,
    ProviderVerificationSource,
    RuntimeIdentityMatch,
    provider_descriptor,
)
from evaluation.runtime_causal_observer import (
    CONTAINER_NAME,
    _container_pair,
    _runtime_sample,
    _sample_complete,
    observe_runtime_causal_truth,
    provider_index_digest,
    validate_runtime_causal_receipt,
)


ROOT = Path(__file__).resolve().parents[2]
POD_FIXTURE = (
    ROOT
    / "evaluation/fixtures/kubernetes-runtime-image-fields/"
    "docker-desktop-containerd-pod.json"
)
INDEX = "sha256:" + "1" * 64
MANIFEST = "sha256:" + "2" * 64
OTHER = "sha256:" + "3" * 64
CONFIG = "sha256:" + "9" * 64
IMAGE = f"registry.example/evaluation/image@{INDEX}"
PLATFORM = {"os": "linux", "architecture": "amd64", "variant": None}
IMAGE_MEDIA_TYPE = "application/vnd.oci.image.manifest.v1+json"


def pod_fixture() -> dict[str, Any]:
    return json.loads(POD_FIXTURE.read_text(encoding="utf-8"))


def main_spec(pod: dict[str, Any]) -> dict[str, Any]:
    return next(
        item for item in pod["spec"]["containers"] if item["name"] == CONTAINER_NAME
    )


def main_status(pod: dict[str, Any]) -> dict[str, Any]:
    return next(
        item
        for item in pod["status"]["containerStatuses"]
        if item["name"] == CONTAINER_NAME
    )


def executable_descriptor() -> dict[str, Any]:
    return provider_descriptor(
        parent_index_digest=INDEX,
        digest=MANIFEST,
        media_type=IMAGE_MEDIA_TYPE,
        role=DescriptorRole.EXECUTABLE_IMAGE,
        platform=PLATFORM,
        provider_verified=True,
        provider_verification_source=(
            ProviderVerificationSource.REGISTRY_MANIFEST_DESCRIPTOR
        ),
        annotations={},
        topo_output_used=False,
    )


class FakeKubectl:
    def __init__(self, pod: dict[str, Any]) -> None:
        self.pod = pod
        self.namespace = {
            "metadata": {
                "name": "topo-eval-lineage-causal-1",
                "uid": "namespace-uid",
            }
        }
        self.deployment = {
            "metadata": {
                "name": "lineage-causal-fixture",
                "uid": "deployment-uid",
            },
            "spec": {"replicas": 1},
            "status": {"unavailableReplicas": 1},
        }
        self.replica_set = {
            "metadata": {
                "creationTimestamp": "2026-01-01T00:00:00Z",
                "name": "fixture-rs",
                "uid": "replicaset-uid",
                "ownerReferences": [
                    {
                        "controller": True,
                        "kind": "Deployment",
                        "uid": "deployment-uid",
                    }
                ],
            }
        }

    def get_json(self, *arguments: str) -> dict[str, Any]:
        resource = arguments[0]
        if resource == "namespace":
            return copy.deepcopy(self.namespace)
        if resource == "deployment":
            return copy.deepcopy(self.deployment)
        if resource == "replicasets":
            return {"items": [copy.deepcopy(self.replica_set)]}
        if resource == "pods":
            return {"items": [copy.deepcopy(self.pod)]}
        if resource == "events":
            return {"items": []}
        raise AssertionError(f"Unexpected fake Kubernetes resource: {resource}")


def runtime_sample(
    pod: dict[str, Any] | None = None,
    *,
    descriptors: list[dict[str, Any]] | None = None,
    kubectl: FakeKubectl | None = None,
) -> dict[str, Any] | None:
    fake = kubectl or FakeKubectl(pod or pod_fixture())
    return _runtime_sample(
        fake,
        namespace="topo-eval-lineage-causal-1",
        immutable_image_ref=IMAGE,
        target_platform=PLATFORM,
        provider_descriptors=descriptors or [],
    )


def runtime_receipt(
    pod: dict[str, Any] | None = None,
    *,
    descriptors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    timestamps = iter(
        [
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:03Z",
            "2026-01-01T00:00:04Z",
        ]
    )
    return observe_runtime_causal_truth(
        FakeKubectl(pod or pod_fixture()),
        run_id=1,
        source_parent_commit="a" * 40,
        source_failure_commit="b" * 40,
        immutable_image_ref=IMAGE,
        context="docker-desktop",
        cluster="docker-desktop",
        target_platform=PLATFORM,
        provider_descriptors=descriptors or [],
        timeout_seconds=1,
        poll_interval_seconds=0,
        now=lambda: next(timestamps),
    )


def _is_type(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }[expected]


def validate_schema(value: Any, schema: dict[str, Any], root: dict[str, Any]) -> None:
    if "$ref" in schema:
        target: Any = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        validate_schema(value, target, root)
        return
    if "oneOf" in schema:
        matches = 0
        for candidate in schema["oneOf"]:
            try:
                validate_schema(value, candidate, root)
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
        required = set(schema.get("required") or [])
        properties = schema.get("properties") or {}
        assert required.issubset(value)
        if schema.get("additionalProperties") is False:
            assert set(value).issubset(properties)
        for key, item in value.items():
            if key in properties:
                validate_schema(item, properties[key], root)
    if isinstance(value, str):
        if "minLength" in schema:
            assert len(value) >= schema["minLength"]
        if "pattern" in schema:
            assert re.fullmatch(schema["pattern"], value)
        if schema.get("format") == "date-time":
            datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(value, int) and not isinstance(value, bool):
        if "minimum" in schema:
            assert value >= schema["minimum"]
        if "maximum" in schema:
            assert value <= schema["maximum"]


def test_realistic_containerd_sample_uses_spec_request_and_image_id_identity():
    sample = runtime_sample()
    assert sample is not None
    assert sample["spec_container"]["image"] == IMAGE
    assert sample["status"]["imageID"].endswith(INDEX)
    assert sample["status"]["image"] == CONFIG
    assert sample["facts"]["requested_image_ref_matches"] is True
    assert sample["artifact_resolution"]["match_type"] == (
        RuntimeIdentityMatch.EXACT_INDEX.value
    )
    assert _sample_complete(sample) is True


def test_realistic_containerd_receipt_records_status_image_diagnostically():
    receipt = runtime_receipt()
    assert receipt["container"]["image"] == IMAGE
    assert receipt["container"]["runtime_status_image"] == CONFIG
    assert receipt["container"]["image_id"].endswith(INDEX)
    validate_runtime_causal_receipt(receipt)


def test_verified_platform_manifest_ignores_different_status_config_digest():
    pod = pod_fixture()
    main_status(pod)["imageID"] = f"containerd://{MANIFEST}"
    sample = runtime_sample(pod, descriptors=[executable_descriptor()])
    assert sample is not None
    assert sample["status"]["image"] == CONFIG
    assert sample["artifact_resolution"]["match_type"] == (
        RuntimeIdentityMatch.VERIFIED_PLATFORM_MANIFEST.value
    )
    assert _sample_complete(sample) is True
    validate_runtime_causal_receipt(
        runtime_receipt(pod, descriptors=[executable_descriptor()])
    )


@pytest.mark.parametrize(
    "requested",
    [
        "registry.example/evaluation/image:latest",
        f"registry.example/evaluation/image@{OTHER}",
    ],
)
def test_mutable_or_wrong_pod_spec_request_fails_closed(requested: str):
    pod = pod_fixture()
    main_spec(pod)["image"] = requested
    sample = runtime_sample(pod)
    assert sample is not None
    assert sample["facts"]["requested_image_ref_matches"] is False
    assert _sample_complete(sample) is False


def test_unrelated_runtime_image_id_is_rejected():
    pod = pod_fixture()
    main_status(pod)["imageID"] = f"containerd://{OTHER}"
    sample = runtime_sample(pod)
    assert sample is not None
    assert sample["artifact_resolution"]["match_type"] == RuntimeIdentityMatch.MISMATCH.value
    assert _sample_complete(sample) is False


def test_unverified_child_runtime_image_id_is_rejected():
    pod = pod_fixture()
    main_status(pod)["imageID"] = f"containerd://{MANIFEST}"
    sample = runtime_sample(pod)
    assert sample is not None
    assert sample["artifact_resolution"]["match_type"] == RuntimeIdentityMatch.MISMATCH.value
    assert _sample_complete(sample) is False


def test_attestation_runtime_image_id_remains_rejected():
    pod = pod_fixture()
    main_status(pod)["imageID"] = f"containerd://{MANIFEST}"
    attestation = executable_descriptor()
    attestation["role"] = DescriptorRole.ATTESTATION.value
    sample = runtime_sample(pod, descriptors=[attestation])
    assert sample is not None
    assert sample["artifact_resolution"]["match_type"] == RuntimeIdentityMatch.MISMATCH.value
    assert sample["artifact_resolution"]["accepted"] is False


def test_exact_named_container_pair_succeeds_regardless_of_array_order():
    pod = pod_fixture()
    pod["spec"]["containers"].reverse()
    pod["status"]["containerStatuses"].reverse()
    pair = _container_pair(pod)
    assert pair is not None
    assert pair[0]["name"] == pair[1]["name"] == CONTAINER_NAME
    assert _sample_complete(runtime_sample(pod)) is True


@pytest.mark.parametrize("section", ["spec", "status"])
def test_missing_named_container_fails_closed(section: str):
    pod = pod_fixture()
    key = "containers" if section == "spec" else "containerStatuses"
    pod[section][key] = [
        item for item in pod[section][key] if item["name"] != CONTAINER_NAME
    ]
    assert _container_pair(pod) is None
    assert runtime_sample(pod) is None


@pytest.mark.parametrize("section", ["spec", "status"])
def test_duplicate_named_container_is_ambiguous_and_fails_closed(section: str):
    pod = pod_fixture()
    key = "containers" if section == "spec" else "containerStatuses"
    matching = next(item for item in pod[section][key] if item["name"] == CONTAINER_NAME)
    pod[section][key].append(copy.deepcopy(matching))
    assert _container_pair(pod) is None
    assert runtime_sample(pod) is None


def test_sidecar_image_id_cannot_satisfy_main_container_identity():
    pod = pod_fixture()
    main_status(pod)["imageID"] = f"containerd://{OTHER}"
    sidecar = next(
        item for item in pod["status"]["containerStatuses"] if item["name"] == "sidecar"
    )
    sidecar["imageID"] = f"containerd://{INDEX}"
    sample = runtime_sample(pod)
    assert sample is not None
    assert sample["artifact_resolution"]["accepted"] is False


def test_sidecar_status_image_cannot_contaminate_main_diagnostic():
    pod = pod_fixture()
    sidecar = next(
        item for item in pod["status"]["containerStatuses"] if item["name"] == "sidecar"
    )
    sidecar["image"] = IMAGE
    receipt = runtime_receipt(pod)
    assert receipt["container"]["runtime_status_image"] == CONFIG


def test_missing_status_image_does_not_invalidate_authoritative_proof():
    pod = pod_fixture()
    main_status(pod).pop("image")
    sample = runtime_sample(pod)
    assert _sample_complete(sample) is True
    receipt = runtime_receipt(pod)
    assert receipt["container"]["runtime_status_image"] is None
    validate_runtime_causal_receipt(receipt)


def test_malformed_status_image_text_is_diagnostic_only():
    pod = pod_fixture()
    main_status(pod)["image"] = "not-an-image-reference"
    sample = runtime_sample(pod)
    assert _sample_complete(sample) is True
    receipt = runtime_receipt(pod)
    assert receipt["container"]["runtime_status_image"] == "not-an-image-reference"
    validate_runtime_causal_receipt(receipt)


def test_historical_v2_receipt_without_optional_status_image_remains_valid():
    receipt = runtime_receipt()
    receipt["container"].pop("runtime_status_image")
    validate_runtime_causal_receipt(receipt)


def test_realistic_v2_receipt_validates_against_machine_schema():
    receipt = runtime_receipt()
    schema = json.loads(
        (
            ROOT
            / "docs/architecture/evaluation/runtime-causal-receipt-v2.schema.json"
        ).read_text(encoding="utf-8")
    )
    validate_schema(receipt, schema, schema)


@pytest.mark.parametrize(
    "gate",
    ["exit_code", "restart", "backoff", "desired", "ready", "ownership"],
)
def test_existing_runtime_causal_gates_remain_fail_closed(gate: str):
    pod = pod_fixture()
    fake = FakeKubectl(pod)
    if gate == "exit_code":
        main_status(pod)["lastState"]["terminated"]["exitCode"] = 1
    elif gate == "restart":
        main_status(pod)["restartCount"] = 0
    elif gate == "backoff":
        main_status(pod)["state"] = {"running": {"startedAt": "2026-01-01T00:00:02Z"}}
    elif gate == "desired":
        fake.deployment["spec"]["replicas"] = 2
    elif gate == "ready":
        fake.deployment["status"]["readyReplicas"] = 1
    else:
        pod["metadata"]["ownerReferences"][0]["uid"] = "wrong-replicaset"
    assert _sample_complete(runtime_sample(pod, kubectl=fake)) is False


def test_requested_index_remains_provider_identity_for_child_runtime():
    pod = pod_fixture()
    main_status(pod)["imageID"] = f"containerd://{MANIFEST}"
    receipt = runtime_receipt(pod, descriptors=[executable_descriptor()])
    assert provider_index_digest(receipt) == INDEX
    assert receipt["container"]["runtime_digest"] == MANIFEST
    assert receipt["experiment"]["requested_artifact"]["index_digest"] == INDEX


def test_observer_uses_no_topo_fuzzy_llm_or_embedding_authority():
    source = (ROOT / "evaluation/runtime_causal_observer.py").read_text(
        encoding="utf-8"
    ).lower()
    assert "backend.app" not in source
    for forbidden in ("fuzzywuzzy", "rapidfuzz", "openai", "embedding"):
        assert forbidden not in source
    assert runtime_receipt()["topo_used_to_construct_truth"] is False


@pytest.mark.parametrize(
    "literal",
    [
        "32695735269",
        "a7616346acbcde6b",
        "a3392fbeae192e86",
        "48d64298dd20b76c",
    ],
)
def test_generic_observer_contains_no_frozen_experiment_literal(literal: str):
    source = (ROOT / "evaluation/runtime_causal_observer.py").read_text(
        encoding="utf-8"
    )
    assert literal not in source
