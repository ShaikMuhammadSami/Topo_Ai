from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from evaluation.lineage_contracts import (
    LINEAGE_HOP_VERSION,
    LINEAGE_RESULT_VERSION,
    LINEAGE_SCENARIO_ID,
    LineageResult,
    deterministic_json,
)
from evaluation.lineage_evaluator import evaluate_lineage_chain
from evaluation.lineage_provider_truth import (
    container_image_canonical_id,
    github_commit_canonical_id,
    github_repository_canonical_id,
    github_workflow_run_canonical_id,
    kubernetes_canonical_id,
    kubernetes_signal_id,
    provider_identity,
    sanitize_provider_receipt,
)


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
RESULTS = ROOT / "evaluation" / "results" / "lineage"
NAMESPACE_PREFIX = "topo-eval-lineage-"
RUN_LABEL = "topo.ai/evaluation-run"
DEFAULT_REPOSITORY = "ShaikMuhammadSami/Topo_Ai"
DEFAULT_COMMIT = "36dd62e1a12010591b90f44ff9d7c8c60e821e9b"
DEFAULT_ACTIONS_RUN = "32633653931"
DEFAULT_IMAGE_DIGEST = (
    "sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10"
)
DEFAULT_IMAGE = f"docker.io/library/nginx@{DEFAULT_IMAGE_DIGEST}"
FAILURE_REASONS = {
    "BackOff",
    "CrashLoopBackOff",
    "ErrImagePull",
    "ImagePullBackOff",
    "Failed",
    "Unhealthy",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run(
    command: list[str],
    *,
    input_text: str | None = None,
    timeout: int = 60,
) -> str:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if completed.returncode:
        safe_stderr = str(sanitize_provider_receipt(completed.stderr.strip()))
        raise RuntimeError(f"Command failed ({command[0]}): {safe_stderr}")
    return completed.stdout


def _json_command(command: list[str], *, timeout: int = 60) -> Any:
    return json.loads(_run(command, timeout=timeout))


def namespace_is_safe_for_cleanup(namespace: dict[str, Any], run_id: str) -> bool:
    metadata = namespace.get("metadata") or {}
    return (
        metadata.get("name") == f"{NAMESPACE_PREFIX}{run_id}"
        and (metadata.get("labels") or {}).get(RUN_LABEL) == run_id
    )


def _cleanup_namespace(namespace_name: str, run_id: str) -> None:
    try:
        namespace = _json_command(
            ["kubectl", "get", "namespace", namespace_name, "-o", "json"]
        )
    except RuntimeError:
        return
    if not namespace_is_safe_for_cleanup(namespace, run_id):
        raise RuntimeError(
            "Refusing cleanup: namespace prefix/name and evaluation-run label do not match."
        )
    _run(
        [
            "kubectl",
            "delete",
            "namespace",
            namespace_name,
            "--wait=true",
            "--timeout=90s",
        ],
        timeout=120,
    )


def _deployment_manifest(namespace: str, run_id: str, image: str) -> dict[str, Any]:
    labels = {"app": "lineage-failure", RUN_LABEL: run_id}
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": "lineage-failure",
            "namespace": namespace,
            "labels": labels,
        },
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"app": "lineage-failure"}},
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "containers": [
                        {
                            "name": "workload",
                            "image": image,
                            "imagePullPolicy": "IfNotPresent",
                            "command": ["/bin/sh", "-c", "exit 17"],
                        }
                    ]
                },
            },
        },
    }


def _create_namespace(namespace: str, run_id: str) -> None:
    manifest = {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {"name": namespace, "labels": {RUN_LABEL: run_id}},
    }
    _run(
        ["kubectl", "apply", "-f", "-"],
        input_text=json.dumps(manifest),
    )


def _apply_failure_deployment(namespace: str, run_id: str, image: str) -> None:
    _run(
        ["kubectl", "apply", "-f", "-"],
        input_text=json.dumps(_deployment_manifest(namespace, run_id, image)),
    )


def _pod_failure_reason(pod: dict[str, Any]) -> str | None:
    statuses = (pod.get("status") or {}).get("containerStatuses") or []
    for status in statuses:
        state = status.get("state") or {}
        waiting = state.get("waiting") or {}
        terminated = state.get("terminated") or {}
        reason = waiting.get("reason") or terminated.get("reason")
        if reason in FAILURE_REASONS:
            return str(reason)
    return None


