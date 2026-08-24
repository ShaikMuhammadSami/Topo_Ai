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

from evaluation.oci_artifact_identity import (
    DescriptorRole,
    OCI_RUNTIME_IDENTITY_VERSION,
    ProviderVerificationSource,
    RuntimeIdentityMatch,
    deterministic_identity_json,
    digest_from_immutable_ref,
    digest_from_runtime_image_id,
    normalize_digest,
    platform_value,
    provider_descriptor,
    resolve_runtime_artifact_identity,
)
from evaluation.runtime_causal_observer import (
    RUNTIME_CAUSAL_RECEIPT_V2_VERSION,
    provider_index_digest,
    validate_runtime_causal_receipt,
)


ROOT = Path(__file__).resolve().parents[2]
INDEX = "sha256:" + "1" * 64
CHILD = "sha256:" + "2" * 64
OTHER = "sha256:" + "3" * 64
ATTESTATION = "sha256:" + "4" * 64
IMAGE = f"registry.example/evaluation/image@{INDEX}"
PLATFORM = {"os": "linux", "architecture": "amd64", "variant": None}
IMAGE_MEDIA_TYPE = "application/vnd.oci.image.manifest.v1+json"
PARENT = "f9b152133a8075428766dd48b3f752b255ec5270"
FAILURE = "4149b194c4c4fdfdcd402a157c5336ad59dfdbbe"
FROZEN_INDEX = "sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed"
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


def descriptor(
    *,
    digest: str = CHILD,
    parent: str = INDEX,
    role: DescriptorRole = DescriptorRole.EXECUTABLE_IMAGE,
    platform: dict[str, Any] | None = PLATFORM,
    verified: bool = True,
    source: ProviderVerificationSource | None = (
        ProviderVerificationSource.REGISTRY_MANIFEST_DESCRIPTOR
    ),
    media_type: str = IMAGE_MEDIA_TYPE,
) -> dict[str, Any]:
    return provider_descriptor(
        parent_index_digest=parent,
        digest=digest,
        media_type=media_type,
        role=role,
        platform=platform,
        provider_verified=verified,
        provider_verification_source=source,
        annotations={},
        topo_output_used=False,
    )


def resolve(
    *,
    runtime_digest: str = CHILD,
    descriptors: list[dict[str, Any]] | None = None,
    target_platform: dict[str, Any] = PLATFORM,
    image_id_prefix: str = "containerd://",
) -> dict[str, Any]:
    return resolve_runtime_artifact_identity(
        requested_immutable_ref=IMAGE,
        runtime_image_id=f"{image_id_prefix}{runtime_digest}",
        target_platform=target_platform,
        provider_descriptors=(descriptors if descriptors is not None else [descriptor()]),
    )


