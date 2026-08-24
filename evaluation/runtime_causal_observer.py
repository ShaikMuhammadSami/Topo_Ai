from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from evaluation.lineage_contracts import deterministic_json
from evaluation.oci_artifact_identity import (
    digest_from_runtime_image_id,
    platform_value,
    resolve_runtime_artifact_identity,
    validate_runtime_identity_resolution,
)


RUNTIME_CAUSAL_RECEIPT_VERSION = "eval-runtime-causal-receipt-v1"
RUNTIME_CAUSAL_RECEIPT_V2_VERSION = "eval-runtime-causal-receipt-v2"
EVALUATION_LABEL = "topo.ai/evaluation-run"
NAMESPACE_PREFIX = "topo-eval-lineage-causal-"
DEPLOYMENT_NAME = "lineage-causal-fixture"
CONTAINER_NAME = "fixture"
FAIL_EXIT_CODE = 42
ACCEPTED_WAITING_REASONS = frozenset({"BackOff", "CrashLoopBackOff"})
EXPECTED_TERMINATION_REASON = "Error"

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_IMMUTABLE_IMAGE = re.compile(
    r"^[a-z0-9][a-z0-9.-]*(?::[0-9]+)?/[^@\s]+@sha256:[0-9a-f]{64}$"
)
_RUN_ID = re.compile(r"^[1-9][0-9]*$")
_UID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Runtime receipt timestamps must be timezone-aware.")
    return parsed.astimezone(timezone.utc)


def namespace_for_run(run_id: str | int) -> str:
    token = str(run_id)
    if not _RUN_ID.fullmatch(token):
        raise ValueError("The evaluation run ID must be a positive decimal integer.")
    return f"{NAMESPACE_PREFIX}{token}"


def require_safe_namespace(
    namespace: str,
    run_id: str | int,
    labels: dict[str, Any] | None = None,
) -> None:
    token = str(run_id)
    if namespace != namespace_for_run(token):
        raise ValueError("Evaluation namespace does not exactly match its run ID.")
    if not namespace.startswith(NAMESPACE_PREFIX):
        raise ValueError("Evaluation namespace prefix is unsafe.")
    if labels is not None and str(labels.get(EVALUATION_LABEL) or "") != token:
        raise ValueError("Evaluation namespace run label does not match.")


def image_digest_from_ref(image_ref: str) -> str:
    if not _IMMUTABLE_IMAGE.fullmatch(image_ref):
        raise ValueError("An exact immutable image digest reference is required.")
    return image_ref.rsplit("@", 1)[1]


def render_deployment_template(
    template_text: str,
    *,
    run_id: str | int,
    immutable_image_ref: str,
) -> str:
    token = str(run_id)
    namespace = namespace_for_run(token)
    image_digest_from_ref(immutable_image_ref)
    if template_text.count("__IMMUTABLE_IMAGE_REF__") != 1:
        raise ValueError("Deployment template must contain exactly one image placeholder.")
    if "__RUN_ID__" not in template_text:
        raise ValueError("Deployment template is missing the run ID placeholder.")
    label_placeholder = f"{EVALUATION_LABEL}: __RUN_ID__"
    if label_placeholder not in template_text:
        raise ValueError("Deployment template is missing the guarded run label.")
    rendered = template_text.replace(
        label_placeholder, f'{EVALUATION_LABEL}: "{token}"'
    )
    rendered = rendered.replace("__RUN_ID__", token).replace(
        "__IMMUTABLE_IMAGE_REF__", immutable_image_ref
    )
    if "__RUN_ID__" in rendered or "__IMMUTABLE_IMAGE_REF__" in rendered:
        raise ValueError("Deployment template rendering is incomplete.")
    if f"name: {namespace}" not in rendered:
        raise ValueError("Rendered deployment does not contain the guarded namespace.")
    return rendered


