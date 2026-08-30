from __future__ import annotations
from domain_tenant_fixtures import TEST_TENANT, seed_domain_tenant

import ast
import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import (
    ChangeEventRecord,
    ChangeRecord,
    RuntimeDependencyRecord,
)
from app.models.agents import AgentSnapshotSubmission
from app.models.build_artifacts import (
    BuildArtifactEvidence,
    BuildArtifactEvidenceCompleteness,
    BuildArtifactEvidenceType,
    BuildArtifactType,
)
from app.models.lifecycle_automation import TopologyCheckpointReason
from app.models.topology import (
    Entity,
    EntityType,
    GraphSnapshot,
    Relationship,
    RelationshipConfidenceSemantics,
    RelationshipOrigin,
    RelationshipType,
)
from app.services.agent_cloud_enrichment import enrich_snapshot_with_aws
from app.services.agent_runtime_enrichment import enrich_runtime_inventory
from app.services.agent_snapshot_ingest import (
    _relationship_id as agent_relationship_id,
    build_agent_snapshot,
)
from app.services.blast_radius import traverse_blast_radius
from app.services.causal_rca import (
    ALGORITHM_VERSION,
    _adjacency,
    _pinned_relationship_metadata,
)
from app.services.change_normalizer import normalize_snapshot_changes
from app.services.container_image_graph import (
    augment_snapshot_with_container_images,
)
from app.services.github_actions_graph import (
    augment_snapshot_with_github_actions,
)
from app.services.github_actions_artifact_lineage import (
    reconcile_build_artifact_lineage,
)
from app.services.github_graph import augment_snapshot_with_github
from app.services.relationship_provenance import (
    ACTIVE_RELATIONSHIP_PREDICATES,
    relationship_provenance,
    source_reference,
)
from app.services import runtime_snapshot_enrichment
from app.services.runtime_snapshot_enrichment import (
    enrich_snapshot_with_runtime_dependencies,
)
from app.services.snapshot_diff import compare_snapshots
from app.services.temporal_semantics import build_temporal_metadata
from app.services.topology_checkpoint import persist_topology_checkpoint

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = (
    ROOT
    / "docs"
    / "architecture"
    / "truth-contract"
    / "relationship-provenance-contract.json"
)


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine)
    return Session(engine)


def _entity(
    entity_id: str,
    *,
    kind: str,
    name: str,
    properties: dict | None = None,
) -> Entity:
    return Entity(
        id=entity_id,
        entity_type=EntityType.WORKLOAD,
        kind=kind,
        name=name,
        source_system="test",
        external_id=entity_id,
        observed_at=NOW,
        properties=properties or {},
    )


def _provenance(
    *,
    origin: RelationshipOrigin = RelationshipOrigin.DECLARED,
    reference: str = "native:edge:one",
) -> object:
    return relationship_provenance(
        predicate=RelationshipType.DEPENDS_ON,
        origin=origin,
        source_component="backend.tests.test_relationship_provenance",
        source_references=[
            source_reference(
                reference_type="test_native_reference",
                reference=reference,
                source_system="test",
            )
        ],
        linker_version="test-linker:v1",
    )


def _relationship(
    *,
    properties: dict | None = None,
    provenance: object | None = None,
    observed_at: datetime = NOW,
) -> Relationship:
    return Relationship(
        id="relationship:service-depends-database",
        source_entity_id="entity:service",
        target_entity_id="entity:database",
        relationship_type=RelationshipType.DEPENDS_ON,
        source_system="test",
        observed_at=observed_at,
        evidence_ids=[],
        provenance=provenance,
        properties=properties or {"port": 5432},
    )