def v2_receipt(resolution: dict[str, Any] | None = None) -> dict[str, Any]:
    resolution = resolution or resolve()
    return {
        "schema_version": RUNTIME_CAUSAL_RECEIPT_V2_VERSION,
        "experiment": {
            "run_id": 1,
            "source_parent_commit": "a" * 40,
            "source_failure_commit": "b" * 40,
            "requested_artifact": {
                "immutable_ref": IMAGE,
                "index_digest": INDEX,
            },
        },
        "kubernetes": {
            "context": "docker-desktop",
            "cluster": "docker-desktop",
            "namespace": "topo-eval-lineage-causal-1",
            "namespace_uid": "namespace-uid",
            "deployment_name": "lineage-causal-fixture",
            "deployment_uid": "deployment-uid",
            "replicaset_name": "fixture-rs",
            "replicaset_uid": "replicaset-uid",
            "pod_name": "fixture-pod",
            "pod_uid": "pod-uid",
        },
        "ownership": {
            "replicaset_owner_deployment_uid": "deployment-uid",
            "pod_owner_replicaset_uid": "replicaset-uid",
        },
        "container": {
            "name": "fixture",
            "image": IMAGE,
            "image_id": resolution["runtime_image_id"],
            "runtime_digest": resolution["runtime_digest"],
            "restart_count": 2,
            "waiting_reason": "CrashLoopBackOff",
            "current_state": "waiting",
            "last_termination_reason": "Error",
            "last_termination_exit_code": 42,
            "last_termination_started_at": "2026-08-24T10:00:00Z",
            "last_termination_finished_at": "2026-08-24T10:00:01Z",
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
        "artifact_resolution": resolution,
        "observation": {
            "started_at": "2026-08-24T09:59:00Z",
            "failure_confirmed_at": "2026-08-24T10:00:02Z",
            "captured_at": "2026-08-24T10:00:03Z",
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
        assert set(schema.get("required") or []).issubset(value)
        properties = schema.get("properties") or {}
        if schema.get("additionalProperties") is False:
            assert set(value).issubset(properties)
        for key, item in value.items():
            if key in properties:
                validate_schema(item, properties[key], root)
    if isinstance(value, list) and "items" in schema:
        for item in value:
            validate_schema(item, schema["items"], root)
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


def test_exact_requested_index_digest_is_accepted():
    result = resolve(runtime_digest=INDEX, descriptors=[])
    assert result["match_type"] == RuntimeIdentityMatch.EXACT_INDEX.value
    assert result["accepted"] is True


def test_exact_immutable_index_reference_is_required():
    assert digest_from_immutable_ref(IMAGE) == INDEX


@pytest.mark.parametrize("value", ["repo/image:latest", "repo/image", "repo/image@sha256:bad"])
def test_mutable_or_malformed_reference_is_rejected(value: str):
    with pytest.raises(ValueError, match="immutable"):
        digest_from_immutable_ref(value)


def test_runtime_image_id_exact_index_is_accepted():
    result = resolve(runtime_digest=INDEX, descriptors=[])
    assert result["runtime_digest"] == INDEX
    assert result["accepted"] is True


def test_verified_linux_amd64_child_manifest_is_accepted():
    result = resolve()
    assert result["match_type"] == RuntimeIdentityMatch.VERIFIED_PLATFORM_MANIFEST.value
    assert result["accepted"] is True


def test_child_digest_must_belong_to_exact_requested_index():
    result = resolve(descriptors=[descriptor(parent=OTHER)])
    assert result["accepted"] is False
    assert result["match_type"] == RuntimeIdentityMatch.MISMATCH.value


def test_same_child_associated_only_with_another_index_is_rejected():
    result = resolve(descriptors=[descriptor(parent=OTHER)])
    assert "different OCI index" in result["reason"]


def test_unrelated_manifest_is_rejected():
    result = resolve(descriptors=[descriptor(digest=OTHER)])
    assert result["accepted"] is False
    assert result["descriptor_digest"] is None


def test_attestation_manifest_is_rejected():
    result = resolve(descriptors=[descriptor(role=DescriptorRole.ATTESTATION)])
    assert result["accepted"] is False
    assert result["descriptor_role"] == DescriptorRole.ATTESTATION.value


@pytest.mark.parametrize("role", [DescriptorRole.SBOM, DescriptorRole.PROVENANCE])
def test_non_executable_evidence_descriptor_is_rejected(role: DescriptorRole):
    result = resolve(descriptors=[descriptor(role=role)])
    assert result["accepted"] is False
    assert result["executable_manifest"] is False


def test_missing_provider_descriptor_proof_is_rejected():
    result = resolve(descriptors=[])
    assert result["accepted"] is False


def test_provider_verified_false_is_rejected_for_child_path():
    result = resolve(descriptors=[descriptor(verified=False, source=None)])
    assert result["match_type"] == RuntimeIdentityMatch.UNVERIFIED.value
    assert result["accepted"] is False


def test_verified_descriptor_requires_provider_source():
    with pytest.raises(ValueError, match="provider source"):
        descriptor(verified=True, source=None)


def test_missing_platform_is_unverified_for_child_path():
    result = resolve(descriptors=[descriptor(platform=None)])
    assert result["match_type"] == RuntimeIdentityMatch.UNVERIFIED.value


def test_platform_mismatch_is_rejected():
    result = resolve(
        descriptors=[descriptor(platform={"os": "linux", "architecture": "arm64"})]
    )
    assert result["match_type"] == RuntimeIdentityMatch.MISMATCH.value


def test_explicit_linux_amd64_platform_matches():
    result = resolve()
    assert result["target_platform"] == PLATFORM
    assert result["descriptor_platform"] == PLATFORM


@pytest.mark.parametrize(
    "image_id",
    [
        f"containerd://{CHILD}",
        f"docker-pullable://registry.example/repo@{CHILD}",
        CHILD,
        f"registry.example/repo@{CHILD}",
    ],
)
def test_common_runtime_image_id_forms_parse_exactly(image_id: str):
    assert digest_from_runtime_image_id(image_id) == CHILD


@pytest.mark.parametrize(
    "image_id",
    [
        "",
        "sha256:bad",
        "image:latest",
        "sha512:" + "a" * 128,
        "sha256:" + "a" * 65,
        "sha256:" + "a" * 64 + "g",
    ],
)
def test_malformed_runtime_digest_is_rejected(image_id: str):
    with pytest.raises(ValueError):
        digest_from_runtime_image_id(image_id)


def test_multiple_conflicting_runtime_digests_are_rejected():
    with pytest.raises(ValueError, match="conflicting"):
        digest_from_runtime_image_id(f"{CHILD} {OTHER}")


def test_digest_normalization_is_deterministic():
    uppercase = "SHA256:" + "A" * 64
    assert normalize_digest(uppercase) == normalize_digest(uppercase)
    assert normalize_digest(uppercase) == "sha256:" + "a" * 64


def test_runtime_receipt_records_index_and_runtime_manifest_separately():
    receipt = v2_receipt()
    validate_runtime_causal_receipt(receipt)
    assert receipt["experiment"]["requested_artifact"]["index_digest"] == INDEX
    assert receipt["container"]["runtime_digest"] == CHILD


def test_receipt_records_provider_verification_source():
    receipt = v2_receipt()
    assert receipt["artifact_resolution"]["provider_verification_source"] == (
        ProviderVerificationSource.REGISTRY_MANIFEST_DESCRIPTOR.value
    )


def test_receipt_records_platform():
    assert v2_receipt()["artifact_resolution"]["target_platform"] == PLATFORM


def test_receipt_records_descriptor_media_type_and_role():
    resolution = v2_receipt()["artifact_resolution"]
    assert resolution["descriptor_media_type"] == IMAGE_MEDIA_TYPE
    assert resolution["descriptor_role"] == DescriptorRole.EXECUTABLE_IMAGE.value


@pytest.mark.parametrize(
    "resolution",
    [
        lambda: resolve(runtime_digest=INDEX, descriptors=[]),
        lambda: resolve(),
        lambda: resolve(descriptors=[]),
    ],
)
def test_identity_result_serialization_is_deterministic(resolution):
    result = resolution()
    assert deterministic_identity_json(result) == deterministic_identity_json(result)


def test_exact_index_does_not_fabricate_child_descriptor():
    result = resolve(runtime_digest=INDEX, descriptors=[])
    assert result["descriptor_digest"] is None
    assert result["provider_verification_source"] is None


def test_child_manifest_does_not_change_provider_index_identity():
    result = resolve()
    assert result["requested_index_digest"] == INDEX
    assert result["runtime_digest"] == CHILD


def test_source_cause_match_remains_anchored_to_index_digest():
    receipt = v2_receipt()
    assert provider_index_digest(receipt) == INDEX
    source = (ROOT / "evaluation/source_cause_match.py").read_text(encoding="utf-8")
    assert "provider_index_digest(runtime_receipt)" in source


def test_topo_output_is_not_used_to_establish_descriptor_truth():
    assert descriptor()["topo_output_used"] is False
    assert resolve()["topo_output_used"] is False


def test_identity_helper_imports_no_product_modules():
    source = (ROOT / "evaluation/oci_artifact_identity.py").read_text(encoding="utf-8")
    assert "backend.app" not in source


@pytest.mark.parametrize("forbidden", ["fuzzywuzzy", "rapidfuzz", "openai", "embedding"])
def test_identity_helper_contains_no_fuzzy_llm_or_embedding_dependency(forbidden: str):
    source = (ROOT / "evaluation/oci_artifact_identity.py").read_text(encoding="utf-8").lower()
    assert forbidden not in source


def test_existing_exit_code_gate_is_unchanged():
    receipt = v2_receipt()
    receipt["container"]["last_termination_exit_code"] = 1
    with pytest.raises(ValueError, match="exit code 42"):
        validate_runtime_causal_receipt(receipt)


def test_existing_ownership_uid_gate_is_unchanged():
    receipt = v2_receipt()
    receipt["ownership"]["pod_owner_replicaset_uid"] = "wrong"
    with pytest.raises(ValueError, match="owner-reference"):
        validate_runtime_causal_receipt(receipt)


@pytest.mark.parametrize("field,bad", [("desired_replicas", 2), ("ready_replicas", 1), ("available_replicas", 1)])
def test_existing_deployment_impact_gate_is_unchanged(field: str, bad: int):
    receipt = v2_receipt()
    receipt["deployment_status"][field] = bad
    with pytest.raises(ValueError, match="replica"):
        validate_runtime_causal_receipt(receipt)


def test_unproven_artifact_keeps_runtime_receipt_inconclusive():
    receipt = v2_receipt(resolve(descriptors=[]))
    with pytest.raises(ValueError, match="inconclusive"):
        validate_runtime_causal_receipt(receipt)


def test_frozen_failure_commit_values_remain_unchanged():
    parents = subprocess.run(
        ["git", "rev-list", "--parents", "-n", "1", FAILURE],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip().split()
    assert parents == [FAILURE, PARENT]


def test_frozen_provider_index_digest_remains_unchanged():
    assert FROZEN_INDEX == "sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed"


@pytest.mark.parametrize("literal", ["a7616346", "48d64298", "df2b5e62", "32695735269"])
def test_generic_identity_implementation_has_no_frozen_special_case(literal: str):
    source = (ROOT / "evaluation/oci_artifact_identity.py").read_text(encoding="utf-8")
    assert literal not in source


def test_backend_and_other_product_paths_are_untouched():
    output = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", "backend/app", "backend/tests", "agent/src", "frontend", "cli/src"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert output == ""


def test_workflows_are_untouched():
    output = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", ".github/workflows"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert output == ""
    workflow = ROOT / ".github/workflows/topo-lineage-provider-fixture.yml"
    assert hashlib.sha256(workflow.read_bytes()).hexdigest() == WORKFLOW_SHA256


@pytest.mark.parametrize("name,expected", sorted(PERMANENT_MANIFEST_HASHES.items()))
def test_permanent_manifest_is_unchanged(name: str, expected: str):
    actual = subprocess.run(
        ["git", "hash-object", f"evaluation/manifests/{name}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert actual == expected


def test_identity_helper_has_no_kubernetes_or_provider_mutation_capability():
    source = (ROOT / "evaluation/oci_artifact_identity.py").read_text(encoding="utf-8").lower()
    for forbidden in ("subprocess", "kubectl", "docker pull", "gh api", "requests", "urllib"):
        assert forbidden not in source


def test_v2_schema_validates_complete_platform_manifest_receipt():
    schema = json.loads(
        (ROOT / "docs/architecture/evaluation/runtime-causal-receipt-v2.schema.json").read_text()
    )
    validate_schema(v2_receipt(), schema, schema)


def test_v2_schema_validates_complete_exact_index_receipt():
    schema = json.loads(
        (ROOT / "docs/architecture/evaluation/runtime-causal-receipt-v2.schema.json").read_text()
    )
    validate_schema(v2_receipt(resolve(runtime_digest=INDEX, descriptors=[])), schema, schema)


def test_v2_schema_is_strict_and_versioned():
    schema = json.loads(
        (ROOT / "docs/architecture/evaluation/runtime-causal-receipt-v2.schema.json").read_text()
    )
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == RUNTIME_CAUSAL_RECEIPT_V2_VERSION
    assert OCI_RUNTIME_IDENTITY_VERSION == "eval-oci-runtime-identity-v1"


def test_explicit_platform_constructor_is_deterministic():
    assert platform_value(os_name="LINUX", architecture="AMD64") == PLATFORM
