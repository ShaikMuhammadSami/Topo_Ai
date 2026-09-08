from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.orm import Session
from app.security.authorization_enforcement import authorize_service_operation

from app.db.models import (
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
    RelationshipOrigin,
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
from app.services.agent_azure_enrichment import (
    enrich_snapshot_with_azure,
)
from app.services.agent_gcp_enrichment import (
    enrich_snapshot_with_gcp,
)
from app.models.lifecycle_automation import (
    TopologyCheckpointReason,
)
from app.services.continuous_lifecycle import (
    failure_signals_from_snapshot,
    ingest_failure_signal_batch,
    reconcile_pending_incidents_for_checkpoint,
)
from app.services.topology_checkpoint import (
    persist_topology_checkpoint,
)
from app.services.canonical_identity import (
    canonical_kubernetes_identity,
)
from app.services.relationship_provenance import (
    relationship_provenance,
    source_reference,
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
    return canonical_kubernetes_identity(
        cluster_name=cluster_name,
        kind=kind,
        name=name,
        namespace=namespace,
        uid=uid,
    ).canonical_id


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

    cluster_identity = canonical_kubernetes_identity(
        cluster_name=(
            submission.cluster_name
        ),
        kind="cluster",
        uid=None,
        namespace=None,
        name=submission.cluster_name,
    )
    cluster_id = cluster_identity.canonical_id

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
            aliases=cluster_identity.aliases,
            identity_version=(
                cluster_identity.identity_version
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

        identity = canonical_kubernetes_identity(
            cluster_name=(
                submission.cluster_name
            ),
            kind=kind_key,
            uid=uid,
            namespace=namespace,
            name=name,
        )
        entity_id = identity.canonical_id

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
                external_id=(
                    identity.source_native_id
                ),
                aliases=identity.aliases,
                identity_version=(
                    identity.identity_version
                ),
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
        origin: RelationshipOrigin = RelationshipOrigin.OBSERVED,
        source_references: list[Any] | None = None,
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
                directed=True,
                evidence_ids=(
                    evidence or []
                ),
                provenance=relationship_provenance(
                    predicate=relation,
                    origin=origin,
                    source_component=(
                        "backend.app.services.agent_snapshot_ingest"
                    ),
                    source_references=[
                        source_reference(
                            reference_type="graph_entity_id",
                            reference=source_id,
                            source_system="topo",
                            attributes={"role": "subject"},
                        ),
                        source_reference(
                            reference_type="graph_entity_id",
                            reference=target_id,
                            source_system="topo",
                            attributes={"role": "object"},
                        ),
                        *(source_references or []),
                    ],
                    linker_version=(
                        "kubernetes-agent-inventory-linker:v1"
                    ),
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
                origin=RelationshipOrigin.DECLARED,
                source_references=[
                    source_reference(
                        reference_type="kubernetes_owner_reference_uid",
                        reference=item.get("owner_uid"),
                        source_system="kubernetes",
                        attributes={"child_uid": item.get("uid")},
                    )
                ],
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
                origin=RelationshipOrigin.DECLARED,
                source_references=[
                    source_reference(
                        reference_type="kubernetes_owner_reference_uid",
                        reference=item.get("owner_uid"),
                        source_system="kubernetes",
                        attributes={"child_uid": item.get("uid")},
                    )
                ],
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
                    origin=RelationshipOrigin.DECLARED,
                    source_references=[
                        source_reference(
                            reference_type="kubernetes_node_name",
                            reference=node_name,
                            source_system="kubernetes",
                            attributes={"pod_uid": item.get("uid")},
                        )
                    ],
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
                    origin=RelationshipOrigin.DERIVED,
                    source_references=[
                        source_reference(
                            reference_type="kubernetes_selector",
                            reference=selector,
                            source_system="kubernetes",
                            attributes={
                                "service_uid": service.get("uid"),
                                "pod_uid": pod.get("uid"),
                            },
                        )
                    ],
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
                    origin=RelationshipOrigin.DECLARED,
                    source_references=[
                        source_reference(
                            reference_type="kubernetes_ingress_backend",
                            reference=backend,
                            source_system="kubernetes",
                            attributes={"ingress_uid": ingress.get("uid")},
                        )
                    ],
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
                    source_references=[
                        source_reference(
                            reference_type="kubernetes_endpoint_target_uid",
                            reference=target_uid,
                            source_system="kubernetes",
                            attributes={
                                "service_name": service_name,
                                "namespace": namespace,
                            },
                        )
                    ],
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
            "namespace": (
                submission.namespace_scope[0]
                if len(
                    submission.namespace_scope
                ) == 1
                else "*"
            ),
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
    authorization_context=None,
) -> AgentSnapshotReceipt:
    authorize_service_operation(
        "app.services.agent_snapshot_ingest.persist_agent_snapshot",
        authorization_context=authorization_context,
    )
    snapshot = build_agent_snapshot(
        agent=agent,
        submission=submission,
    )
    snapshot = enrich_runtime_inventory(
      snapshot=snapshot,
      agent=agent,
      submission=submission,
    )
    snapshot = enrich_snapshot_with_runtime_dependencies(
        session=session,
        agent=agent,
        snapshot=snapshot,
        window_minutes=30,
        tenant_id=agent.tenant_id,
    )
    snapshot = enrich_snapshot_with_aws(
     snapshot=snapshot,
     agent=agent,
     submission=submission,
    )
    snapshot = enrich_snapshot_with_azure(
     snapshot=snapshot,
     agent=agent,
     submission=submission,
    )
    snapshot = enrich_snapshot_with_gcp(
     snapshot=snapshot,
     agent=agent,
     submission=submission,
    )

    persist_cloud_inventory(
        session=session,
        agent=agent,
        submission=submission,
        tenant_id=agent.tenant_id,
    )

    requested_reason = str(
        submission.metadata.get(
            "checkpoint_reason",
            TopologyCheckpointReason
            .PERIODIC_RECONCILE.value,
        )
    )

    try:
        reason = TopologyCheckpointReason(
            requested_reason
        )

    except ValueError:
        reason = (
            TopologyCheckpointReason
            .PERIODIC_RECONCILE
        )

    raw_trigger_ids = submission.metadata.get(
        "trigger_event_ids",
        [],
    )
    trigger_event_ids = (
        [str(item) for item in raw_trigger_ids]
        if isinstance(raw_trigger_ids, list)
        else []
    )
    raw_trigger_signal_ids = submission.metadata.get(
        "trigger_signal_ids",
        [],
    )
    trigger_signal_ids = (
        [
            str(item)
            for item in raw_trigger_signal_ids
        ]
        if isinstance(raw_trigger_signal_ids, list)
        else []
    )
    raw_trigger_signal_observations = (
        submission.metadata.get(
            "trigger_signal_observations",
            {},
        )
    )
    trigger_signal_observations = (
        {
            str(key): str(value)
            for key, value in (
                raw_trigger_signal_observations
            ).items()
        }
        if isinstance(
            raw_trigger_signal_observations,
            dict,
        )
        else {}
    )
    checkpoint = persist_topology_checkpoint(
        session=session,
        snapshot=snapshot,
        reason=reason,
        trigger_event_ids=trigger_event_ids,
        trigger_signal_ids=trigger_signal_ids,
        trigger_signal_observations=(trigger_signal_observations),
        agent_id=agent.agent_id,
        derive_changes=True,
        force=(reason == TopologyCheckpointReason.MANUAL),
        tenant_id=agent.tenant_id,
        authorization_context=authorization_context,
    )

    checkpoint_snapshot = snapshot.model_copy(
        update={
            "snapshot_id": checkpoint.snapshot_id
        }
    )
    failure_signals = (
        failure_signals_from_snapshot(
            checkpoint_snapshot
        )
    )
    lifecycle_result = None
    warnings: list[str] = []
    reconciled_results = reconcile_pending_incidents_for_checkpoint(
        session,
        snapshot_id=checkpoint.snapshot_id,
        tenant_id=agent.tenant_id,
        authorization_context=authorization_context,
    )

    if failure_signals:
        try:
            lifecycle_result = ingest_failure_signal_batch(
                session=session,
                signals=failure_signals,
                tenant_id=agent.tenant_id,
                authorization_context=authorization_context,
            )

        except Exception as exc:
            warnings.append(
                "Automatic failure processing failed; "
                "the topology checkpoint was preserved: "
                f"{type(exc).__name__}: {exc}"
            )

    record_snapshot_success(
        session=session,
        record=agent,
        tenant_id=agent.tenant_id,
    )

    return AgentSnapshotReceipt(
        agent_id=agent.agent_id,
        submission_id=(
            submission.submission_id
        ),
        snapshot_id=(
            checkpoint.snapshot_id
        ),
        accepted_at=utc_now_iso(),
        entity_count=len(
            snapshot.entities
        ),
        relationship_count=len(
            snapshot.relationships
        ),
        checkpoint_created=(
            checkpoint.created
        ),
        checkpoint_reused=(
            checkpoint.reused
        ),
        checkpoint_reason=reason.value,
        state_digest=(
            checkpoint.state_digest
        ),
        detected_change_count=(
            checkpoint.detected_change_count
        ),
        failure_signal_count=len(
            failure_signals
        ),
        incident_created_count=(
            lifecycle_result
            .incident_created_count
            if lifecycle_result is not None
            else 0
        ),
        incident_correlated_count=(
            (
                lifecycle_result
                .incident_correlated_count
                if lifecycle_result is not None
                else 0
            )
            + len(reconciled_results)
        ),
        automatic_analysis_states=(
            [
                result
                .automatic_analysis_state
                .value
                for result in (
                    (
                        lifecycle_result.results
                        if lifecycle_result
                        is not None
                        else []
                    )
                    + reconciled_results
                )
            ]
        ),
        warnings=warnings,
    )