def _snapshot(
    snapshot_id: str,
    *,
    relationship: Relationship | None,
    collected_at: datetime = NOW,
) -> GraphSnapshot:
    return GraphSnapshot(
        snapshot_id=snapshot_id,
        collected_at=collected_at,
        collector_name="tc2-test",
        collector_version="1",
        scope={"cluster": "test"},
        entities=[
            _entity(
                "entity:service",
                kind="KubernetesService",
                name="payment-api",
            ),
            _entity(
                "entity:database",
                kind="Database",
                name="payments-db",
            ),
        ],
        relationships=(
            [relationship]
            if relationship is not None
            else []
        ),
        evidence=[],
        metadata={},
    )


def _kubernetes_snapshot() -> GraphSnapshot:
    submission = AgentSnapshotSubmission(
        submission_id="submission:tc2-kubernetes",
        collected_at=NOW.isoformat(),
        cluster_name="production",
        environment="production",
        namespace_scope=["payments"],
        collector_version="1.0",
        inventory={
            "namespaces": [{"uid": "ns-uid", "name": "payments"}],
            "nodes": [{"uid": "node-uid", "name": "worker-one"}],
            "deployments": [
                {
                    "uid": "deployment-uid",
                    "name": "payment-api",
                    "namespace": "payments",
                    "labels": {"app": "payment-api"},
                }
            ],
            "replicasets": [
                {
                    "uid": "replicaset-uid",
                    "owner_uid": "deployment-uid",
                    "name": "payment-api-7d9",
                    "namespace": "payments",
                    "labels": {"app": "payment-api"},
                }
            ],
            "pods": [
                {
                    "uid": "pod-uid",
                    "owner_uid": "replicaset-uid",
                    "name": "payment-api-7d9-abcd1",
                    "namespace": "payments",
                    "node_name": "worker-one",
                    "labels": {"app": "payment-api"},
                }
            ],
            "services": [
                {
                    "uid": "service-uid",
                    "name": "payment-api",
                    "namespace": "payments",
                    "selector": {"app": "payment-api"},
                }
            ],
            "ingresses": [
                {
                    "uid": "ingress-uid",
                    "name": "payment-api",
                    "namespace": "payments",
                    "backends": [{"service_name": "payment-api", "port": 80}],
                }
            ],
            "endpoint_slices": [
                {
                    "uid": "slice-uid",
                    "name": "payment-api-abc",
                    "namespace": "payments",
                    "service_name": "payment-api",
                    "endpoints": [{"target_uid": "pod-uid"}],
                }
            ],
        },
        metadata={},
    )
    return build_agent_snapshot(
        agent=SimpleNamespace(
            agent_id="agent:tc2",
            name="tc2-agent",
        ),
        submission=submission,
    )


def _edge(
    snapshot: GraphSnapshot,
    *,
    predicate: RelationshipType,
    source_kind: str,
    target_kind: str,
) -> Relationship:
    entities = {item.id: item for item in snapshot.entities}
    return next(
        relationship
        for relationship in snapshot.relationships
        if relationship.relationship_type == predicate
        and entities[relationship.source_entity_id].kind == source_kind
        and entities[relationship.target_entity_id].kind == target_kind
    )


def test_kubernetes_owner_edges_carry_declared_origin_and_owner_uid() -> None:
    snapshot = _kubernetes_snapshot()
    deployment_to_rs = _edge(
        snapshot,
        predicate=RelationshipType.OWNS,
        source_kind="KubernetesDeployment",
        target_kind="KubernetesReplicaSet",
    )
    rs_to_pod = _edge(
        snapshot,
        predicate=RelationshipType.OWNS,
        source_kind="KubernetesReplicaSet",
        target_kind="KubernetesPod",
    )

    for relationship, owner_uid in (
        (deployment_to_rs, "deployment-uid"),
        (rs_to_pod, "replicaset-uid"),
    ):
        assert relationship.provenance is not None
        assert relationship.provenance.origin == RelationshipOrigin.DECLARED
        assert relationship.confidence is None
        assert any(
            reference.reference_type == "kubernetes_owner_reference_uid"
            and reference.reference == owner_uid
            for reference in relationship.provenance.source_references
        )


