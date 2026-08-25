from __future__ import annotations

import inspect
import math
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import ChangeEventRecord, IncidentRecord, SnapshotRecord
from app.models.build_artifacts import (
    BuildArtifactEvidence,
    BuildArtifactEvidenceCompleteness,
    BuildArtifactEvidenceType,
    BuildArtifactType,
)
from app.models.causal_candidates import (
    CAUSAL_CANDIDATE_ADMISSION_POLICY_VERSION,
    CAUSAL_CANDIDATE_POLICY_VERSION,
    CandidateAdmissionBasis,
    LineageAdmissionReason,
    LineageAdmissionState,
)
from app.models.causal_rca import CausalAnalysisRequest, CausalAnalysisResponse
from app.models.change_events import (
    ChangeEventCreate,
    ChangeEventKind,
    ChangeEventSource,
)
from app.models.signals import (
    NormalizedSignal,
    SignalCategory,
    SignalSeverity,
    SignalType,
)
from app.models.source_file_mutations import (
    SourceFileCaptureState,
    SourceFileChangeType,
    SourceFileEvidenceCompleteness,
    SourceFileIdentityState,
    SourceFileMutationEnrichment,
    SourceFileMutationEvidence,
    SourceFileMutationSide,
    SourceFileParentContext,
    SourceFileParentContextType,
    SourceRepositoryIdentity,
)
from app.models.temporal import TimeOrigin, TimeQuality
from app.models.topology import (
    Entity,
    EntityType,
    GraphSnapshot,
    Relationship,
    RelationshipOrigin,
    RelationshipProvenanceCompleteness,
    RelationshipType,
)
from app.repositories.build_artifact_evidence_repository import (
    save_build_artifact_evidence,
)
from app.repositories.causal_analysis_repository import latest_causal_analysis
from app.repositories.change_event_repository import ingest_change_event
from app.repositories.signal_repository import save_signals
from app.repositories.snapshot_repository import save_snapshot
from app.services.causal_rca import analyze_causal_rca
from app.services.container_image_graph import (
    augment_snapshot_with_container_images,
)
from app.services.container_image_identity import (
    normalize_regular_container_images,
)
from app.services.incident_change_analysis import analyze_incident_change_events
from app.services.lineage_candidate_admission import (
    MAX_PROVIDER_PATHS_PER_ARTIFACT,
    evaluate_lineage_candidate_admission,
)
from app.services.relationship_provenance import (
    relationship_provenance,
    source_reference,
)
from app.services.temporal_semantics import build_temporal_metadata


INCIDENT_TIME = datetime(2026, 7, 20, 18, 0, tzinfo=timezone.utc)
SOURCE_TIME = INCIDENT_TIME - timedelta(minutes=600)
PROVIDER_TIME = SOURCE_TIME + timedelta(minutes=5)
DIGEST = "sha256:" + "a" * 64
OTHER_DIGEST = "sha256:" + "b" * 64
REPOSITORY = "acme/runtime"
REPOSITORY_ID = "9001"
REVISION = "c" * 40
OTHER_REVISION = "d" * 40


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _entity(
    entity_id: str,
    kind: str,
    *,
    properties: dict | None = None,
    external_id: str | None = None,
) -> Entity:
    entity_type = {
        "KubernetesPod": EntityType.RUNTIME_INSTANCE,
        "KubernetesReplicaSet": EntityType.WORKLOAD,
        "KubernetesDeployment": EntityType.WORKLOAD,
        "ContainerImage": EntityType.ARTIFACT,
    }[kind]
    return Entity(
        id=entity_id,
        entity_type=entity_type,
        kind=kind,
        name=entity_id.rsplit(":", 1)[-1],
        source_system=(
            "container-registry" if kind == "ContainerImage" else "kubernetes"
        ),
        external_id=external_id,
        identity_version="canonical-identity-v1",
        observed_at=INCIDENT_TIME,
        properties=properties or {},
    )


