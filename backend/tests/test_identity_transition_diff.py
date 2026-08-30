from __future__ import annotations
from domain_tenant_fixtures import TEST_TENANT, seed_domain_tenant

import inspect
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import ChangeEventRecord, ChangeRecord
from app.models.lifecycle_automation import TopologyCheckpointReason
from app.models.topology import (
    Entity,
    EntityType,
    GraphSnapshot,
    Relationship,
    RelationshipType,
)
from app.services.canonical_identity import (
    canonical_kubernetes_identity,
)
from app.services.change_normalizer import normalize_snapshot_changes
from app.services.snapshot_diff import compare_snapshots
from app.services.topology_checkpoint import persist_topology_checkpoint

NOW = datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)
CLUSTER = "production"
NAMESPACE = "payments"


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine)
    return Session(engine)


def _count(session: Session, model) -> int:
    return int(
        session.scalar(select(func.count()).select_from(model))
        or 0
    )


def _entity(
    *,
    kind: str,
    name: str,
    legacy: bool,
    observed_at: datetime,
    image: str | None = None,
    entity_id_override: str | None = None,
) -> Entity:
    identity = canonical_kubernetes_identity(
        cluster_name=CLUSTER,
        kind=kind,
        name=name,
        namespace=NAMESPACE,
        uid=None,
    )
    kind_token = kind.removeprefix("Kubernetes").lower()
    entity_id = (
        entity_id_override
        or (
            f"k8s:{CLUSTER}:{kind_token}:{NAMESPACE}:{name}"
            if legacy
            else identity.canonical_id
        )
    )
    properties: dict[str, object] = {
        "cluster": CLUSTER,
        "namespace": NAMESPACE,
    }
    if image is not None:
        properties["containers"] = [
            {"name": "payment", "image": image}
        ]

    return Entity(
        id=entity_id,
        entity_type=(
            EntityType.WORKLOAD
            if kind == "KubernetesDeployment"
            else EntityType.NETWORK
        ),
        kind=kind,
        name=name,
        source_system="kubernetes",
        external_id=None,
        aliases=[] if legacy else identity.aliases,
        identity_version="legacy" if legacy else "v1",
        environment="production",
        observed_at=observed_at,
        properties=properties,
    )


def _snapshot(
    snapshot_id: str,
    *,
    legacy: bool,
    observed_at: datetime,
    image: str = "registry.example/payment:v1",
    include_deployment: bool = True,
    include_service: bool = True,
    duplicate_legacy_deployment: bool = False,
) -> GraphSnapshot:
    entities: list[Entity] = []
    if include_deployment:
        entities.append(
            _entity(
                kind="KubernetesDeployment",
                name="payment-api",
                legacy=legacy,
                observed_at=observed_at,
                image=image,
            )
        )
        if duplicate_legacy_deployment:
            entities.append(
                _entity(
                    kind="KubernetesDeployment",
                    name="payment-api",
                    legacy=True,
                    observed_at=observed_at,
                    image=image,
                    entity_id_override="legacy:duplicate:payment-api",
                )
            )
    if include_service:
        entities.append(
            _entity(
                kind="KubernetesService",
                name="payment-api",
                legacy=legacy,
                observed_at=observed_at,
            )
        )

    relationships: list[Relationship] = []
    if include_deployment and include_service:
        deployment = next(
            entity
            for entity in entities
            if entity.kind == "KubernetesDeployment"
        )
        service = next(
            entity
            for entity in entities
            if entity.kind == "KubernetesService"
        )
        relationships.append(
            Relationship(
                id=(
                    "relationship:legacy:selects"
                    if legacy
                    else "relationship:v1:selects"
                ),
                source_entity_id=service.id,
                target_entity_id=deployment.id,
                relationship_type=RelationshipType.SELECTS,
                source_system="kubernetes",
                observed_at=observed_at,
                properties={"selector": {"app": "payment-api"}},
            )
        )

    return GraphSnapshot(
        snapshot_id=snapshot_id,
        collected_at=observed_at,
        collector_name="identity-transition-test",
        collector_version="1.0",
        scope={"cluster": CLUSTER, "namespace": NAMESPACE},
        entities=entities,
        relationships=relationships,
        evidence=[],
        metadata={},
    )


def test_identity_version_only_transition_has_no_entity_or_edge_churn() -> None:
    before = _snapshot(
        "snapshot:legacy",
        legacy=True,
        observed_at=NOW,
    )
    after = _snapshot(
        "snapshot:v1",
        legacy=False,
        observed_at=NOW + timedelta(minutes=1),
    )

    result = compare_snapshots(before, after)

    assert result.summary == {
        "added_entities": 0,
        "removed_entities": 0,
        "changed_entities": 0,
        "added_relationships": 0,
        "removed_relationships": 0,
        "changed_relationships": 0,
    }


def test_material_update_survives_legacy_to_v1_alignment() -> None:
    before = _snapshot(
        "snapshot:legacy",
        legacy=True,
        observed_at=NOW,
        image="registry.example/payment:v1",
    )
    after = _snapshot(
        "snapshot:v1",
        legacy=False,
        observed_at=NOW + timedelta(minutes=1),
        image="registry.example/payment:v2",
    )

    result = compare_snapshots(before, after)
    changes = normalize_snapshot_changes(before, after)

    assert result.summary["added_entities"] == 0
    assert result.summary["removed_entities"] == 0
    assert result.summary["changed_entities"] == 1
    assert len(changes) == 1
    assert changes[0].change_type.value == "entity_updated"
    assert "properties.containers" in changes[0].changed_fields
    assert changes[0].entity_id.startswith(
        "k8s:production:deployment:"
    )


