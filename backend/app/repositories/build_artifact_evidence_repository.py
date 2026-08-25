from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import BuildArtifactEvidenceRecord, utc_now_iso
from app.models.build_artifacts import BuildArtifactEvidence


def _view(record: BuildArtifactEvidenceRecord) -> BuildArtifactEvidence:
    return BuildArtifactEvidence(
        evidence_id=record.evidence_id,
        provider=record.provider,
        repository_id=record.repository_id,
        repository=record.repository,
        workflow_id=record.workflow_id,
        workflow_ref=record.workflow_ref,
        run_id=record.workflow_run_id,
        run_attempt=record.run_attempt,
        commit_sha=record.commit_sha,
        artifact_type=record.artifact_type,
        image_repository=record.image_repository,
        image_reference=record.image_reference,
        image_digest=record.image_digest,
        immutable_image_ref=record.immutable_image_ref,
        provider_evidence_type=record.provider_evidence_type,
        provider_evidence_id=record.provider_evidence_id,
        provider_evidence_reference=record.provider_evidence_reference,
        provider_evidence_digest=record.provider_evidence_digest,
        provider_build_record_digest=record.provider_build_record_digest,
        provider_builder_id=record.provider_builder_id,
        provider_build_started_at=record.provider_build_started_at,
        provider_build_finished_at=record.provider_build_finished_at,
        provider_run_updated_at=record.provider_run_updated_at,
        observed_at=record.observed_at,
        temporal=json.loads(record.temporal_json),
        completeness=record.completeness,
    )


def _immutable_fact(value: BuildArtifactEvidence) -> tuple[object, ...]:
    return (
        value.provider,
        value.repository_id,
        value.repository.casefold(),
        value.run_id,
        value.run_attempt,
        value.commit_sha,
        value.image_repository.casefold(),
        value.image_digest,
        value.provider_evidence_id,
        value.provider_evidence_digest,
        value.provider_build_record_digest,
        value.provider_builder_id,
    )


def save_build_artifact_evidence(
    session: Session,
    *,
    evidence: BuildArtifactEvidence,
    commit: bool = True,
) -> tuple[BuildArtifactEvidence, bool]:
    existing = session.get(BuildArtifactEvidenceRecord, evidence.evidence_id)
    if existing is not None:
        view = _view(existing)
        if _immutable_fact(view) != _immutable_fact(evidence):
            raise ValueError(
                "Build artifact evidence ID conflicts with an existing provider fact."
            )
        return view, False

    now = utc_now_iso()
    record = BuildArtifactEvidenceRecord(
        evidence_id=evidence.evidence_id,
        provider=evidence.provider,
        repository_id=evidence.repository_id,
        repository=evidence.repository,
        workflow_id=evidence.workflow_id,
        workflow_ref=evidence.workflow_ref,
        workflow_run_id=evidence.run_id,
        run_attempt=evidence.run_attempt,
        commit_sha=evidence.commit_sha,
        artifact_type=evidence.artifact_type.value,
        image_repository=evidence.image_repository,
        image_reference=evidence.image_reference,
        image_digest=evidence.image_digest,
        immutable_image_ref=evidence.immutable_image_ref,
        provider_evidence_type=evidence.provider_evidence_type.value,
        provider_evidence_id=evidence.provider_evidence_id,
        provider_evidence_reference=evidence.provider_evidence_reference,
        provider_evidence_digest=evidence.provider_evidence_digest,
        provider_build_record_digest=evidence.provider_build_record_digest,
        provider_builder_id=evidence.provider_builder_id,
        provider_build_started_at=(
            evidence.provider_build_started_at.isoformat()
            if evidence.provider_build_started_at
            else None
        ),
        provider_build_finished_at=(
            evidence.provider_build_finished_at.isoformat()
            if evidence.provider_build_finished_at
            else None
        ),
        provider_run_updated_at=evidence.provider_run_updated_at.isoformat(),
        observed_at=evidence.observed_at.isoformat(),
        temporal_json=evidence.temporal.model_dump_json(),
        completeness=evidence.completeness.value,
        created_at=now,
        updated_at=now,
    )
    session.add(record)
    session.flush()
    if commit:
        session.commit()
    return evidence, True


def list_build_artifact_evidence(
    session: Session,
    *,
    repository_id: str,
    run_ids: set[str] | None = None,
    limit: int = 1000,
) -> list[BuildArtifactEvidence]:
    statement = select(BuildArtifactEvidenceRecord).where(
        BuildArtifactEvidenceRecord.repository_id == str(repository_id)
    )
    if run_ids:
        statement = statement.where(
            BuildArtifactEvidenceRecord.workflow_run_id.in_(sorted(run_ids))
        )
    statement = statement.order_by(
        BuildArtifactEvidenceRecord.workflow_run_id,
        BuildArtifactEvidenceRecord.run_attempt,
        BuildArtifactEvidenceRecord.image_digest,
        BuildArtifactEvidenceRecord.provider_evidence_id,
    ).limit(max(1, min(limit, 1000)))
    return [_view(record) for record in session.scalars(statement).all()]


def list_build_artifact_evidence_for_image_digest(
    session: Session,
    *,
    image_digest: str,
    limit: int = 33,
) -> list[BuildArtifactEvidence]:
    """Return a bounded exact-digest provider lineage lookup.

    This is deliberately artifact-first. It never scans source revisions or
    applies repository/name similarity to discover candidate history.
    """

    statement = (
        select(BuildArtifactEvidenceRecord)
        .where(
            BuildArtifactEvidenceRecord.image_digest
            == image_digest.strip().lower()
        )
        .order_by(
            BuildArtifactEvidenceRecord.repository_id,
            BuildArtifactEvidenceRecord.commit_sha,
            BuildArtifactEvidenceRecord.workflow_run_id,
            BuildArtifactEvidenceRecord.run_attempt,
            BuildArtifactEvidenceRecord.provider_evidence_id,
            BuildArtifactEvidenceRecord.evidence_id,
        )
        .limit(max(1, min(limit, 1000)))
    )
    return [_view(record) for record in session.scalars(statement).all()]

