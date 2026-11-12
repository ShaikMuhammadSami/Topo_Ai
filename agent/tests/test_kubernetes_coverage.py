from __future__ import annotations

import json
from types import SimpleNamespace

from kubernetes.client.exceptions import ApiException

from topo_agent.collector import (
    KubernetesCollector,
    _config_map_refs,
)
from topo_agent.config import AgentConfig
from topo_agent.plugins.kubernetes import KubernetesPlugin


def _metadata(name: str, uid: str, **extra) -> SimpleNamespace:
    return SimpleNamespace(
        uid=uid,
        name=name,
        namespace="shop",
        labels={"app": name},
        owner_references=extra.pop("owner_references", []),
        annotations=extra.pop("annotations", None),
    )


def _pod_spec() -> SimpleNamespace:
    return SimpleNamespace(
        node_name="worker-1",
        init_containers=[
            SimpleNamespace(
                image="migrate:v1",
                env=[],
                env_from=[
                    SimpleNamespace(
                        config_map_ref=SimpleNamespace(name="migrate-config")
                    )
                ],
            )
        ],
        containers=[
            SimpleNamespace(
                image="nginx:1.27",
                env=[
                    SimpleNamespace(
                        name="ORDERS_MODE",
                        value=None,
                        value_from=SimpleNamespace(
                            config_map_key_ref=SimpleNamespace(
                                name="orders-config",
                                key="ORDERS_MODE",
                            )
                        ),
                    ),
                    SimpleNamespace(
                        name="PLAIN",
                        value="literal-value",
                        value_from=None,
                    ),
                ],
                env_from=[],
            )
        ],
        volumes=[
            SimpleNamespace(
                config_map=SimpleNamespace(name="nginx-config"),
                projected=None,
            ),
            SimpleNamespace(
                config_map=None,
                projected=SimpleNamespace(
                    sources=[
                        SimpleNamespace(
                            config_map=SimpleNamespace(name="orders-config"),
                            service_account_token=None,
                        )
                    ]
                ),
            ),
            # Injected kube-api-access-* volume: not a declared dependency.
            SimpleNamespace(
                config_map=None,
                projected=SimpleNamespace(
                    sources=[
                        SimpleNamespace(
                            config_map=None,
                            service_account_token=SimpleNamespace(
                                path="token"
                            ),
                        ),
                        SimpleNamespace(
                            config_map=SimpleNamespace(
                                name="kube-root-ca.crt"
                            ),
                            service_account_token=None,
                        ),
                    ]
                ),
            ),
        ],
    )


def _template() -> SimpleNamespace:
    spec = _pod_spec()
    return SimpleNamespace(
        spec=spec,
        to_dict=lambda: {"spec": {"containers": [{"image": "nginx:1.27"}]}},
    )


def _resources() -> dict[str, list[object]]:
    cron_uid = "cronjob-uid"
    return {
        "daemon_set": [
            SimpleNamespace(
                metadata=_metadata("node-agent", "ds-uid"),
                spec=SimpleNamespace(
                    selector=SimpleNamespace(match_labels={"app": "node-agent"}),
                    template=_template(),
                ),
                status=SimpleNamespace(
                    desired_number_scheduled=3,
                    number_ready=3,
                ),
            )
        ],
        "stateful_set": [
            SimpleNamespace(
                metadata=_metadata("orders-db", "sts-uid"),
                spec=SimpleNamespace(
                    selector=SimpleNamespace(match_labels={"app": "orders-db"}),
                    replicas=1,
                    template=_template(),
                ),
                status=SimpleNamespace(ready_replicas=1),
            )
        ],
        "job": [
            SimpleNamespace(
                metadata=_metadata(
                    "nightly-28001",
                    "job-uid",
                    owner_references=[
                        SimpleNamespace(
                            uid=cron_uid,
                            kind="CronJob",
                            controller=True,
                        )
                    ],
                ),
                spec=SimpleNamespace(template=_template()),
                status=SimpleNamespace(active=None, succeeded=1, failed=None),
            )
        ],
        "cron_job": [
            SimpleNamespace(
                metadata=_metadata("nightly", cron_uid),
                spec=SimpleNamespace(
                    schedule="0 1 * * *",
                    suspend=None,
                    job_template=SimpleNamespace(
                        spec=SimpleNamespace(template=_template())
                    ),
                ),
            )
        ],
        "config_map": [
            SimpleNamespace(
                metadata=_metadata("orders-config", "cm-uid"),
                data={"ORDERS_MODE": "live-secret-ish-value"},
                binary_data={"blob": "AAEC"},
            )
        ],
        "pod": [
            SimpleNamespace(
                metadata=_metadata(
                    "checkout-api-1",
                    "pod-uid",
                    annotations={
                        "topo.ai/depends-on": "shop/orders-api",
                        "topo.ai/outbound-hosts": "api.stripe.com:443",
                        "kubectl.kubernetes.io/last-applied-configuration": "{}",
                    },
                ),
                spec=_pod_spec(),
                status=SimpleNamespace(
                    phase="Running",
                    pod_ip="10.0.0.9",
                    conditions=[],
                    container_statuses=[],
                    init_container_statuses=[],
                    ephemeral_container_statuses=[],
                ),
            )
        ],
    }


