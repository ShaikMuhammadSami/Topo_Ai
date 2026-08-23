from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

from evaluation.contracts import ProviderObject
from evaluation.topo_client import bounded_wait


EVALUATION_LABEL = "topo.ai/evaluation-run"
SAFE_NAMESPACE = re.compile(r"^topo-eval-[abcd]-[a-z0-9]{6,12}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Kubectl:
    def __init__(self, context: str | None = None):
        self.context = context

    def run(self, *args: str, timeout: float = 60.0, json_output: bool = False) -> Any:
        command = ["kubectl"]
        if self.context:
            command.extend(("--context", self.context))
        command.extend(args)
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if completed.returncode:
            raise RuntimeError(
                f"kubectl failed ({completed.returncode}): {' '.join(command)}\n"
                f"stdout: {completed.stdout.strip()}\nstderr: {completed.stderr.strip()}"
            )
        if json_output:
            return json.loads(completed.stdout)
        return completed.stdout.strip()

    def current_context(self) -> str:
        return str(self.run("config", "current-context"))

    def cluster_name(self) -> str:
        value = self.run(
            "config",
            "view",
            "--minify",
            "-o",
            "jsonpath={.contexts[0].context.cluster}",
        )
        return str(value) or self.current_context()

    def validate_prerequisites(self) -> dict[str, Any]:
        context = self.current_context()
        version = self.run("version", "-o", "json", json_output=True)
        return {
            "provider": "kubernetes",
            "context": context,
            "cluster": self.cluster_name(),
            "server_version": version.get("serverVersion", {}).get("gitVersion"),
        }

    def create_namespace(self, namespace: str, run_id: str) -> dict[str, Any]:
        if not SAFE_NAMESPACE.fullmatch(namespace):
            raise ValueError(f"Unsafe evaluation namespace: {namespace}")
        self.run("create", "namespace", namespace)
        self.run("label", "namespace", namespace, f"{EVALUATION_LABEL}={run_id}", "--overwrite")
        return self.get("namespace", namespace)

    def cleanup_namespace(self, namespace: str, run_id: str) -> None:
        if not SAFE_NAMESPACE.fullmatch(namespace):
            raise ValueError(f"Refusing cleanup for unsafe namespace: {namespace}")
        existing = self.get("namespace", namespace, allow_missing=True)
        if existing is None:
            return
        actual = existing.get("metadata", {}).get("labels", {}).get(EVALUATION_LABEL)
        if actual != run_id:
            raise ValueError(
                f"Refusing cleanup: namespace label {EVALUATION_LABEL}={actual!r}, expected {run_id!r}."
            )
        self.run(
            "delete",
            "namespace",
            namespace,
            "--wait=true",
            "--timeout=120s",
            timeout=130,
        )

    def get(
        self,
        kind: str,
        name: str | None = None,
        *,
        namespace: str | None = None,
        selector: str | None = None,
        allow_missing: bool = False,
    ) -> dict[str, Any] | None:
        args = ["get", kind]
        if name:
            args.append(name)
        if namespace:
            args.extend(("-n", namespace))
        if selector:
            args.extend(("-l", selector))
        args.extend(("-o", "json"))
        try:
            return self.run(*args, json_output=True)
        except RuntimeError as exc:
            if allow_missing and "NotFound" in str(exc):
                return None
            raise

    def create_deployment(self, namespace: str, name: str, image: str, run_id: str) -> dict[str, Any]:
        self.run("create", "deployment", name, "-n", namespace, f"--image={image}", "--replicas=1")
        self.run(
            "label",
            "deployment",
            name,
            "-n",
            namespace,
            f"{EVALUATION_LABEL}={run_id}",
            "--overwrite",
        )
        return self.get("deployment", name, namespace=namespace) or {}

    def expose_deployment(self, namespace: str, name: str, port: int, run_id: str) -> dict[str, Any]:
        self.run("expose", "deployment", name, "-n", namespace, f"--port={port}", f"--target-port={port}")
        self.run("label", "service", name, "-n", namespace, f"{EVALUATION_LABEL}={run_id}", "--overwrite")
        return self.get("service", name, namespace=namespace) or {}

    def wait_ready(self, namespace: str, name: str, timeout_seconds: float = 180.0) -> dict[str, Any]:
        return bounded_wait(
            lambda: self.get("deployment", name, namespace=namespace),
            lambda value: bool(
                value
                and value.get("status", {}).get("availableReplicas", 0) >= 1
                and value.get("status", {}).get("observedGeneration", 0)
                >= value.get("metadata", {}).get("generation", 0)
            ),
            timeout_seconds=timeout_seconds,
            interval_seconds=3,
        )

    def set_image(self, namespace: str, deployment: str, image: str) -> dict[str, Any]:
        before = self.get("deployment", deployment, namespace=namespace) or {}
        containers = before.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        if not containers:
            raise RuntimeError(f"Deployment {deployment} has no container.")
        container_name = str(containers[0]["name"])
        self.run("set", "image", f"deployment/{deployment}", f"{container_name}={image}", "-n", namespace)
        return self.get("deployment", deployment, namespace=namespace) or {}

    def wait_image_pull_failure(self, namespace: str, deployment: str, timeout_seconds: float = 180.0) -> dict[str, Any]:
        def newest_failing_pod() -> dict[str, Any] | None:
            deployment_object = self.get("deployment", deployment, namespace=namespace) or {}
            selector = deployment_object.get("spec", {}).get("selector", {}).get("matchLabels", {})
            selector_text = ",".join(f"{key}={value}" for key, value in sorted(selector.items()))
            pod_list = self.get("pods", namespace=namespace, selector=selector_text) or {"items": []}
            candidates = sorted(
                pod_list.get("items", []),
                key=lambda item: item.get("metadata", {}).get("creationTimestamp", ""),
                reverse=True,
            )
            for pod in candidates:
                for status in pod.get("status", {}).get("containerStatuses", []):
                    reason = status.get("state", {}).get("waiting", {}).get("reason")
                    if reason in {"ImagePullBackOff", "ErrImagePull"}:
                        return pod
            return None

        return bounded_wait(
            newest_failing_pod,
            lambda value: value is not None,
            timeout_seconds=timeout_seconds,
            interval_seconds=3,
        )

    def ready_service_endpoint_count(self, namespace: str, service: str) -> int:
        endpoint_slices = self.get(
            "endpointslices",
            namespace=namespace,
            selector=f"kubernetes.io/service-name={service}",
        ) or {"items": []}
        count = 0
        for endpoint_slice in endpoint_slices.get("items", []):
            for endpoint in endpoint_slice.get("endpoints", []):
                if endpoint.get("conditions", {}).get("ready") is not False:
                    count += len(endpoint.get("addresses", []))
        return count

    @staticmethod
    def provider_object(logical_name: str, value: dict[str, Any]) -> ProviderObject:
        metadata = value.get("metadata", {})
        spec = value.get("spec", {})
        owner_references = metadata.get("ownerReferences", [])
        containers = spec.get("template", {}).get("spec", {}).get("containers") or spec.get("containers", [])
        relevant_spec: dict[str, Any] = {}
        if containers:
            relevant_spec["images"] = [item.get("image") for item in containers]
        if spec.get("selector") is not None:
            relevant_spec["selector"] = spec.get("selector")
        if spec.get("generation") is not None:
            relevant_spec["generation"] = spec.get("generation")
        return ProviderObject(
            logical_name=logical_name,
            provider_kind=str(value.get("kind") or ""),
            namespace=str(metadata.get("namespace") or ""),
            name=str(metadata.get("name") or ""),
            uid=str(metadata.get("uid") or ""),
            observed_at=utc_now(),
            spec=relevant_spec,
            status=value.get("status", {}),
            owner_uid=(str(owner_references[0].get("uid")) if owner_references else None),
            labels={str(key): str(item) for key, item in metadata.get("labels", {}).items()},
            selectors={str(key): str(item) for key, item in (spec.get("selector") or {}).items()} if value.get("kind") == "Service" else {},
        )

    def owned_chain(self, namespace: str, deployment: dict[str, Any], pod: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        pod_owners = pod.get("metadata", {}).get("ownerReferences", [])
        if not pod_owners:
            raise RuntimeError("Failing Pod has no provider-native owner reference.")
        replica_set = self.get("replicaset", str(pod_owners[0]["name"]), namespace=namespace) or {}
        deployment_uid = str(deployment.get("metadata", {}).get("uid") or "")
        rs_owners = replica_set.get("metadata", {}).get("ownerReferences", [])
        if not any(str(item.get("uid")) == deployment_uid for item in rs_owners):
            raise RuntimeError("Provider truth does not link failing ReplicaSet to expected Deployment.")
        return replica_set, pod