def _relationship(
    relationship_id: str,
    source: str,
    target: str,
    predicate: RelationshipType,
    *,
    trusted: bool = True,
    origin: RelationshipOrigin | None = None,
    container_name: str | None = None,
) -> Relationship:
    if predicate in {RelationshipType.OWNS, RelationshipType.RUNS}:
        component = "backend.app.collectors.kubernetes_collector"
        references = [
            source_reference(
                reference_type="kubernetes_owner_reference_uid",
                reference=f"uid:{target}",
                source_system="kubernetes",
            )
        ]
        resolved_origin = origin or RelationshipOrigin.DECLARED
    else:
        component = "backend.app.services.container_image_graph"
        references = [
            source_reference(
                reference_type="container_image_reference",
                reference=f"ghcr.io/{REPOSITORY}@{DIGEST}",
                source_system="kubernetes",
                attributes={"container_name": container_name},
            ),
            source_reference(
                reference_type="container_image_digest",
                reference=(DIGEST if target == "image:app" else OTHER_DIGEST),
                source_system="kubernetes",
            ),
        ]
        resolved_origin = origin or RelationshipOrigin.DERIVED
    provenance = relationship_provenance(
        predicate=predicate,
        origin=resolved_origin,
        source_component=component,
        source_references=references,
        completeness=(
            RelationshipProvenanceCompleteness.COMPLETE
            if trusted
            else RelationshipProvenanceCompleteness.PARTIAL
        ),
        linker_version="test:v1",
    )
    return Relationship(
        id=relationship_id,
        source_entity_id=source,
        target_entity_id=target,
        relationship_type=predicate,
        source_system="kubernetes",
        observed_at=INCIDENT_TIME,
        provenance=provenance,
        properties=(
            {
                "container_name": container_name,
                "requested_image": (
                    f"ghcr.io/{REPOSITORY}@{DIGEST}"
                    if target == "image:app"
                    else f"ghcr.io/acme/sidecar@{OTHER_DIGEST}"
                ),
            }
            if container_name
            else {}
        ),
    )


def _snapshot(
    *,
    snapshot_id: str = "snapshot:pinned",
    containers: tuple[str, ...] = ("app",),
    trusted: bool = True,
    immutable: bool = True,
    include_owners: bool = True,
    include_workload_use: bool = True,
) -> GraphSnapshot:
    entities = [
        _entity("deployment:app", "KubernetesDeployment"),
        _entity("replicaset:app", "KubernetesReplicaSet"),
        _entity("pod:app", "KubernetesPod"),
        _entity(
            "image:app",
            "ContainerImage",
            external_id=DIGEST if immutable else "ghcr.io/acme/runtime:latest",
            properties={
                "registry": "ghcr.io",
                "repository": REPOSITORY,
                "digest": DIGEST if immutable else None,
                "immutable": immutable,
                "requested_references": [f"ghcr.io/{REPOSITORY}:fixture"],
            },
        ),
    ]
    relationships: list[Relationship] = []
    if include_owners:
        relationships.extend(
            [
                _relationship(
                    "rel:deployment-rs",
                    "deployment:app",
                    "replicaset:app",
                    RelationshipType.OWNS,
                    trusted=trusted,
                ),
                _relationship(
                    "rel:rs-pod",
                    "replicaset:app",
                    "pod:app",
                    RelationshipType.RUNS,
                    trusted=trusted,
                ),
            ]
        )
    for index, container in enumerate(containers):
        image_id = "image:app" if container == "app" else f"image:sidecar:{index}"
        if container != "app":
            image_id = f"image:sidecar:{index}"
            entities.append(
                _entity(
                    image_id,
                    "ContainerImage",
                    external_id=OTHER_DIGEST,
                    properties={
                        "registry": "ghcr.io",
                        "repository": f"acme/sidecar-{index}",
                        "digest": OTHER_DIGEST,
                        "immutable": True,
                        "requested_references": [
                            f"ghcr.io/acme/sidecar-{index}:fixture"
                        ],
                    },
                )
            )
        relationships.append(
            _relationship(
                f"rel:pod-image:{container}",
                "pod:app",
                image_id,
                RelationshipType.USES,
                trusted=trusted,
                container_name=container,
            )
        )
        if include_workload_use:
            relationships.append(
                _relationship(
                    f"rel:deployment-image:{container}",
                    "deployment:app",
                    image_id,
                    RelationshipType.USES,
                    trusted=trusted,
                    container_name=container,
                )
            )
    return GraphSnapshot(
        snapshot_id=snapshot_id,
        collected_at=INCIDENT_TIME,
        collector_name="sc2-test",
        collector_version="1",
        scope={"cluster": "prod", "namespace": "payments"},
        entities=entities,
        relationships=relationships,
    )


def _mutation(index: int = 0, *, completeness="complete") -> dict:
    path = f"config/mode-{index}.txt"
    repository = SourceRepositoryIdentity(
        provider="github",
        provider_repository_id=REPOSITORY_ID,
        full_name=REPOSITORY,
    )
    before = SourceFileMutationSide(
        identity_state=SourceFileIdentityState.PRESENT,
        path=path,
        provider_blob_oid="1" * 40,
        provider_blob_source="github_rest_api",
        content_sha256="1" * 64,
        size_bytes=4,
        content_capture_state=SourceFileCaptureState.CAPTURED,
        semantic_value="old",
        semantic_capture_state=SourceFileCaptureState.CAPTURED,
    )
    after = SourceFileMutationSide(
        identity_state=SourceFileIdentityState.PRESENT,
        path=path,
        provider_blob_oid="2" * 40,
        provider_blob_source="github_rest_api",
        content_sha256="2" * 64,
        size_bytes=4,
        content_capture_state=SourceFileCaptureState.CAPTURED,
        semantic_value="new",
        semantic_capture_state=SourceFileCaptureState.CAPTURED,
    )
    return SourceFileMutationEvidence(
        mutation_id="source-file-mutation:" + f"{index + 1:040x}",
        provider="github",
        repository=repository,
        commit_sha=REVISION,
        parent_context=SourceFileParentContext(
            context_type=SourceFileParentContextType.SINGLE_PARENT,
            parent_shas=["e" * 40],
        ),
        change_type=SourceFileChangeType.MODIFIED,
        provider_status="modified",
        current_path=path,
        before=before,
        after=after,
        completeness=SourceFileEvidenceCompleteness(completeness),
    ).model_dump(mode="json")


