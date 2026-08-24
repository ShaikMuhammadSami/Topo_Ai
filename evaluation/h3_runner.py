from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation.h3_observation import (
    build_h3_result,
    evaluate_h3,
    load_provider_receipt,
    observe_topo_snapshot,
    provider_expected_from_receipt,
    serialize_h3_result,
)


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DEFAULT_RECEIPT = (
    ROOT
    / "evaluation/results/provider-receipts/32688747741-1"
    / "topo-lineage-provider-receipt.json"
)
RESULTS = ROOT / "evaluation/results/lineage/h3"
NAMESPACE_PREFIX = "topo-eval-h3-"
RUN_LABEL = "topo.ai/evaluation-run"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run(
    command: list[str],
    *,
    input_text: str | None = None,
    check: bool = True,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"Read/exercise command failed ({command[0]} {command[1]}): "
            f"exit {completed.returncode}"
        )
    return completed


def _json_command(command: list[str], *, timeout: int = 60) -> dict[str, Any]:
    completed = _run(command, timeout=timeout)
    return json.loads(completed.stdout)


def _github_verification(receipt: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    repository = receipt["repository"]
    run_id = str(receipt["run_id"])
    repo = _json_command(["gh", "api", f"repos/{repository}"])
    commit = _json_command(
        ["gh", "api", f"repos/{repository}/commits/{receipt['commit_sha']}"]
    )
    run = _json_command(["gh", "api", f"repos/{repository}/actions/runs/{run_id}"])
    workflow = _json_command(
        ["gh", "api", f"repos/{repository}/actions/workflows/{run['workflow_id']}"]
    )
    artifacts = _json_command(
        ["gh", "api", f"repos/{repository}/actions/runs/{run_id}/artifacts"]
    )

    checks = {
        "repository_id_match": str(repo.get("id")) == str(receipt["repository_id"]),
        "repository_name_match": repo.get("full_name") == receipt["repository"],
        "commit_sha_match": str(commit.get("sha", "")).lower()
        == receipt["commit_sha"],
        "run_id_match": str(run.get("id")) == run_id,
        "run_attempt_match": run.get("run_attempt") == receipt["run_attempt"],
        "run_number_match": run.get("run_number") == receipt["run_number"],
        "workflow_name_match": run.get("name") == receipt["workflow_name"],
        "workflow_path_match": workflow.get("path")
        == ".github/workflows/topo-lineage-provider-fixture.yml",
        "head_sha_match": str(run.get("head_sha", "")).lower()
        == receipt["commit_sha"],
        "event_match": run.get("event") == receipt["event_name"],
        "completed_successfully": run.get("status") == "completed"
        and run.get("conclusion") == "success",
    }
    if not all(checks.values()):
        failed = sorted(key for key, value in checks.items() if not value)
        raise RuntimeError(f"Independent GitHub verification failed: {', '.join(failed)}")

    verification = {
        "method": "read_only_github_api_via_gh",
        "checks": checks,
        "repository": {
            "id": repo.get("id"),
            "full_name": repo.get("full_name"),
            "private": repo.get("private"),
            "default_branch": repo.get("default_branch"),
        },
        "workflow": {
            "id": workflow.get("id"),
            "name": workflow.get("name"),
            "path": workflow.get("path"),
            "state": workflow.get("state"),
        },
        "run": {
            "id": run.get("id"),
            "run_attempt": run.get("run_attempt"),
            "run_number": run.get("run_number"),
            "workflow_id": run.get("workflow_id"),
            "name": run.get("name"),
            "head_sha": run.get("head_sha"),
            "head_branch": run.get("head_branch"),
            "event": run.get("event"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "created_at": run.get("created_at"),
            "run_started_at": run.get("run_started_at"),
            "updated_at": run.get("updated_at"),
            "html_url": run.get("html_url"),
        },
        "run_timestamps": {
            "created_at": run.get("created_at"),
            "run_started_at": run.get("run_started_at"),
            "updated_at": run.get("updated_at"),
        },
        "artifacts": [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "size_in_bytes": item.get("size_in_bytes"),
                "expired": item.get("expired"),
                "created_at": item.get("created_at"),
            }
            for item in artifacts.get("artifacts") or []
        ],
    }
    product_payloads = {
        "repository": repo,
        "commit": commit,
        "workflow_run": run,
    }
    return verification, product_payloads


def _registry_verification(immutable_ref: str) -> dict[str, Any]:
    completed = _run(
        ["docker", "buildx", "imagetools", "inspect", "--raw", immutable_ref],
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        return {
            "registry_read_verification": "unavailable",
            "method": "docker_buildx_imagetools_read_only",
            "reason": "anonymous_registry_read_denied_or_unavailable",
        }
    manifest = json.loads(completed.stdout)
    return {
        "registry_read_verification": "verified",
        "method": "docker_buildx_imagetools_read_only",
        "media_type": manifest.get("mediaType"),
        "schema_version": manifest.get("schemaVersion"),
        "manifest_count": len(manifest.get("manifests") or []),
    }


def _namespace_manifest(namespace: str, run_id: str) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {"name": namespace, "labels": {RUN_LABEL: run_id}},
    }


def _deployment_manifest(
    namespace: str, run_id: str, immutable_ref: str
) -> dict[str, Any]:
    labels = {
        "app.kubernetes.io/name": "h3-image-materialization",
        RUN_LABEL: run_id,
    }
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": "h3-image-materialization",
            "namespace": namespace,
            "labels": labels,
        },
        "spec": {
            "replicas": 0,
            "selector": {"matchLabels": labels},
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "containers": [
                        {"name": "fixture", "image": immutable_ref}
                    ]
                },
            },
        },
    }


