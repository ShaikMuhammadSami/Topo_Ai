from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from evaluation import HARNESS_VERSION
from evaluation.blast_scenarios import KubernetesBlastScenario
from evaluation.contracts import (
    EvaluationResult,
    EvaluationStatus,
    ProviderVerification,
    ScenarioManifest,
    TopoObservation,
)
from evaluation.evaluator import IndependentEvaluator
from evaluation.kubernetes import Kubectl, utc_now
from evaluation.scenarios import KubernetesSentinel, manifest_path, receipt_dict
from evaluation.topo_client import HttpObservation, TopoClient, bounded_wait


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = Path(__file__).with_name("results")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _tail(path: Path, lines: int = 30) -> str:
    if not path.exists():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])


class ManagedTopoEnvironment:
    def __init__(self, namespace: str, context: str | None, timeout_seconds: float):
        self.namespace = namespace
        self.context = context
        self.timeout_seconds = timeout_seconds
        self.root = Path(tempfile.mkdtemp(prefix="topo-eval-"))
        self.port = _free_port()
        self.client = TopoClient(f"http://127.0.0.1:{self.port}")
        self.backend: subprocess.Popen[str] | None = None
        self.agent: subprocess.Popen[str] | None = None
        self._files: list[Any] = []

    def start_backend(self) -> None:
        python = REPOSITORY_ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
        if not python.exists():
            raise RuntimeError(f"Backend virtual environment not found: {python}")
        log_path = self.root / "backend.log"
        log = log_path.open("w", encoding="utf-8")
        self._files.append(log)
        env = os.environ.copy()
        env.update(
            {
                "TOPO_DATABASE_URL": f"sqlite:///{(self.root / 'topo-eval.db').as_posix()}",
                "TOPO_AUTH_ENABLED": "false",
                "PYTHONUNBUFFERED": "1",
            }
        )
        self.backend = subprocess.Popen(
            [str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=REPOSITORY_ROOT / "backend",
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            bounded_wait(
                lambda: self.client.get("/api/v1/system/whoami"),
                lambda response: response.status == 200,
                timeout_seconds=45,
                interval_seconds=1,
            )
        except Exception as exc:
            raise RuntimeError(f"Isolated backend did not start.\n{_tail(log_path)}") from exc

    def start_agent(self, kubectl: Kubectl, run_id: str) -> dict[str, Any]:
        token_response = self.client.post(
            "/api/v1/agents/enrollment-tokens",
            {"label": f"eval-{run_id}", "expires_in_minutes": 30, "max_uses": 1},
        )
        if token_response.status != 201:
            raise RuntimeError(f"Could not create isolated agent enrollment token: {token_response.body}")
        enrollment = self.client.post(
            "/api/v1/agents/enroll",
            {
                "enrollment_token": token_response.body["enrollment_token"],
                "name": f"eval-{run_id}",
                "agent_type": "kubernetes",
                "cluster_name": kubectl.cluster_name(),
                "environment": "evaluation",
                "version": "0.7.0",
                "collection_interval_seconds": 30,
                "heartbeat_interval_seconds": 10,
                "namespace_scope": [self.namespace],
                "capabilities": ["topology", "change-watch", "failure-signals"],
                "labels": {"evaluation_run": run_id},
                "metadata": {"purpose": "EVAL-1 isolated sentinel"},
            },
        )
        if enrollment.status != 201:
            raise RuntimeError(f"Could not enroll isolated agent: {enrollment.body}")
        executable = REPOSITORY_ROOT / "agent" / ".venv" / "Scripts" / "topo-agent.exe"
        if not executable.exists():
            raise RuntimeError(f"Agent executable not found: {executable}")
        log_path = self.root / "agent.log"
        log = log_path.open("w", encoding="utf-8")
        self._files.append(log)
        env = os.environ.copy()
        env.update(
            {
                "TOPO_AGENT_HOME": str(self.root / "agent-home"),
                "TOPO_BACKEND_URL": self.client.base_url,
                "TOPO_AGENT_ID": enrollment.body["agent_id"],
                "TOPO_AGENT_TOKEN": enrollment.body["agent_token"],
                "TOPO_AGENT_NAME": f"eval-{run_id}",
                "TOPO_CLUSTER_NAME": kubectl.cluster_name(),
                "TOPO_NAMESPACES": self.namespace,
                "TOPO_KUBE_CONTEXT": self.context or kubectl.current_context(),
                "TOPO_ENABLED_PLUGINS": "kubernetes",
                "TOPO_COLLECTION_INTERVAL": "30",
                "TOPO_HEARTBEAT_INTERVAL": "10",
                "TOPO_CHANGE_WATCH_INTERVAL": "5",
                "TOPO_CHANGE_WATCH_OVERLAP": "20",
                "TOPO_CHANGE_WATCH_KUBERNETES": "true",
                "PYTHONUNBUFFERED": "1",
            }
        )
        self.agent = subprocess.Popen(
            [str(executable), "run"],
            cwd=REPOSITORY_ROOT / "agent",
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return {"agent_id": enrollment.body["agent_id"]}

    def wait_for_initial_snapshot(self, expected_entity_name: str) -> dict[str, Any]:
        def find() -> dict[str, Any] | None:
            listing = self.client.get("/api/v1/snapshots", limit=100)
            if listing.status != 200:
                return None
            for summary in listing.body:
                snapshot = self.client.get(f"/api/v1/snapshots/{summary['snapshot_id']}")
                if snapshot.status != 200:
                    continue
                if any(
                    entity.get("name") == expected_entity_name
                    and entity.get("properties", {}).get("namespace") == self.namespace
                    for entity in snapshot.body.get("entities", [])
                ):
                    return snapshot.body
            return None

        return bounded_wait(
            find,
            lambda value: value is not None,
            timeout_seconds=self.timeout_seconds,
            interval_seconds=3,
        )

    def diagnostics(self) -> str:
        return "BACKEND\n" + _tail(self.root / "backend.log") + "\nAGENT\n" + _tail(self.root / "agent.log")

    def close(self) -> None:
        for process in (self.agent, self.backend):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        for file in self._files:
            file.close()
        last_error: OSError | None = None
        for _ in range(10):
            try:
                shutil.rmtree(self.root)
                return
            except OSError as exc:
                last_error = exc
                time.sleep(0.25)
        if last_error is not None:
            raise RuntimeError(
                f"Could not remove isolated evaluation state {self.root}: {last_error}"
            ) from last_error


def _capture_topo(client: TopoClient, namespace: str, timeout_seconds: float) -> TopoObservation:
    statuses: dict[str, int] = {}
    times: dict[str, str] = {}

    def incidents() -> HttpObservation:
        return client.get("/api/v1/incident-records", namespace=namespace, limit=100)

    incident_list = bounded_wait(
        incidents,
        lambda response: response.status == 200 and bool(response.body),
        timeout_seconds=timeout_seconds,
        interval_seconds=3,
    )
    times["incident"] = utc_now()
    summary = sorted(incident_list.body, key=lambda item: item["first_observed_at"])[-1]
    incident_id = summary["incident_id"]
    incident_response = client.get(f"/api/v1/incident-records/{incident_id}")
    statuses["incident"] = incident_response.status
    incident = incident_response.body if incident_response.status == 200 else None

    signals_response = client.get(f"/api/v1/incident-records/{incident_id}/signals")
    statuses["signals"] = signals_response.status

    analysis_response = bounded_wait(
        lambda: client.get(f"/api/v1/incidents/{incident_id}/causal-rca/latest"),
        lambda response: response.status == 200,
        timeout_seconds=timeout_seconds,
        interval_seconds=3,
    )
    statuses["causal_analysis"] = analysis_response.status
    times["causal_analysis"] = str(analysis_response.body.get("generated_at") or utc_now())
    analysis = analysis_response.body

    briefing_response = client.get(f"/api/v1/incidents/{incident_id}/briefing", include_ai="false")
    statuses["briefing"] = briefing_response.status
    briefing = briefing_response.body if briefing_response.status == 200 else None
    if briefing is not None:
        times["briefing"] = str(briefing.get("generated_at") or utc_now())

    snapshot = None
    snapshot_id = (incident or {}).get("topology_snapshot_id")
    if snapshot_id:
        snapshot_response = client.get(f"/api/v1/snapshots/{snapshot_id}")
        statuses["snapshot"] = snapshot_response.status
        snapshot = snapshot_response.body if snapshot_response.status == 200 else None

    blast_response = client.get(f"/api/v1/incidents/{incident_id}/blast-radius")
    statuses["blast_radius"] = blast_response.status
    blast = blast_response.body if blast_response.status == 200 else None

    changes_response = client.get("/api/v1/change-events", namespace=namespace, limit=5000)
    statuses["change_events"] = changes_response.status
    incident_changes_response = client.get(
        f"/api/v1/incidents/{incident_id}/change-events",
        lookback_minutes=180,
        after_minutes=10,
        limit=100,
    )
    statuses["incident_change_analysis"] = incident_changes_response.status

    return TopoObservation(
        observation_version="eval-1.topo-observation.v1",
        captured_at=utc_now(),
        incident=incident,
        incident_candidates=incident_list.body,
        incident_signals=(signals_response.body if signals_response.status == 200 else None),
        snapshot=snapshot,
        causal_analysis=analysis,
        briefing=briefing,
        blast_radius=blast,
        change_events=(changes_response.body if changes_response.status == 200 else []),
        incident_change_analysis=(
            incident_changes_response.body
            if incident_changes_response.status == 200
            else None
        ),
        endpoint_statuses=statuses,
        observed_times=times,
    )


def run_scenario(
    scenario_id: str,
    *,
    context: str | None = None,
    timeout_seconds: float = 240.0,
    output_dir: Path = RESULTS_DIR,
) -> tuple[EvaluationResult, Path]:
    manifest = ScenarioManifest.load(manifest_path(scenario_id))
    run_id = uuid.uuid4().hex[:8]
    namespace_token = scenario_id if scenario_id.startswith("blast-") else scenario_id[-1]
    namespace = f"topo-eval-{namespace_token}-{run_id}"
    started_at = utc_now()
    kubectl = Kubectl(context)
    environment = kubectl.validate_prerequisites()
    environment["isolated_backend_database"] = True
    environment["isolated_agent_state"] = True
    managed = ManagedTopoEnvironment(namespace, context, timeout_seconds)
    scenario = (
        KubernetesBlastScenario(manifest, kubectl, namespace, run_id)
        if scenario_id.startswith("blast-")
        else KubernetesSentinel(manifest, kubectl, namespace, run_id)
    )
    receipt: dict[str, Any] = {}
    provider = ProviderVerification(
        verification_version="eval-1.provider.v1",
        source="kubernetes-api-via-kubectl",
        observed_at=started_at,
        established=False,
    )
    topo = TopoObservation(observation_version="eval-1.topo-observation.v1", captured_at=started_at)
    warnings: list[str] = []
    status = EvaluationStatus.HARNESS_ERROR
    metrics: dict[str, Any] = {}
    assertions: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    try:
        managed.start_backend()
        scenario.prepare()
        first_deployment = next(
            str(value.get("metadata", {}).get("name"))
            for alias, value in scenario.objects.items()
            if alias.endswith("deployment")
        )
        environment.update(managed.start_agent(kubectl, run_id))
        initial = managed.wait_for_initial_snapshot(first_deployment)
        environment["initial_snapshot_id"] = initial.get("snapshot_id")
        execution_receipt, provider = scenario.execute()
        receipt = receipt_dict(execution_receipt)
        try:
            topo = _capture_topo(managed.client, namespace, timeout_seconds)
        except TimeoutError as exc:
            warnings.append(str(exc))
            # Provider truth exists: lack of Topo reaction is a product failure,
            # not a harness failure.
        status, metrics, assertions, failures = IndependentEvaluator().evaluate(
            manifest,
            provider,
            topo,
            scenario_started_at=started_at,
        )
    except Exception as exc:
        failures.append(
            {
                "assertion": "scenario_execution",
                "category": "HARNESS",
                "detail": str(exc),
            }
        )
        warnings.append(managed.diagnostics())
        status = EvaluationStatus.HARNESS_ERROR
    finally:
        try:
            existing_namespace = kubectl.get(
                "namespace",
                namespace,
                allow_missing=True,
            )
            if existing_namespace is not None:
                environment["namespace_cleanup_requested"] = True
                kubectl.cleanup_namespace(namespace, run_id)
                environment["namespace_cleanup_completed"] = True
        except Exception as exc:
            warnings.append(f"Cleanup failed: {exc}")
            status = EvaluationStatus.HARNESS_ERROR
        try:
            managed.close()
        except Exception as exc:
            warnings.append(str(exc))
            status = EvaluationStatus.HARNESS_ERROR

    completed_at = utc_now()
    result = EvaluationResult(
        result_version="eval-1.result.v1",
        harness_version=HARNESS_VERSION,
        run_id=run_id,
        scenario_id=scenario_id,
        topo_git_commit=_git_commit(),
        started_at=started_at,
        completed_at=completed_at,
        environment=environment,
        ground_truth=manifest.ground_truth_copy(),
        execution_receipt=receipt,
        provider_verification=asdict(provider),
        topo_observation=asdict(topo),
        metric_results=metrics,
        assertions=assertions,
        failures=failures,
        warnings=warnings,
        overall_status=status,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{scenario_id}-{run_id}.json"
    output_path.write_text(result.to_json(), encoding="utf-8")
    return result, output_path