def _source_metadata(
    *,
    mutations: int = 1,
    completeness: SourceFileEvidenceCompleteness = (
        SourceFileEvidenceCompleteness.COMPLETE
    ),
) -> dict:
    repository = SourceRepositoryIdentity(
        provider="github",
        provider_repository_id=REPOSITORY_ID,
        full_name=REPOSITORY,
    )
    capture = SourceFileMutationEnrichment(
        provider="github",
        repository=repository,
        completeness=completeness,
        requested_commit_count=1,
        enriched_commit_count=1,
        mutation_count=mutations,
    )
    return {
        "source_file_mutation_enrichment": capture.model_dump(mode="json"),
        "source_file_mutations": [_mutation(index) for index in range(mutations)],
    }


def _add_source_change(
    session: Session,
    *,
    occurred_at: datetime = SOURCE_TIME,
    revision: str = REVISION,
    repository: str = REPOSITORY,
    metadata: dict | None = None,
) -> str:
    receipt = ingest_change_event(
        session,
        request=ChangeEventCreate(
            source=ChangeEventSource.GITHUB,
            kind=ChangeEventKind.CODE,
            external_id=f"github:{repository}:{revision}",
            title="Provider-authentic source revision",
            occurred_at=occurred_at.isoformat(),
            repository=repository,
            commit_sha=revision,
            risk_score=20,
            metadata=metadata if metadata is not None else _source_metadata(),
        ),
        auto_correlate=False,
        source_time_trusted=True,
        observed_at=(occurred_at + timedelta(minutes=1)).isoformat(),
    )
    return receipt.event_id


def _add_provider(
    session: Session,
    *,
    evidence_index: int = 1,
    revision: str = REVISION,
    digest: str = DIGEST,
    repository: str = REPOSITORY,
    repository_id: str = REPOSITORY_ID,
    effective_at: datetime = PROVIDER_TIME,
    observed_at: datetime = INCIDENT_TIME + timedelta(hours=2),
    completeness: BuildArtifactEvidenceCompleteness = (
        BuildArtifactEvidenceCompleteness.COMPLETE
    ),
) -> None:
    temporal = build_temporal_metadata(
        source_event_at=effective_at,
        observed_at=observed_at,
        recorded_at=observed_at + timedelta(minutes=1),
        source_time_trusted=True,
        source_field="provider.build.finished_at",
        source_origin=TimeOrigin.SOURCE_REPORTED,
        source_quality=TimeQuality.EXACT,
    )
    save_build_artifact_evidence(
        session,
        evidence=BuildArtifactEvidence(
            evidence_id=f"build-artifact-evidence:{evidence_index:040x}",
            provider="github_actions",
            repository_id=repository_id,
            repository=repository,
            run_id=str(100 + evidence_index),
            run_attempt=1,
            commit_sha=revision,
            artifact_type=BuildArtifactType.CONTAINER_IMAGE,
            image_repository=f"ghcr.io/{repository}",
            image_reference=f"ghcr.io/{repository}:fixture",
            image_digest=digest,
            immutable_image_ref=f"ghcr.io/{repository}@{digest}",
            provider_evidence_type=(
                BuildArtifactEvidenceType.GITHUB_ACTIONS_DOCKER_BUILD_RECORD
            ),
            provider_evidence_id=str(500 + evidence_index),
            provider_evidence_reference=(
                f"https://api.github.com/repos/{repository}/actions/artifacts/"
                f"{500 + evidence_index}"
            ),
            provider_evidence_digest="sha256:" + "3" * 64,
            provider_build_record_digest="sha256:" + "4" * 64,
            provider_builder_id=(
                f"https://github.com/{repository}/actions/runs/"
                f"{100 + evidence_index}/attempts/1"
            ),
            provider_run_updated_at=effective_at,
            observed_at=observed_at,
            temporal=temporal,
            completeness=completeness,
        ),
    )


