from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from evaluation.contracts import ExecutionAction, ExecutionReceipt, ProviderVerification, ScenarioManifest
from evaluation.kubernetes import Kubectl, utc_now


HEALTHY_IMAGE = "nginx:1.27-alpine"
DISTRACTOR_IMAGE = "nginx:1.26-alpine"


class KubernetesSentinel:
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
        self.kubectl.create_namespace(self.namespace, self.run_id)
        scenario = self.manifest.scenario_id
        if scenario == "sentinel-a":
            self._workload("sentinel-a-app", "root_deployment", "root_service")
        elif scenario == "sentinel-b":
            self._workload("victim-app", "victim_deployment", "victim_service")
            self._workload("distractor-app", "distractor_deployment", "distractor_service")
        elif scenario == "sentinel-c":
            self._workload("sentinel-c-app", "root_deployment", "root_service")
        elif scenario == "sentinel-d":
            self._workload("victim-app", "victim_deployment", "victim_service")
            self._workload("unaffected-app", "unaffected_deployment", "unaffected_service")
        else:
            raise ValueError(f"Unknown sentinel: {scenario}")

    def _workload(self, name: str, deployment_alias: str, service_alias: str) -> None:
        deployment = self.kubectl.create_deployment(self.namespace, name, HEALTHY_IMAGE, self.run_id)
        self.kubectl.expose_deployment(self.namespace, name, 80, self.run_id)
        self.kubectl.wait_ready(self.namespace, name)
        self.objects[deployment_alias] = deployment
        self.objects[service_alias] = self.kubectl.get("service", name, namespace=self.namespace) or {}

    def execute(self) -> tuple[ExecutionReceipt, ProviderVerification]:
        scenario = self.manifest.scenario_id
        if scenario == "sentinel-b":
            self._mutate("distractor_deployment", DISTRACTOR_IMAGE, "distractor_image_change")
            self.kubectl.wait_ready(self.namespace, "distractor-app")
        target_alias = "victim_deployment" if scenario in {"sentinel-b", "sentinel-d"} else "root_deployment"
        invalid_image = f"registry.invalid/topo-eval/{scenario}:{self.run_id}"
        self._mutate(target_alias, invalid_image, "causal_bad_image")
        target = self.objects[target_alias]
        target_name = str(target.get("metadata", {}).get("name"))
        pod = self.kubectl.wait_image_pull_failure(self.namespace, target_name)
        deployment = self.kubectl.get("deployment", target_name, namespace=self.namespace) or {}
        replica_set, pod = self.kubectl.owned_chain(self.namespace, deployment, pod)

        root_prefix = "victim" if target_alias.startswith("victim") else "root"
        self.objects[target_alias] = deployment
        self.objects[f"{root_prefix}_replicaset"] = replica_set
        self.objects[f"{root_prefix}_pod"] = pod

        for alias, value in list(self.objects.items()):
            name = str(value.get("metadata", {}).get("name") or "")
            if alias.endswith("deployment"):
                self.objects[alias] = self.kubectl.get(
                    "deployment", name, namespace=self.namespace
                ) or value
            elif alias.endswith("service"):
                self.objects[alias] = self.kubectl.get(
                    "service", name, namespace=self.namespace
                ) or value

        provider_objects = []
        for alias in self.manifest.aliases:
            value = self.objects.get(alias)
            if value:
                provider_objects.append(self.kubectl.provider_object(alias, value))
        failure_reason = self._pod_failure_reason(pod)
        observed_at = utc_now()
        deployment_uid = str(deployment.get("metadata", {}).get("uid") or "")
        rs_owner_uid = str((replica_set.get("metadata", {}).get("ownerReferences") or [{}])[0].get("uid") or "")
        pod_owner_uid = str((pod.get("metadata", {}).get("ownerReferences") or [{}])[0].get("uid") or "")
        service_endpoint_counts = {
            alias: self.kubectl.ready_service_endpoint_count(
                self.namespace,
                str(value.get("metadata", {}).get("name") or ""),
            )
            for alias, value in self.objects.items()
            if alias.endswith("service")
        }
        explicitly_unaffected = set(
            self.manifest.value["expected_blast_radius"]["explicitly_unaffected"]
        )
        unaffected_deployments_available = {
            alias: int(value.get("status", {}).get("availableReplicas", 0))
            for alias, value in self.objects.items()
            if alias.endswith("deployment") and alias in explicitly_unaffected
        }
        unaffected_truth_established = all(
            count >= 1
            for alias, count in service_endpoint_counts.items()
            if alias in explicitly_unaffected
        ) and all(count >= 1 for count in unaffected_deployments_available.values())
        causal_action_time = next(
            action.executed_at
            for action in self.receipt.actions
            if action.action_type == "causal_bad_image"
        )
        established = bool(
            deployment_uid
            and rs_owner_uid == deployment_uid
            and pod_owner_uid == str(replica_set.get("metadata", {}).get("uid") or "")
            and failure_reason in {"ImagePullBackOff", "ErrImagePull"}
            and unaffected_truth_established
        )
        verification = ProviderVerification(
            verification_version="eval-1.provider.v1",
            source="kubernetes-api-via-kubectl",
            observed_at=observed_at,
            established=established,
            objects=provider_objects,
            assertions=[
                {
                    "assertion": "bad_image_failure_chain",
                    "deployment_uid": deployment_uid,
                    "replicaset_owner_uid": rs_owner_uid,
                    "pod_owner_uid": pod_owner_uid,
                    "failure_reason": failure_reason,
                    "failure_observed_at": observed_at,
                    "causal_action_executed_at": causal_action_time,
                    "passed": established,
                    "ready_service_endpoint_counts": service_endpoint_counts,
                    "unaffected_deployment_available_replicas": (
                        unaffected_deployments_available
                    ),
                }
            ],
        )
        self.receipt.completed_at = observed_at
        return self.receipt, verification

    def _mutate(self, alias: str, image: str, action_type: str) -> None:
        before = self.objects[alias]
        before_image = self._image(before)
        name = str(before.get("metadata", {}).get("name"))
        after = self.kubectl.set_image(self.namespace, name, image)
        self.objects[alias] = after
        self.receipt.actions.append(
            ExecutionAction(
                action_id=f"{self.run_id}:{len(self.receipt.actions) + 1}",
                action_type=action_type,
                logical_target=alias,
                provider_uid=str(before.get("metadata", {}).get("uid") or ""),
                executed_at=utc_now(),
                before={"image": before_image, "generation": before.get("metadata", {}).get("generation")},
                after={"image": image, "generation": after.get("metadata", {}).get("generation")},
                provider_receipt={"resourceVersion": after.get("metadata", {}).get("resourceVersion")},
            )
        )

    @staticmethod
    def _image(value: dict[str, Any]) -> str | None:
        containers = value.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        return str(containers[0].get("image")) if containers else None

    @staticmethod
    def _pod_failure_reason(pod: dict[str, Any]) -> str | None:
        for status in pod.get("status", {}).get("containerStatuses", []):
            reason = status.get("state", {}).get("waiting", {}).get("reason")
            if reason:
                return str(reason)
        return None


def manifest_path(scenario_id: str) -> Path:
    return Path(__file__).with_name("manifests") / f"{scenario_id}.json"


def receipt_dict(receipt: ExecutionReceipt) -> dict[str, Any]:
    return asdict(receipt)