def test_service_selector_edge_is_derived_with_real_selector_reference() -> None:
    relationship = _edge(
        _kubernetes_snapshot(),
        predicate=RelationshipType.SELECTS,
        source_kind="KubernetesService",
        target_kind="KubernetesPod",
    )

    assert relationship.provenance is not None
    assert relationship.provenance.origin == RelationshipOrigin.DERIVED
    assert relationship.confidence is None
    selector = next(
        item
        for item in relationship.provenance.source_references
        if item.reference_type == "kubernetes_selector"
    )
    assert json.loads(selector.reference) == {"app": "payment-api"}


def test_ingress_and_endpoint_relationships_keep_distinct_origins() -> None:
    snapshot = _kubernetes_snapshot()
    ingress = _edge(
        snapshot,
        predicate=RelationshipType.ROUTES_TO,
        source_kind="KubernetesIngress",
        target_kind="KubernetesService",
    )
    endpoint = _edge(
        snapshot,
        predicate=RelationshipType.ROUTES_TO,
        source_kind="KubernetesService",
        target_kind="KubernetesPod",
    )

    assert ingress.provenance is not None
    assert endpoint.provenance is not None
    assert ingress.provenance.origin == RelationshipOrigin.DECLARED
    assert endpoint.provenance.origin == RelationshipOrigin.OBSERVED


def test_node_scheduling_edge_is_declared_and_referenced() -> None:
    relationship = _edge(
        _kubernetes_snapshot(),
        predicate=RelationshipType.ATTACHED_TO,
        source_kind="KubernetesPod",
        target_kind="KubernetesNode",
    )
    assert relationship.provenance is not None
    assert relationship.provenance.origin == RelationshipOrigin.DECLARED
    assert any(
        item.reference == "worker-one"
        for item in relationship.provenance.source_references
    )


def test_linker_metadata_and_serialization_are_deterministic() -> None:
    first_reference = source_reference(
        reference_type="native",
        reference="b",
        source_system="test",
    )
    second_reference = source_reference(
        reference_type="native",
        reference="a",
        source_system="test",
    )
    first = relationship_provenance(
        predicate=RelationshipType.CALLS,
        origin=RelationshipOrigin.OBSERVED,
        source_component="test.component",
        source_references=[first_reference, second_reference],
        linker_version="test-linker:v1",
    )
    second = relationship_provenance(
        predicate=RelationshipType.CALLS,
        origin=RelationshipOrigin.OBSERVED,
        source_component="test.component",
        source_references=[second_reference, first_reference, second_reference],
        linker_version="test-linker:v1",
    )

    assert first.model_dump_json() == second.model_dump_json()
    assert first.linker_version == "test-linker:v1"


def test_legacy_relationship_loads_without_fabricated_provenance() -> None:
    relationship = Relationship.model_validate(
        {
            "id": "relationship:legacy",
            "source_entity_id": "entity:one",
            "target_entity_id": "entity:two",
            "relationship_type": "depends_on",
            "source_system": "legacy",
            "observed_at": NOW.isoformat(),
            "confidence": 1.0,
            "directed": True,
            "evidence_ids": [],
            "properties": {},
        }
    )

    assert relationship.provenance is None
    assert relationship.confidence == 1.0
    assert relationship.confidence_semantics is None


def test_observed_declared_and_derived_edges_cannot_claim_numeric_confidence() -> None:
    for origin in (
        RelationshipOrigin.OBSERVED,
        RelationshipOrigin.DECLARED,
        RelationshipOrigin.DERIVED,
    ):
        with pytest.raises(ValueError, match="Only inferred"):
            Relationship(
                id=f"relationship:{origin.value}",
                source_entity_id="entity:one",
                target_entity_id="entity:two",
                relationship_type=RelationshipType.CALLS,
                source_system="test",
                observed_at=NOW,
                confidence=0.9,
                confidence_semantics=(
                    RelationshipConfidenceSemantics.HEURISTIC_SCORE
                ),
                provenance=relationship_provenance(
                    predicate=RelationshipType.CALLS,
                    origin=origin,
                    source_component="test",
                ),
            )