def _world(
    *,
    snapshot: GraphSnapshot | None = None,
    failing_container: str | None = "app",
    include_provider: bool = True,
    include_source: bool = True,
    source_time: datetime = SOURCE_TIME,
    mutation_count: int = 1,
) -> tuple[Session, str | None]:
    session = _session()
    pinned = snapshot or _snapshot()
    save_snapshot(session, pinned)
    signal = NormalizedSignal(
        signal_id="signal:failure",
        fingerprint="signal-fingerprint",
        signal_type=SignalType.KUBERNETES_EVENT,
        severity=SignalSeverity.ERROR,
        category=SignalCategory.HEALTH,
        source_system="kubernetes",
        title="Container failed",
        summary="Pinned workload failure",
        reason="CrashLoopBackOff",
        first_observed_at=INCIDENT_TIME,
        last_observed_at=INCIDENT_TIME,
        cluster_name="prod",
        namespace="payments",
        topology_snapshot_id=pinned.snapshot_id,
        involved_entity_id="pod:app",
        involved_object_uid="pod-uid",
        involved_object_kind="Pod",
        involved_object_name="app-pod",
        attributes=(
            {"field_path": f"spec.containers{{{failing_container}}}"}
            if failing_container is not None
            else {}
        ),
    )
    save_signals(session, [signal])
    session.add(
        IncidentRecord(
            incident_id="incident:sc2",
            fingerprint="incident-fingerprint",
            status="investigating",
            severity="error",
            title="SC-2 contract incident",
            summary="Exact immutable lineage fixture",
            cluster_name="prod",
            namespace="payments",
            primary_signal_id=signal.signal_id,
            latest_signal_id=signal.signal_id,
            topology_snapshot_id=pinned.snapshot_id,
            affected_entity_id="pod:app",
            affected_object_kind="Pod",
            affected_object_name="app-pod",
            first_observed_at=INCIDENT_TIME.isoformat(),
            last_observed_at=INCIDENT_TIME.isoformat(),
            created_at=INCIDENT_TIME.isoformat(),
            updated_at=INCIDENT_TIME.isoformat(),
        )
    )
    session.commit()
    event_id = None
    if include_source:
        event_id = _add_source_change(
            session,
            occurred_at=source_time,
            metadata=_source_metadata(mutations=mutation_count),
        )
    if include_provider:
        _add_provider(session)
    return session, event_id


def _analysis(session: Session):
    return analyze_incident_change_events(
        session,
        incident_id="incident:sc2",
        lookback_minutes=180,
    )


def test_lineage_1_shaped_old_revision_is_admitted_once_without_time_rewrite():
    session, event_id = _world()
    result = _analysis(session)
    assert [item.event.event_id for item in result.candidates] == [event_id]
    candidate = result.candidates[0]
    assert candidate.admission_basis == [
        CandidateAdmissionBasis.EXACT_IMMUTABLE_LINEAGE
    ]
    assert candidate.event.temporal.effective_at == SOURCE_TIME
    assert candidate.minutes_before_incident == 600
    assert len(candidate.mutation_set) == 1
    assert candidate.score == round(40 * math.exp(-10) + 20 * 0.09, 2)


def test_recent_temporal_path_is_unchanged_and_dual_admission_deduplicates():
    recent = INCIDENT_TIME - timedelta(minutes=90)
    session, event_id = _world(source_time=recent, include_provider=False)
    _add_provider(session, effective_at=recent + timedelta(minutes=1))
    result = _analysis(session)
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.event.event_id == event_id
    assert candidate.admission_basis == [
        CandidateAdmissionBasis.TEMPORAL,
        CandidateAdmissionBasis.EXACT_IMMUTABLE_LINEAGE,
    ]
    assert candidate.score == round(40 * math.exp(-1.5) + 20 * 0.09, 2)


def test_old_change_without_exact_lineage_stays_excluded():
    session, _event_id = _world(include_provider=False)
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.IMAGE_TO_RUN_MISSING
    )


def test_no_source_age_cutoff_for_exact_lineage():
    session, event_id = _world(source_time=INCIDENT_TIME - timedelta(days=120))
    result = _analysis(session)
    assert [item.event.event_id for item in result.candidates] == [event_id]
    assert result.candidates[0].minutes_before_incident == 172800


def test_distractor_remains_temporal_and_is_not_forced_below_lineage_candidate():
    session, lineage_id = _world()
    distractor_id = _add_source_change(
        session,
        occurred_at=INCIDENT_TIME - timedelta(minutes=5),
        revision=OTHER_REVISION,
        repository="other/repository",
        metadata={},
    )
    result = _analysis(session)
    assert {item.event.event_id for item in result.candidates} == {
        lineage_id,
        distractor_id,
    }
    assert result.candidates[0].event.event_id == distractor_id
    assert result.candidates[0].admission_basis == [CandidateAdmissionBasis.TEMPORAL]


def test_multi_file_revision_is_one_candidate_with_one_mutation_bundle():
    session, event_id = _world(mutation_count=7)
    result = _analysis(session)
    assert [item.event.event_id for item in result.candidates] == [event_id]
    assert len(result.candidates[0].mutation_set) == 7


