from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import (
    SnapshotRecord,
    TopoAgentRecord,
    utc_now_iso,
)
from app.models.agents import (
    AgentSnapshotReceipt,
    AgentSnapshotSubmission,
)
from app.models.topology import (
    Entity,
    EntityType,
    GraphSnapshot,
    Relationship,
    RelationshipType,
)
from app.repositories.agent_repository import (
    record_snapshot_success,
)
from app.services.agent_runtime_enrichment import (
    enrich_runtime_inventory,
)
from app.services.runtime_snapshot_enrichment import (
    enrich_snapshot_with_runtime_dependencies,
)
from app.repositories.cloud_repository import (
    persist_cloud_inventory,
)
from app.services.agent_cloud_enrichment import (
    enrich_snapshot_with_aws,
)

def _enum_member(
    enum_type: type,
    names: tuple[str, ...],
):
    for name in names:
        member = getattr(
            enum_type,
            name,
            None,
        )

        if member is not None:
            return member

    return next(iter(enum_type))


def _entity_type(
    *names: str,
):
    return _enum_member(
        EntityType,
        tuple(names)
        + ("UNKNOWN",),
    )


def _relationship_type(
    *names: str,
):
    return _enum_member(
        RelationshipType,
        tuple(names)
        + ("UNKNOWN",),
    )


def _stable_digest(
    value: str,
    length: int = 24,
) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:length]


def _entity_id(
    *,
    cluster_name: str,
    kind: str,
    uid: str | None,
    namespace: str | None,
    name: str,
) -> str:
    identity = (
        uid
        or _stable_digest(
            "|".join(
                [
                    cluster_name,
                    kind,
                    namespace or "",
                    name,
                ]
            )
        )
    )

    return (
        f"k8s:{cluster_name}:"
        f"{kind.lower()}:{identity}"
    )


def _relationship_id(
    source_id: str,
    relation: str,
    target_id: str,
) -> str:
    return (
        "relationship:"
        + _stable_digest(
            f"{source_id}|"
            f"{relation}|"
            f"{target_id}"
        )
    )


def _labels(
    value: Any,
) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}

    return {
        str(key): str(item)
        for key, item
        in value.items()
    }


