from __future__ import annotations

from dataclasses import asdict
from typing import Any

from evaluation.contracts import (
    ExecutionAction,
    ExecutionReceipt,
    ProviderVerification,
    ScenarioManifest,
)
from evaluation.kubernetes import Kubectl, utc_now


HEALTHY_IMAGE = "nginx:1.27-alpine"


class KubernetesBlastScenario:
    """Provider-native BR-0 fixtures; this class never defines truth from Topo output."""

    def __init__(self, manifest: ScenarioManifest, kubectl: Kubectl, namespace: str, run_id: str):
        self.manifest = manifest
        self.kubectl = kubectl
        self.namespace = namespace
        self.run_id = run_id
        self.objects: dict[str, dict[str, Any]] = {}
        self.receipt = ExecutionReceipt(
            receipt_version="eval-1.execution.v1",
            scenario_id=manifest.scenario_id,
            run_id=run_id,
            namespace=namespace,
            started_at=utc_now(),
        )

    def prepare(self) -> None:
        self.objects["scenario_namespace"] = self.kubectl.create_namespace(
            self.namespace,
            self.run_id,
        )
        if self.manifest.scenario_id == "blast-01":
            self._workload(
                "failing-app",
                "root_deployment",
                service_alias=None,
                recreate=True,
            )
            self._workload(
                "healthy-app",
                "healthy_deployment",
                service_alias="healthy_service",
            )
        elif self.manifest.scenario_id == "blast-02":
            self._workload(
                "partial-backend",
                "root_deployment",
                service_alias="root_service",
                replicas=2,
                persistent_failure_probe=True,
            )
        elif self.manifest.scenario_id == "blast-03":
            self._workload(
                "failed-backend",
                "root_deployment",
                service_alias="root_service",
                replicas=2,
                recreate=True,
            )
            self._workload(
                "unrelated-app",
                "unrelated_deployment",
                service_alias="unrelated_service",
            )
        else:
            raise ValueError(f"Unknown blast scenario: {self.manifest.scenario_id}")

    def _workload(
        self,
        name: str,
        deployment_alias: str,
        *,
        service_alias: str | None,
        replicas: int = 1,
        recreate: bool = False,
        persistent_failure_probe: bool = False,
    ) -> None:
        deployment = self.kubectl.create_deployment(
            self.namespace,
            name,
            HEALTHY_IMAGE,
            self.run_id,
            replicas=replicas,
        )
        if recreate:
            deployment = self.kubectl.use_recreate_strategy(self.namespace, name)
        if persistent_failure_probe:
            deployment = self.kubectl.configure_persistent_failure_probe(
                self.namespace,
                name,
            )
        if service_alias:
            self.objects[service_alias] = self.kubectl.expose_deployment(
                self.namespace,
                name,
                80,
                self.run_id,
            )
        self.objects[deployment_alias] = self.kubectl.wait_ready(
            self.namespace,
            name,
            replicas=replicas,
        )
        self.kubectl.wait_deployment_pods_ready(
            self.namespace,
            name,
            replicas=replicas,
        )

    def execute(self) -> tuple[ExecutionReceipt, ProviderVerification]:
        if self.manifest.scenario_id == "blast-01":
            return self._execute_structural_containment()
        if self.manifest.scenario_id == "blast-02":
            return self._execute_partial_backend_failure()
        return self._execute_complete_backend_failure()

    def _execute_structural_containment(self) -> tuple[ExecutionReceipt, ProviderVerification]:
        action_time = self._mutate_bad_image("root_deployment")
        root_deployment = self._refresh("root_deployment", "deployment")
        root_name = self._name(root_deployment)
        failed_pod = self.kubectl.wait_image_pull_failure(self.namespace, root_name)
        root_replicaset, failed_pod = self.kubectl.owned_chain(
            self.namespace,
            root_deployment,
            failed_pod,
        )
        healthy_deployment = self._refresh("healthy_deployment", "deployment")
        healthy_service = self._refresh("healthy_service", "service")
        healthy_pods = self.kubectl.wait_deployment_pods_ready(
            self.namespace,
            self._name(healthy_deployment),
            replicas=1,
        )
        self.objects.update(
            {
                "root_replicaset": root_replicaset,
                "failed_pod": failed_pod,
                "healthy_pod": healthy_pods[0],
                "healthy_service": healthy_service,
            }
        )
        healthy_endpoints = self.kubectl.service_endpoint_truth(
            self.namespace,
            self._name(healthy_service),
        )
        owner_ok = self._owner_chain_ok(root_deployment, root_replicaset, failed_pod)
        failure_reason = self.kubectl.pod_failure_reason(failed_pod)
        established = bool(
            owner_ok
            and failure_reason in {"ImagePullBackOff", "ErrImagePull"}
            and self.kubectl.pod_ready(healthy_pods[0])
            and healthy_endpoints["ready_endpoint_count"] >= 1
        )
        return self._verification(
            established,
            action_time,
            {
                "assertion": "structural_containment_provider_truth",
                "failure_reason": failure_reason,
                "failed_pod_ready": self.kubectl.pod_ready(failed_pod),
                "healthy_pod_ready": self.kubectl.pod_ready(healthy_pods[0]),
                "healthy_service_endpoint_truth": healthy_endpoints,
                "owner_chain_valid": owner_ok,
                "passed": established,
            },
        )

    def _execute_partial_backend_failure(self) -> tuple[ExecutionReceipt, ProviderVerification]:
        deployment = self._refresh("root_deployment", "deployment")
        initial_pods = self.kubectl.wait_deployment_pods_ready(
            self.namespace,
            self._name(deployment),
            replicas=2,
        )
        target = initial_pods[0]
        action_time = utc_now()
        failed_pod, healthy_pods = self.kubectl.induce_single_pod_crashloop(
            self.namespace,
            self._name(deployment),
        )
        self.receipt.actions.append(
            ExecutionAction(
                action_id=f"{self.run_id}:1",
                action_type="targeted_pod_liveness_failure",
                logical_target="failed_pod",
                provider_uid=str(target.get("metadata", {}).get("uid") or ""),
                executed_at=action_time,
                before={"ready": True, "restart_count": self._restart_count(target)},
                after={
                    "ready": self.kubectl.pod_ready(failed_pod),
                    "failure_reason": self.kubectl.pod_failure_reason(failed_pod),
                    "restart_count": self._restart_count(failed_pod),
                },
                provider_receipt={
                    "pod_uid": failed_pod.get("metadata", {}).get("uid"),
                    "method": "pod-scoped persistent liveness failure flag in emptyDir",
                },
            )
        )
        deployment = self._refresh("root_deployment", "deployment")
        service = self._refresh("root_service", "service")
        root_replicaset, failed_pod = self.kubectl.owned_chain(
            self.namespace,
            deployment,
            failed_pod,
        )
        endpoint_truth = self.kubectl.service_endpoint_truth(
            self.namespace,
            self._name(service),
        )
        healthy_pod = healthy_pods[0]
        self.objects.update(
            {
                "root_replicaset": root_replicaset,
                "failed_pod": failed_pod,
                "healthy_pod": healthy_pod,
            }
        )
        failed_uid = str(failed_pod.get("metadata", {}).get("uid") or "")
        healthy_uid = str(healthy_pod.get("metadata", {}).get("uid") or "")
        owner_ok = self._owner_chain_ok(deployment, root_replicaset, failed_pod)
        established = bool(
            owner_ok
            and self.kubectl.pod_failure_reason(failed_pod) == "CrashLoopBackOff"
            and not self.kubectl.pod_ready(failed_pod)
            and self.kubectl.pod_ready(healthy_pod)
            and endpoint_truth["ready_endpoint_count"] >= 1
            and healthy_uid in endpoint_truth["ready_target_uids"]
            and failed_uid not in endpoint_truth["ready_target_uids"]
        )
        return self._verification(
            established,
            action_time,
            {
                "assertion": "partial_backend_provider_truth",
                "failed_pod_uid": failed_uid,
                "failed_pod_ready": self.kubectl.pod_ready(failed_pod),
                "failure_reason": self.kubectl.pod_failure_reason(failed_pod),
                "healthy_pod_uid": healthy_uid,
                "healthy_pod_ready": self.kubectl.pod_ready(healthy_pod),
                "service_endpoint_truth": endpoint_truth,
                "owner_chain_valid": owner_ok,
                "passed": established,
            },
        )

    def _execute_complete_backend_failure(self) -> tuple[ExecutionReceipt, ProviderVerification]:
        action_time = self._mutate_bad_image("root_deployment")
        deployment = self._refresh("root_deployment", "deployment")
        failed_pods = self.kubectl.wait_image_pull_failures(
            self.namespace,
            self._name(deployment),
            expected=2,
        )
        root_replicaset, _ = self.kubectl.owned_chain(
            self.namespace,
            deployment,
            failed_pods[0],
        )
        service = self._refresh("root_service", "service")
        endpoint_truth = self.kubectl.service_endpoint_truth(
            self.namespace,
            self._name(service),
        )
        unrelated_deployment = self._refresh("unrelated_deployment", "deployment")
        unrelated_service = self._refresh("unrelated_service", "service")
        unrelated_pods = self.kubectl.wait_deployment_pods_ready(
            self.namespace,
            self._name(unrelated_deployment),
            replicas=1,
        )
        unrelated_endpoint_truth = self.kubectl.service_endpoint_truth(
            self.namespace,
            self._name(unrelated_service),
        )
        self.objects.update(
            {
                "root_replicaset": root_replicaset,
                "failed_pod_1": failed_pods[0],
                "failed_pod_2": failed_pods[1],
                "unrelated_pod": unrelated_pods[0],
            }
        )
        owner_ok = all(
            self._owner_chain_ok(deployment, root_replicaset, pod)
            for pod in failed_pods
        )
        failure_reasons = [self.kubectl.pod_failure_reason(pod) for pod in failed_pods]
        established = bool(
            owner_ok
            and all(reason in {"ImagePullBackOff", "ErrImagePull"} for reason in failure_reasons)
            and endpoint_truth["ready_endpoint_count"] == 0
            and self.kubectl.pod_ready(unrelated_pods[0])
            and unrelated_endpoint_truth["ready_endpoint_count"] >= 1
        )
        return self._verification(
            established,
            action_time,
            {
                "assertion": "complete_backend_provider_truth",
                "failed_pod_uids": [pod.get("metadata", {}).get("uid") for pod in failed_pods],
                "failure_reasons": failure_reasons,
                "failed_pods_ready": [self.kubectl.pod_ready(pod) for pod in failed_pods],
                "service_endpoint_truth": endpoint_truth,
                "unrelated_pod_ready": self.kubectl.pod_ready(unrelated_pods[0]),
                "unrelated_service_endpoint_truth": unrelated_endpoint_truth,
                "owner_chain_valid": owner_ok,
                "passed": established,
            },
        )

    def _verification(
        self,
        established: bool,
        action_time: str,
        scenario_assertion: dict[str, Any],
    ) -> tuple[ExecutionReceipt, ProviderVerification]:
        observed_at = utc_now()
        impact = self.manifest.value["expected_blast_radius"].get("impact_truth", {})
        provider_assertions = [
            {
                "assertion": "provider_ground_truth_is_independent",
                "causal_action_executed_at": action_time,
                "failure_observed_at": observed_at,
                "impact_truth": impact,
                "passed": established,
            },
            scenario_assertion,
        ]
        provider_objects = [
            self.kubectl.provider_object(alias, self.objects[alias])
            for alias in sorted(self.manifest.aliases)
            if self.objects.get(alias)
        ]
        self.receipt.completed_at = observed_at
        return self.receipt, ProviderVerification(
            verification_version="eval-1.provider.v1",
            source="kubernetes-api-via-kubectl",
            observed_at=observed_at,
            established=established,
            objects=provider_objects,
            assertions=provider_assertions,
        )

    def _mutate_bad_image(self, alias: str) -> str:
        before = self.objects[alias]
        target_name = self._name(before)
        image = f"registry.invalid/topo-eval/{self.manifest.scenario_id}:{self.run_id}"
        action_time = utc_now()
        after = self.kubectl.set_image(self.namespace, target_name, image)
        self.objects[alias] = after
        self.receipt.actions.append(
            ExecutionAction(
                action_id=f"{self.run_id}:{len(self.receipt.actions) + 1}",
                action_type="causal_bad_image",
                logical_target=alias,
                provider_uid=str(before.get("metadata", {}).get("uid") or ""),
                executed_at=action_time,
                before={
                    "image": self._image(before),
                    "generation": before.get("metadata", {}).get("generation"),
                },
                after={
                    "image": image,
                    "generation": after.get("metadata", {}).get("generation"),
                },
                provider_receipt={
                    "resourceVersion": after.get("metadata", {}).get("resourceVersion")
                },
            )
        )
        return action_time

    def _refresh(self, alias: str, kind: str) -> dict[str, Any]:
        value = self.objects[alias]
        current = self.kubectl.get(kind, self._name(value), namespace=self.namespace) or value
        self.objects[alias] = current
        return current

    @staticmethod
    def _name(value: dict[str, Any]) -> str:
        return str(value.get("metadata", {}).get("name") or "")

    @staticmethod
    def _image(value: dict[str, Any]) -> str | None:
        containers = value.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        return str(containers[0].get("image")) if containers else None

    @staticmethod
    def _restart_count(pod: dict[str, Any]) -> int:
        return sum(
            int(status.get("restartCount", 0))
            for status in pod.get("status", {}).get("containerStatuses", [])
        )

    @staticmethod
    def _owner_chain_ok(
        deployment: dict[str, Any],
        replica_set: dict[str, Any],
        pod: dict[str, Any],
    ) -> bool:
        deployment_uid = str(deployment.get("metadata", {}).get("uid") or "")
        replica_set_uid = str(replica_set.get("metadata", {}).get("uid") or "")
        rs_owner_uids = {
            str(item.get("uid") or "")
            for item in replica_set.get("metadata", {}).get("ownerReferences", [])
        }
        pod_owner_uids = {
            str(item.get("uid") or "")
            for item in pod.get("metadata", {}).get("ownerReferences", [])
        }
        return bool(
            deployment_uid
            and replica_set_uid
            and deployment_uid in rs_owner_uids
            and replica_set_uid in pod_owner_uids
        )


def receipt_dict(receipt: ExecutionReceipt) -> dict[str, Any]:
    return asdict(receipt)