def test_inferred_edge_may_be_honestly_unscored() -> None:
    relationship = Relationship(
        id="relationship:inferred-unscored",
        source_entity_id="entity:one",
        target_entity_id="entity:two",
        relationship_type=RelationshipType.CALLS,
        source_system="test",
        observed_at=NOW,
        provenance=relationship_provenance(
            predicate=RelationshipType.CALLS,
            origin=RelationshipOrigin.INFERRED,
            source_component="test",
        ),
    )
    assert relationship.confidence is None
    assert relationship.confidence_semantics is None


def test_inferred_computed_score_is_explicitly_heuristic() -> None:
    relationship = Relationship(
        id="relationship:inferred-scored",
        source_entity_id="entity:one",
        target_entity_id="entity:two",
        relationship_type=RelationshipType.CALLS,
        source_system="test",
        observed_at=NOW,
        confidence=0.72,
        confidence_semantics=RelationshipConfidenceSemantics.HEURISTIC_SCORE,
        provenance=relationship_provenance(
            predicate=RelationshipType.CALLS,
            origin=RelationshipOrigin.INFERRED,
            source_component="test",
        ),
    )
    assert relationship.confidence == 0.72


def test_relationship_id_excludes_provenance_time_and_evidence_order() -> None:
    first = agent_relationship_id("entity:a", "calls", "entity:b")
    second = agent_relationship_id("entity:a", "calls", "entity:b")
    before = Relationship(
        id=first,
        source_entity_id="entity:a",
        target_entity_id="entity:b",
        relationship_type=RelationshipType.CALLS,
        source_system="test",
        observed_at=NOW,
        evidence_ids=["evidence:b", "evidence:a"],
        provenance=relationship_provenance(
            predicate=RelationshipType.CALLS,
            origin=RelationshipOrigin.OBSERVED,
            source_component="test:v1",
        ),
    )
    after = before.model_copy(
        update={
            "observed_at": NOW + timedelta(hours=1),
            "evidence_ids": ["evidence:a", "evidence:b"],
            "provenance": relationship_provenance(
                predicate=RelationshipType.CALLS,
                origin=RelationshipOrigin.OBSERVED,
                source_component="test:v2",
            ),
        }
    )

    assert first == second == before.id == after.id


def test_provenance_only_enrichment_is_not_a_topology_change() -> None:
    before = _snapshot("snapshot:legacy", relationship=_relationship())
    after = _snapshot(
        "snapshot:tc2",
        relationship=_relationship(
            provenance=_provenance(),
            observed_at=NOW + timedelta(minutes=1),
        ),
        collected_at=NOW + timedelta(minutes=1),
    )

    diff = compare_snapshots(before, after)
    assert diff.summary["changed_relationships"] == 0
    assert normalize_snapshot_changes(before, after) == []


def test_provenance_only_checkpoint_creates_no_change_record_or_event() -> None:
    session = _session()
    persist_topology_checkpoint(
        session,
        snapshot=_snapshot("snapshot:legacy-checkpoint", relationship=_relationship()),
        reason=TopologyCheckpointReason.PERIODIC_RECONCILE,
        tenant_id=TEST_TENANT,
    )
    result = persist_topology_checkpoint(
        session,
        snapshot=_snapshot(
            "snapshot:tc2-checkpoint",
            relationship=_relationship(provenance=_provenance()),
            collected_at=NOW + timedelta(minutes=1),
        ),
        reason=TopologyCheckpointReason.AUTOMATIC_CHANGE,
        tenant_id=TEST_TENANT,
    )

    assert result.detected_change_count == 0
    assert session.scalar(select(func.count()).select_from(ChangeRecord)) == 0
    assert session.scalar(select(func.count()).select_from(ChangeEventRecord)) == 0


