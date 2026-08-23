from __future__ import annotations

from datetime import datetime, timezone
import inspect
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.collectors.kubernetes_collector import KubernetesCollector
from app.db.database import Base
from app.db.models import (
    ChangeEntityLinkRecord,
    IncidentRecord,
    TopoAgentRecord,
    utc_now_iso,
)
from app.models.agents import AgentSnapshotSubmission
from app.models.canonical_identity import (
    CanonicalIdentityResolutionStatus,
)
from app.models.change_events import (
    ChangeEventCreate,
    ChangeEventEntityReference,
    ChangeEventKind,
    ChangeEventSource,
)
from app.models.signals import (
    NormalizedSignal,
    SignalCategory,
    SignalSeverity,
    SignalType,
)
from app.models.ownership import OwnershipMappingCreate
from app.models.topology import Entity, EntityType, GraphSnapshot
from app.repositories.change_event_repository import (
    ingest_change_event,
)
from app.repositories.snapshot_repository import load_snapshot, save_snapshot
from app.services.agent_snapshot_ingest import build_agent_snapshot
from app.services.blast_radius import calculate_blast_radius
from app.services.canonical_identity import (
    IDENTITY_VERSION,
    canonical_aws_identity,
    canonical_azure_identity,
    canonical_ci_build_identity,
    canonical_container_image_identity,
    canonical_gcp_identity,
    canonical_git_commit_identity,
    canonical_git_repository_identity,
    canonical_kubernetes_identity,
    resolve_snapshot_entity_identity,
)
from app.services.continuous_lifecycle import _entity_for_signal
from app.services.ownership_resolver import (
    create_ownership_mapping,
    resolve_entity_ownership,
)
import app.services.canonical_identity as canonical_identity_service
from app.services.network_topology_enricher import _entity_id as network_entity_id


NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def _snapshot(*entities: Entity, snapshot_id: str = "snapshot:identity") -> GraphSnapshot:
    return GraphSnapshot(
        snapshot_id=snapshot_id,
        collected_at=NOW,
        collector_name="identity-test",
        collector_version="1.0",
        scope={"cluster": "production", "environment": "production"},
        entities=list(entities),
    )


def _kubernetes_entity(
    *,
    cluster: str = "production",
    namespace: str = "payments",
    kind: str = "Pod",
    name: str = "payment-api-abcde",
    uid: str | None = None,
) -> Entity:
    identity = canonical_kubernetes_identity(
        cluster_name=cluster,
        kind=kind,
        name=name,
        namespace=namespace,
        uid=uid,
    )
    return Entity(
        id=identity.canonical_id,
        entity_type=EntityType.RUNTIME_INSTANCE,
        kind=f"Kubernetes{kind}",
        name=name,
        source_system="kubernetes",
        external_id=identity.source_native_id,
        aliases=identity.aliases,
        identity_version=identity.identity_version,
        environment="production",
        observed_at=NOW,
        properties={"cluster": cluster, "namespace": namespace},
    )


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_kubernetes_uid_identity_is_stable_across_name_change() -> None:
    first = canonical_kubernetes_identity(
        cluster_name="production",
        kind="Pod",
        name="payment-api-old",
        namespace="payments",
        uid="pod-uid-1",
    )
    second = canonical_kubernetes_identity(
        cluster_name="production",
        kind="KubernetesPod",
        name="payment-api-new",
        namespace="payments",
        uid="pod-uid-1",
    )

    assert first.canonical_id == second.canonical_id
    assert first.identity_version == second.identity_version == IDENTITY_VERSION


def test_uidless_kubernetes_identity_is_stable_and_fully_scoped() -> None:
    first = canonical_kubernetes_identity(
        cluster_name="production",
        kind="Service",
        name="payment-api",
        namespace="payments",
        uid=None,
    )
    second = canonical_kubernetes_identity(
        cluster_name="production",
        kind="KubernetesService",
        name="payment-api",
        namespace="payments",
        uid=None,
    )
    other_cluster = canonical_kubernetes_identity(
        cluster_name="staging",
        kind="Service",
        name="payment-api",
        namespace="payments",
        uid=None,
    )
    other_kind = canonical_kubernetes_identity(
        cluster_name="production",
        kind="Deployment",
        name="payment-api",
        namespace="payments",
        uid=None,
    )

    assert first.canonical_id == second.canonical_id
    assert first.canonical_id != other_cluster.canonical_id
    assert first.canonical_id != other_kind.canonical_id


