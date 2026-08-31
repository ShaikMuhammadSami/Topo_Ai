from __future__ import annotations
from app.repositories.tenant_scope import (
    DomainTenant,
    tenant_predicate,
    tenant_get,
    require_record_owner,
)

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ChangeEventRecord, IncidentRecord, SnapshotRecord
from app.services.tenant_world_model import snapshot_from_owned_record
from app.models.build_artifacts import BuildArtifactEvidenceCompleteness
from app.models.causal_candidates import (
    CandidateAdmissionBasis,
    CandidateAdmissionEvidenceReference,
    LineageAdmissionReason,
    LineageAdmissionState,
    LineageCandidateAdmissionAudit,
    LineageContainerScope,
    LineagePathAudit,
)
from app.models.change_events import ChangeEventKind, ChangeEventSource
from app.models.source_file_mutations import (
    SourceFileMutationEnrichment,
    SourceFileMutationEvidence,
)
from app.models.temporal import TemporalStatus, TimeQuality
from app.models.topology import (
    Entity,
    GraphSnapshot,
    Relationship,
    RelationshipOrigin,
    RelationshipProvenanceCompleteness,
    RelationshipType,
)
from app.repositories.build_artifact_evidence_repository import (
    list_build_artifact_evidence_for_image_digest,
)
from app.repositories.signal_repository import load_signal
from app.services.temporal_semantics import change_event_temporal

MAX_PROVIDER_PATHS_PER_ARTIFACT = 32
MAX_SOURCE_EVENTS_PER_REVISION = 8
KUBERNETES_GRAPH_SOURCE = "backend.app.collectors.kubernetes_collector"
CONTAINER_IMAGE_GRAPH_SOURCE = "backend.app.services.container_image_graph"
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_CONTAINER_FIELD_PATH = re.compile(
    r"(?:^|\.)containers\{(?P<name>[^{}]+)\}(?:\.|$)"
)


@dataclass(frozen=True)
class LineageAdmittedChange:
    record: ChangeEventRecord
    audit: LineageCandidateAdmissionAudit


@dataclass(frozen=True)
class LineageAdmissionResult:
    admitted: tuple[LineageAdmittedChange, ...]
    audit: tuple[LineageCandidateAdmissionAudit, ...]


def _incomplete(
    reason: LineageAdmissionReason,
    *,
    revision: str | None = None,
) -> LineageAdmissionResult:
    audit = LineageCandidateAdmissionAudit(
        revision=revision,
        admission_state=LineageAdmissionState.INCOMPLETE,
        admission_reason=reason,
    )
    return LineageAdmissionResult(admitted=(), audit=(audit,))


def _trusted_relationship(
    relationship: Relationship,
    *,
    predicate: RelationshipType,
    source_component: str,
    required_reference_types: set[str],
    allowed_origins: set[RelationshipOrigin],
) -> bool:
    provenance = relationship.provenance
    if (
        relationship.relationship_type != predicate
        or provenance is None
        or provenance.completeness
        != RelationshipProvenanceCompleteness.COMPLETE
        or provenance.origin not in allowed_origins
        or provenance.source_component != source_component
        or relationship.directed is not True
    ):
        return False
    reference_types = {
        item.reference_type for item in provenance.source_references
    }
    return required_reference_types <= reference_types


def _owner_relationships(
    snapshot: GraphSnapshot,
    *,
    target_id: str,
    predicate: RelationshipType,
    owner_kind: str,
    entities: dict[str, Entity],
) -> list[Relationship]:
    return sorted(
        (
            relationship
            for relationship in snapshot.relationships
            if relationship.target_entity_id == target_id
            and relationship.relationship_type == predicate
            and entities.get(relationship.source_entity_id) is not None
            and entities[relationship.source_entity_id].kind == owner_kind
        ),
        key=lambda value: value.id,
    )


