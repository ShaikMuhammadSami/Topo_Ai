from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence


FIXTURE_REPOSITORY = "ShaikMuhammadSami/topoai-golden-fixture"
FIXTURE_IMAGE_REPOSITORY = (
    "ghcr.io/shaikmuhammadsami/topoai-golden-fixture"
)
HEALTHY_FIXTURE_COMMIT = "78a9669b6977597d2d656c428fd64cde0866ed8c"
HEALTHY_ACTIONS_RUN_ID = 36470584042
HEALTHY_ACTIONS_RUN_ATTEMPT = 1
HEALTHY_IMAGE_DIGEST = (
    "sha256:590587b3f8d03e4ba71ab3d515827e6047b693bdf29c227fde5bd726461d4b32"
)
HEALTHY_IMAGE_URI = f"{FIXTURE_IMAGE_REPOSITORY}@{HEALTHY_IMAGE_DIGEST}"
BASE_IMAGE_DIGEST = (
    "sha256:b7f3d86d6e84fc17718c48bcde1450807faa2d56704205c697b4bd5df7b9e29f"
)
EVALUATION_NAMESPACE = "topo-eval"
EVALUATION_DEPLOYMENT = "topo-golden-fixture"
EVALUATION_CONTAINER = "fixture"
SCENARIO_ID = "G-POS-1"
MANIFEST_PATH = Path(__file__).resolve().parent / "golden/cx0/g_pos_1_workload.json"

_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_LABELS = {
    "topo.ai/evaluation": "cx0",
    "topo.ai/managed-by": "cx0-g1a",
    "topo.ai/scenario": SCENARIO_ID,
}


class G1AContractError(ValueError):
    """Raised when observed G1A evidence violates the frozen adapter contract."""


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise G1AContractError(f"JSON authority is not an object: {path}")
    return value