def test_real_relationship_addition_and_removal_remain_material() -> None:
    empty = _snapshot("snapshot:empty", relationship=None)
    with_edge = _snapshot(
        "snapshot:edge",
        relationship=_relationship(provenance=_provenance()),
    )

    added = compare_snapshots(empty, with_edge)
    removed = compare_snapshots(with_edge, empty)
    assert len(added.added_relationships) == 1
    assert len(removed.removed_relationships) == 1
    assert normalize_snapshot_changes(empty, with_edge)[0].change_type.value == (
        "relationship_added"
    )
    assert normalize_snapshot_changes(with_edge, empty)[0].change_type.value == (
        "relationship_removed"
    )


def test_real_relationship_property_update_remains_material() -> None:
    before = _snapshot(
        "snapshot:before-property",
        relationship=_relationship(
            properties={"port": 5432},
            provenance=_provenance(),
        ),
    )
    after = _snapshot(
        "snapshot:after-property",
        relationship=_relationship(
            properties={"port": 6432},
            provenance=_provenance(reference="stronger-source"),
        ),
    )

    diff = compare_snapshots(before, after)
    assert len(diff.changed_relationships) == 1
    assert "properties" in diff.changed_relationships[0].changed_fields


def test_pinned_rca_relationship_metadata_never_reads_newer_provenance() -> None:
    pinned = _snapshot(
        "snapshot:pinned",
        relationship=_relationship(
            provenance=_provenance(reference="incident-time-reference")
        ),
    )
    newer = _snapshot(
        "snapshot:newer",
        relationship=_relationship(
            provenance=_provenance(reference="future-reference")
        ),
        collected_at=NOW + timedelta(hours=1),
    )

    metadata = _pinned_relationship_metadata(
        pinned,
        left_entity_id="entity:service",
        right_entity_id="entity:database",
    )
    encoded = json.dumps(metadata, sort_keys=True)

    assert metadata["topology_snapshot_id"] == "snapshot:pinned"
    assert "incident-time-reference" in encoded
    assert "future-reference" not in encoded
    assert newer.snapshot_id != metadata["topology_snapshot_id"]


def test_legacy_pinned_rca_relationship_reports_unspecified_provenance() -> None:
    metadata = _pinned_relationship_metadata(
        _snapshot("snapshot:legacy-pinned", relationship=_relationship()),
        left_entity_id="entity:service",
        right_entity_id="entity:database",
    )
    assert metadata["relationship_provenance"] is None
    assert metadata["relationship_provenance_status"] == "legacy_unspecified"