def _exact_container_from_incident(
    session: Session,
    incident: IncidentRecord,
    *,
    tenant_id: DomainTenant,
) -> str | None:
    require_record_owner(incident, tenant_id=tenant_id)
    signal = load_signal(session, incident.primary_signal_id, tenant_id=tenant_id)
    if signal is None:
        return None
    for key in ("container_name", "container"):
        value = signal.attributes.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    field_path = signal.attributes.get("field_path")
    if isinstance(field_path, str):
        match = _CONTAINER_FIELD_PATH.search(field_path)
        if match:
            return match.group("name")
    involved = signal.raw_payload.get("involvedObject")
    if isinstance(involved, dict):
        raw_path = involved.get("fieldPath")
        if isinstance(raw_path, str):
            match = _CONTAINER_FIELD_PATH.search(raw_path)
            if match:
                return match.group("name")
    return None


def _normalized_image_repository(reference: str) -> str:
    value = reference.strip().lower().split("@", 1)[0]
    slash = value.rfind("/")
    colon = value.rfind(":")
    if colon > slash:
        value = value[:colon]
    return value


def _runtime_image_repository_identities(
    relationships: list[Relationship],
) -> set[str]:
    per_relationship: list[set[str]] = []
    for relationship in relationships:
        if relationship.relationship_type != RelationshipType.USES:
            continue
        values: set[str] = set()
        requested = relationship.properties.get("requested_image")
        if isinstance(requested, str):
            value = _normalized_image_repository(requested)
            if value:
                values.add(value)
        if relationship.provenance is not None:
            for reference in relationship.provenance.source_references:
                if reference.reference_type != "container_image_reference":
                    continue
                value = _normalized_image_repository(reference.reference)
                if value:
                    values.add(value)
        if values:
            per_relationship.append(values)
    if not per_relationship:
        return set()
    result = set(per_relationship[0])
    for values in per_relationship[1:]:
        result &= values
    return result