def _apply_json_manifest(manifest: dict[str, Any]) -> None:
    _run(["kubectl", "apply", "-f", "-"], input_text=json.dumps(manifest))


def _create_materialization(namespace: str, run_id: str, immutable_ref: str) -> None:
    existing = _run(
        ["kubectl", "get", "namespace", namespace, "-o", "json"],
        check=False,
    )
    if existing.returncode == 0:
        raise RuntimeError(f"Disposable namespace already exists: {namespace}")
    _apply_json_manifest(_namespace_manifest(namespace, run_id))
    _apply_json_manifest(_deployment_manifest(namespace, run_id, immutable_ref))


def _cleanup_materialization(namespace: str, run_id: str) -> None:
    existing = _run(
        ["kubectl", "get", "namespace", namespace, "-o", "json"],
        check=False,
    )
    if existing.returncode != 0:
        return
    payload = json.loads(existing.stdout)
    labels = (payload.get("metadata") or {}).get("labels") or {}
    if not namespace.startswith(NAMESPACE_PREFIX):
        raise RuntimeError("Refusing cleanup: namespace prefix guard failed")
    if labels.get(RUN_LABEL) != run_id:
        raise RuntimeError("Refusing cleanup: evaluation-run label guard failed")
    _run(
        [
            "kubectl",
            "delete",
            "namespace",
            namespace,
            "--wait=true",
            "--timeout=90s",
        ],
        timeout=100,
    )