def test_genuine_entity_creation_and_removal_are_preserved() -> None:
    removed = compare_snapshots(
        _snapshot(
            "snapshot:before-removal",
            legacy=True,
            observed_at=NOW,
        ),
        _snapshot(
            "snapshot:after-removal",
            legacy=False,
            observed_at=NOW + timedelta(minutes=1),
            include_service=False,
        ),
    )
    created = compare_snapshots(
        _snapshot(
            "snapshot:before-addition",
            legacy=True,
            observed_at=NOW,
            include_service=False,
        ),
        _snapshot(
            "snapshot:after-addition",
            legacy=False,
            observed_at=NOW + timedelta(minutes=1),
        ),
    )

    assert [entity.kind for entity in removed.removed_entities] == [
        "KubernetesService"
    ]
    assert [entity.kind for entity in created.added_entities] == [
        "KubernetesService"
    ]


def test_ambiguous_legacy_identity_is_not_silently_merged() -> None:
    before = _snapshot(
        "snapshot:ambiguous-legacy",
        legacy=True,
        observed_at=NOW,
        include_service=False,
        duplicate_legacy_deployment=True,
    )
    after = _snapshot(
        "snapshot:one-v1",
        legacy=False,
        observed_at=NOW + timedelta(minutes=1),
        include_service=False,
    )

    result = compare_snapshots(before, after)

    assert len(result.removed_entities) == 2
    assert len(result.added_entities) == 1
    assert result.changed_entities == []


def test_diff_alignment_is_scoped_to_the_two_supplied_snapshots() -> None:
    before = _snapshot(
        "snapshot:production",
        legacy=True,
        observed_at=NOW,
        include_service=False,
    )
    after_entity = _entity(
        kind="KubernetesDeployment",
        name="payment-api",
        legacy=False,
        observed_at=NOW + timedelta(minutes=1),
        image="registry.example/payment:v1",
    )
    other_cluster_identity = canonical_kubernetes_identity(
        cluster_name="disaster-recovery",
        kind="KubernetesDeployment",
        name="payment-api",
        namespace=NAMESPACE,
        uid=None,
    )
    after_entity.id = other_cluster_identity.canonical_id
    after_entity.aliases = other_cluster_identity.aliases
    after_entity.properties["cluster"] = "disaster-recovery"
    after = GraphSnapshot(
        snapshot_id="snapshot:other-cluster",
        collected_at=NOW + timedelta(minutes=1),
        collector_name="identity-transition-test",
        collector_version="1.0",
        scope={
            "cluster": "disaster-recovery",
            "namespace": NAMESPACE,
        },
        entities=[after_entity],
        relationships=[],
        evidence=[],
        metadata={},
    )

    result = compare_snapshots(before, after)
    source = inspect.getsource(compare_snapshots)

    assert len(result.removed_entities) == 1
    assert len(result.added_entities) == 1
    assert "latest" not in source.casefold()
    assert "repository" not in source.casefold()


def test_identity_only_checkpoint_creates_no_change_record_or_event() -> None:
    session = _session()
    persist_topology_checkpoint(
        session,
        snapshot=_snapshot(
            "snapshot:legacy-checkpoint",
            legacy=True,
            observed_at=NOW,
        ),
        reason=TopologyCheckpointReason.PERIODIC_RECONCILE,
        tenant_id=TEST_TENANT,
    )
    result = persist_topology_checkpoint(
        session,
        snapshot=_snapshot(
            "snapshot:v1-checkpoint",
            legacy=False,
            observed_at=NOW + timedelta(minutes=1),
        ),
        reason=TopologyCheckpointReason.AUTOMATIC_CHANGE,
        tenant_id=TEST_TENANT,
    )

    assert result.created is True
    assert result.detected_change_count == 0
    assert _count(session, ChangeRecord) == 0
    assert _count(session, ChangeEventRecord) == 0


def test_material_transition_reaches_durable_change_intelligence() -> None:
    session = _session()
    persist_topology_checkpoint(
        session,
        snapshot=_snapshot(
            "snapshot:legacy-material",
            legacy=True,
            observed_at=NOW,
            image="registry.example/payment:v1",
        ),
        reason=TopologyCheckpointReason.PERIODIC_RECONCILE,
        tenant_id=TEST_TENANT,
    )
    result = persist_topology_checkpoint(
        session,
        snapshot=_snapshot(
            "snapshot:v1-material",
            legacy=False,
            observed_at=NOW + timedelta(minutes=1),
            image="registry.example/payment:v2",
        ),
        reason=TopologyCheckpointReason.AUTOMATIC_CHANGE,
        tenant_id=TEST_TENANT,
    )

    records = list(session.scalars(select(ChangeRecord)).all())
    events = list(session.scalars(select(ChangeEventRecord)).all())

    assert result.detected_change_count == 1
    assert len(records) == 1
    assert records[0].change_type == "entity_updated"
    assert len(events) == 1
    assert events[0].source == "topology_diff"