def _wait_for_runtime(namespace: str, timeout: int) -> tuple[dict[str, Any], str]:
    deadline = time.monotonic() + timeout
    last_pod: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        payload = _json_command(
            [
                "kubectl",
                "get",
                "pods",
                "-n",
                namespace,
                "-l",
                "app=lineage-failure",
                "-o",
                "json",
            ]
        )
        items = payload.get("items") or []
        if items:
            last_pod = items[0]
            reason = _pod_failure_reason(last_pod)
            if reason:
                return last_pod, reason
        time.sleep(3)
    raise RuntimeError(
        "Timed out waiting for structured runtime failure; "
        f"last Pod phase={((last_pod or {}).get('status') or {}).get('phase')}"
    )


def _wait_for_failure_event(
    namespace: str,
    pod_uid: str,
    timeout: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = _json_command(
            ["kubectl", "get", "events", "-n", namespace, "-o", "json"]
        )
        candidates = [
            event
            for event in payload.get("items") or []
            if ((event.get("involvedObject") or {}).get("uid") == pod_uid)
            and event.get("reason") in FAILURE_REASONS
        ]
        if candidates:
            return sorted(
                candidates,
                key=lambda item: (
                    item.get("lastTimestamp")
                    or item.get("eventTime")
                    or (item.get("metadata") or {}).get("creationTimestamp")
                    or ""
                ),
            )[-1]
        time.sleep(3)
    raise RuntimeError("Timed out waiting for a provider-native Pod failure event.")


def _github_receipts(repository: str, commit_sha: str, run_id: str) -> dict[str, Any]:
    repo = _json_command(["gh", "api", f"repos/{repository}"])
    commit = _json_command(["gh", "api", f"repos/{repository}/commits/{commit_sha}"])
    run = _json_command(["gh", "api", f"repos/{repository}/actions/runs/{run_id}"])
    artifacts = _json_command(
        ["gh", "api", f"repos/{repository}/actions/runs/{run_id}/artifacts"]
    )
    return sanitize_provider_receipt(
        {
            "repository": {
                "id": repo.get("id"),
                "node_id": repo.get("node_id"),
                "full_name": repo.get("full_name"),
                "html_url": repo.get("html_url"),
                "clone_url": repo.get("clone_url"),
                "default_branch": repo.get("default_branch"),
                "private": repo.get("private"),
            },
            "commit": {
                "sha": commit.get("sha"),
                "html_url": commit.get("html_url"),
                "commit": commit.get("commit"),
                "repository_full_name": repo.get("full_name"),
            },
            "workflow_run": {
                key: run.get(key)
                for key in (
                    "id",
                    "name",
                    "workflow_id",
                    "run_number",
                    "run_attempt",
                    "head_sha",
                    "head_branch",
                    "event",
                    "status",
                    "conclusion",
                    "created_at",
                    "updated_at",
                    "run_started_at",
                    "html_url",
                    "jobs_url",
                    "logs_url",
                )
            },
            "artifacts": [
                {
                    key: artifact.get(key)
                    for key in (
                        "id",
                        "name",
                        "size_in_bytes",
                        "expired",
                        "created_at",
                        "updated_at",
                    )
                }
                for artifact in artifacts.get("artifacts") or []
            ],
        }
    )


def _registry_receipt(image: str, digest: str) -> dict[str, Any]:
    raw = _run(["docker", "buildx", "imagetools", "inspect", "--raw", image])
    manifest = json.loads(raw)
    return {
        "image_reference": image,
        "immutable_digest": digest,
        "media_type": manifest.get("mediaType"),
        "schema_version": manifest.get("schemaVersion"),
        "manifest_count": len(manifest.get("manifests") or []),
    }


def _load_product_observation(
    namespace: str,
    github: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    sys.path.insert(0, str(BACKEND))
    from app.collectors.kubernetes_collector import KubernetesCollector
    from app.collectors.kubernetes_event_collector import KubernetesEventCollector
    from app.services.github_actions_graph import augment_snapshot_with_github_actions
    from app.services.github_graph import augment_snapshot_with_github

    collector = KubernetesCollector(namespace=namespace, environment="evaluation")
    snapshot = collector.collect()
    snapshot, github_stats = augment_snapshot_with_github(
        snapshot,
        github["repository"],
        [github["commit"]],
        "https://api.github.com",
    )
    snapshot, actions_stats = augment_snapshot_with_github_actions(
        snapshot,
        [github["workflow_run"]],
        github["repository"]["full_name"],
        "https://api.github.com",
    )
    signals = KubernetesEventCollector(
        collector.core_api,
        collector.connection.cluster_name,
        namespace,
    ).collect(snapshot)
    snapshot_json = snapshot.model_dump(mode="json")
    signal_json = [signal.model_dump(mode="json") for signal in signals]
    return (
        {
            "snapshot_id": snapshot.snapshot_id,
            "incident_id": None,
            "pinned_snapshot_id": None,
            "cluster_name": collector.connection.cluster_name,
            "entities": snapshot_json["entities"],
            "relationships": snapshot_json["relationships"],
            "signals": signal_json,
            "collected_at": snapshot_json["collected_at"],
        },
        {
            "github": asdict(github_stats),
            "github_actions": actions_stats,
        },
    )


def _provider_hops(
    github: dict[str, Any],
    registry: dict[str, Any],
    deployment: dict[str, Any],
    replica_set: dict[str, Any],
    pod: dict[str, Any],
    event: dict[str, Any],
    cluster_name: str,
) -> dict[str, dict[str, Any]]:
    repo = github["repository"]
    commit = github["commit"]
    run = github["workflow_run"]
    repo_id = github_repository_canonical_id(
        api_url="https://api.github.com", repository_native_id=repo["id"]
    )
    commit_id = github_commit_canonical_id(
        repository_canonical_id=repo_id, sha=commit["sha"]
    )
    run_entity_id = github_workflow_run_canonical_id(
        api_url="https://api.github.com", run_id=run["id"]
    )
    digest = registry["immutable_digest"]
    image_id = container_image_canonical_id(digest)
    dep_meta = deployment["metadata"]
    rs_meta = replica_set["metadata"]
    pod_meta = pod["metadata"]
    event_meta = event["metadata"]
    commit_time = ((commit.get("commit") or {}).get("committer") or {}).get("date")
    deployment_time = dep_meta.get("creationTimestamp")
    rs_time = rs_meta.get("creationTimestamp")
    pod_time = pod_meta.get("creationTimestamp")
    failure_time = (
        event.get("firstTimestamp")
        or event.get("eventTime")
        or event_meta.get("creationTimestamp")
    )
    repo_identity = provider_identity(
        provider="github",
        kind="GitRepository",
        native_id=repo["id"],
        canonical_id=repo_id,
        name=repo["full_name"],
    )
    commit_identity = provider_identity(
        provider="github",
        kind="GitCommit",
        native_id=commit["sha"],
        canonical_id=commit_id,
        name=commit["sha"],
        scope={"repository": repo["full_name"]},
    )
    run_identity = provider_identity(
        provider="github-actions",
        kind="GitHubWorkflowRun",
        native_id=run["id"],
        canonical_id=run_entity_id,
        name=run.get("name"),
        scope={"repository": repo["full_name"]},
    )
    image_identity = provider_identity(
        provider="registry",
        kind="ContainerImage",
        native_id=digest,
        canonical_id=image_id,
        name=registry["image_reference"],
        immutable_digest=digest,
    )

    def kube_identity(kind: str, metadata: dict[str, Any]) -> dict[str, Any]:
        return provider_identity(
            provider="kubernetes",
            kind=f"Kubernetes{kind}",
            native_id=metadata["uid"],
            canonical_id=kubernetes_canonical_id(
                cluster=cluster_name, kind=kind, uid=metadata["uid"]
            ),
            name=metadata["name"],
            scope={"cluster": cluster_name, "namespace": metadata.get("namespace")},
        )

    dep_identity = kube_identity("Deployment", dep_meta)
    rs_identity = kube_identity("ReplicaSet", rs_meta)
    pod_identity = kube_identity("Pod", pod_meta)
    signal_identity = provider_identity(
        provider="kubernetes",
        kind="RuntimeFailureSignal",
        native_id=event_meta["uid"],
        canonical_id=kubernetes_signal_id(
            cluster=cluster_name, event_uid=event_meta["uid"]
        ),
        name=event.get("reason"),
        scope={"cluster": cluster_name, "namespace": event_meta.get("namespace")},
    )
    evidence = {
        "repository_url": repo.get("html_url"),
        "commit_url": commit.get("html_url"),
        "workflow_run_url": run.get("html_url"),
    }
    return {
        "H1": {
            "source_identity": repo_identity,
            "target_identity": commit_identity,
            "relationship_established": commit.get("repository_full_name") == repo["full_name"],
            "direction": "repository_to_commit",
            "source_time": None,
            "target_time": commit_time,
            "evidence_references": evidence,
        },
        "H2": {
            "source_identity": commit_identity,
            "target_identity": run_identity,
            "relationship_established": str(run.get("head_sha", "")).lower()
            == str(commit["sha"]).lower(),
            "direction": "commit_to_workflow_run",
            "source_time": commit_time,
            "target_time": run.get("created_at"),
            "evidence_references": evidence,
        },
        "H3": {
            "status": "PROVIDER_PREREQUISITE_BLOCKED",
            "source_identity": run_identity,
            "target_identity": None,
            "relationship_established": False,
            "direction": "workflow_run_to_image",
            "source_time": run.get("updated_at"),
            "target_time": None,
            "immutable_artifact_proven": None,
            "evidence_references": evidence,
            "reason": (
                "The selected real Actions run produced only a CLI archive. No existing "
                "evaluation-safe workflow/run links this run to a published container digest."
            ),
        },
        "H4": {
            "source_identity": image_identity,
            "target_identity": dep_identity,
            "relationship_established": any(
                container.get("image") == registry["image_reference"]
                for container in (((deployment.get("spec") or {}).get("template") or {}).get("spec") or {}).get("containers") or []
            ),
            "direction": "deployment_uses_image",
            "source_time": None,
            "target_time": deployment_time,
            "immutable_artifact_proven": True,
            "evidence_references": {
                "image_reference": registry["image_reference"],
                "deployment_uid": dep_meta["uid"],
            },
        },
        "H5": {
            "source_identity": dep_identity,
            "target_identity": rs_identity,
            "relationship_established": any(
                ref.get("uid") == dep_meta["uid"]
                for ref in rs_meta.get("ownerReferences") or []
            ),
            "direction": "deployment_to_replicaset",
            "source_time": deployment_time,
            "target_time": rs_time,
            "evidence_references": {"owner_references": rs_meta.get("ownerReferences")},
        },
        "H6": {
            "source_identity": rs_identity,
            "target_identity": pod_identity,
            "relationship_established": any(
                ref.get("uid") == rs_meta["uid"]
                for ref in pod_meta.get("ownerReferences") or []
            ),
            "direction": "replicaset_to_pod",
            "source_time": rs_time,
            "target_time": pod_time,
            "evidence_references": {"owner_references": pod_meta.get("ownerReferences")},
        },
        "H7": {
            "source_identity": pod_identity,
            "target_identity": signal_identity,
            "relationship_established": (
                (event.get("involvedObject") or {}).get("uid") == pod_meta["uid"]
                and event.get("reason") in FAILURE_REASONS
            ),
            "direction": "pod_to_failure_signal",
            "source_time": pod_time,
            "target_time": failure_time,
            "accepted_failure_reasons": sorted(FAILURE_REASONS),
            "evidence_references": {
                "event_uid": event_meta["uid"],
                "reason": event.get("reason"),
                "pod_uid": pod_meta["uid"],
            },
        },
    }


def run_baseline(args: argparse.Namespace) -> Path:
    started_at = _utc_now()
    run_id = uuid4().hex[:8]
    namespace = f"{NAMESPACE_PREFIX}{run_id}"
    github: dict[str, Any] | None = None
    try:
        github = _github_receipts(args.repository, args.commit, args.actions_run)
        if str(github["workflow_run"].get("head_sha", "")).lower() != args.commit.lower():
            raise RuntimeError("Selected Actions run does not use the requested exact commit SHA.")
        registry = _registry_receipt(args.image, args.image_digest)
        _create_namespace(namespace, run_id)
        _apply_failure_deployment(namespace, run_id, args.image)
        pod, runtime_reason = _wait_for_runtime(namespace, args.timeout)
        pod_uid = pod["metadata"]["uid"]
        event = _wait_for_failure_event(namespace, pod_uid, args.timeout)
        deployment = _json_command(
            ["kubectl", "get", "deployment", "lineage-failure", "-n", namespace, "-o", "json"]
        )
        replica_sets = _json_command(
            ["kubectl", "get", "replicasets", "-n", namespace, "-l", "app=lineage-failure", "-o", "json"]
        )["items"]
        if len(replica_sets) != 1:
            raise RuntimeError("Expected exactly one disposable ReplicaSet.")
        replica_set = replica_sets[0]
        topo, enrichment_stats = _load_product_observation(namespace, github)
        provider_hops = _provider_hops(
            github,
            registry,
            deployment,
            replica_set,
            pod,
            event,
            topo["cluster_name"],
        )
        evaluation = evaluate_lineage_chain(provider_hops, topo)
        product_commit = _run(["git", "rev-parse", "HEAD"]).strip()
        prerequisites = {
            "github_repo_available": {"value": True, "reason": "Repository read succeeded."},
            "github_authenticated": {"value": True, "reason": "Authenticated read-only gh API calls succeeded."},
            "safe_actions_run_available": {
                "value": False,
                "reason": "A real H2 run exists, but no existing run publishes a container digest for H3.",
            },
            "safe_workflow_dispatch_available": {
                "value": False,
                "reason": "No inspected workflow_dispatch builds and publishes a bounded evaluation container.",
            },
            "immutable_image_digest_available": {
                "value": True,
                "reason": "An independent Docker Hub digest was available for H4-H7 only.",
            },
            "registry_access_available": {"value": True, "reason": "Read-only registry manifest inspection succeeded."},
            "kubernetes_available": {"value": True, "reason": "Disposable Docker Desktop namespace executed."},
            "topo_isolated_environment_available": {
                "value": True,
                "reason": "Current product collectors observed only the disposable namespace.",
            },
        }
        provider_truth = {
            "github": github,
            "registry": registry,
            "kubernetes": {
                "namespace": namespace,
                "namespace_label": {RUN_LABEL: run_id},
                "deployment": deployment,
                "replica_set": replica_set,
                "pod": pod,
                "failure_event": event,
                "runtime_failure_reason": runtime_reason,
                "runtime_failure_cause": "deployment_runtime_override",
            },
            "hop_truth": provider_hops,
            "enrichment_stats": enrichment_stats,
        }
        result = LineageResult(
            result_version=LINEAGE_RESULT_VERSION,
            hop_contract_version=LINEAGE_HOP_VERSION,
            run_id=run_id,
            scenario_id=LINEAGE_SCENARIO_ID,
            started_at=started_at,
            completed_at=_utc_now(),
            product_git_commit=product_commit,
            execution_mode="MODE_C",
            prerequisites=prerequisites,
            provider_truth=provider_truth,
            topo_observation=topo,
            hop_results=evaluation["hop_results"],
            first_broken_hop=evaluation["first_broken_hop"],
            first_broken_hop_id=evaluation["first_broken_hop_id"],
            proven_hop_count=evaluation["proven_hop_count"],
            partial_hop_count=evaluation["partial_hop_count"],
            missing_hop_count=evaluation["missing_hop_count"],
            wrong_hop_count=evaluation["wrong_hop_count"],
            inconclusive_hop_count=evaluation["inconclusive_hop_count"],
            provider_blocked_hop_count=evaluation["provider_blocked_hop_count"],
            lineage_complete=evaluation["lineage_complete"],
            immutable_artifact_chain_complete=evaluation["immutable_artifact_chain_complete"],
            source_to_runtime_strength=evaluation["source_to_runtime_strength"],
            source_change_causally_proven="not_tested",
            commercial_proof_status=evaluation["commercial_proof_status"],
            warnings=[
                "H3 was not executed because provider prerequisites are absent.",
                "The nginx digest used for H4-H7 is not attributed to the selected GitHub Actions run.",
                "The runtime failure was induced by a Deployment command override; source-change causality was not tested.",
                "No incident was produced; incident-pinned lineage evaluation was therefore not applicable.",
            ],
        )
        safe_result = sanitize_provider_receipt(result.as_dict())
        RESULTS.mkdir(parents=True, exist_ok=True)
        output = RESULTS / f"lineage-{run_id}.json"
        output.write_text(deterministic_json(safe_result), encoding="utf-8")
        return output
    finally:
        _cleanup_namespace(namespace, run_id)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the LINEAGE-0 provider baseline.")
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--commit", default=DEFAULT_COMMIT)
    parser.add_argument("--actions-run", default=DEFAULT_ACTIONS_RUN)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--image-digest", default=DEFAULT_IMAGE_DIGEST)
    parser.add_argument("--timeout", type=int, default=150)
    return parser


def main(argv: list[str] | None = None) -> int:
    output = run_baseline(build_parser().parse_args(argv))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
