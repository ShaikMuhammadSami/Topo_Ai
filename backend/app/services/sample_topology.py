from datetime import datetime, timezone

from app.models.topology import (
    Entity,
    EntityType,
    Evidence,
    EvidenceType,
    GraphSnapshot,
    Relationship,
    RelationshipOrigin,
    RelationshipType,
)
from app.services.relationship_provenance import (
    relationship_provenance,
    source_reference,
)


def build_sample_snapshot() -> GraphSnapshot:
    observed_at = datetime.now(timezone.utc)

    namespace_id = "k8s:demo-cluster:namespace:payments"
    deployment_id = (
        "k8s:demo-cluster:deployment:payments:payment-service"
    )
    pod_id = (
        "k8s:demo-cluster:pod:payments:payment-service-7c9f8"
    )
    service_id = (
        "k8s:demo-cluster:service:payments:payment-service"
    )

    entities = [
        Entity(
            id=namespace_id,
            entity_type=EntityType.ENVIRONMENT,
            kind="KubernetesNamespace",
            name="payments",
            source_system="kubernetes",
            environment="development",
            observed_at=observed_at,
            labels={},
            properties={
                "cluster": "demo-cluster",
            },
        ),
        Entity(
            id=deployment_id,
            entity_type=EntityType.WORKLOAD,
            kind="KubernetesDeployment",
            name="payment-service",
            source_system="kubernetes",
            environment="development",
            observed_at=observed_at,
            labels={
                "app": "payment-service",
            },
            properties={
                "cluster": "demo-cluster",
                "namespace": "payments",
                "desired_replicas": 1,
                "ready_replicas": 1,
            },
        ),
        Entity(
            id=pod_id,
            entity_type=EntityType.RUNTIME_INSTANCE,
            kind="KubernetesPod",
            name="payment-service-7c9f8",
            source_system="kubernetes",
            environment="development",
            observed_at=observed_at,
            labels={
                "app": "payment-service",
            },
            properties={
                "cluster": "demo-cluster",
                "namespace": "payments",
                "phase": "Running",
            },
        ),
        Entity(
            id=service_id,
            entity_type=EntityType.ENDPOINT,
            kind="KubernetesService",
            name="payment-service",
            source_system="kubernetes",
            environment="development",
            observed_at=observed_at,
            labels={
                "app": "payment-service",
            },
            properties={
                "cluster": "demo-cluster",
                "namespace": "payments",
                "service_type": "ClusterIP",
                "ports": [8080],
            },
        ),
    ]

    relationships = [
        Relationship(
            id="rel:namespace-contains-deployment",
            source_entity_id=namespace_id,
            target_entity_id=deployment_id,
            relationship_type=RelationshipType.CONTAINS,
            source_system="kubernetes",
            observed_at=observed_at,
            provenance=relationship_provenance(
                predicate=RelationshipType.CONTAINS,
                origin=RelationshipOrigin.DECLARED,
                source_component="backend.app.services.sample_topology",
                source_references=[
                    source_reference(
                        reference_type="sample_definition",
                        reference="namespace-contains-deployment",
                        source_system="topo-sample",
                    )
                ],
                linker_version="sample-topology-linker:v1",
            ),
        ),
        Relationship(
            id="rel:deployment-runs-pod",
            source_entity_id=deployment_id,
            target_entity_id=pod_id,
            relationship_type=RelationshipType.RUNS,
            source_system="kubernetes",
            observed_at=observed_at,
            provenance=relationship_provenance(
                predicate=RelationshipType.RUNS,
                origin=RelationshipOrigin.DECLARED,
                source_component="backend.app.services.sample_topology",
                source_references=[
                    source_reference(
                        reference_type="sample_definition",
                        reference="deployment-runs-pod",
                        source_system="topo-sample",
                    )
                ],
                linker_version="sample-topology-linker:v1",
            ),
        ),
        Relationship(
            id="rel:service-selects-pod",
            source_entity_id=service_id,
            target_entity_id=pod_id,
            relationship_type=RelationshipType.SELECTS,
            source_system="kubernetes",
            observed_at=observed_at,
            provenance=relationship_provenance(
                predicate=RelationshipType.SELECTS,
                origin=RelationshipOrigin.DERIVED,
                source_component="backend.app.services.sample_topology",
                source_references=[
                    source_reference(
                        reference_type="kubernetes_selector",
                        reference={"app": "payment-service"},
                        source_system="topo-sample",
                    )
                ],
                linker_version="sample-topology-linker:v1",
            ),
            properties={
                "selector": {
                    "app": "payment-service",
                }
            },
        ),
    ]

    evidence = [
        Evidence(
            id="evidence:sample-discovery",
            evidence_type=EvidenceType.DISCOVERY,
            source_system="kubernetes",
            summary=(
                "Payment service resources were discovered "
                "from the Kubernetes API."
            ),
            observed_at=observed_at,
            related_entity_ids=[
                namespace_id,
                deployment_id,
                pod_id,
                service_id,
            ],
            related_relationship_ids=[
                relationship.id for relationship in relationships
            ],
            payload={
                "cluster": "demo-cluster",
                "collector_mode": "sample",
            },
        )
    ]

    return GraphSnapshot(
        snapshot_id=(
            f"snapshot:demo-cluster:"
            f"{observed_at.strftime('%Y%m%dT%H%M%SZ')}"
        ),
        collected_at=observed_at,
        collector_name="sample-topology-builder",
        collector_version="0.1.0",
        scope={
            "platform": "kubernetes",
            "cluster": "demo-cluster",
            "environment": "development",
        },
        entities=entities,
        relationships=relationships,
        evidence=evidence,
        metadata={
            "mode": "sample",
        },
    )