def _runtime_path(
    session: Session,
    *,
    incident: IncidentRecord,
    snapshot: GraphSnapshot,
    tenant_id: DomainTenant,
) -> (
    tuple[
        Entity,
        Entity | None,
        Entity,
        Entity,
        str,
        list[Relationship],
    ]
    | LineageAdmissionReason
):
    require_record_owner(incident, tenant_id=tenant_id)
    entities = {entity.id: entity for entity in snapshot.entities}
    affected_id = str(incident.affected_entity_id or "")
    affected = entities.get(affected_id)
    if affected is None:
        return LineageAdmissionReason.AFFECTED_ENTITY_IDENTITY_INCOMPLETE

    pod: Entity | None
    workload: Entity
    owner_relationships: list[Relationship] = []
    if affected.kind == "KubernetesPod":
        pod = affected
        run_edges = _owner_relationships(
            snapshot,
            target_id=pod.id,
            predicate=RelationshipType.RUNS,
            owner_kind="KubernetesReplicaSet",
            entities=entities,
        )
        if not run_edges:
            return LineageAdmissionReason.WORKLOAD_OWNER_MISSING
        if len(run_edges) != 1:
            return LineageAdmissionReason.WORKLOAD_OWNER_AMBIGUOUS
        replica_set = entities[run_edges[0].source_entity_id]
        own_edges = _owner_relationships(
            snapshot,
            target_id=replica_set.id,
            predicate=RelationshipType.OWNS,
            owner_kind="KubernetesDeployment",
            entities=entities,
        )
        if not own_edges:
            return LineageAdmissionReason.WORKLOAD_OWNER_MISSING
        if len(own_edges) != 1:
            return LineageAdmissionReason.WORKLOAD_OWNER_AMBIGUOUS
        owner_relationships = [run_edges[0], own_edges[0]]
        workload = entities[own_edges[0].source_entity_id]
    elif affected.kind == "KubernetesDeployment":
        pod = None
        workload = affected
    else:
        return LineageAdmissionReason.AFFECTED_ENTITY_UNSUPPORTED

    for relationship in owner_relationships:
        if not _trusted_relationship(
            relationship,
            predicate=relationship.relationship_type,
            source_component=KUBERNETES_GRAPH_SOURCE,
            required_reference_types={"kubernetes_owner_reference_uid"},
            allowed_origins={
                RelationshipOrigin.DECLARED,
                RelationshipOrigin.DERIVED,
                RelationshipOrigin.OBSERVED,
            },
        ):
            return LineageAdmissionReason.RELATIONSHIP_PROVENANCE_INCOMPLETE

    use_source_id = pod.id if pod is not None else workload.id
    pod_uses = sorted(
        (
            relationship
            for relationship in snapshot.relationships
            if relationship.source_entity_id == use_source_id
            and relationship.relationship_type == RelationshipType.USES
            and entities.get(relationship.target_entity_id) is not None
            and entities[relationship.target_entity_id].kind == "ContainerImage"
        ),
        key=lambda value: (
            str(value.properties.get("container_name") or ""),
            value.target_entity_id,
            value.id,
        ),
    )
    if not pod_uses:
        return LineageAdmissionReason.IMMUTABLE_IMAGE_MISSING

    exact_container = _exact_container_from_incident(
        session, incident, tenant_id=tenant_id
    )
    container_names = {
        str(item.properties.get("container_name") or "").strip()
        for item in pod_uses
        if str(item.properties.get("container_name") or "").strip()
    }
    if exact_container is None:
        if len(container_names) != 1:
            return LineageAdmissionReason.AFFECTED_CONTAINER_AMBIGUOUS
        exact_container = next(iter(container_names))

    selected = [
        item
        for item in pod_uses
        if str(item.properties.get("container_name") or "").strip()
        == exact_container
    ]
    if not selected:
        return LineageAdmissionReason.AFFECTED_CONTAINER_MISSING
    if len(selected) != 1:
        return LineageAdmissionReason.AFFECTED_CONTAINER_AMBIGUOUS
    use_relationship = selected[0]
    if not _trusted_relationship(
        use_relationship,
        predicate=RelationshipType.USES,
        source_component=CONTAINER_IMAGE_GRAPH_SOURCE,
        required_reference_types={
            "container_image_reference",
            "container_image_digest",
        },
        allowed_origins={
            RelationshipOrigin.DERIVED,
            RelationshipOrigin.OBSERVED,
        },
    ):
        return LineageAdmissionReason.RELATIONSHIP_PROVENANCE_INCOMPLETE

    image = entities[use_relationship.target_entity_id]
    digest = str(image.properties.get("digest") or "").lower()
    if image.properties.get("immutable") is not True or not _DIGEST.fullmatch(
        digest
    ):
        return LineageAdmissionReason.IMMUTABLE_IMAGE_IDENTITY_INCOMPLETE
    if str(image.external_id or "").lower() != digest:
        return LineageAdmissionReason.IMMUTABLE_IMAGE_IDENTITY_INCOMPLETE

    workload_uses = sorted(
        (
            relationship
            for relationship in snapshot.relationships
            if relationship.source_entity_id == workload.id
            and relationship.target_entity_id == image.id
            and relationship.relationship_type == RelationshipType.USES
            and str(relationship.properties.get("container_name") or "").strip()
            == exact_container
        ),
        key=lambda value: value.id,
    )
    if len(workload_uses) != 1:
        return LineageAdmissionReason.WORKLOAD_IMAGE_MISMATCH
    if not _trusted_relationship(
        workload_uses[0],
        predicate=RelationshipType.USES,
        source_component=CONTAINER_IMAGE_GRAPH_SOURCE,
        required_reference_types={
            "container_image_reference",
            "container_image_digest",
        },
        allowed_origins={
            RelationshipOrigin.DERIVED,
            RelationshipOrigin.OBSERVED,
        },
    ):
        return LineageAdmissionReason.RELATIONSHIP_PROVENANCE_INCOMPLETE

    return (
        affected,
        pod,
        workload,
        image,
        exact_container,
        [*owner_relationships, use_relationship, workload_uses[0]],
    )