def test_source_to_runtime_existing_hops_have_honest_provenance() -> None:
    sha = "a" * 40
    digest = "sha256:" + "b" * 64
    workload = Entity(
        id="k8s:production:deployment:payment",
        entity_type=EntityType.WORKLOAD,
        kind="KubernetesDeployment",
        name="payment-api",
        source_system="kubernetes",
        observed_at=NOW,
        properties={
            "containers": [
                {"name": "payment", "image": f"ghcr.io/acme/payment@{digest}"}
            ],
            "annotations": {
                "topo.ai/source-repository": "acme/payment",
                "topo.ai/source-revision": sha,
                "topo.ai/workflow-run-id": "42",
                "topo.ai/image-digest": digest,
            },
        },
    )
    snapshot = GraphSnapshot(
        snapshot_id="snapshot:source-runtime",
        collected_at=NOW,
        collector_name="test",
        collector_version="1",
        scope={},
        entities=[workload],
        relationships=[],
        evidence=[],
        metadata={},
    )
    snapshot = augment_snapshot_with_container_images(snapshot)
    snapshot, _ = augment_snapshot_with_github(
        snapshot,
        repository={"id": 101, "full_name": "acme/payment"},
        commits=[{"sha": sha, "commit": {"message": "release"}}],
        api_url="https://api.github.com",
    )
    snapshot, _ = augment_snapshot_with_github_actions(
        snapshot,
        workflow_runs=[
            {
                "id": 42,
                "name": "build",
                "run_number": 7,
                "run_attempt": 1,
                "head_sha": sha,
                "conclusion": "success",
                "updated_at": NOW.isoformat(),
            }
        ],
        repository_full_name="acme/payment",
        api_url="https://api.github.com",
    )
    snapshot, _ = reconcile_build_artifact_lineage(
        snapshot,
        evidence=[
            BuildArtifactEvidence(
                evidence_id="build-artifact-evidence:relationship-provenance",
                provider="github_actions",
                repository_id="101",
                repository="acme/payment",
                workflow_id=None,
                workflow_ref="acme/payment/.github/workflows/build.yml@refs/heads/main",
                run_id="42",
                run_attempt=1,
                commit_sha=sha,
                artifact_type=BuildArtifactType.CONTAINER_IMAGE,
                image_repository="ghcr.io/acme/payment",
                image_reference="ghcr.io/acme/payment:release",
                image_digest=digest,
                immutable_image_ref=f"ghcr.io/acme/payment@{digest}",
                provider_evidence_type=(
                    BuildArtifactEvidenceType.GITHUB_ACTIONS_DOCKER_BUILD_RECORD
                ),
                provider_evidence_id="9001",
                provider_evidence_reference=(
                    "https://api.github.com/repos/acme/payment/actions/artifacts/9001"
                ),
                provider_evidence_digest="sha256:" + "c" * 64,
                provider_build_record_digest="sha256:" + "d" * 64,
                provider_builder_id=(
                    "https://github.com/acme/payment/actions/runs/42/attempts/1"
                ),
                provider_build_started_at=NOW - timedelta(minutes=2),
                provider_build_finished_at=NOW - timedelta(minutes=1),
                provider_run_updated_at=NOW,
                observed_at=NOW,
                temporal=build_temporal_metadata(
                    source_event_at=NOW - timedelta(minutes=1),
                    observed_at=NOW,
                    recorded_at=NOW,
                    source_time_trusted=True,
                    source_field=(
                        "docker_build_record.slsa.runDetails.metadata.finishedOn"
                    ),
                ),
                completeness=BuildArtifactEvidenceCompleteness.COMPLETE,
            )
        ],
        api_url="https://api.github.com",
    )
    entities = {item.id: item for item in snapshot.entities}

    def find(predicate: str, source_kind: str, target_kind: str) -> Relationship:
        return next(
            item
            for item in snapshot.relationships
            if item.relationship_type.value == predicate
            and entities[item.source_entity_id].kind == source_kind
            and entities[item.target_entity_id].kind == target_kind
        )

    repository_commit = find("contains", "GitRepository", "GitCommit")
    commit_run = find("triggers", "GitCommit", "GitHubWorkflowRun")
    run_image = find("produces", "GitHubWorkflowRun", "ContainerImage")
    workload_image = find("uses", "KubernetesDeployment", "ContainerImage")

    assert repository_commit.provenance is not None
    assert repository_commit.provenance.origin == RelationshipOrigin.OBSERVED
    assert commit_run.provenance is not None
    assert commit_run.provenance.origin == RelationshipOrigin.OBSERVED
    assert run_image.provenance is not None
    assert run_image.provenance.origin == RelationshipOrigin.OBSERVED
    assert run_image.confidence is None
    assert workload_image.provenance is not None
    assert workload_image.provenance.origin == RelationshipOrigin.DERIVED
    assert workload_image.confidence is None
    assert any(
        item.reference == digest
        for item in workload_image.provenance.source_references
    )