def test_partial_mutation_bundle_retains_revision_level_admission():
    session, _ = _world(include_source=False)
    event_id = _add_source_change(
        session,
        metadata=_source_metadata(
            mutations=1,
            completeness=SourceFileEvidenceCompleteness.PARTIAL,
        ),
    )
    result = _analysis(session)
    assert result.candidates[0].event.event_id == event_id
    assert result.candidates[0].mutation_completeness == "partial"


def test_empty_mutation_bundle_does_not_block_exact_revision_or_fabricate_file():
    session, _ = _world(include_source=False)
    event_id = _add_source_change(
        session,
        metadata=_source_metadata(
            mutations=0,
            completeness=SourceFileEvidenceCompleteness.PARTIAL,
        ),
    )
    result = _analysis(session)
    assert result.candidates[0].event.event_id == event_id
    assert result.candidates[0].mutation_set == []


def test_unavailable_mutation_capture_retains_exact_revision_level_admission():
    session, _ = _world(include_source=False)
    capture = SourceFileMutationEnrichment(
        provider="github",
        completeness=SourceFileEvidenceCompleteness.UNAVAILABLE,
        reasons=["provider_error"],
        requested_commit_count=1,
    )
    event_id = _add_source_change(
        session,
        metadata={
            "source_file_mutation_enrichment": capture.model_dump(mode="json"),
            "source_file_mutations": [],
        },
    )
    candidate = _analysis(session).candidates[0]
    assert candidate.event.event_id == event_id
    assert candidate.mutation_set == []
    assert candidate.mutation_completeness == "unavailable"


@pytest.mark.parametrize(
    ("snapshot", "reason"),
    [
        (_snapshot(immutable=False), LineageAdmissionReason.IMMUTABLE_IMAGE_IDENTITY_INCOMPLETE),
        (_snapshot(include_owners=False), LineageAdmissionReason.WORKLOAD_OWNER_MISSING),
        (_snapshot(trusted=False), LineageAdmissionReason.RELATIONSHIP_PROVENANCE_INCOMPLETE),
        (_snapshot(include_workload_use=False), LineageAdmissionReason.WORKLOAD_IMAGE_MISMATCH),
    ],
)
def test_broken_runtime_hops_fail_closed(snapshot, reason):
    session, _ = _world(snapshot=snapshot)
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == reason


def test_sc3_requested_identity_repairs_measured_shape_without_weakening_sc2():
    snapshot = _snapshot()
    snapshot.entities = [
        item for item in snapshot.entities if item.kind != "ContainerImage"
    ]
    snapshot.relationships = [
        item
        for item in snapshot.relationships
        if item.relationship_type != RelationshipType.USES
    ]
    deployment = next(
        item for item in snapshot.entities if item.id == "deployment:app"
    )
    pod = next(item for item in snapshot.entities if item.id == "pod:app")
    requested = f"ghcr.io/{REPOSITORY}@{DIGEST}"
    deployment.properties["containers"] = normalize_regular_container_images(
        spec_containers=[{"name": "app", "image": requested}],
        spec_source_field=(
            "deployment.spec.template.spec.containers[].image"
        ),
    )
    pod.properties["containers"] = normalize_regular_container_images(
        spec_containers=[{"name": "app", "image": requested}],
        status_containers=[
            {
                "name": "app",
                "image": OTHER_DIGEST,
                "image_id": f"containerd://{OTHER_DIGEST}",
            }
        ],
    )
    snapshot = augment_snapshot_with_container_images(snapshot)

    session, event_id = _world(snapshot=snapshot)
    result = _analysis(session)

    assert result.candidates[0].event.event_id == event_id
    assert result.candidates[0].container_scope.image_digest == DIGEST
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.EXACT_IMMUTABLE_LINEAGE
    )
    pod_use = next(
        item
        for item in snapshot.relationships
        if item.source_entity_id == "pod:app"
        and item.relationship_type == RelationshipType.USES
    )
    assert pod_use.properties["requested_image"] == requested
    assert pod_use.properties["runtime_status_image"] == OTHER_DIGEST
    assert pod_use.properties["runtime_image_id"] == (
        f"containerd://{OTHER_DIGEST}"
    )


def test_latest_snapshot_never_substitutes_for_incident_pin():
    session, _ = _world(snapshot=_snapshot(include_owners=False))
    save_snapshot(session, _snapshot(snapshot_id="snapshot:latest"))
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.WORKLOAD_OWNER_MISSING
    )


def test_missing_incident_pin_never_uses_repository_latest_snapshot():
    session, _ = _world()
    incident = session.get(IncidentRecord, "incident:sc2")
    incident.topology_snapshot_id = None
    session.commit()
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.INCIDENT_PINNED_TOPOLOGY_MISSING
    )


def test_exact_failing_container_uses_only_its_image():
    session, event_id = _world(
        snapshot=_snapshot(containers=("app", "envoy")),
        failing_container="app",
    )
    result = _analysis(session)
    assert result.candidates[0].event.event_id == event_id
    assert result.candidates[0].container_scope.container_name == "app"
    assert result.candidates[0].container_scope.image_digest == DIGEST


