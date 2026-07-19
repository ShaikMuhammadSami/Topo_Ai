import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    PostIncidentReportRecord,
    ReportActionItemRecord,
    utc_now_iso,
)
from app.models.incident_explanation import (
    ExplanationProvider,
    GroundingEvidence,
)
from app.models.post_incident_report import (
    GeneratedPostIncidentReport,
    PostIncidentReportDetail,
    PostIncidentReportStatus,
    PostIncidentReportSummary,
    PostIncidentReportUpdateRequest,
    ReportActionItemUpdateRequest,
    ReportActionItemView,
    ReportActionPriority,
    ReportActionStatus,
)


def _action_to_view(
    record: ReportActionItemRecord,
) -> ReportActionItemView:
    return ReportActionItemView(
        action_item_id=record.action_item_id,
        report_id=record.report_id,
        incident_id=record.incident_id,
        sequence=record.sequence,
        title=record.title,
        description=record.description,
        owner_team=record.owner_team,
        owner_contact=record.owner_contact,
        priority=ReportActionPriority(
            record.priority
        ),
        due_date=record.due_date,
        success_criteria=(
            record.success_criteria
        ),
        evidence_ids=json.loads(
            record.evidence_ids_json
        ),
        status=ReportActionStatus(
            record.status
        ),
        notes=record.notes,
        completed_at=record.completed_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _load_action_records(
    session: Session,
    report_id: str,
) -> list[ReportActionItemRecord]:
    statement = (
        select(
            ReportActionItemRecord
        )
        .where(
            ReportActionItemRecord.report_id
            == report_id
        )
        .order_by(
            ReportActionItemRecord
            .sequence
            .asc()
        )
    )

    return list(
        session.scalars(
            statement
        ).all()
    )


def _report_to_summary(
    session: Session,
    record: PostIncidentReportRecord,
) -> PostIncidentReportSummary:
    actions = _load_action_records(
        session=session,
        report_id=record.report_id,
    )

    completed = sum(
        action.status
        == ReportActionStatus.COMPLETED.value
        for action in actions
    )

    return PostIncidentReportSummary(
        report_id=record.report_id,
        incident_id=record.incident_id,
        version=record.version,
        title=record.title,
        status=PostIncidentReportStatus(
            record.status
        ),
        provider=ExplanationProvider(
            record.provider
        ),
        model_name=record.model_name,
        prompt_version=record.prompt_version,
        grounding_hash=record.grounding_hash,
        overall_confidence=float(
            record.overall_confidence
        ),
        action_item_count=len(actions),
        completed_action_item_count=(
            completed
        ),
        reviewer_name=record.reviewer_name,
        reviewed_at=record.reviewed_at,
        approved_at=record.approved_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def load_post_incident_report(
    session: Session,
    report_id: str,
) -> PostIncidentReportDetail | None:
    record = session.get(
        PostIncidentReportRecord,
        report_id,
    )

    if record is None:
        return None

    generated = (
        GeneratedPostIncidentReport
        .model_validate_json(
            record.payload_json
        )
    )

    summary = _report_to_summary(
        session=session,
        record=record,
    )

    actions = [
        _action_to_view(action)
        for action in _load_action_records(
            session=session,
            report_id=report_id,
        )
    ]

    evidence_values = json.loads(
        record.evidence_json
    )

    return PostIncidentReportDetail(
        **summary.model_dump(),
        executive_summary=(
            generated.executive_summary
        ),
        incident_overview=(
            generated.incident_overview
        ),
        root_cause=generated.root_cause,
        contributing_factors=(
            generated.contributing_factors
        ),
        business_impact=(
            generated.business_impact
        ),
        technical_impact=(
            generated.technical_impact
        ),
        timeline=generated.timeline,
        investigation_findings=(
            generated.investigation_findings
        ),
        remediation_summary=(
            generated.remediation_summary
        ),
        recovery_validation=(
            generated.recovery_validation
        ),
        lessons_learned=(
            generated.lessons_learned
        ),
        evidence_gaps=(
            generated.evidence_gaps
        ),
        action_items=actions,
        review_notes=record.review_notes,
        evidence_count=len(
            evidence_values
        ),
        warnings=json.loads(
            record.warnings_json
        ),
    )


def load_latest_post_incident_report(
    session: Session,
    incident_id: str,
) -> PostIncidentReportDetail | None:
    statement = (
        select(
            PostIncidentReportRecord
        )
        .where(
            PostIncidentReportRecord
            .incident_id
            == incident_id
        )
        .order_by(
            PostIncidentReportRecord
            .version
            .desc()
        )
        .limit(1)
    )

    record = session.scalars(
        statement
    ).first()

    if record is None:
        return None

    return load_post_incident_report(
        session=session,
        report_id=record.report_id,
    )


def list_post_incident_reports(
    session: Session,
    incident_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[PostIncidentReportSummary]:
    statement = (
        select(
            PostIncidentReportRecord
        )
        .where(
            PostIncidentReportRecord
            .incident_id
            == incident_id
        )
        .order_by(
            PostIncidentReportRecord
            .version
            .desc()
        )
        .offset(offset)
        .limit(limit)
    )

    records = list(
        session.scalars(
            statement
        ).all()
    )

    return [
        _report_to_summary(
            session=session,
            record=record,
        )
        for record in records
    ]


def create_post_incident_report(
    session: Session,
    *,
    report_id: str,
    incident_id: str,
    version: int,
    provider: ExplanationProvider,
    model_name: str | None,
    prompt_version: str,
    grounding_hash: str,
    generated:
        GeneratedPostIncidentReport,
    evidence: list[GroundingEvidence],
    warnings: list[str],
) -> PostIncidentReportDetail:
    existing = load_post_incident_report(
        session=session,
        report_id=report_id,
    )

    if existing is not None:
        return existing

    now = utc_now_iso()

    record = PostIncidentReportRecord(
        report_id=report_id,
        incident_id=incident_id,
        version=version,
        title=generated.title,
        status=(
            PostIncidentReportStatus
            .DRAFT.value
        ),
        provider=provider.value,
        model_name=model_name,
        prompt_version=prompt_version,
        grounding_hash=grounding_hash,
        overall_confidence=str(
            generated.overall_confidence
        ),
        payload_json=(
            generated.model_dump_json()
        ),
        evidence_json=json.dumps(
            [
                item.model_dump(
                    mode="json"
                )
                for item in evidence
            ]
        ),
        warnings_json=json.dumps(
            warnings
        ),
        reviewer_name=None,
        review_notes=None,
        reviewed_at=None,
        approved_at=None,
        created_at=now,
        updated_at=now,
    )

    session.add(record)

    for action in generated.action_items:
        identity = (
            f"{report_id}|"
            f"{action.sequence}|"
            f"{action.title}"
        )

        digest = hashlib.sha256(
            identity.encode("utf-8")
        ).hexdigest()[:24]

        action_record = (
            ReportActionItemRecord(
                action_item_id=(
                    "report-action:"
                    f"{digest}"
                ),
                report_id=report_id,
                incident_id=incident_id,
                sequence=action.sequence,
                title=action.title,
                description=(
                    action.description
                ),
                owner_team=(
                    action.owner_team
                ),
                owner_contact=(
                    action.owner_contact
                ),
                priority=(
                    action.priority.value
                ),
                due_date=action.due_date,
                success_criteria=(
                    action.success_criteria
                ),
                evidence_ids_json=json.dumps(
                    action.evidence_ids
                ),
                status=(
                    ReportActionStatus
                    .OPEN.value
                ),
                notes=None,
                completed_at=None,
                created_at=now,
                updated_at=now,
            )
        )

        session.add(action_record)

    session.commit()

    result = load_post_incident_report(
        session=session,
        report_id=report_id,
    )

    if result is None:
        raise RuntimeError(
            "Report was saved but could "
            "not be reloaded."
        )

    return result


def update_post_incident_report(
    session: Session,
    *,
    report_id: str,
    request:
        PostIncidentReportUpdateRequest,
) -> PostIncidentReportDetail | None:
    record = session.get(
        PostIncidentReportRecord,
        report_id,
    )

    if record is None:
        return None

    values = request.model_dump(
        exclude_unset=True
    )

    if "reviewer_name" in values:
        record.reviewer_name = (
            values["reviewer_name"]
        )

    if "review_notes" in values:
        record.review_notes = (
            values["review_notes"]
        )

    if "status" in values:
        status_value = values["status"]

        record.status = (
            status_value.value
            if hasattr(
                status_value,
                "value",
            )
            else status_value
        )

        if record.status in {
            PostIncidentReportStatus
            .IN_REVIEW.value,
            PostIncidentReportStatus
            .APPROVED.value,
            PostIncidentReportStatus
            .REJECTED.value,
        }:
            record.reviewed_at = (
                utc_now_iso()
            )

        if (
            record.status
            == PostIncidentReportStatus
            .APPROVED.value
        ):
            if not record.reviewer_name:
                raise ValueError(
                    "A reviewer name is required "
                    "before approving the report."
                )

            record.approved_at = (
                utc_now_iso()
            )
        else:
            record.approved_at = None

    record.updated_at = utc_now_iso()

    session.commit()

    return load_post_incident_report(
        session=session,
        report_id=report_id,
    )


def update_report_action_item(
    session: Session,
    *,
    report_id: str,
    action_item_id: str,
    request:
        ReportActionItemUpdateRequest,
) -> PostIncidentReportDetail | None:
    action = session.get(
        ReportActionItemRecord,
        action_item_id,
    )

    if (
        action is None
        or action.report_id != report_id
    ):
        return None

    values = request.model_dump(
        exclude_unset=True
    )

    if "owner_team" in values:
        action.owner_team = (
            values["owner_team"]
        )

    if "owner_contact" in values:
        action.owner_contact = (
            values["owner_contact"]
        )

    if "due_date" in values:
        action.due_date = (
            values["due_date"]
        )

    if "notes" in values:
        action.notes = values["notes"]

    if "status" in values:
        status_value = values["status"]

        action.status = (
            status_value.value
            if hasattr(
                status_value,
                "value",
            )
            else status_value
        )

        if (
            action.status
            == ReportActionStatus
            .COMPLETED.value
        ):
            action.completed_at = (
                utc_now_iso()
            )
        else:
            action.completed_at = None

    action.updated_at = utc_now_iso()

    report = session.get(
        PostIncidentReportRecord,
        report_id,
    )

    if report:
        report.updated_at = utc_now_iso()

    session.commit()

    return load_post_incident_report(
        session=session,
        report_id=report_id,
    )