def _utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise G1AContractError("Provider receipt timestamp is missing.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise G1AContractError("Provider receipt timestamp lacks UTC authority.")
    return parsed


def _required_labels(value: Any, *, subject: str) -> None:
    if not isinstance(value, Mapping):
        raise G1AContractError(f"{subject} labels are missing.")
    for key, expected in _LABELS.items():
        if value.get(key) != expected:
            raise G1AContractError(f"{subject} label mismatch: {key}")


def validate_workload_manifest(
    manifest: Mapping[str, Any],
) -> dict[str, str]:
    if manifest.get("apiVersion") != "v1" or manifest.get("kind") != "List":
        raise G1AContractError("G1A workload must be one Kubernetes List.")
    items = manifest.get("items")
    if not isinstance(items, list) or len(items) != 2:
        raise G1AContractError("G1A workload must contain Namespace and Deployment only.")
    namespace = next(
        (item for item in items if isinstance(item, Mapping) and item.get("kind") == "Namespace"),
        None,
    )
    deployment = next(
        (item for item in items if isinstance(item, Mapping) and item.get("kind") == "Deployment"),
        None,
    )
    if namespace is None or deployment is None:
        raise G1AContractError("Namespace or Deployment is missing from G1A workload.")

    namespace_meta = namespace.get("metadata") or {}
    if namespace_meta.get("name") != EVALUATION_NAMESPACE:
        raise G1AContractError("Evaluation namespace authority mismatch.")
    _required_labels(namespace_meta.get("labels"), subject="namespace")

    metadata = deployment.get("metadata") or {}
    if (
        metadata.get("name") != EVALUATION_DEPLOYMENT
        or metadata.get("namespace") != EVALUATION_NAMESPACE
    ):
        raise G1AContractError("Evaluation Deployment authority mismatch.")
    _required_labels(metadata.get("labels"), subject="deployment")

    spec = deployment.get("spec") or {}
    if spec.get("replicas") != 1:
        raise G1AContractError("G1A Deployment must have exactly one replica.")
    template = spec.get("template") or {}
    _required_labels((template.get("metadata") or {}).get("labels"), subject="pod")
    pod_spec = template.get("spec") or {}
    if pod_spec.get("automountServiceAccountToken") is not False:
        raise G1AContractError("G1A Pod must not mount a service-account token.")
    containers = pod_spec.get("containers")
    if not isinstance(containers, list) or len(containers) != 1:
        raise G1AContractError("G1A Pod must contain exactly one container.")
    container = containers[0]
    if container.get("name") != EVALUATION_CONTAINER:
        raise G1AContractError("G1A container authority mismatch.")
    if container.get("image") != HEALTHY_IMAGE_URI:
        raise G1AContractError("G1A manifest must use the accepted healthy digest.")
    if "imagePullSecrets" in pod_spec:
        raise G1AContractError("G1A must not use an imagePullSecret.")
    probe = container.get("readinessProbe") or {}
    http_get = probe.get("httpGet") or {}
    if http_get.get("path") != "/index.html" or http_get.get("port") != "http":
        raise G1AContractError("G1A readiness probe authority mismatch.")
    return {
        "namespace": EVALUATION_NAMESPACE,
        "deployment": EVALUATION_DEPLOYMENT,
        "container": EVALUATION_CONTAINER,
        "image": HEALTHY_IMAGE_URI,
    }


def validate_provider_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_commit: str,
    expected_run_id: int,
    expected_run_attempt: int,
    expected_image_digest: str | None = None,
) -> dict[str, Any]:
    if _SHA1.fullmatch(expected_commit) is None:
        raise G1AContractError("Expected provider commit is invalid.")
    if receipt.get("schema_version") != "topoai-golden-provider-build-receipt-v1":
        raise G1AContractError("Provider receipt schema mismatch.")
    expected = {
        "repository": FIXTURE_REPOSITORY,
        "workflow_name": "Build Golden Fixture Image",
        "workflow_file": ".github/workflows/build-image.yml",
        "run_id": expected_run_id,
        "run_attempt": expected_run_attempt,
        "source_commit": expected_commit,
        "source_ref": "refs/heads/main",
        "image_repository": FIXTURE_IMAGE_REPOSITORY,
        "base_image_digest": BASE_IMAGE_DIGEST,
    }
    for field, value in expected.items():
        if receipt.get(field) != value:
            raise G1AContractError(f"Provider receipt mismatch: {field}")
    digest = receipt.get("image_digest")
    if not isinstance(digest, str) or _IMAGE_DIGEST.fullmatch(digest) is None:
        raise G1AContractError("Provider receipt image digest is invalid.")
    if expected_image_digest is not None and digest != expected_image_digest:
        raise G1AContractError("Provider receipt image digest changed.")
    image_uri = f"{FIXTURE_IMAGE_REPOSITORY}@{digest}"
    if receipt.get("image_uri_by_digest") != image_uri:
        raise G1AContractError("Provider receipt digest URI mismatch.")
    started = _utc(receipt.get("build_started_or_observed_utc"))
    completed = _utc(receipt.get("build_completed_utc"))
    if completed < started:
        raise G1AContractError("Provider receipt completion precedes start.")
    return {
        "repository": FIXTURE_REPOSITORY,
        "source_commit": expected_commit,
        "run_id": expected_run_id,
        "run_attempt": expected_run_attempt,
        "image_digest": digest,
        "image_uri_by_digest": image_uri,
        "build_started_or_observed_utc": started.isoformat(),
        "build_completed_utc": completed.isoformat(),
    }


def _controller_uid(resource: Mapping[str, Any], *, kind: str) -> str:
    metadata = resource.get("metadata") or {}
    owners = metadata.get("ownerReferences") or []
    matches = [
        owner
        for owner in owners
        if isinstance(owner, Mapping)
        and owner.get("kind") == kind
        and owner.get("controller") is True
        and isinstance(owner.get("uid"), str)
        and owner.get("uid")
    ]
    if len(matches) != 1:
        raise G1AContractError(f"Expected one controller owner of kind {kind}.")
    return str(matches[0]["uid"])


def _resource_uid(resource: Mapping[str, Any], *, subject: str) -> str:
    uid = (resource.get("metadata") or {}).get("uid")
    if not isinstance(uid, str) or not uid:
        raise G1AContractError(f"{subject} UID is missing.")
    return uid


def _requested_image(resource: Mapping[str, Any], *, pod_template: bool) -> str:
    if pod_template:
        containers = (
            (((resource.get("spec") or {}).get("template") or {}).get("spec") or {}).get("containers")
            or []
        )
    else:
        containers = ((resource.get("spec") or {}).get("containers") or [])
    matches = [
        item
        for item in containers
        if isinstance(item, Mapping) and item.get("name") == EVALUATION_CONTAINER
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("image"), str):
        raise G1AContractError("Fixture requested image is missing.")
    return str(matches[0]["image"])