def test_multi_container_unknown_failure_is_explicitly_ambiguous():
    session, _ = _world(
        snapshot=_snapshot(containers=("app", "envoy")),
        failing_container=None,
    )
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.AFFECTED_CONTAINER_AMBIGUOUS
    )


@pytest.mark.parametrize("containers", [("app", "envoy"), ("envoy", "app")])
def test_container_array_order_does_not_change_exact_scope(containers):
    session, _ = _world(
        snapshot=_snapshot(containers=containers), failing_container="app"
    )
    result = _analysis(session)
    assert result.candidates[0].container_scope.container_name == "app"
    assert result.candidates[0].container_scope.image_digest == DIGEST


def test_single_container_without_signal_container_can_proceed():
    session, event_id = _world(failing_container=None)
    result = _analysis(session)
    assert result.candidates[0].event.event_id == event_id
    assert result.candidates[0].container_scope.container_name == "app"


def test_healthy_app_image_cannot_admit_when_exact_failure_is_sidecar():
    session, _ = _world(
        snapshot=_snapshot(containers=("app", "envoy")),
        failing_container="envoy",
    )
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.IMAGE_TO_RUN_MISSING
    )


def test_unknown_named_container_does_not_fall_back_to_first_container():
    session, _ = _world(failing_container="missing")
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.AFFECTED_CONTAINER_MISSING
    )


def test_duplicate_owner_paths_are_ambiguous_not_first_match():
    snapshot = _snapshot()
    snapshot.relationships.append(
        _relationship(
            "rel:rs-pod:duplicate",
            "replicaset:app",
            "pod:app",
            RelationshipType.RUNS,
        )
    )
    session, _ = _world(snapshot=snapshot)
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.WORKLOAD_OWNER_AMBIGUOUS
    )


def test_declared_tag_semantics_cannot_replace_derived_digest_provenance():
    snapshot = _snapshot()
    uses = next(
        item
        for item in snapshot.relationships
        if item.id == "rel:pod-image:app"
    )
    uses.provenance = uses.provenance.model_copy(
        update={"origin": RelationshipOrigin.DECLARED}
    )
    session, _ = _world(snapshot=snapshot)
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.RELATIONSHIP_PROVENANCE_INCOMPLETE
    )


def test_exact_deployment_affected_entity_uses_workload_image_without_rewrite():
    session, event_id = _world()
    incident = session.get(IncidentRecord, "incident:sc2")
    incident.affected_entity_id = "deployment:app"
    session.commit()
    result = _analysis(session)
    assert result.candidates[0].event.event_id == event_id
    assert result.candidates[0].container_scope.affected_entity_id == (
        "deployment:app"
    )
    assert result.candidates[0].container_scope.pod_entity_id is None


def test_missing_affected_entity_is_explicit_and_does_not_guess_from_signal():
    session, _ = _world()
    incident = session.get(IncidentRecord, "incident:sc2")
    incident.affected_entity_id = None
    session.commit()
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.AFFECTED_ENTITY_MISSING
    )


def test_noncanonical_affected_entity_reference_is_not_fuzzily_resolved():
    session, _ = _world()
    incident = session.get(IncidentRecord, "incident:sc2")
    incident.affected_entity_id = "app"
    session.commit()
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.AFFECTED_ENTITY_IDENTITY_INCOMPLETE
    )


def test_missing_pinned_snapshot_record_does_not_search_for_replacement():
    session, _ = _world()
    session.delete(session.get(SnapshotRecord, "snapshot:pinned"))
    session.commit()
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.INCIDENT_PINNED_TOPOLOGY_MISSING
    )


def test_late_observed_and_recorded_provider_evidence_may_qualify():
    session, event_id = _world(include_provider=False)
    _add_provider(
        session,
        observed_at=INCIDENT_TIME + timedelta(days=30),
        effective_at=PROVIDER_TIME,
    )
    result = _analysis(session)
    assert result.candidates[0].event.event_id == event_id
    assert result.candidates[0].lineage_paths[0].provider_effective_at == (
        PROVIDER_TIME.isoformat()
    )


def test_provider_relation_effective_after_incident_is_rejected():
    session, _ = _world(include_provider=False)
    _add_provider(session, effective_at=INCIDENT_TIME + timedelta(minutes=1))
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.PROVIDER_EFFECTIVE_TIME_INCOMPATIBLE
    )


def test_same_digest_distinct_revisions_fail_closed():
    session, _ = _world()
    _add_provider(session, evidence_index=2, revision=OTHER_REVISION)
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.AMBIGUOUS_SOURCE_PROVENANCE
    )