def test_pod_and_owning_deployment_remain_separate_entities() -> None:
    pod = canonical_kubernetes_identity(
        cluster_name="production",
        kind="Pod",
        name="payment-api-abcde",
        namespace="payments",
        uid="pod-uid",
    )
    deployment = canonical_kubernetes_identity(
        cluster_name="production",
        kind="Deployment",
        name="payment-api",
        namespace="payments",
        uid="deployment-uid",
    )

    assert pod.canonical_id != deployment.canonical_id
    assert pod.entity_kind == "Pod"
    assert deployment.entity_kind == "Deployment"


def test_legacy_kubernetes_id_resolves_by_safe_alias() -> None:
    entity = _kubernetes_entity(uid=None)
    legacy_id = next(
        alias
        for alias in entity.aliases
        if alias.endswith(":payments:payment-api-abcde")
    )
    resolution = resolve_snapshot_entity_identity(
        _snapshot(entity),
        identifier=legacy_id,
        cluster_name="production",
        namespace="payments",
        kind="Pod",
    )

    assert resolution.status == CanonicalIdentityResolutionStatus.RESOLVED
    assert resolution.resolved_entity_id == entity.id
    assert resolution.resolved_canonical_id == entity.id
    assert resolution.matched_value == legacy_id


def test_ambiguous_alias_is_unresolved_instead_of_guessed() -> None:
    first = _kubernetes_entity(name="first", uid="uid-first")
    second = _kubernetes_entity(name="second", uid="uid-second")
    first = first.model_copy(update={"aliases": ["legacy:shared"]})
    second = second.model_copy(update={"aliases": ["legacy:shared"]})

    resolution = resolve_snapshot_entity_identity(
        _snapshot(first, second),
        identifier="legacy:shared",
        cluster_name="production",
        namespace="payments",
        kind="Pod",
    )

    assert resolution.status == CanonicalIdentityResolutionStatus.AMBIGUOUS
    assert resolution.resolved_entity_id is None
    assert resolution.candidate_entity_ids == sorted([first.id, second.id])


def test_resolution_does_not_use_fuzzy_name_matching() -> None:
    entity = _kubernetes_entity(name="checkout-api", uid=None)
    resolution = resolve_snapshot_entity_identity(
        _snapshot(entity),
        kind="Pod",
        name="checkout",
        cluster_name="production",
        namespace="payments",
    )

    assert resolution.status == CanonicalIdentityResolutionStatus.UNRESOLVED


def test_cloud_native_resource_identities_remain_stable() -> None:
    aws_one = canonical_aws_identity(
        account_id="123456789012",
        region="us-east-1",
        resource_type="aws_ec2_instance",
        resource_id="i-012345",
        arn="arn:aws:ec2:us-east-1:123456789012:instance/i-012345",
    )
    aws_two = canonical_aws_identity(
        account_id="123456789012",
        region="us-east-1",
        resource_type="aws_ec2_instance",
        resource_id="i-012345",
        arn="arn:aws:ec2:us-east-1:123456789012:instance/i-012345",
    )
    azure_one = canonical_azure_identity(
        subscription_id="sub-1",
        resource_type="azure_virtual_machine",
        resource_id="/SUBSCRIPTIONS/SUB-1/RESOURCEGROUPS/RG/PROVIDERS/MICROSOFT.COMPUTE/VIRTUALMACHINES/VM1/",
    )
    azure_two = canonical_azure_identity(
        subscription_id="sub-1",
        resource_type="azure_virtual_machine",
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
    )
    gcp_one = canonical_gcp_identity(
        project_id="project-1",
        resource_type="gcp_compute_instance",
        resource_id="//COMPUTE.GOOGLEAPIS.COM/PROJECTS/PROJECT-1/ZONES/US-CENTRAL1-A/INSTANCES/API-1/",
    )
    gcp_two = canonical_gcp_identity(
        project_id="project-1",
        resource_type="gcp_compute_instance",
        resource_id="//compute.googleapis.com/projects/project-1/zones/us-central1-a/instances/api-1",
    )

    assert aws_one.canonical_id == aws_two.canonical_id
    assert azure_one.canonical_id == azure_two.canonical_id
    assert gcp_one.canonical_id == gcp_two.canonical_id