def validate_uid_chain(
    deployment: Mapping[str, Any],
    replica_set: Mapping[str, Any],
    pod: Mapping[str, Any],
    *,
    expected_image_uri: str,
) -> dict[str, Any]:
    deployment_uid = _resource_uid(deployment, subject="Deployment")
    replica_set_uid = _resource_uid(replica_set, subject="ReplicaSet")
    pod_uid = _resource_uid(pod, subject="Pod")
    if _controller_uid(replica_set, kind="Deployment") != deployment_uid:
        raise G1AContractError("ReplicaSet does not reference the exact Deployment UID.")
    if _controller_uid(pod, kind="ReplicaSet") != replica_set_uid:
        raise G1AContractError("Pod does not reference the exact ReplicaSet UID.")
    requested = {
        _requested_image(deployment, pod_template=True),
        _requested_image(replica_set, pod_template=True),
        _requested_image(pod, pod_template=False),
    }
    if requested != {expected_image_uri}:
        raise G1AContractError("Requested image authority differs across the UID chain.")
    generation = (deployment.get("metadata") or {}).get("generation")
    if not isinstance(generation, int) or generation < 1:
        raise G1AContractError("Deployment generation is missing.")
    return {
        "deployment_uid": deployment_uid,
        "deployment_generation": generation,
        "replica_set_uid": replica_set_uid,
        "pod_uid": pod_uid,
        "requested_image_uri": expected_image_uri,
        "uid_owner_chain_exact": True,
    }


def control_plane_fingerprint(deployments: Sequence[Mapping[str, Any]]) -> str:
    expected = {"topo-backend", "topo-frontend", "topo-observer"}
    summaries: list[dict[str, Any]] = []
    for deployment in deployments:
        metadata = deployment.get("metadata") or {}
        name = metadata.get("name")
        if name not in expected:
            continue
        spec = deployment.get("spec") or {}
        status = deployment.get("status") or {}
        containers = (((spec.get("template") or {}).get("spec") or {}).get("containers") or [])
        summaries.append(
            {
                "available_replicas": status.get("availableReplicas", 0),
                "generation": metadata.get("generation"),
                "images": sorted(
                    str(item.get("image"))
                    for item in containers
                    if isinstance(item, Mapping) and item.get("image")
                ),
                "name": name,
                "observed_generation": status.get("observedGeneration"),
                "ready_replicas": status.get("readyReplicas", 0),
                "replicas": spec.get("replicas", 0),
                "uid": metadata.get("uid"),
                "updated_replicas": status.get("updatedReplicas", 0),
            }
        )
    if {item["name"] for item in summaries} != expected:
        raise G1AContractError("Protected control-plane Deployment set is incomplete.")
    encoded = json.dumps(
        sorted(summaries, key=lambda item: item["name"]),
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def recovery_command(*, healthy_image_uri: str = HEALTHY_IMAGE_URI) -> str:
    return "\n".join(
        (
            "kubectl --context topo-golden `",
            "  -n topo-eval `",
            "  set image `",
            "  deployment/topo-golden-fixture `",
            f"  fixture={healthy_image_uri}",
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic CX-0A G1A evidence adapter.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate-manifest")
    commands.add_parser("recovery-command")
    receipt = commands.add_parser("validate-provider-receipt")
    receipt.add_argument("path", type=Path)
    receipt.add_argument("--commit", required=True)
    receipt.add_argument("--run-id", type=int, required=True)
    receipt.add_argument("--run-attempt", type=int, required=True)
    receipt.add_argument("--image-digest")
    arguments = parser.parse_args(argv)

    if arguments.command == "validate-manifest":
        value = validate_workload_manifest(_load_object(MANIFEST_PATH))
        print(json.dumps(value, indent=2, sort_keys=True))
    elif arguments.command == "recovery-command":
        print(recovery_command())
    else:
        value = validate_provider_receipt(
            _load_object(arguments.path),
            expected_commit=arguments.commit,
            expected_run_id=arguments.run_id,
            expected_run_attempt=arguments.run_attempt,
            expected_image_digest=arguments.image_digest,
        )
        print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