def _source_event(
    session: Session,
    *,
    repository_id: str,
    repository: str,
    revision: str,
    incident_time: datetime,
    provider_effective_at: datetime,
    tenant_id: DomainTenant,
) -> tuple[
    ChangeEventRecord | None,
    list[dict],
    str | None,
    LineageAdmissionReason | None,
]:
    records = list(
        session.scalars(
            select(ChangeEventRecord)
            .where(tenant_predicate(ChangeEventRecord, tenant_id))
            .where(ChangeEventRecord.commit_sha == revision)
            .order_by(ChangeEventRecord.event_id)
            .limit(MAX_SOURCE_EVENTS_PER_REVISION + 1)
        ).all()
    )
    if len(records) > MAX_SOURCE_EVENTS_PER_REVISION:
        return None, [], None, LineageAdmissionReason.LINEAGE_BUDGET_EXCEEDED

    exact: list[tuple[ChangeEventRecord, SourceFileMutationEnrichment, list]] = []
    for record in records:
        temporal = change_event_temporal(record)
        if (
            record.source != ChangeEventSource.GITHUB.value
            or record.kind != ChangeEventKind.CODE.value
            or str(record.repository or "").casefold() != repository.casefold()
            or str(record.commit_sha or "").lower() != revision
            or str(record.external_id or "").casefold()
            != f"github:{repository}:{revision}".casefold()
            or temporal.source_time_authoritative is not True
            or temporal.time_quality != TimeQuality.EXACT
            or temporal.effective_at > incident_time
            or temporal.effective_at > provider_effective_at
        ):
            continue
        try:
            metadata = json.loads(record.metadata_json or "{}")
            capture = SourceFileMutationEnrichment.model_validate(
                metadata.get("source_file_mutation_enrichment")
            )
        except (json.JSONDecodeError, ValidationError, TypeError):
            continue
        if capture.repository is not None and (
            capture.repository.provider_repository_id != repository_id
            or capture.repository.full_name.casefold() != repository.casefold()
        ):
            continue
        mutations: list[SourceFileMutationEvidence] = []
        raw_mutations = metadata.get("source_file_mutations")
        if isinstance(raw_mutations, list):
            for raw in raw_mutations:
                try:
                    mutation = SourceFileMutationEvidence.model_validate(raw)
                except ValidationError:
                    continue
                if (
                    mutation.commit_sha.lower() == revision
                    and mutation.repository.provider_repository_id
                    == repository_id
                    and mutation.repository.full_name.casefold()
                    == repository.casefold()
                ):
                    mutations.append(mutation)
        exact.append((record, capture, mutations))

    if not exact:
        return None, [], None, LineageAdmissionReason.SOURCE_CHANGE_MISSING
    if len(exact) != 1:
        return None, [], None, LineageAdmissionReason.SOURCE_CHANGE_AMBIGUOUS
    record, capture, mutations = exact[0]
    mutation_payload = [
        item.model_dump(mode="json")
        for item in sorted(
            mutations,
            key=lambda value: (
                value.current_path,
                value.previous_path or "",
                value.mutation_id,
            ),
        )
    ]
    mutation_completeness = capture.completeness.value
    if len(mutations) != capture.mutation_count:
        mutation_completeness = "partial"
    return record, mutation_payload, mutation_completeness, None