def test_repository_commit_and_ci_build_scopes_prevent_collisions() -> None:
    repository_one = canonical_git_repository_identity(
        provider="github",
        api_url="https://api.github.com",
        repository_native_id="101",
        repository_name="acme/payments",
    )
    repository_two = canonical_git_repository_identity(
        provider="github",
        api_url="https://api.github.com",
        repository_native_id="202",
        repository_name="acme/checkout",
    )
    commit_one = canonical_git_commit_identity(
        repository_canonical_id=repository_one.canonical_id,
        commit_sha="a" * 40,
    )
    commit_two = canonical_git_commit_identity(
        repository_canonical_id=repository_two.canonical_id,
        commit_sha="a" * 40,
    )
    build_one = canonical_ci_build_identity(
        provider="jenkins",
        pipeline_scope="payments/deploy",
        native_build_id=718,
    )
    build_two = canonical_ci_build_identity(
        provider="jenkins",
        pipeline_scope="checkout/deploy",
        native_build_id=718,
    )

    assert repository_one.canonical_id != repository_two.canonical_id
    assert commit_one.canonical_id != commit_two.canonical_id
    assert build_one.canonical_id != build_two.canonical_id

    commit_entities = [
        Entity(
            id=identity.canonical_id,
            entity_type=EntityType.SOURCE_REVISION,
            kind="GitCommit",
            name=("a" * 12),
            source_system="github",
            external_id="a" * 40,
            aliases=identity.aliases,
            identity_version=identity.identity_version,
            observed_at=NOW,
        )
        for identity in (commit_one, commit_two)
    ]
    ambiguous = resolve_snapshot_entity_identity(
        _snapshot(*commit_entities),
        source_native_id="a" * 40,
        kind="GitCommit",
    )
    assert ambiguous.status == CanonicalIdentityResolutionStatus.AMBIGUOUS
    assert ambiguous.resolved_entity_id is None


def test_image_digest_identity_is_distinct_from_mutable_tag_identity() -> None:
    digest = canonical_container_image_identity(
        normalized_reference="registry.example.com/payments/api@sha256:" + "a" * 64,
        digest="sha256:" + "a" * 64,
    )
    tag = canonical_container_image_identity(
        normalized_reference="registry.example.com/payments/api:latest",
        digest=None,
    )

    assert digest.canonical_id != tag.canonical_id
    assert digest.strategy == "container_image_digest"
    assert tag.strategy == "container_image_mutable_reference"


def test_real_watcher_collector_and_snapshot_paths_share_uidless_identity() -> None:
    metadata = SimpleNamespace(
        name="payment-api-abcde",
        namespace="payments",
        uid=None,
    )
    collector = KubernetesCollector.__new__(KubernetesCollector)
    collector.connection = SimpleNamespace(cluster_name="production")
    direct_id = collector._entity_id("pod", metadata)
    enriched_id = network_entity_id(
        "production",
        "pod",
        None,
        "payments",
        "payment-api-abcde",
    )

    now = utc_now_iso()
    agent = TopoAgentRecord(
        agent_id="agent:identity-test",
        name="identity-test",
        agent_type="kubernetes",
        cluster_name="production",
        environment="production",
        version="1.0",
        token_hash="a" * 64,
        token_hint="test",
        status="online",
        collection_interval_seconds=300,
        heartbeat_interval_seconds=30,
        namespace_scope_json='["payments"]',
        capabilities_json="[]",
        labels_json="{}",
        metadata_json="{}",
        buffered_item_count=0,
        enrolled_at=now,
        created_at=now,
        updated_at=now,
    )
    submission = AgentSnapshotSubmission(
        submission_id="submission:identity-test",
        collected_at=NOW.isoformat(),
        cluster_name="production",
        environment="production",
        namespace_scope=["payments"],
        collector_version="1.0",
        inventory={
            "pods": [
                {
                    "uid": None,
                    "name": "payment-api-abcde",
                    "namespace": "payments",
                    "labels": {"app": "payment-api"},
                    "owner_references": [],
                    "containers": [],
                    "container_ids": [],
                }
            ]
        },
    )
    snapshot = build_agent_snapshot(agent=agent, submission=submission)
    pod = next(entity for entity in snapshot.entities if entity.kind == "KubernetesPod")
    signal = NormalizedSignal(
        signal_id="signal:watcher-identity",
        fingerprint="watcher-identity",
        signal_type=SignalType.KUBERNETES_EVENT,
        severity=SignalSeverity.ERROR,
        category=SignalCategory.HEALTH,
        source_system="kubernetes",
        title="BackOff on Pod/payment-api-abcde",
        summary="Watcher observed a UID-less Pod failure.",
        reason="BackOff",
        first_observed_at=NOW,
        last_observed_at=NOW,
        cluster_name="production",
        namespace="payments",
        involved_object_kind="Pod",
        involved_object_name="payment-api-abcde",
    )

    assert pod.id == direct_id == enriched_id
    assert _entity_for_signal(snapshot, signal).id == pod.id