def test_multiple_runs_same_revision_deduplicate_candidate_and_keep_paths():
    session, event_id = _world()
    _add_provider(session, evidence_index=2)
    result = _analysis(session)
    assert [item.event.event_id for item in result.candidates] == [event_id]
    assert len(result.candidates[0].lineage_paths) == 2
    assert [path.run_id for path in result.candidates[0].lineage_paths] == [
        "101",
        "102",
    ]


def test_missing_canonical_source_change_fails_closed():
    session, _ = _world(include_source=False)
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.SOURCE_CHANGE_MISSING
    )


def test_source_repository_identity_must_match_provider_record():
    session, _ = _world(include_source=False)
    metadata = _source_metadata()
    metadata["source_file_mutation_enrichment"]["repository"][
        "provider_repository_id"
    ] = "different"
    _add_source_change(session, metadata=metadata)
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.SOURCE_CHANGE_MISSING
    )


def test_source_external_identity_must_be_canonical():
    session, event_id = _world()
    event = session.get(ChangeEventRecord, event_id)
    event.external_id = "github:wrong/repository:" + REVISION
    session.commit()
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.SOURCE_CHANGE_MISSING
    )


def test_commit_message_and_timestamp_cannot_substitute_for_exact_revision():
    session, _ = _world(include_source=False)
    _add_source_change(
        session,
        revision=OTHER_REVISION,
        occurred_at=SOURCE_TIME,
        metadata={},
    )
    event = session.query(ChangeEventRecord).one()
    event.title = REVISION
    event.summary = f"mentions {REVISION}"
    session.commit()
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.SOURCE_CHANGE_MISSING
    )


def test_provider_repository_name_similarity_is_not_used():
    session, _ = _world(include_provider=False)
    _add_provider(session, repository="acme/runtime-similar")
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.IMAGE_TO_RUN_MISSING
    )


def test_untrusted_or_incomplete_provider_record_does_not_admit():
    session, _ = _world(include_provider=False)
    _add_provider(
        session,
        completeness=BuildArtifactEvidenceCompleteness.INCOMPLETE,
    )
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.IMAGE_TO_RUN_MISSING
    )


def test_lineage_budget_overflow_is_explicit_and_never_selects_first():
    session, _ = _world(include_provider=False)
    for index in range(1, MAX_PROVIDER_PATHS_PER_ARTIFACT + 2):
        _add_provider(session, evidence_index=index)
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.LINEAGE_BUDGET_EXCEEDED
    )


def test_admission_audit_is_deterministic_across_repeated_reads():
    session, _ = _world()
    first = _analysis(session).model_dump(mode="json")
    second = _analysis(session).model_dump(mode="json")
    assert first == second


def test_admission_evidence_references_are_sorted_unique_and_artifact_scoped():
    session, _ = _world()
    _add_provider(session, evidence_index=2)
    candidate = _analysis(session).candidates[0]
    serialized = [
        (item.reference_type, item.reference, item.source_system)
        for item in candidate.admission_evidence_refs
    ]
    assert len(serialized) == len(set(serialized))
    assert serialized == [
        (item.reference_type, item.reference, item.source_system)
        for item in _analysis(session).candidates[0].admission_evidence_refs
    ]
    assert ("container_image_digest", DIGEST, "docker-buildx") in serialized
    assert all(OTHER_DIGEST not in value for item in serialized for value in item)


def test_lineage_path_respects_existing_relationship_directions():
    session, _ = _world()
    path = _analysis(session).candidates[0].lineage_paths[0]
    assert path.relationship_ids == sorted(
        [
            "rel:deployment-image:app",
            "rel:deployment-rs",
            "rel:pod-image:app",
            "rel:rs-pod",
        ]
    )
    assert path.entity_ids[0] == "pod:app"


def test_admitted_audit_has_bounded_explicit_state_and_reason():
    session, event_id = _world()
    audit = _analysis(session).lineage_admission_audit[0]
    assert audit.canonical_change_id == event_id
    assert audit.admission_state == LineageAdmissionState.ADMITTED
    assert audit.admission_reason == LineageAdmissionReason.EXACT_IMMUTABLE_LINEAGE
    assert audit.admission_basis == [
        CandidateAdmissionBasis.EXACT_IMMUTABLE_LINEAGE
    ]


def test_lineage_path_order_is_provider_run_order_not_insert_order():
    session, _ = _world(include_provider=False)
    _add_provider(session, evidence_index=9)
    _add_provider(session, evidence_index=2)
    paths = _analysis(session).candidates[0].lineage_paths
    assert [item.run_id for item in paths] == ["102", "109"]


def test_source_effective_time_must_precede_provider_build_truth():
    session, _ = _world(
        include_source=False,
        source_time=PROVIDER_TIME + timedelta(minutes=1),
    )
    _add_source_change(
        session,
        occurred_at=PROVIDER_TIME + timedelta(minutes=1),
    )
    result = _analysis(session)
    assert result.candidates == []
    assert result.lineage_admission_audit[0].admission_reason == (
        LineageAdmissionReason.SOURCE_CHANGE_MISSING
    )