def test_runtime_network_edge_is_observed_with_native_references() -> None:
    submission = AgentSnapshotSubmission(
        submission_id="submission:runtime",
        collected_at=NOW.isoformat(),
        cluster_name="runtime",
        environment="test",
        namespace_scope=[],
        collector_version="1",
        inventory={
            "hosts": [{"id": "host-native", "name": "worker"}],
            "processes": [
                {
                    "pid": 321,
                    "name": "payment-api",
                    "host_id": "worker",
                    "create_time": "2026-08-23T12:00:00Z",
                }
            ],
            "network_connections": [
                {
                    "pid": 321,
                    "protocol": "tcp",
                    "remote_address": "10.10.0.5",
                    "remote_port": 5432,
                    "status": "ESTABLISHED",
                }
            ],
        },
        metadata={},
    )
    snapshot = enrich_runtime_inventory(
        snapshot=GraphSnapshot(
            snapshot_id="snapshot:runtime",
            collected_at=NOW,
            collector_name="test",
            collector_version="1",
            scope={},
            entities=[],
            relationships=[],
            evidence=[],
            metadata={},
        ),
        agent=SimpleNamespace(agent_id="agent:runtime"),
        submission=submission,
    )
    relationship = next(
        item
        for item in snapshot.relationships
        if item.relationship_type == RelationshipType.CALLS
    )

    assert relationship.provenance is not None
    assert relationship.provenance.origin == RelationshipOrigin.OBSERVED
    assert relationship.confidence is None
    assert any(
        item.reference == "10.10.0.5:5432"
        for item in relationship.provenance.source_references
    )


def test_tetragon_edge_references_real_runtime_dependency_record(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        runtime_snapshot_enrichment,
        "datetime",
        SimpleNamespace(
            now=lambda tz: NOW,
        ),
    )
    session = _session()
    session.add(
        RuntimeDependencyRecord(
            runtime_dependency_id="runtime-dependency:one",
            agent_id="agent:tetragon",
            sensor_id="sensor:one",
            cluster_name="production",
            node_name="worker-one",
            source_namespace="payments",
            source_pod_name="payment-api-abc",
            source_pod_uid="pod-native-uid",
            source_workload_name="payment-api",
            source_container_id="container-one",
            source_binary="/app/payment",
            source_pid=101,
            destination_name="payments-db",
            destination_address="10.20.0.7",
            destination_port=5432,
            protocol="tcp",
            direction="outbound",
            observation_count=8,
            success_count=7,
            failure_count=1,
            first_seen_at=(NOW - timedelta(minutes=5)).isoformat(),
            last_seen_at=NOW.isoformat(),
            metadata_json="{}",
            tenant_id=TEST_TENANT,
        )
    )
    session.commit()
    pod = Entity(
        id="k8s:production:pod:pod-native-uid",
        entity_type=EntityType.RUNTIME_INSTANCE,
        kind="KubernetesPod",
        name="payment-api-abc",
        source_system="kubernetes",
        external_id="pod-native-uid",
        observed_at=NOW,
        properties={
            "namespace": "payments",
            "cluster": "production",
        },
    )
    snapshot = enrich_snapshot_with_runtime_dependencies(
        session,
        agent=SimpleNamespace(
            agent_id="agent:tetragon",
            environment="production",
        ),
        snapshot=GraphSnapshot(
            snapshot_id="snapshot:tetragon",
            collected_at=NOW,
            collector_name="test",
            collector_version="1",
            scope={"cluster": "production"},
            entities=[pod],
            relationships=[],
            evidence=[],
            metadata={},
        ),
        window_minutes=30,
        tenant_id=TEST_TENANT,
    )
    relationship = next(
        item
        for item in snapshot.relationships
        if item.relationship_type == RelationshipType.CALLS
    )

    assert relationship.provenance is not None
    assert relationship.provenance.origin == RelationshipOrigin.OBSERVED
    assert relationship.confidence is None
    assert any(
        item.reference == "runtime-dependency:one"
        for item in relationship.provenance.source_references
    )


