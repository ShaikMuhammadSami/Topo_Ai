from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from typing import Any

from evaluation.contracts import ProviderObject
from evaluation.topo_client import bounded_wait


EVALUATION_LABEL = "topo.ai/evaluation-run"
SAFE_NAMESPACE = re.compile(
    r"^topo-eval-(?:[abcd]|blast-(?:01|02|03))-[a-z0-9]{6,12}$"
)


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

    def create_deployment(
        self,
        namespace: str,
        name: str,
        image: str,
        run_id: str,
        *,
        replicas: int = 1,
    ) -> dict[str, Any]:
        self.run(
            "create",
            "deployment",
            name,
            "-n",
            namespace,
            f"--image={image}",
            f"--replicas={replicas}",
        )
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

    def wait_ready(
        self,
        namespace: str,
        name: str,
        *,
        replicas: int = 1,
        timeout_seconds: float = 180.0,
    ) -> dict[str, Any]:
        return bounded_wait(
            lambda: self.get("deployment", name, namespace=namespace),
            lambda value: bool(
                value
                and value.get("status", {}).get("availableReplicas", 0) >= replicas
                and value.get("status", {}).get("observedGeneration", 0)
                >= value.get("metadata", {}).get("generation", 0)
            ),
            timeout_seconds=timeout_seconds,
            interval_seconds=3,
        )

    def use_recreate_strategy(self, namespace: str, deployment: str) -> dict[str, Any]:
        patch = '{"spec":{"strategy":{"type":"Recreate","rollingUpdate":null}}}'
        self.run(
            "patch",
            "deployment",
            deployment,
            "-n",
            namespace,
            "--type=merge",
            "-p",
            patch,
        )
        return self.get("deployment", deployment, namespace=namespace) or {}

    def configure_persistent_failure_probe(
        self,
        namespace: str,
        deployment: str,
    ) -> dict[str, Any]:
        current = self.get("deployment", deployment, namespace=namespace) or {}
        containers = current.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        if not containers:
            raise RuntimeError(f"Deployment {deployment} has no container.")
        patch = json.dumps(
            {
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": containers[0]["name"],
                                    "livenessProbe": {
                                        "exec": {
                                            "command": [
                                                "/bin/sh",
                                                "-c",
                                                "test ! -f /topo-eval-state/fail",
                                            ]
                                        },
                                        "failureThreshold": 1,
                                        "initialDelaySeconds": 1,
                                        "periodSeconds": 1,
                                        "timeoutSeconds": 1,
                                    },
                                    "volumeMounts": [
                                        {
                                            "name": "topo-eval-state",
                                            "mountPath": "/topo-eval-state",
                                        }
                                    ],
                                }
                            ],
                            "volumes": [
                                {"name": "topo-eval-state", "emptyDir": {}}
                            ],
                        }
                    }
                }
            },
            separators=(",", ":"),
        )
        self.run(
            "patch",
            "deployment",
            deployment,
            "-n",
            namespace,
            "--type=strategic",
            "-p",
            patch,
        )
        return self.get("deployment", deployment, namespace=namespace) or {}

    def deployment_pods(self, namespace: str, deployment: str) -> list[dict[str, Any]]:
        deployment_object = self.get("deployment", deployment, namespace=namespace) or {}
        selector = deployment_object.get("spec", {}).get("selector", {}).get("matchLabels", {})
        selector_text = ",".join(f"{key}={value}" for key, value in sorted(selector.items()))
        pod_list = self.get("pods", namespace=namespace, selector=selector_text) or {"items": []}
        return sorted(
            pod_list.get("items", []),
            key=lambda item: str(item.get("metadata", {}).get("name") or ""),
        )

    @staticmethod
    def pod_ready(pod: dict[str, Any]) -> bool:
        return any(
            condition.get("type") == "Ready" and condition.get("status") == "True"
            for condition in pod.get("status", {}).get("conditions", [])
        )

    def wait_deployment_pods_ready(
        self,
        namespace: str,
        deployment: str,
        *,
        replicas: int,
        timeout_seconds: float = 180.0,
    ) -> list[dict[str, Any]]:
        return bounded_wait(
            lambda: self.deployment_pods(namespace, deployment),
            lambda pods: len(pods) == replicas and all(self.pod_ready(pod) for pod in pods),
            timeout_seconds=timeout_seconds,
            interval_seconds=2,
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

    def wait_image_pull_failures(
        self,
        namespace: str,
        deployment: str,
        *,
        expected: int,
        timeout_seconds: float = 180.0,
    ) -> list[dict[str, Any]]:
        def failing_pods() -> list[dict[str, Any]]:
            return [
                pod
                for pod in self.deployment_pods(namespace, deployment)
                if self.pod_failure_reason(pod) in {"ImagePullBackOff", "ErrImagePull"}
            ]

        return bounded_wait(
            failing_pods,
            lambda pods: len(pods) >= expected,
            timeout_seconds=timeout_seconds,
            interval_seconds=3,
        )

    def induce_single_pod_crashloop(
        self,
        namespace: str,
        deployment: str,
        *,
        timeout_seconds: float = 180.0,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Crash exactly one selected Pod while its sibling continues serving."""
        initial = self.wait_deployment_pods_ready(
            namespace,
            deployment,
            replicas=2,
            timeout_seconds=timeout_seconds,
        )
        target_name = str(initial[0].get("metadata", {}).get("name") or "")
        target_uid = str(initial[0].get("metadata", {}).get("uid") or "")
        if not target_name or not target_uid:
            raise RuntimeError("Could not establish the target Pod's stable provider identity.")

        self.run(
            "exec",
            target_name,
            "-n",
            namespace,
            "--",
            "/bin/sh",
            "-c",
            "touch /topo-eval-state/fail",
            timeout=20,
        )

        failed = bounded_wait(
            lambda: self.get("pod", target_name, namespace=namespace),
            lambda pod: bool(
                pod
                and str(pod.get("metadata", {}).get("uid") or "") == target_uid
                and self.pod_failure_reason(pod) == "CrashLoopBackOff"
            ),
            timeout_seconds=timeout_seconds,
            interval_seconds=2,
        )
        siblings = [
            pod
            for pod in self.deployment_pods(namespace, deployment)
            if str(pod.get("metadata", {}).get("uid") or "") != target_uid
        ]
        if not siblings or not all(self.pod_ready(pod) for pod in siblings):
            raise RuntimeError("The independent healthy sibling Pod did not remain Ready.")
        return failed, siblings

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

    def service_endpoint_truth(self, namespace: str, service: str) -> dict[str, Any]:
        service_object = self.get("service", service, namespace=namespace) or {}
        endpoint_slices = self.get(
            "endpointslices",
            namespace=namespace,
            selector=f"kubernetes.io/service-name={service}",
        ) or {"items": []}
        slices: list[dict[str, Any]] = []
        ready_target_uids: list[str] = []
        for endpoint_slice in sorted(
            endpoint_slices.get("items", []),
            key=lambda item: str(item.get("metadata", {}).get("name") or ""),
        ):
            targets: list[dict[str, Any]] = []
            for endpoint in endpoint_slice.get("endpoints", []):
                target_ref = endpoint.get("targetRef") or {}
                ready = endpoint.get("conditions", {}).get("ready") is not False
                target_uid = str(target_ref.get("uid") or "")
                if ready and target_uid:
                    ready_target_uids.append(target_uid)
                targets.append(
                    {
                        "addresses": sorted(str(value) for value in endpoint.get("addresses", [])),
                        "ready": ready,
                        "target_kind": target_ref.get("kind"),
                        "target_name": target_ref.get("name"),
                        "target_uid": target_uid or None,
                    }
                )
            slices.append(
                {
                    "name": endpoint_slice.get("metadata", {}).get("name"),
                    "uid": endpoint_slice.get("metadata", {}).get("uid"),
                    "targets": targets,
                }
            )
        return {
            "service_uid": service_object.get("metadata", {}).get("uid"),
            "selector": service_object.get("spec", {}).get("selector", {}),
            "endpoint_slices": slices,
            "ready_endpoint_count": sum(
                len(target["addresses"])
                for endpoint_slice in slices
                for target in endpoint_slice["targets"]
                if target["ready"]
            ),
            "ready_target_uids": sorted(set(ready_target_uids)),
        }

    @staticmethod
    def pod_failure_reason(pod: dict[str, Any]) -> str | None:
        for status in pod.get("status", {}).get("containerStatuses", []):
            reason = status.get("state", {}).get("waiting", {}).get("reason")
            if reason:
                return str(reason)
        return None

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