def test_admission_metadata_survives_causal_analysis_persistence_round_trip():
    session, event_id = _world()
    analysis = analyze_causal_rca(
        session,
        incident_id="incident:sc2",
        request=CausalAnalysisRequest(),
    )
    loaded = latest_causal_analysis(session, incident_id="incident:sc2")
    assert loaded is not None
    assert loaded.analysis_id == analysis.analysis_id
    assert loaded.candidate_admission_policy_version == (
        CAUSAL_CANDIDATE_ADMISSION_POLICY_VERSION
    )
    audit = {item.event_id: item for item in loaded.candidate_selection_audit}
    assert audit[event_id].admission_basis == [
        CandidateAdmissionBasis.EXACT_IMMUTABLE_LINEAGE
    ]
    assert audit[event_id].lineage_paths
    assert audit[event_id].mutation_set
    assert loaded.lineage_admission_audit[0].canonical_change_id == event_id


def test_historical_causal_analysis_payload_without_sc2_fields_still_loads():
    payload = {
        "analysis_id": "causal-analysis:legacy",
        "incident_id": "incident:legacy",
        "incident_title": "Legacy",
        "incident_time": INCIDENT_TIME.isoformat(),
        "topology_snapshot_id": None,
        "algorithm_version": "causal-rca-v1",
        "generated_at": INCIDENT_TIME.isoformat(),
        "parameters": {},
        "candidate_count": 0,
        "node_count": 0,
        "edge_count": 0,
        "evidence_count": 0,
        "hypothesis_count": 0,
        "top_hypothesis": None,
    }
    loaded = CausalAnalysisResponse.model_validate(payload)
    assert loaded.candidate_admission_policy_version is None
    assert loaded.lineage_admission_audit == []


def test_lineage_candidate_can_still_safely_abstain():
    session, event_id = _world()
    event = session.get(ChangeEventRecord, event_id)
    event.status = "no_change"
    session.commit()
    analysis = analyze_causal_rca(
        session,
        incident_id="incident:sc2",
        request=CausalAnalysisRequest(),
    )
    assert analysis.candidate_count == 1
    assert analysis.top_hypothesis is None
    assert analysis.hypotheses == []


@pytest.mark.parametrize(
    ("literal", "expected"),
    [
        ("CAUSAL_CANDIDATE_POLICY_VERSION", "causal-candidate-v1"),
        (
            "CAUSAL_CANDIDATE_ADMISSION_POLICY_VERSION",
            "causal-candidate-admission-v2",
        ),
    ],
)
def test_policy_versions_are_explicit(literal, expected):
    assert globals()[literal] == expected


def test_frozen_180_minute_default_and_no_lineage_score_bonus():
    assert CausalAnalysisRequest().lookback_minutes == 180
    source = inspect.getsource(analyze_incident_change_events)
    assert "score +=" not in source
    selection_source = inspect.getsource(
        __import__(
            "app.services.causal_candidate_policy", fromlist=["select_causal_candidates"]
        ).select_causal_candidates
    ).lower()
    assert "candidate.score +" not in selection_source
    assert "candidate.score *" not in selection_source


@pytest.mark.parametrize(
    "forbidden",
    [
        "openai",
        "embedding",
        "subprocess",
        "git ",
        "evaluation",
        "sourcefile",
        "entity(",
        "relationship(",
    ],
)
def test_admission_service_has_no_forbidden_inference_or_graph_expansion(forbidden):
    source = inspect.getsource(evaluate_lineage_candidate_admission).lower()
    assert forbidden not in source


@pytest.mark.parametrize(
    "frozen_module",
    [
        "app.services.causal_relevance_policy",
        "app.services.incident_lifecycle",
        "app.services.continuous_lifecycle",
        "app.services.causal_evidence_ledger",
    ],
)
def test_sc2_service_does_not_import_frozen_downstream_subsystems(frozen_module):
    source = inspect.getsource(
        __import__("app.services.lineage_candidate_admission", fromlist=["*"])
    )
    assert frozen_module not in source


@pytest.mark.parametrize(
    "reason",
    [
        "incident_pinned_topology_missing",
        "affected_entity_missing",
        "affected_entity_identity_incomplete",
        "affected_entity_unsupported",
        "workload_owner_missing",
        "workload_owner_ambiguous",
        "relationship_provenance_incomplete",
        "affected_container_ambiguous",
        "affected_container_missing",
        "immutable_image_missing",
        "immutable_image_identity_incomplete",
        "workload_image_mismatch",
        "image_to_run_missing",
        "source_change_missing",
        "source_change_ambiguous",
        "provider_effective_time_incompatible",
        "ambiguous_source_provenance",
        "lineage_budget_exceeded",
    ],
)
def test_fail_closed_reason_contract_is_bounded_and_stable(reason):
    assert LineageAdmissionReason(reason).value == reason