def test_identity_resolution_is_deterministic_and_has_no_llm_or_fuzzy_dependency() -> None:
    entity = _kubernetes_entity(uid=None)
    snapshot = _snapshot(entity)
    first = resolve_snapshot_entity_identity(
        snapshot,
        identifier=entity.aliases[0],
        kind="Pod",
        cluster_name="production",
        namespace="payments",
    )
    second = resolve_snapshot_entity_identity(
        snapshot,
        identifier=entity.aliases[0],
        kind="Pod",
        cluster_name="production",
        namespace="payments",
    )
    source = inspect.getsource(canonical_identity_service).casefold()

    assert first.model_dump() == second.model_dump()
    assert first.identity_version == IDENTITY_VERSION
    assert "openai" not in source
    assert "llm" not in source
    assert "sequencematcher" not in source
    assert "difflib" not in source


def test_snapshot_history_incident_change_and_blast_compatibility() -> None:
    session = _session()
    try:
        canonical = _kubernetes_entity(name="payment-api", kind="Service", uid=None)
        legacy_id = next(
            alias
            for alias in canonical.aliases
            if alias.endswith(":payments:payment-api")
        )
        legacy = canonical.model_copy(
            update={
                "id": legacy_id,
                "aliases": [],
                "identity_version": "legacy",
            }
        )
        historical = _snapshot(legacy, snapshot_id="snapshot:legacy-identity")
        save_snapshot(session, historical)
        loaded = load_snapshot(session, historical.snapshot_id)
        assert loaded is not None
        assert loaded.entities[0].id == legacy_id
        assert loaded.entities[0].identity_version == "legacy"
        historical_resolution = resolve_snapshot_entity_identity(
            loaded,
            identifier=canonical.id,
            kind="Service",
            cluster_name="production",
            namespace="payments",
        )
        assert historical_resolution.status == CanonicalIdentityResolutionStatus.RESOLVED
        assert historical_resolution.resolved_entity_id == legacy_id

        create_ownership_mapping(
            session,
            OwnershipMappingCreate(
                entity_id=legacy_id,
                owner_team="Payments Platform",
            ),
        )
        ownership = resolve_entity_ownership(
            session,
            _snapshot(canonical, snapshot_id="snapshot:ownership-alias"),
            canonical,
        )
        assert ownership.resolved is True
        assert ownership.owner_team == "Payments Platform"

        now = utc_now_iso()
        session.add(
            IncidentRecord(
                incident_id="incident:legacy-identity",
                fingerprint="fingerprint:legacy-identity",
                status="open",
                severity="error",
                title="Historical payment incident",
                summary="Historical entity IDs remain authoritative.",
                cluster_name="production",
                namespace="payments",
                primary_signal_id="signal:legacy-identity",
                topology_snapshot_id=historical.snapshot_id,
                affected_entity_id=legacy_id,
                affected_object_kind="Service",
                affected_object_name="payment-api",
                first_observed_at=NOW.isoformat(),
                last_observed_at=NOW.isoformat(),
                recommendation_count=0,
                occurrence_count=1,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

        blast = calculate_blast_radius(session, "incident:legacy-identity")
        assert blast.root_entity_id == legacy_id
        assert blast.affected_entity_count == 1

        current = _snapshot(canonical, snapshot_id="snapshot:canonical-identity")
        save_snapshot(session, current)
        receipt = ingest_change_event(
            session,
            request=ChangeEventCreate(
                source=ChangeEventSource.KUBERNETES,
                kind=ChangeEventKind.CONFIGURATION,
                title="Service annotation changed",
                occurred_at=NOW.isoformat(),
                cluster_name="production",
                namespace="payments",
                entity_refs=[
                    ChangeEventEntityReference(
                        entity_id=legacy_id,
                        kind="Service",
                        name="payment-api",
                        namespace="payments",
                        cluster_name="production",
                    )
                ],
            ),
            auto_correlate=True,
            correlation_snapshot_id=current.snapshot_id,
        )
        links = list(
            session.scalars(
                select(ChangeEntityLinkRecord).where(
                    ChangeEntityLinkRecord.event_id == receipt.event_id
                )
            ).all()
        )
        assert receipt.linked_entity_count == 1
        assert [link.entity_id for link in links] == [canonical.id]
    finally:
        session.close()