def _references(
    runtime_relationships: list[Relationship],
    provider_evidence: list,
) -> list[CandidateAdmissionEvidenceReference]:
    values: dict[str, CandidateAdmissionEvidenceReference] = {}

    def add(reference_type: str, reference: object, source_system: str) -> None:
        item = CandidateAdmissionEvidenceReference(
            reference_type=reference_type,
            reference=str(reference),
            source_system=source_system,
        )
        key = json.dumps(item.model_dump(mode="json"), sort_keys=True)
        values[key] = item

    for relationship in runtime_relationships:
        add("topology_relationship", relationship.id, "topo")
        if relationship.provenance is not None:
            for reference in relationship.provenance.source_references:
                add(
                    reference.reference_type,
                    reference.reference,
                    reference.source_system,
                )
    for item in provider_evidence:
        add("build_artifact_evidence", item.evidence_id, "topo")
        add("github_repository_id", item.repository_id, "github")
        add("github_workflow_run_id", item.run_id, "github-actions")
        add("github_workflow_run_attempt", item.run_attempt, "github-actions")
        add("git_commit_sha", item.commit_sha, "github")
        add("container_image_digest", item.image_digest, "docker-buildx")
        add(
            "github_actions_artifact_id",
            item.provider_evidence_id,
            "github-actions",
        )
        add(
            "docker_build_record_digest",
            item.provider_build_record_digest,
            "docker-buildx",
        )
    return [values[key] for key in sorted(values)]