def build_agent_snapshot(
    *,
    agent: TopoAgentRecord,
    submission: AgentSnapshotSubmission,
) -> GraphSnapshot:
    entities: list[Entity] = []
    relationships: list[
        Relationship
    ] = []

    entity_by_uid: dict[
        str,
        str,
    ] = {}

    entity_by_name: dict[
        tuple[str, str, str],
        str,
    ] = {}

    relationship_keys: set[
        tuple[str, str, str]
    ] = set()

    observed_at = (
        submission.collected_at
    )

    cluster_id = _entity_id(
        cluster_name=(
            submission.cluster_name
        ),
        kind="cluster",
        uid=None,
        namespace=None,
        name=submission.cluster_name,
    )

    entities.append(
        Entity(
            id=cluster_id,
            entity_type=_entity_type(
                "CLUSTER",
                "INFRASTRUCTURE",
            ),
            kind="KubernetesCluster",
            name=submission.cluster_name,
            source_system="kubernetes",
            external_id=(
                submission.cluster_name
            ),
            environment=(
                submission.environment
            ),
            observed_at=observed_at,
            confidence=1.0,
            labels={},
            properties={
                "agent_id":
                    agent.agent_id,
                "agent_name":
                    agent.name,
            },
        )
    )

    def add_entity(
        *,
        item: dict[str, Any],
        kind_key: str,
        kind_name: str,
        entity_type_names:
            tuple[str, ...],
    ) -> str:
        name = str(
            item.get("name")
            or "unknown"
        )

        namespace_value = (
            item.get("namespace")
        )

        namespace = (
            str(namespace_value)
            if namespace_value
            else None
        )

        uid_value = item.get("uid")

        uid = (
            str(uid_value)
            if uid_value
            else None
        )

        entity_id = _entity_id(
            cluster_name=(
                submission.cluster_name
            ),
            kind=kind_key,
            uid=uid,
            namespace=namespace,
            name=name,
        )

        properties = {
            key: value
            for key, value
            in item.items()
            if key not in {
                "labels",
            }
        }

        entities.append(
            Entity(
                id=entity_id,
                entity_type=_entity_type(
                    *entity_type_names
                ),
                kind=kind_name,
                name=name,
                source_system="kubernetes",
                external_id=uid,
                environment=(
                    submission.environment
                ),
                observed_at=observed_at,
                confidence=1.0,
                labels=_labels(
                    item.get("labels")
                ),
                properties=properties,
            )
        )

        if uid:
            entity_by_uid[uid] = (
                entity_id
            )

        entity_by_name[
            (
                kind_key,
                namespace or "",
                name,
            )
        ] = entity_id

        return entity_id

    def add_relationship(
        *,
        source_id: str,
        target_id: str,
        relation_name: str,
        evidence:
            list[str] | None = None,
    ) -> None:
        key = (
            source_id,
            relation_name,
            target_id,
        )

        if key in relationship_keys:
            return

        relationship_keys.add(key)

        relation = (
            _relationship_type(
                relation_name
            )
        )

        relationships.append(
            Relationship(
                id=_relationship_id(
                    source_id,
                    relation.value,
                    target_id,
                ),
                source_entity_id=source_id,
                target_entity_id=target_id,
                relationship_type=relation,
                source_system="kubernetes",
                observed_at=observed_at,
                confidence=1.0,
                directed=True,
                evidence_ids=(
                    evidence or []
                ),
                properties={},
            )
        )

    inventory = submission.inventory

    for item in inventory.get(
        "namespaces",
        [],
    ):
        namespace_id = add_entity(
            item=item,
            kind_key="namespace",
            kind_name=(
                "KubernetesNamespace"
            ),
            entity_type_names=(
                "NAMESPACE",
                "BOUNDARY",
            ),
        )

        add_relationship(
            source_id=cluster_id,
            target_id=namespace_id,
            relation_name="CONTAINS",
        )

    for item in inventory.get(
        "nodes",
        [],
    ):
        node_id = add_entity(
            item=item,
            kind_key="node",
            kind_name="KubernetesNode",
            entity_type_names=(
                "HOST",
                "COMPUTE",
            ),
        )

        add_relationship(
            source_id=cluster_id,
            target_id=node_id,
            relation_name="CONTAINS",
        )

    resource_definitions = [
        (
            "deployments",
            "deployment",
            "KubernetesDeployment",
            ("WORKLOAD", "COMPUTE"),
        ),
        (
            "replicasets",
            "replicaset",
            "KubernetesReplicaSet",
            ("WORKLOAD", "COMPUTE"),
        ),
        (
            "pods",
            "pod",
            "KubernetesPod",
            ("WORKLOAD", "COMPUTE"),
        ),
        (
            "services",
            "service",
            "KubernetesService",
            ("SERVICE", "NETWORK"),
        ),
        (
            "ingresses",
            "ingress",
            "KubernetesIngress",
            ("NETWORK", "SERVICE"),
        ),
        (
            "endpoint_slices",
            "endpointslice",
            "KubernetesEndpointSlice",
            ("NETWORK", "SERVICE"),
        ),
    ]

    for (
        inventory_key,
        kind_key,
        kind_name,
        entity_types,
    ) in resource_definitions:
        for item in inventory.get(
            inventory_key,
            [],
        ):
            entity_id = add_entity(
                item=item,
                kind_key=kind_key,
                kind_name=kind_name,
                entity_type_names=(
                    entity_types
                ),
            )

            namespace = str(
                item.get("namespace")
                or ""
            )

            namespace_id = (
                entity_by_name.get(
                    (
                        "namespace",
                        "",
                        namespace,
                    )
                )
            )

            if namespace_id:
                add_relationship(
                    source_id=namespace_id,
                    target_id=entity_id,
                    relation_name=(
                        "CONTAINS"
                    ),
                )

    for item in inventory.get(
        "replicasets",
        [],
    ):
        child_id = entity_by_uid.get(
            str(item.get("uid"))
        )

        owner_id = entity_by_uid.get(
            str(
                item.get("owner_uid")
            )
        )

        if child_id and owner_id:
            add_relationship(
                source_id=owner_id,
                target_id=child_id,
                relation_name="OWNS",
            )

    for item in inventory.get(
        "pods",
        [],
    ):
        pod_id = entity_by_uid.get(
            str(item.get("uid"))
        )

        owner_id = entity_by_uid.get(
            str(
                item.get("owner_uid")
            )
        )

        if pod_id and owner_id:
            add_relationship(
                source_id=owner_id,
                target_id=pod_id,
                relation_name="OWNS",
            )

        node_name = item.get(
            "node_name"
        )

        if pod_id and node_name:
            node_id = (
                entity_by_name.get(
                    (
                        "node",
                        "",
                        str(node_name),
                    )
                )
            )

            if node_id:
                add_relationship(
                    source_id=pod_id,
                    target_id=node_id,
                    relation_name=(
                        "ATTACHED_TO"
                    ),
                )

    pods = inventory.get(
        "pods",
        [],
    )

    for service in inventory.get(
        "services",
        [],
    ):
        namespace = str(
            service.get("namespace")
            or ""
        )

        service_id = (
            entity_by_uid.get(
                str(service.get("uid"))
            )
        )

        selector = service.get(
            "selector"
        )

        if (
            not service_id
            or not isinstance(
                selector,
                dict,
            )
            or not selector
        ):
            continue

        for pod in pods:
            if (
                str(
                    pod.get("namespace")
                    or ""
                )
                != namespace
            ):
                continue

            pod_labels = _labels(
                pod.get("labels")
            )

            matches = all(
                pod_labels.get(
                    str(key)
                )
                == str(value)
                for key, value
                in selector.items()
            )

            if not matches:
                continue

            pod_id = entity_by_uid.get(
                str(pod.get("uid"))
            )

            if pod_id:
                add_relationship(
                    source_id=service_id,
                    target_id=pod_id,
                    relation_name="SELECTS",
                )

    for ingress in inventory.get(
        "ingresses",
        [],
    ):
        ingress_id = entity_by_uid.get(
            str(ingress.get("uid"))
        )

        namespace = str(
            ingress.get("namespace")
            or ""
        )

        if not ingress_id:
            continue

        for backend in ingress.get(
            "backends",
            [],
        ):
            service_name = str(
                backend.get(
                    "service_name"
                )
                or ""
            )

            service_id = (
                entity_by_name.get(
                    (
                        "service",
                        namespace,
                        service_name,
                    )
                )
            )

            if service_id:
                add_relationship(
                    source_id=ingress_id,
                    target_id=service_id,
                    relation_name=(
                        "ROUTES_TO"
                    ),
                )

    for endpoint_slice in (
        inventory.get(
            "endpoint_slices",
            [],
        )
    ):
        namespace = str(
            endpoint_slice.get(
                "namespace"
            )
            or ""
        )

        service_name = str(
            endpoint_slice.get(
                "service_name"
            )
            or ""
        )

        service_id = (
            entity_by_name.get(
                (
                    "service",
                    namespace,
                    service_name,
                )
            )
        )

        if not service_id:
            continue

        for endpoint in (
            endpoint_slice.get(
                "endpoints",
                [],
            )
        ):
            target_uid = endpoint.get(
                "target_uid"
            )

            pod_id = (
                entity_by_uid.get(
                    str(target_uid)
                )
                if target_uid
                else None
            )

            if pod_id:
                add_relationship(
                    source_id=service_id,
                    target_id=pod_id,
                    relation_name=(
                        "ROUTES_TO"
                    ),
                )

    snapshot_identity = "|".join(
        [
            agent.agent_id,
            submission.submission_id,
            submission.collected_at,
            str(len(entities)),
            str(len(relationships)),
        ]
    )

    snapshot_id = (
        "snapshot:agent:"
        + _stable_digest(
            snapshot_identity,
            length=32,
        )
    )
    

    return GraphSnapshot(
        schema_version="1.0",
        snapshot_id=snapshot_id,
        collected_at=(
            submission.collected_at
        ),
        collector_name=(
            "topo-agent-kubernetes"
        ),
        collector_version=(
            submission.collector_version
        ),
        scope={
            "cluster":
                submission.cluster_name,
            "namespaces": (
                ",".join(submission.namespace_scope)
                if isinstance(submission.namespace_scope,list)
                else submission.scope.namespace_scope
            ),
                
            "agent_id":
                agent.agent_id,
        },
        entities=entities,
        relationships=relationships,
        evidence=[],
        metadata={
            "agent_id":
                agent.agent_id,
            "agent_name":
                agent.name,
            "submission_id":
                submission.submission_id,
            **submission.metadata,
        },
    )