def test_cloud_relationship_uses_provider_native_references() -> None:
    submission = AgentSnapshotSubmission(
        submission_id="submission:aws",
        collected_at=NOW.isoformat(),
        cluster_name="aws",
        environment="test",
        namespace_scope=[],
        collector_version="1",
        inventory={
            "resources": [
                {
                    "provider": "aws",
                    "account_id": "123456789012",
                    "region": "us-east-1",
                    "resource_type": "aws_vpc",
                    "resource_id": "vpc-123",
                    "name": "vpc-123",
                    "tags": {},
                    "subnet_ids": [],
                    "properties": {},
                },
                {
                    "provider": "aws",
                    "account_id": "123456789012",
                    "region": "us-east-1",
                    "resource_type": "aws_subnet",
                    "resource_id": "subnet-123",
                    "name": "subnet-123",
                    "vpc_id": "vpc-123",
                    "tags": {},
                    "subnet_ids": [],
                    "properties": {},
                },
            ]
        },
        metadata={},
    )
    result = enrich_snapshot_with_aws(
        snapshot=GraphSnapshot(
            snapshot_id="snapshot:aws",
            collected_at=NOW,
            collector_name="test",
            collector_version="1",
            scope={},
            entities=[],
            relationships=[],
            evidence=[],
            metadata={},
        ),
        agent=SimpleNamespace(agent_id="agent:aws", environment="test"),
        submission=submission,
    )
    relationship = next(
        item
        for item in result.relationships
        if item.relationship_type == RelationshipType.CONTAINS
    )
    references = {
        item.reference
        for item in relationship.provenance.source_references
    }

    assert relationship.provenance is not None
    assert relationship.provenance.origin == RelationshipOrigin.DECLARED
    assert relationship.confidence is None
    assert {"vpc-123", "subnet-123"}.issubset(references)


def test_provenance_does_not_change_causal_adjacency_or_blast_traversal() -> None:
    legacy = _snapshot("snapshot:legacy", relationship=_relationship())
    enriched = _snapshot(
        "snapshot:enriched",
        relationship=_relationship(provenance=_provenance()),
    )

    assert _adjacency(legacy) == _adjacency(enriched)
    assert set(
        traverse_blast_radius(
            "entity:service",
            legacy.relationships,
            5,
        )
    ) == set(
        traverse_blast_radius(
            "entity:service",
            enriched.relationships,
            5,
        )
    )
    assert ALGORITHM_VERSION == "13c-causal-v1"


def test_machine_contract_matches_active_runtime_predicate_registry() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    documented = {
        item["predicate"]
        for item in contract["active_predicates"]
    }
    unused = set(contract["declared_but_not_constructed"])

    assert documented == set(ACTIVE_RELATIONSHIP_PREDICATES)
    assert documented.isdisjoint(unused)
    assert documented | unused == {
        item.value for item in RelationshipType
    }


def test_every_product_relationship_constructor_sets_provenance() -> None:
    constructor_files = [
        ROOT / "backend" / "app" / "collectors" / "kubernetes_collector.py",
        *[
            ROOT / "backend" / "app" / "services" / name
            for name in (
                "agent_azure_enrichment.py",
                "agent_cloud_enrichment.py",
                "agent_gcp_enrichment.py",
                "agent_runtime_enrichment.py",
                "agent_snapshot_ingest.py",
                "container_image_graph.py",
                "github_actions_graph.py",
                "github_actions_artifact_lineage.py",
                "github_graph.py",
                "network_topology_enricher.py",
                "runtime_snapshot_enrichment.py",
                "sample_topology.py",
            )
        ],
    ]

    for path in constructor_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Relationship"
        ]
        assert calls, path
        for call in calls:
            assert "provenance" in {
                keyword.arg for keyword in call.keywords
            }, f"{path}:{call.lineno}"


def test_relationship_linker_has_no_llm_or_fuzzy_matching() -> None:
    source = inspect.getsource(relationship_provenance).casefold()
    assert "openai" not in source
    assert "llm" not in source
    assert "fuzzy" not in source
    assert "embedding" not in source
