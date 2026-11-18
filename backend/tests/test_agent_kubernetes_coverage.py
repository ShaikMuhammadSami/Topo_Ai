from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

from app.db.models import TopoAgentRecord, utc_now_iso
from app.models.agents import AgentSnapshotSubmission
from app.models.change_events import ChangeEventKind
from app.models.changes import (
    ChangeCategory,
    ChangeImportance,
    ChangeType,
)
from app.models.topology import (
    GraphSnapshot,
    RelationshipOrigin,
    RelationshipType,
)
from app.services.agent_snapshot_ingest import build_agent_snapshot
from app.services.change_event_bridge import normalized_change_to_event
from app.services.change_normalizer import normalize_snapshot_changes

NOW = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)


def _agent() -> TopoAgentRecord:
    now = utc_now_iso()
    return TopoAgentRecord(
        agent_id="agent:coverage-test",
        name="coverage-test",
        agent_type="kubernetes",
        cluster_name="production",
        environment="production",
        version="1.0",
        token_hash="a" * 64,
        token_hint="test",
        status="online",
        collection_interval_seconds=300,
        heartbeat_interval_seconds=30,
        namespace_scope_json="[]",
        capabilities_json="[]",
        labels_json="{}",
        metadata_json="{}",
        buffered_item_count=0,
        enrolled_at=now,
        created_at=now,
        updated_at=now,
    )


def _workload(name: str, uid: str, **extra) -> dict:
    return {
        "uid": uid,
        "name": name,
        "namespace": "shop",
        "labels": {"app": name},
        "images": ["nginx:1.27"],
        "pod_template_fingerprint": "sha256:" + "0" * 64,
        **extra,
    }


def _inventory() -> dict:
    return {
        "namespaces": [
            {"uid": "ns-uid", "name": "shop", "labels": {}, "phase": "Active"}
        ],
        "deployments": [
            _workload(
                "orders-api",
                "deploy-uid",
                selector={"app": "orders-api"},
                replicas=1,
                available_replicas=1,
                config_map_refs=["orders-config"],
            )
        ],
        "daemonsets": [
            _workload(
                "node-agent",
                "ds-uid",
                selector={"app": "node-agent"},
                desired_scheduled=3,
                ready_scheduled=3,
                config_map_refs=[],
            )
        ],
        "statefulsets": [
            _workload(
                "orders-db",
                "sts-uid",
                selector={"app": "orders-db"},
                replicas=1,
                ready_replicas=1,
                config_map_refs=["orders-config"],
            )
        ],
        "cronjobs": [
            _workload(
                "nightly",
                "cron-uid",
                schedule="0 1 * * *",
                suspend=False,
                config_map_refs=[],
            )
        ],
        "jobs": [
            _workload(
                "nightly-28001",
                "job-uid",
                owner_uid="cron-uid",
                owner_kind="CronJob",
                active=None,
                succeeded=1,
                failed=None,
                config_map_refs=[],
            )
        ],
        "configmaps": [
            {
                "uid": "cm-uid",
                "name": "orders-config",
                "namespace": "shop",
                "labels": {},
                "keys": ["ORDERS_MODE"],
                "data_sha256": "sha256:" + "1" * 64,
            }
        ],
        "services": [
            {
                "uid": "svc-uid",
                "name": "orders-api",
                "namespace": "shop",
                "labels": {},
                "selector": {"app": "orders-api"},
            }
        ],
        "pods": [
            {
                "uid": "pod-uid",
                "name": "checkout-api-1",
                "namespace": "shop",
                "labels": {"app": "checkout-api"},
                "owner_uid": "job-uid",
                "owner_kind": "Job",
                "images": ["nginx:1.27"],
                "config_map_refs": ["orders-config", "not-collected"],
                "annotations": {
                    "topo.ai/depends-on": "shop/orders-api",
                    "topo.ai/outbound-hosts": "api.stripe.com:443",
                },
            }
        ],
    }


def _snapshot(inventory: dict, *, minutes: int = 0) -> GraphSnapshot:
    submission = AgentSnapshotSubmission(
        submission_id=f"submission:coverage-{minutes}",
        collected_at=(NOW + timedelta(minutes=minutes)).isoformat(),
        cluster_name="production",
        environment="production",
        namespace_scope=[],
        collector_version="1.0",
        inventory=inventory,
    )
    snapshot = build_agent_snapshot(agent=_agent(), submission=submission)
    return snapshot.model_copy(
        update={"snapshot_id": f"snapshot:coverage-{minutes}"}
    )


def _entity(snapshot: GraphSnapshot, kind: str, name: str):
    return next(
        entity
        for entity in snapshot.entities
        if entity.kind == kind and entity.name == name
    )


def _edges(snapshot: GraphSnapshot, predicate: RelationshipType):
    names = {entity.id: (entity.kind, entity.name) for entity in snapshot.entities}
    return {
        (names[edge.source_entity_id], names[edge.target_entity_id]): edge
        for edge in snapshot.relationships
        if edge.relationship_type == predicate
    }