def verify_local_cluster(
    *,
    context: str,
    cluster: str,
    server: str,
    nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    parsed = urlsplit(server)
    local_host = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    local_name = context == "docker-desktop" and cluster == "docker-desktop"
    provider_ids = [
        str(item.get("spec", {}).get("providerID") or "") for item in nodes
    ]
    local_nodes = bool(provider_ids) and all(
        value.startswith("kind://docker/desktop/") for value in provider_ids
    )
    safe = local_name and local_host and local_nodes
    result = {
        "safe": safe,
        "context": context,
        "cluster": cluster,
        "server": server,
        "node_names": sorted(
            str(item.get("metadata", {}).get("name") or "") for item in nodes
        ),
        "node_provider_ids": sorted(provider_ids),
        "policy": "docker_desktop_loopback_kind_nodes",
    }
    if not safe:
        raise ValueError("INCONCLUSIVE_LOCAL_CLUSTER_SAFETY")
    return result


class KubectlJson:
    def __init__(self, executable: str = "kubectl"):
        self.executable = executable

    def run(
        self,
        *arguments: str,
        timeout: float = 60.0,
        json_output: bool = False,
    ) -> Any:
        completed = subprocess.run(
            [self.executable, *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        if completed.returncode:
            raise RuntimeError(
                f"kubectl failed ({completed.returncode}): "
                f"{' '.join(arguments)}\n{completed.stderr.strip()}"
            )
        return json.loads(completed.stdout) if json_output else completed.stdout.strip()

    def get_json(self, *arguments: str) -> dict[str, Any]:
        return self.run("get", *arguments, "-o", "json", json_output=True)

    def local_cluster_truth(self) -> dict[str, Any]:
        context = str(self.run("config", "current-context"))
        config = self.run(
            "config", "view", "--minify", "-o", "json", json_output=True
        )
        contexts = config.get("contexts") or []
        clusters = config.get("clusters") or []
        cluster = str(
            (contexts[0].get("context") or {}).get("cluster") if contexts else ""
        )
        server = str(
            (clusters[0].get("cluster") or {}).get("server") if clusters else ""
        )
        node_list = self.get_json("nodes")
        return verify_local_cluster(
            context=context,
            cluster=cluster,
            server=server,
            nodes=node_list.get("items") or [],
        )


def _owner_uid(value: dict[str, Any], expected_kind: str) -> str | None:
    matches = [
        str(item.get("uid") or "")
        for item in value.get("metadata", {}).get("ownerReferences") or []
        if str(item.get("kind") or "") == expected_kind
        and item.get("controller") is True
    ]
    return matches[0] if len(matches) == 1 and matches[0] else None


def _owned_item(
    values: list[dict[str, Any]], *, owner_kind: str, owner_uid: str
) -> dict[str, Any] | None:
    matches = [item for item in values if _owner_uid(item, owner_kind) == owner_uid]
    return sorted(
        matches,
        key=lambda item: str(item.get("metadata", {}).get("creationTimestamp") or ""),
        reverse=True,
    )[0] if matches else None


def _container_status(pod: dict[str, Any]) -> dict[str, Any] | None:
    matches = [
        item
        for item in pod.get("status", {}).get("containerStatuses") or []
        if item.get("name") == CONTAINER_NAME
    ]
    return matches[0] if len(matches) == 1 else None


def _backoff_observation(
    *, pod: dict[str, Any], status: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any] | None:
    waiting = (status.get("state") or {}).get("waiting") or {}
    waiting_reason = str(waiting.get("reason") or "")
    if waiting_reason in ACCEPTED_WAITING_REASONS:
        return {
            "source": "container_status_waiting",
            "reason": waiting_reason,
            "event_uid": None,
            "event_count": None,
            "observed_at": None,
        }
    pod_uid = str(pod.get("metadata", {}).get("uid") or "")
    candidates = [
        item
        for item in events
        if str((item.get("involvedObject") or {}).get("uid") or "") == pod_uid
        and str(item.get("reason") or "") == "BackOff"
    ]
    if not candidates:
        return None
    selected = sorted(
        candidates,
        key=lambda item: str(item.get("lastTimestamp") or item.get("eventTime") or ""),
        reverse=True,
    )[0]
    return {
        "source": "kubernetes_event",
        "reason": "BackOff",
        "event_uid": selected.get("metadata", {}).get("uid"),
        "event_count": selected.get("count"),
        "observed_at": selected.get("lastTimestamp") or selected.get("eventTime"),
    }


def _runtime_sample(
    kubectl: KubectlJson,
    *,
    namespace: str,
    immutable_image_ref: str,
    target_platform: dict[str, Any],
    provider_descriptors: list[dict[str, Any]],
) -> dict[str, Any] | None:
    namespace_object = kubectl.get_json("namespace", namespace)
    deployment = kubectl.get_json("deployment", DEPLOYMENT_NAME, "-n", namespace)
    deployment_uid = str(deployment.get("metadata", {}).get("uid") or "")
    replica_sets = kubectl.get_json(
        "replicasets", "-n", namespace, "-l", f"{EVALUATION_LABEL}={namespace.removeprefix(NAMESPACE_PREFIX)}"
    ).get("items") or []
    replica_set = _owned_item(
        replica_sets, owner_kind="Deployment", owner_uid=deployment_uid
    )
    if replica_set is None:
        return None
    replica_set_uid = str(replica_set.get("metadata", {}).get("uid") or "")
    pods = kubectl.get_json(
        "pods", "-n", namespace, "-l", f"{EVALUATION_LABEL}={namespace.removeprefix(NAMESPACE_PREFIX)}"
    ).get("items") or []
    pod = _owned_item(pods, owner_kind="ReplicaSet", owner_uid=replica_set_uid)
    if pod is None:
        return None
    status = _container_status(pod)
    if status is None:
        return None
    events = kubectl.get_json("events", "-n", namespace).get("items") or []
    backoff = _backoff_observation(pod=pod, status=status, events=events)
    state = status.get("state") or {}
    current_state = next(
        (name for name in ("waiting", "running", "terminated") if state.get(name)),
        "unknown",
    )
    waiting = state.get("waiting") or {}
    terminated = (status.get("lastState") or {}).get("terminated") or {}
    deployment_spec = deployment.get("spec") or {}
    deployment_status = deployment.get("status") or {}
    image_id = status.get("imageID")
    artifact_resolution = resolve_runtime_artifact_identity(
        requested_immutable_ref=immutable_image_ref,
        runtime_image_id=image_id,
        target_platform=target_platform,
        provider_descriptors=provider_descriptors,
    )
    return {
        "namespace": namespace_object,
        "deployment": deployment,
        "replica_set": replica_set,
        "pod": pod,
        "status": status,
        "backoff": backoff,
        "facts": {
            "image_ref_matches": status.get("image") == immutable_image_ref,
            "runtime_artifact_identity_confirmed": artifact_resolution[
                "accepted"
            ],
            "owner_chain_matches": (
                _owner_uid(replica_set, "Deployment") == deployment_uid
                and _owner_uid(pod, "ReplicaSet") == replica_set_uid
            ),
            "failure_mechanism_confirmed": (
                terminated.get("exitCode") == FAIL_EXIT_CODE
                and terminated.get("reason") == EXPECTED_TERMINATION_REASON
            ),
            "runtime_manifestation_confirmed": (
                int(status.get("restartCount") or 0) >= 1 and backoff is not None
            ),
            "operational_impact_confirmed": (
                deployment_spec.get("replicas") == 1
                and int(deployment_status.get("readyReplicas") or 0) == 0
                and int(deployment_status.get("availableReplicas") or 0) == 0
            ),
            "current_state": current_state,
            "waiting_reason": waiting.get("reason"),
            "last_termination": terminated,
        },
        "artifact_resolution": artifact_resolution,
    }


def _sample_complete(sample: dict[str, Any] | None) -> bool:
    if not sample:
        return False
    facts = sample["facts"]
    return all(
        facts.get(name) is True
        for name in (
            "image_ref_matches",
            "runtime_artifact_identity_confirmed",
            "owner_chain_matches",
            "failure_mechanism_confirmed",
            "runtime_manifestation_confirmed",
            "operational_impact_confirmed",
        )
    )


def observe_runtime_causal_truth(
    kubectl: KubectlJson,
    *,
    run_id: str | int,
    source_parent_commit: str,
    source_failure_commit: str,
    immutable_image_ref: str,
    context: str,
    cluster: str,
    target_platform: dict[str, Any],
    provider_descriptors: list[dict[str, Any]],
    timeout_seconds: int = 120,
    poll_interval_seconds: float = 2.0,
    now: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    if timeout_seconds < 1 or timeout_seconds > 120:
        raise ValueError("Runtime observation timeout must be between 1 and 120 seconds.")
    namespace = namespace_for_run(run_id)
    started_at = now()
    deadline = time.monotonic() + timeout_seconds
    sample: dict[str, Any] | None = None
    while time.monotonic() <= deadline:
        sample = _runtime_sample(
            kubectl,
            namespace=namespace,
            immutable_image_ref=immutable_image_ref,
            target_platform=target_platform,
            provider_descriptors=provider_descriptors,
        )
        if _sample_complete(sample):
            break
        time.sleep(poll_interval_seconds)
    if not _sample_complete(sample):
        raise RuntimeError("INCONCLUSIVE_GROUND_TRUTH")

    failure_confirmed_at = now()
    captured_at = now()
    assert sample is not None
    namespace_object = sample["namespace"]
    deployment = sample["deployment"]
    replica_set = sample["replica_set"]
    pod = sample["pod"]
    status = sample["status"]
    facts = sample["facts"]
    terminated = facts["last_termination"]
    deployment_status = deployment.get("status") or {}
    receipt = {
        "schema_version": RUNTIME_CAUSAL_RECEIPT_V2_VERSION,
        "experiment": {
            "run_id": int(run_id),
            "source_parent_commit": source_parent_commit.lower(),
            "source_failure_commit": source_failure_commit.lower(),
            "requested_artifact": {
                "immutable_ref": immutable_image_ref,
                "index_digest": image_digest_from_ref(immutable_image_ref),
            },
        },
        "kubernetes": {
            "context": context,
            "cluster": cluster,
            "namespace": namespace,
            "namespace_uid": namespace_object.get("metadata", {}).get("uid"),
            "deployment_name": deployment.get("metadata", {}).get("name"),
            "deployment_uid": deployment.get("metadata", {}).get("uid"),
            "replicaset_name": replica_set.get("metadata", {}).get("name"),
            "replicaset_uid": replica_set.get("metadata", {}).get("uid"),
            "pod_name": pod.get("metadata", {}).get("name"),
            "pod_uid": pod.get("metadata", {}).get("uid"),
        },
        "ownership": {
            "replicaset_owner_deployment_uid": _owner_uid(
                replica_set, "Deployment"
            ),
            "pod_owner_replicaset_uid": _owner_uid(pod, "ReplicaSet"),
        },
        "container": {
            "name": status.get("name"),
            "image": status.get("image"),
            "image_id": status.get("imageID"),
            "runtime_digest": sample["artifact_resolution"]["runtime_digest"],
            "restart_count": int(status.get("restartCount") or 0),
            "waiting_reason": facts.get("waiting_reason"),
            "current_state": facts.get("current_state"),
            "last_termination_reason": terminated.get("reason"),
            "last_termination_exit_code": terminated.get("exitCode"),
            "last_termination_started_at": terminated.get("startedAt"),
            "last_termination_finished_at": terminated.get("finishedAt"),
            "backoff_observation": sample.get("backoff"),
        },
        "deployment_status": {
            "desired_replicas": deployment.get("spec", {}).get("replicas"),
            "ready_replicas": int(deployment_status.get("readyReplicas") or 0),
            "available_replicas": int(
                deployment_status.get("availableReplicas") or 0
            ),
            "unavailable_replicas": int(
                deployment_status.get("unavailableReplicas") or 0
            ),
        },
        "artifact_resolution": sample["artifact_resolution"],
        "observation": {
            "started_at": started_at,
            "failure_confirmed_at": failure_confirmed_at,
            "captured_at": captured_at,
            "timeout_seconds": timeout_seconds,
        },
        "ground_truth": {
            "exact_image_identity_confirmed": (
                facts["image_ref_matches"]
                and facts["runtime_artifact_identity_confirmed"]
            ),
            "ownership_chain_confirmed": facts["owner_chain_matches"],
            "failure_mechanism_confirmed": facts[
                "failure_mechanism_confirmed"
            ],
            "runtime_manifestation_confirmed": facts[
                "runtime_manifestation_confirmed"
            ],
            "operational_impact_confirmed": facts[
                "operational_impact_confirmed"
            ],
        },
        "topo_used_to_construct_truth": False,
    }
    validate_runtime_causal_receipt(receipt)
    return receipt


def validate_runtime_causal_receipt(value: dict[str, Any]) -> None:
    version = value.get("schema_version")
    if version == RUNTIME_CAUSAL_RECEIPT_VERSION:
        _validate_runtime_causal_receipt_v1(value)
        return
    if version == RUNTIME_CAUSAL_RECEIPT_V2_VERSION:
        _validate_runtime_causal_receipt_v2(value)
        return
    raise ValueError("Unsupported runtime causal receipt version.")


def _validate_runtime_causal_receipt_v1(value: dict[str, Any]) -> None:
    expected_top = {
        "schema_version",
        "experiment",
        "kubernetes",
        "ownership",
        "container",
        "deployment_status",
        "observation",
        "ground_truth",
        "topo_used_to_construct_truth",
    }
    if set(value) != expected_top:
        raise ValueError("Runtime causal receipt fields do not match v1.")
    if value.get("schema_version") != RUNTIME_CAUSAL_RECEIPT_VERSION:
        raise ValueError("Unsupported runtime causal receipt version.")
    if value.get("topo_used_to_construct_truth") is not False:
        raise ValueError("Topo cannot define independent runtime truth.")

    experiment = value.get("experiment") or {}
    if set(experiment) != {
        "run_id",
        "source_parent_commit",
        "source_failure_commit",
        "immutable_image_ref",
        "image_digest",
    }:
        raise ValueError("Runtime experiment identity fields do not match v1.")
    if not isinstance(experiment.get("run_id"), int) or experiment["run_id"] < 1:
        raise ValueError("Runtime experiment run ID is invalid.")
    for field in ("source_parent_commit", "source_failure_commit"):
        if not re.fullmatch(r"[0-9a-f]{40}", str(experiment.get(field) or "")):
            raise ValueError("Runtime experiment commit identity is invalid.")
    if experiment["source_parent_commit"] == experiment["source_failure_commit"]:
        raise ValueError("Runtime source parent and failure commit must differ.")
    digest = image_digest_from_ref(str(experiment.get("immutable_image_ref") or ""))
    if experiment.get("image_digest") != digest or not _DIGEST.fullmatch(digest):
        raise ValueError("Runtime experiment image digest is inconsistent.")

    kubernetes = value.get("kubernetes") or {}
    required_kubernetes = {
        "context",
        "cluster",
        "namespace",
        "namespace_uid",
        "deployment_name",
        "deployment_uid",
        "replicaset_name",
        "replicaset_uid",
        "pod_name",
        "pod_uid",
    }
    if set(kubernetes) != required_kubernetes:
        raise ValueError("Runtime Kubernetes identity fields do not match v1.")
    require_safe_namespace(
        str(kubernetes.get("namespace") or ""), experiment["run_id"]
    )
    if kubernetes.get("deployment_name") != DEPLOYMENT_NAME:
        raise ValueError("Runtime deployment name is invalid.")
    for field in ("namespace_uid", "deployment_uid", "replicaset_uid", "pod_uid"):
        if not _UID.fullmatch(str(kubernetes.get(field) or "")):
            raise ValueError(f"Runtime {field} is required.")

    ownership = value.get("ownership") or {}
    if ownership != {
        "replicaset_owner_deployment_uid": kubernetes["deployment_uid"],
        "pod_owner_replicaset_uid": kubernetes["replicaset_uid"],
    }:
        raise ValueError("Runtime owner-reference UID chain is invalid.")

    container = value.get("container") or {}
    required_container = {
        "name",
        "image",
        "image_id",
        "restart_count",
        "waiting_reason",
        "current_state",
        "last_termination_reason",
        "last_termination_exit_code",
        "last_termination_started_at",
        "last_termination_finished_at",
        "backoff_observation",
    }
    if set(container) != required_container:
        raise ValueError("Runtime container fields do not match v1.")
    if container.get("name") != CONTAINER_NAME:
        raise ValueError("Runtime container identity is invalid.")
    if container.get("image") != experiment["immutable_image_ref"]:
        raise ValueError("A different image was deployed.")
    if container.get("image_id") and digest not in str(container["image_id"]):
        raise ValueError("Runtime image ID does not match the immutable digest.")
    if not isinstance(container.get("restart_count"), int) or container[
        "restart_count"
    ] < 1:
        raise ValueError("At least one runtime restart is required.")
    if container.get("last_termination_exit_code") != FAIL_EXIT_CODE:
        raise ValueError("Runtime failure mechanism is not exit code 42.")
    if container.get("last_termination_reason") != EXPECTED_TERMINATION_REASON:
        raise ValueError("Runtime termination reason is not Error.")
    backoff = container.get("backoff_observation") or {}
    if backoff.get("reason") not in ACCEPTED_WAITING_REASONS:
        raise ValueError("Structured runtime backoff evidence is required.")

    deployment_status = value.get("deployment_status") or {}
    if deployment_status.get("desired_replicas") != 1:
        raise ValueError("Runtime desired replica truth is invalid.")
    if deployment_status.get("ready_replicas") != 0:
        raise ValueError("Runtime ready replica truth is invalid.")
    if deployment_status.get("available_replicas") != 0:
        raise ValueError("Runtime available replica truth is invalid.")

    observation = value.get("observation") or {}
    if not isinstance(observation.get("timeout_seconds"), int) or not (
        1 <= observation["timeout_seconds"] <= 120
    ):
        raise ValueError("Runtime observation timeout is invalid.")
    timestamps = [
        _aware_datetime(str(observation.get(field) or ""))
        for field in ("started_at", "failure_confirmed_at", "captured_at")
    ]
    if timestamps != sorted(timestamps):
        raise ValueError("Runtime observation timestamps are out of order.")

    ground_truth = value.get("ground_truth") or {}
    required_truth = {
        "exact_image_identity_confirmed",
        "ownership_chain_confirmed",
        "failure_mechanism_confirmed",
        "runtime_manifestation_confirmed",
        "operational_impact_confirmed",
    }
    if set(ground_truth) != required_truth or any(
        ground_truth.get(field) is not True for field in required_truth
    ):
        raise ValueError("Independent runtime ground truth is incomplete.")


def _validate_runtime_causal_receipt_v2(value: dict[str, Any]) -> None:
    expected_top = {
        "schema_version",
        "experiment",
        "kubernetes",
        "ownership",
        "container",
        "deployment_status",
        "artifact_resolution",
        "observation",
        "ground_truth",
        "topo_used_to_construct_truth",
    }
    if set(value) != expected_top:
        raise ValueError("Runtime causal receipt v2 fields do not match.")
    if value.get("topo_used_to_construct_truth") is not False:
        raise ValueError("Topo cannot define independent runtime truth.")

    experiment = value.get("experiment") or {}
    if set(experiment) != {
        "run_id",
        "source_parent_commit",
        "source_failure_commit",
        "requested_artifact",
    }:
        raise ValueError("Runtime experiment v2 identity fields do not match.")
    if not isinstance(experiment.get("run_id"), int) or experiment["run_id"] < 1:
        raise ValueError("Runtime experiment run ID is invalid.")
    for field in ("source_parent_commit", "source_failure_commit"):
        if not re.fullmatch(r"[0-9a-f]{40}", str(experiment.get(field) or "")):
            raise ValueError("Runtime experiment commit identity is invalid.")
    if experiment["source_parent_commit"] == experiment["source_failure_commit"]:
        raise ValueError("Runtime source parent and failure commit must differ.")
    requested = experiment.get("requested_artifact") or {}
    if set(requested) != {"immutable_ref", "index_digest"}:
        raise ValueError("Requested OCI artifact fields do not match v2.")
    digest = image_digest_from_ref(str(requested.get("immutable_ref") or ""))
    if requested.get("index_digest") != digest:
        raise ValueError("Requested OCI index digest is inconsistent.")

    resolution = value.get("artifact_resolution") or {}
    validate_runtime_identity_resolution(resolution)
    if resolution.get("requested_immutable_ref") != requested["immutable_ref"]:
        raise ValueError("Runtime resolution requested reference is inconsistent.")
    if resolution.get("requested_index_digest") != digest:
        raise ValueError("Runtime resolution index digest is inconsistent.")
    if resolution.get("accepted") is not True:
        raise ValueError("Runtime artifact identity remains inconclusive.")

    kubernetes = value.get("kubernetes") or {}
    required_kubernetes = {
        "context",
        "cluster",
        "namespace",
        "namespace_uid",
        "deployment_name",
        "deployment_uid",
        "replicaset_name",
        "replicaset_uid",
        "pod_name",
        "pod_uid",
    }
    if set(kubernetes) != required_kubernetes:
        raise ValueError("Runtime Kubernetes identity fields do not match v2.")
    require_safe_namespace(
        str(kubernetes.get("namespace") or ""), experiment["run_id"]
    )
    if kubernetes.get("deployment_name") != DEPLOYMENT_NAME:
        raise ValueError("Runtime deployment name is invalid.")
    for field in ("namespace_uid", "deployment_uid", "replicaset_uid", "pod_uid"):
        if not _UID.fullmatch(str(kubernetes.get(field) or "")):
            raise ValueError(f"Runtime {field} is required.")

    ownership = value.get("ownership") or {}
    if ownership != {
        "replicaset_owner_deployment_uid": kubernetes["deployment_uid"],
        "pod_owner_replicaset_uid": kubernetes["replicaset_uid"],
    }:
        raise ValueError("Runtime owner-reference UID chain is invalid.")

    container = value.get("container") or {}
    required_container = {
        "name",
        "image",
        "image_id",
        "runtime_digest",
        "restart_count",
        "waiting_reason",
        "current_state",
        "last_termination_reason",
        "last_termination_exit_code",
        "last_termination_started_at",
        "last_termination_finished_at",
        "backoff_observation",
    }
    if set(container) != required_container:
        raise ValueError("Runtime container fields do not match v2.")
    if container.get("name") != CONTAINER_NAME:
        raise ValueError("Runtime container identity is invalid.")
    if container.get("image") != requested["immutable_ref"]:
        raise ValueError("A different image was requested by the Pod.")
    if container.get("image_id") != resolution.get("runtime_image_id"):
        raise ValueError("Runtime imageID and artifact resolution differ.")
    if container.get("runtime_digest") != resolution.get("runtime_digest"):
        raise ValueError("Runtime digest and artifact resolution differ.")
    if digest_from_runtime_image_id(str(container.get("image_id") or "")) != (
        container.get("runtime_digest")
    ):
        raise ValueError("Runtime imageID digest is inconsistent.")
    if not isinstance(container.get("restart_count"), int) or container[
        "restart_count"
    ] < 1:
        raise ValueError("At least one runtime restart is required.")
    if container.get("last_termination_exit_code") != FAIL_EXIT_CODE:
        raise ValueError("Runtime failure mechanism is not exit code 42.")
    if container.get("last_termination_reason") != EXPECTED_TERMINATION_REASON:
        raise ValueError("Runtime termination reason is not Error.")
    backoff = container.get("backoff_observation") or {}
    if backoff.get("reason") not in ACCEPTED_WAITING_REASONS:
        raise ValueError("Structured runtime backoff evidence is required.")

    deployment_status = value.get("deployment_status") or {}
    if deployment_status.get("desired_replicas") != 1:
        raise ValueError("Runtime desired replica truth is invalid.")
    if deployment_status.get("ready_replicas") != 0:
        raise ValueError("Runtime ready replica truth is invalid.")
    if deployment_status.get("available_replicas") != 0:
        raise ValueError("Runtime available replica truth is invalid.")

    observation = value.get("observation") or {}
    if not isinstance(observation.get("timeout_seconds"), int) or not (
        1 <= observation["timeout_seconds"] <= 120
    ):
        raise ValueError("Runtime observation timeout is invalid.")
    timestamps = [
        _aware_datetime(str(observation.get(field) or ""))
        for field in ("started_at", "failure_confirmed_at", "captured_at")
    ]
    if timestamps != sorted(timestamps):
        raise ValueError("Runtime observation timestamps are out of order.")

    ground_truth = value.get("ground_truth") or {}
    required_truth = {
        "exact_image_identity_confirmed",
        "ownership_chain_confirmed",
        "failure_mechanism_confirmed",
        "runtime_manifestation_confirmed",
        "operational_impact_confirmed",
    }
    if set(ground_truth) != required_truth or any(
        ground_truth.get(field) is not True for field in required_truth
    ):
        raise ValueError("Independent runtime ground truth is incomplete.")


def provider_index_digest(value: dict[str, Any]) -> str:
    validate_runtime_causal_receipt(value)
    if value["schema_version"] == RUNTIME_CAUSAL_RECEIPT_VERSION:
        return str(value["experiment"]["image_digest"])
    return str(value["experiment"]["requested_artifact"]["index_digest"])


def guarded_cleanup(
    kubectl: KubectlJson, *, run_id: str | int, timeout_seconds: int = 120
) -> None:
    namespace = namespace_for_run(run_id)
    namespace_object = kubectl.get_json("namespace", namespace)
    require_safe_namespace(
        namespace,
        run_id,
        namespace_object.get("metadata", {}).get("labels") or {},
    )
    kubectl.run(
        "delete",
        "namespace",
        namespace,
        "--wait=true",
        f"--timeout={timeout_seconds}s",
        timeout=timeout_seconds + 10,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Observe LINEAGE-1C runtime truth.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture")
    capture.add_argument("--run-id", required=True)
    capture.add_argument("--parent-commit", required=True)
    capture.add_argument("--failure-commit", required=True)
    capture.add_argument("--image", required=True)
    capture.add_argument(
        "--platform",
        required=True,
        help="Explicit OCI runtime platform, for example linux/amd64.",
    )
    capture.add_argument(
        "--provider-descriptors",
        type=Path,
        help="Independent provider descriptor JSON; required for child-manifest identity.",
    )
    capture.add_argument("--template", type=Path, required=True)
    capture.add_argument("--rendered", type=Path, required=True)
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("--timeout", type=int, default=120)
    cleanup = subparsers.add_parser("cleanup")
    cleanup.add_argument("--run-id", required=True)
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    kubectl = KubectlJson()
    cluster_truth = kubectl.local_cluster_truth()
    if args.command == "cleanup":
        guarded_cleanup(kubectl, run_id=args.run_id)
        return 0

    template = args.template.read_text(encoding="utf-8")
    platform_tokens = args.platform.split("/")
    if len(platform_tokens) not in {2, 3}:
        raise ValueError("Runtime platform must be os/architecture[/variant].")
    target_platform = platform_value(
        os_name=platform_tokens[0],
        architecture=platform_tokens[1],
        variant=platform_tokens[2] if len(platform_tokens) == 3 else None,
    )
    provider_descriptors: list[dict[str, Any]] = []
    if args.provider_descriptors:
        descriptor_document = json.loads(
            args.provider_descriptors.read_text(encoding="utf-8")
        )
        provider_descriptors = (
            descriptor_document
            if isinstance(descriptor_document, list)
            else descriptor_document.get("descriptors") or []
        )
        if not isinstance(provider_descriptors, list):
            raise ValueError("Provider descriptor document must contain a list.")
    rendered = render_deployment_template(
        template, run_id=args.run_id, immutable_image_ref=args.image
    )
    args.rendered.parent.mkdir(parents=True, exist_ok=True)
    args.rendered.write_text(rendered, encoding="utf-8", newline="\n")
    kubectl.run("apply", "-f", str(args.rendered), timeout=120)
    receipt = observe_runtime_causal_truth(
        kubectl,
        run_id=args.run_id,
        source_parent_commit=args.parent_commit,
        source_failure_commit=args.failure_commit,
        immutable_image_ref=args.image,
        context=cluster_truth["context"],
        cluster=cluster_truth["cluster"],
        target_platform=target_platform,
        provider_descriptors=provider_descriptors,
        timeout_seconds=args.timeout,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(deterministic_json(receipt), encoding="utf-8", newline="\n")
    print(deterministic_json(receipt), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