def persist_agent_snapshot(
    session: Session,
    *,
    agent: TopoAgentRecord,
    submission: AgentSnapshotSubmission,
) -> AgentSnapshotReceipt:
    snapshot = build_agent_snapshot(
        agent=agent,
        submission=submission,
    )
    snapshot = enrich_runtime_inventory(
      snapshot=snapshot,
      agent=agent,
      submission=submission,
    )
    snapshot = enrich_snapshot_with_aws(
     snapshot=snapshot,
     agent=agent,
     submission=submission,
    )
    snapshot = (
     enrich_snapshot_with_runtime_dependencies(
         session=session,
         agent=agent,
         snapshot=snapshot,
         window_minutes=30,
        )
    )

    existing = session.get(
        SnapshotRecord,
        snapshot.snapshot_id,
    )
    persist_cloud_inventory(
     session=session,
     agent=agent,
     submission=submission,
    )

    if existing is None:
        payload = snapshot.model_dump(
            mode="json"
        )

        namespace_value = (
            submission
            .namespace_scope[0]
            if len(
                submission
                .namespace_scope
            )
            == 1
            else None
        )
    
        record = SnapshotRecord(
            snapshot_id=(
                snapshot.snapshot_id
            ),
            schema_version=(
                snapshot.schema_version
            ),
            collected_at=(
                snapshot.collected_at
            ),
            collector_name=(
                snapshot.collector_name
            ),
            collector_version=(
                snapshot
                .collector_version
            ),
            cluster_name=(
                submission.cluster_name
            ),
            namespace=namespace_value,
            entity_count=len(
                snapshot.entities
            ),
            relationship_count=len(
                snapshot.relationships
            ),
            evidence_count=len(
                snapshot.evidence
            ),
            scope_json=json.dumps(
                payload.get(
                    "scope",
                    {},
                )
            ),
            payload_json=json.dumps(
                payload
            ),
            created_at=utc_now_iso(),
        )

        session.add(record)
        session.commit()

    record_snapshot_success(
        session=session,
        record=agent,
    )

    return AgentSnapshotReceipt(
        agent_id=agent.agent_id,
        submission_id=(
            submission.submission_id
        ),
        snapshot_id=(
            snapshot.snapshot_id
        ),
        accepted_at=utc_now_iso(),
        entity_count=len(
            snapshot.entities
        ),
        relationship_count=len(
            snapshot.relationships
        ),
    )