def test_agent_inventory_builds_new_workload_and_config_map_entities() -> None:
    snapshot = _snapshot(_inventory())
    kinds = {entity.kind for entity in snapshot.entities}

    assert {
        "KubernetesDaemonSet",
        "KubernetesStatefulSet",
        "KubernetesJob",
        "KubernetesCronJob",
        "KubernetesConfigMap",
    } <= kinds

    config_map = _entity(snapshot, "KubernetesConfigMap", "orders-config")
    assert config_map.properties["keys"] == ["ORDERS_MODE"]
    assert config_map.properties["data_sha256"].startswith("sha256:")
    assert all(
        "config_map_refs" not in entity.properties
        for entity in snapshot.entities
    )

    pod = _entity(snapshot, "KubernetesPod", "checkout-api-1")
    assert pod.properties["annotations"] == {
        "topo.ai/depends-on": "shop/orders-api",
        "topo.ai/outbound-hosts": "api.stripe.com:443",
    }


def test_owner_edges_cover_cron_job_to_job_to_pod() -> None:
    owns = _edges(_snapshot(_inventory()), RelationshipType.OWNS)

    assert (
        ("KubernetesCronJob", "nightly"),
        ("KubernetesJob", "nightly-28001"),
    ) in owns
    assert (
        ("KubernetesJob", "nightly-28001"),
        ("KubernetesPod", "checkout-api-1"),
    ) in owns


def test_config_map_references_become_declared_depends_on_edges() -> None:
    depends_on = _edges(_snapshot(_inventory()), RelationshipType.DEPENDS_ON)
    config_map = ("KubernetesConfigMap", "orders-config")

    for subject in (
        ("KubernetesPod", "checkout-api-1"),
        ("KubernetesDeployment", "orders-api"),
        ("KubernetesStatefulSet", "orders-db"),
    ):
        edge = depends_on[(subject, config_map)]
        assert edge.provenance.origin == RelationshipOrigin.DECLARED
        assert any(
            reference.reference_type == "kubernetes_config_map_reference"
            and reference.reference == "shop/orders-config"
            for reference in edge.provenance.source_references
        )

    # A reference to a ConfigMap that was not collected creates no edge.
    assert not any(
        target[1] == "not-collected" for _, target in depends_on
    )


def test_topo_annotations_become_declared_dependency_edges() -> None:
    snapshot = _snapshot(_inventory())
    pod = ("KubernetesPod", "checkout-api-1")

    depends_on = _edges(snapshot, RelationshipType.DEPENDS_ON)
    assert (pod, ("KubernetesService", "orders-api")) in depends_on

    calls = _edges(snapshot, RelationshipType.CALLS)
    edge = calls[(pod, ("ExternalEndpoint", "api.stripe.com"))]
    assert edge.provenance.origin == RelationshipOrigin.DECLARED
    external = _entity(snapshot, "ExternalEndpoint", "api.stripe.com")
    assert external.properties["port"] == 443


def test_build_is_deterministic() -> None:
    first = _snapshot(_inventory())
    second = _snapshot(_inventory())

    assert [entity.id for entity in first.entities] == [
        entity.id for entity in second.entities
    ]
    assert [edge.id for edge in first.relationships] == [
        edge.id for edge in second.relationships
    ]


def _single_entity_update(before: dict, after: dict, kind: str):
    changes = [
        change
        for change in normalize_snapshot_changes(
            _snapshot(before),
            _snapshot(after, minutes=1),
        )
        if change.change_type == ChangeType.ENTITY_UPDATED
    ]
    assert [change.entity_kind for change in changes] == [kind]
    return changes[0]


def test_config_map_key_removal_is_a_high_configuration_change() -> None:
    before = _inventory()
    after = copy.deepcopy(before)
    after["configmaps"][0]["keys"] = ["OTHER"]
    after["configmaps"][0]["data_sha256"] = "sha256:" + "2" * 64

    change = _single_entity_update(before, after, "KubernetesConfigMap")

    assert change.category == ChangeCategory.CONFIGURATION
    assert change.importance == ChangeImportance.HIGH
    assert "properties.keys" in change.changed_fields
    assert (
        normalized_change_to_event(change).kind
        == ChangeEventKind.CONFIGURATION
    )


def test_config_map_value_change_is_a_medium_configuration_change() -> None:
    before = _inventory()
    after = copy.deepcopy(before)
    after["configmaps"][0]["data_sha256"] = "sha256:" + "2" * 64

    change = _single_entity_update(before, after, "KubernetesConfigMap")

    assert change.category == ChangeCategory.CONFIGURATION
    assert change.importance == ChangeImportance.MEDIUM


def test_stateful_set_image_change_is_titled_by_its_kind() -> None:
    before = _inventory()
    after = copy.deepcopy(before)
    after["statefulsets"][0]["images"] = ["postgres:17"]

    change = _single_entity_update(before, after, "KubernetesStatefulSet")

    assert change.category == ChangeCategory.DEPLOYMENT
    assert change.importance == ChangeImportance.HIGH
    assert change.title == "StatefulSet configuration changed"


def test_new_config_map_refs_field_does_not_change_existing_entities() -> None:
    after = _inventory()
    before = copy.deepcopy(after)
    for key in ("deployments", "statefulsets", "pods"):
        for item in before[key]:
            item.pop("config_map_refs", None)

    changes = normalize_snapshot_changes(
        _snapshot(before),
        _snapshot(after, minutes=1),
    )

    assert not [
        change
        for change in changes
        if change.change_type == ChangeType.ENTITY_UPDATED
    ]