def _plain_stats(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _exercise_product_path(
    *,
    namespace: str,
    provider_payloads: dict[str, Any],
    github_token: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    sys.path.insert(0, str(BACKEND))
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.collectors.kubernetes_collector import KubernetesCollector
    from app.connectors.github_connector import GitHubConnector, GitHubSettings
    from app.db.database import Base
    from app.services.github_actions_artifact_lineage import (
        enrich_snapshot_with_github_actions_provider_evidence,
    )
    from app.services.github_graph import augment_snapshot_with_github

    provider_repository = provider_payloads["repository"]
    owner, repository_name = str(provider_repository["full_name"]).split("/", 1)
    connector = GitHubConnector(
        GitHubSettings(
            owner=owner,
            repository=repository_name,
            token=github_token,
            api_url="https://api.github.com",
            api_version="2026-03-10",
            timeout_seconds=30,
            commit_limit=1,
        )
    )
    repository = connector.get_repository()
    commit = connector.get_commit(provider_payloads["commit"]["sha"])
    workflow_run = connector.get_workflow_run(
        provider_payloads["workflow_run"]["id"]
    )
    collector = KubernetesCollector(namespace=namespace, environment="evaluation")
    snapshot = collector.collect()
    snapshot, github_stats = augment_snapshot_with_github(
        snapshot,
        repository,
        [commit],
        connector.settings.api_url,
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        snapshot, actions_stats, lineage_stats = (
            enrich_snapshot_with_github_actions_provider_evidence(
                session,
                snapshot=snapshot,
                connector=connector,
                repository=repository,
                workflow_runs=[workflow_run],
            )
        )
    return snapshot.model_dump(mode="json"), {
        "github_enrichment": _plain_stats(github_stats),
        "github_actions_enrichment": _plain_stats(actions_stats),
        "github_actions_build_artifact_lineage": _plain_stats(lineage_stats),
    }


def run_h3_observation(args: argparse.Namespace) -> Path:
    receipt = load_provider_receipt(args.receipt)
    github_verification, provider_payloads = _github_verification(receipt)
    expected = provider_expected_from_receipt(
        receipt,
        github_verification=github_verification,
    )
    registry_verification = _registry_verification(receipt["immutable_image_ref"])
    provider_verification = {
        "receipt_schema_validation": "passed",
        "github": github_verification,
        "registry": registry_verification,
    }
    run_id = str(receipt["run_id"])
    namespace = f"{NAMESPACE_PREFIX}{run_id}"
    github_token = _run(["gh", "auth", "token"]).stdout.strip()
    if not github_token:
        raise RuntimeError("GitHub CLI did not provide an authenticated token")
    created = False
    try:
        _create_materialization(namespace, run_id, receipt["immutable_image_ref"])
        created = True
        snapshot, enrichment_stats = _exercise_product_path(
            namespace=namespace,
            provider_payloads=provider_payloads,
            github_token=github_token,
        )
        observation = observe_topo_snapshot(snapshot, expected)
        evaluation = evaluate_h3(expected, observation)
        product_commit = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
        ingestion_exercise = {
            "mode": "general_product_provider_connector_and_build_record_ingestion",
            "fresh_isolated_scope": namespace,
            "github_delivery": "read_only_product_connector_provider_api_ingestion",
            "receipt_used_as_product_input": False,
            "kubernetes_materialization_required": True,
            "kubernetes_materialization": {
                "namespace": namespace,
                "namespace_label": {RUN_LABEL: run_id},
                "deployment": "h3-image-materialization",
                "replicas": 0,
                "image": receipt["immutable_image_ref"],
                "runtime_failure_created": False,
                "workflow_run_metadata_added": False,
            },
            "enrichment_stats": enrichment_stats,
            "product_code_changed": True,
        }
        warnings = []
        if registry_verification["registry_read_verification"] == "unavailable":
            warnings.append(
                "Independent registry read was unavailable; the accepted receipt and "
                "successful provider run remain authoritative provider truth."
            )
        result = build_h3_result(
            provider_expected=expected,
            provider_verification=provider_verification,
            ingestion_exercise=ingestion_exercise,
            observation=observation,
            evaluation=evaluation,
            observed_at=_utc_now(),
            product_git_commit=product_commit,
            warnings=warnings,
        )
        RESULTS.mkdir(parents=True, exist_ok=True)
        output = RESULTS / f"h3-{run_id}-{receipt['run_attempt']}.json"
        output.write_text(serialize_h3_result(result), encoding="utf-8")
        return output
    finally:
        if created:
            _cleanup_materialization(namespace, run_id)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Observe current Topo H3 Actions-to-image lineage."
    )
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    return parser


def main(argv: list[str] | None = None) -> int:
    output = run_h3_observation(build_parser().parse_args(argv))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