def evaluate_lineage_candidate_admission(
    session: Session,
    *,
    incident: IncidentRecord,
    incident_time: datetime,
    tenant_id: DomainTenant,
) -> LineageAdmissionResult:
    """Admit one old canonical source change only through exact lineage.

    The runtime half is loaded solely from the incident's explicit immutable
    topology pin. The provider half begins with the resulting exact digest and
    performs bounded indexed lookups. This function neither scores nor ranks.
    """
    require_record_owner(incident, tenant_id=tenant_id)

    if not incident.topology_snapshot_id:
        return _incomplete(
            LineageAdmissionReason.INCIDENT_PINNED_TOPOLOGY_MISSING
        )
    snapshot_record = tenant_get(
        session, SnapshotRecord, incident.topology_snapshot_id, tenant_id=tenant_id
    )
    if snapshot_record is None:
        return _incomplete(
            LineageAdmissionReason.INCIDENT_PINNED_TOPOLOGY_MISSING
        )
    if not incident.affected_entity_id:
        return _incomplete(LineageAdmissionReason.AFFECTED_ENTITY_MISSING)
    snapshot = snapshot_from_owned_record(snapshot_record, tenant_id=tenant_id)
    runtime = _runtime_path(
        session,
        incident=incident,
        snapshot=snapshot,
        tenant_id=tenant_id,
    )
    if isinstance(runtime, LineageAdmissionReason):
        return _incomplete(runtime)
    affected, pod, workload, image, container_name, runtime_relationships = runtime
    digest = str(image.properties["digest"]).lower()
    repository_identities = _runtime_image_repository_identities(
        runtime_relationships
    )
    if not repository_identities:
        return _incomplete(
            LineageAdmissionReason.IMMUTABLE_IMAGE_IDENTITY_INCOMPLETE
        )

    provider = list_build_artifact_evidence_for_image_digest(
        session,
        image_digest=digest,
        limit=MAX_PROVIDER_PATHS_PER_ARTIFACT + 1,
        tenant_id=tenant_id,
    )
    if len(provider) > MAX_PROVIDER_PATHS_PER_ARTIFACT:
        return _incomplete(LineageAdmissionReason.LINEAGE_BUDGET_EXCEEDED)
    matching_repository = [
        item
        for item in provider
        if item.completeness == BuildArtifactEvidenceCompleteness.COMPLETE
        and item.temporal.source_time_authoritative is True
        and item.temporal.time_quality == TimeQuality.EXACT
        and item.temporal.status == TemporalStatus.COMPLETE
        and item.image_repository.strip().casefold() in repository_identities
    ]
    if not matching_repository:
        return _incomplete(LineageAdmissionReason.IMAGE_TO_RUN_MISSING)
    historically_compatible = [
        item
        for item in matching_repository
        if item.temporal.effective_at <= incident_time
    ]
    if not historically_compatible:
        return _incomplete(
            LineageAdmissionReason.PROVIDER_EFFECTIVE_TIME_INCOMPATIBLE
        )

    revisions = {
        (item.repository_id, item.repository.casefold(), item.commit_sha)
        for item in historically_compatible
    }
    if len(revisions) != 1:
        return _incomplete(LineageAdmissionReason.AMBIGUOUS_SOURCE_PROVENANCE)
    repository_id, _repository_key, revision = next(iter(revisions))
    repository = sorted(
        {item.repository for item in historically_compatible}, key=str.casefold
    )[0]
    relevant_paths = sorted(
        (
            item
            for item in historically_compatible
            if item.repository_id == repository_id
            and item.repository.casefold() == repository.casefold()
            and item.commit_sha == revision
        ),
        key=lambda item: (
            item.run_id,
            item.run_attempt,
            item.provider_evidence_id,
            item.evidence_id,
        ),
    )
    source_event, mutations, mutation_completeness, source_error = _source_event(
        session,
        repository_id=repository_id,
        repository=repository,
        revision=revision,
        incident_time=incident_time,
        provider_effective_at=min(
            item.temporal.effective_at for item in relevant_paths
        ),
        tenant_id=tenant_id,
    )
    if source_error is not None or source_event is None:
        return _incomplete(
            source_error or LineageAdmissionReason.SOURCE_CHANGE_MISSING,
            revision=revision,
        )

    container_scope = LineageContainerScope(
        affected_entity_id=affected.id,
        pod_entity_id=pod.id if pod is not None else None,
        workload_entity_id=workload.id,
        container_name=container_name,
        image_entity_id=image.id,
        image_digest=digest,
    )
    relationship_ids = sorted({item.id for item in runtime_relationships})
    base_entity_ids = [affected.id]
    for relationship in runtime_relationships:
        base_entity_ids.extend(
            [relationship.source_entity_id, relationship.target_entity_id]
        )
    entity_ids = list(dict.fromkeys(base_entity_ids))
    paths: list[LineagePathAudit] = []
    for item in relevant_paths:
        payload = {
            "affected": affected.id,
            "relationships": relationship_ids,
            "image_digest": digest,
            "evidence": item.evidence_id,
            "run": item.run_id,
            "attempt": item.run_attempt,
            "revision": revision,
            "change": source_event.event_id,
        }
        path_id = "lineage-path:" + hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()[:40]
        paths.append(
            LineagePathAudit(
                path_id=path_id,
                affected_entity_id=affected.id,
                entity_ids=entity_ids,
                relationship_ids=relationship_ids,
                provider_evidence_ids=[item.evidence_id],
                container_name=container_name,
                image_entity_id=image.id,
                image_entity_kind=image.kind,
                image_digest=digest,
                repository_id=repository_id,
                repository=repository,
                run_id=item.run_id,
                run_attempt=item.run_attempt,
                revision=revision,
                canonical_change_id=source_event.event_id,
                provider_effective_at=item.temporal.effective_at.isoformat(),
            )
        )
    audit = LineageCandidateAdmissionAudit(
        canonical_change_id=source_event.event_id,
        revision=revision,
        admission_basis=[CandidateAdmissionBasis.EXACT_IMMUTABLE_LINEAGE],
        admission_evidence_refs=_references(
            runtime_relationships, relevant_paths
        ),
        lineage_paths=paths,
        container_scope=container_scope,
        mutation_set=mutations,
        mutation_completeness=mutation_completeness,
        admission_state=LineageAdmissionState.ADMITTED,
        admission_reason=LineageAdmissionReason.EXACT_IMMUTABLE_LINEAGE,
    )
    admitted = LineageAdmittedChange(record=source_event, audit=audit)
    return LineageAdmissionResult(admitted=(admitted,), audit=(audit,))