class _Api:
    def __init__(
        self,
        resources: dict[str, list[object]],
        denied: dict[str, int] | None = None,
    ) -> None:
        self.resources = resources
        self.denied = denied or {}

    def __getattr__(self, name: str):
        resource = (
            name.removeprefix("list_namespaced_")
            .removeprefix("list_")
            .removesuffix("_for_all_namespaces")
        )

        def list_resources(*args, **kwargs):
            if resource in self.denied:
                raise ApiException(
                    status=self.denied[resource],
                    reason="Forbidden",
                )
            return SimpleNamespace(
                items=self.resources.get(resource, [])
            )

        return list_resources


def _collector(api: _Api) -> KubernetesCollector:
    collector = object.__new__(KubernetesCollector)
    collector.config = AgentConfig(
        cluster_name="production",
        namespaces=[],
    )
    collector.access_mode = "test"
    collector.core = api
    collector.apps = api
    collector.networking = api
    collector.discovery = api
    collector.batch = api
    return collector


def test_config_map_refs_cover_env_env_from_and_volumes_without_values() -> None:
    refs = _config_map_refs(_pod_spec())

    assert refs == ["migrate-config", "nginx-config", "orders-config"]
    assert "literal-value" not in json.dumps(refs)


def test_collect_reports_workload_kinds_and_config_maps() -> None:
    submission = _collector(_Api(_resources())).collect()
    inventory = submission["inventory"]

    daemon_set = inventory["daemonsets"][0]
    assert daemon_set["name"] == "node-agent"
    assert daemon_set["desired_scheduled"] == 3
    assert daemon_set["images"] == ["nginx:1.27"]
    assert daemon_set["pod_template_fingerprint"].startswith("sha256:")
    assert daemon_set["config_map_refs"] == [
        "migrate-config",
        "nginx-config",
        "orders-config",
    ]

    assert inventory["statefulsets"][0]["replicas"] == 1

    job = inventory["jobs"][0]
    assert job["owner_uid"] == "cronjob-uid"
    assert job["owner_kind"] == "CronJob"
    assert job["succeeded"] == 1

    cron_job = inventory["cronjobs"][0]
    assert cron_job["schedule"] == "0 1 * * *"
    assert cron_job["suspend"] is False
    assert cron_job["images"] == ["nginx:1.27"]

    config_map = inventory["configmaps"][0]
    assert config_map["keys"] == ["ORDERS_MODE", "blob"]
    assert config_map["data_sha256"].startswith("sha256:")
    serialized = json.dumps(inventory, sort_keys=True)
    assert "live-secret-ish-value" not in serialized
    assert "AAEC" not in serialized
    assert "literal-value" not in serialized

    assert submission["metadata"]["collection_errors"] == []
    assert submission["metadata"]["skipped_optional"] == []


def test_config_map_hash_changes_with_values_and_is_stable() -> None:
    resources = _resources()
    first = _collector(_Api(resources)).collect()
    again = _collector(_Api(resources)).collect()
    resources["config_map"][0].data = {"ORDERS_MODE": "dry-run"}
    changed = _collector(_Api(resources)).collect()

    def config_map(submission):
        return submission["inventory"]["configmaps"][0]

    assert config_map(first) == config_map(again)
    assert config_map(changed)["keys"] == config_map(first)["keys"]
    assert (
        config_map(changed)["data_sha256"]
        != config_map(first)["data_sha256"]
    )


def test_pod_carries_only_topo_annotations_and_config_map_refs() -> None:
    pod = _collector(_Api(_resources())).collect()["inventory"]["pods"][0]

    assert pod["annotations"] == {
        "topo.ai/depends-on": "shop/orders-api",
        "topo.ai/outbound-hosts": "api.stripe.com:443",
    }
    assert pod["config_map_refs"] == [
        "migrate-config",
        "nginx-config",
        "orders-config",
    ]


def test_pod_without_topo_annotations_has_no_annotations_key() -> None:
    resources = _resources()
    resources["pod"][0].metadata.annotations = {
        "kubectl.kubernetes.io/restartedAt": "now"
    }

    pod = _collector(_Api(resources)).collect()["inventory"]["pods"][0]

    assert "annotations" not in pod


def test_forbidden_config_maps_are_skipped_not_errors() -> None:
    api = _Api(_resources(), denied={"config_map": 403})
    collector = _collector(api)
    plugin = object.__new__(KubernetesPlugin)
    plugin.collector = collector

    submission = collector.collect()
    result = plugin.collect()

    assert submission["inventory"]["configmaps"] == []
    assert submission["metadata"]["collection_errors"] == []
    assert submission["metadata"]["skipped_optional"] == [
        "configmaps: 403 Forbidden"
    ]
    assert result.status == "success"
    assert result.metadata["skipped_optional"] == [
        "configmaps: 403 Forbidden"
    ]
    assert "kubernetes.configmaps" in result.capabilities


def test_forbidden_workload_kind_is_a_collection_error() -> None:
    api = _Api(_resources(), denied={"daemon_set": 403})
    plugin = object.__new__(KubernetesPlugin)
    plugin.collector = _collector(api)

    result = plugin.collect()

    assert result.status == "partial"
    assert result.errors == ["daemonsets: 403 Forbidden"]
    assert result.inventory["statefulsets"]
