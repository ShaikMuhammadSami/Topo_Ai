import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    InvestigationPlanRecord,
    InvestigationStepRecord,
    utc_now_iso,
)
from app.models.incident_explanation import (
    ExplanationProvider,
    GroundingEvidence,
)
from app.models.investigation_plan import (
    GeneratedInvestigationPlan,
    InvestigationCommandType,
    InvestigationPlanDetail,
    InvestigationPlanStatus,
    InvestigationPlanSummary,
    InvestigationStepStatus,
    InvestigationStepUpdateRequest,
    InvestigationStepView,
)


def _step_to_view(
    record: InvestigationStepRecord,
) -> InvestigationStepView:
    return InvestigationStepView(
        step_id=record.step_id,
        plan_id=record.plan_id,
        incident_id=record.incident_id,
        sequence=record.sequence,
        title=record.title,
        objective=record.objective,
        command_type=(
            InvestigationCommandType(
                record.command_type
            )
        ),
        command=record.command,
        target=record.target,
        expected_observation=(
            record.expected_observation
        ),
        success_criteria=(
            record.success_criteria
        ),
        failure_indication=(
            record.failure_indication
        ),
        evidence_ids=json.loads(
            record.evidence_ids_json
        ),
        status=InvestigationStepStatus(
            record.status
        ),
        finding=record.finding,
        responder_notes=(
            record.responder_notes
        ),
        completed_at=record.completed_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _load_step_records(
    session: Session,
    plan_id: str,
) -> list[InvestigationStepRecord]:
    statement = (
        select(
            InvestigationStepRecord
        )
        .where(
            InvestigationStepRecord.plan_id
            == plan_id
        )
        .order_by(
            InvestigationStepRecord
            .sequence
            .asc()
        )
    )

    return list(
        session.scalars(
            statement
        ).all()
    )


def _plan_to_summary(
    session: Session,
    record: InvestigationPlanRecord,
) -> InvestigationPlanSummary:
    steps = _load_step_records(
        session=session,
        plan_id=record.plan_id,
    )

    completed = sum(
        step.status
        in {
            InvestigationStepStatus
            .COMPLETED.value,
            InvestigationStepStatus
            .SKIPPED.value,
        }
        for step in steps
    )

    blocked = sum(
        step.status
        == InvestigationStepStatus
        .BLOCKED.value
        for step in steps
    )

    return InvestigationPlanSummary(
        plan_id=record.plan_id,
        incident_id=record.incident_id,
        title=record.title,
        objective=record.objective,
        provider=ExplanationProvider(
            record.provider
        ),
        model_name=record.model_name,
        prompt_version=(
            record.prompt_version
        ),
        grounding_hash=(
            record.grounding_hash
        ),
        status=InvestigationPlanStatus(
            record.status
        ),
        overall_confidence=float(
            record.overall_confidence
        ),
        step_count=len(steps),
        completed_step_count=completed,
        blocked_step_count=blocked,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def load_investigation_plan(
    session: Session,
    plan_id: str,
) -> InvestigationPlanDetail | None:
    record = session.get(
        InvestigationPlanRecord,
        plan_id,
    )

    if record is None:
        return None

    summary = _plan_to_summary(
        session=session,
        record=record,
    )

    steps = [
        _step_to_view(step)
        for step in _load_step_records(
            session=session,
            plan_id=plan_id,
        )
    ]

    evidence_values = json.loads(
        record.evidence_json
    )

    return InvestigationPlanDetail(
        **summary.model_dump(),
        incident_summary=(
            record.incident_summary
        ),
        evidence_gaps=json.loads(
            record.evidence_gaps_json
        ),
        warnings=json.loads(
            record.warnings_json
        ),
        evidence_count=len(
            evidence_values
        ),
        steps=steps,
    )


def list_incident_investigation_plans(
    session: Session,
    incident_id: str,
    limit: int = 50,
) -> list[InvestigationPlanSummary]:
    statement = (
        select(
            InvestigationPlanRecord
        )
        .where(
            InvestigationPlanRecord
            .incident_id
            == incident_id
        )
        .order_by(
            InvestigationPlanRecord
            .created_at
            .desc()
        )
        .limit(limit)
    )

    records = list(
        session.scalars(
            statement
        ).all()
    )

    return [
        _plan_to_summary(
            session=session,
            record=record,
        )
        for record in records
    ]


def create_investigation_plan(
    session: Session,
    *,
    plan_id: str,
    incident_id: str,
    provider: ExplanationProvider,
    model_name: str | None,
    prompt_version: str,
    grounding_hash: str,
    generated:
        GeneratedInvestigationPlan,
    evidence: list[GroundingEvidence],
    warnings: list[str],
) -> InvestigationPlanDetail:
    existing = load_investigation_plan(
        session=session,
        plan_id=plan_id,
    )

    if existing is not None:
        return existing

    now = utc_now_iso()

    plan_record = InvestigationPlanRecord(
        plan_id=plan_id,
        incident_id=incident_id,
        title=generated.title,
        objective=generated.objective,
        incident_summary=(
            generated.incident_summary
        ),
        provider=provider.value,
        model_name=model_name,
        prompt_version=prompt_version,
        grounding_hash=grounding_hash,
        status=(
            InvestigationPlanStatus
            .ACTIVE.value
        ),
        overall_confidence=str(
            generated.overall_confidence
        ),
        evidence_gaps_json=json.dumps(
            generated.evidence_gaps
        ),
        warnings_json=json.dumps(
            warnings
        ),
        evidence_json=json.dumps(
            [
                item.model_dump(
                    mode="json"
                )
                for item in evidence
            ]
        ),
        payload_json=(
            generated.model_dump_json()
        ),
        created_at=now,
        updated_at=now,
    )

    session.add(plan_record)

    for step in generated.steps:
        step_hash = hashlib.sha256(
            (
                f"{plan_id}|"
                f"{step.sequence}|"
                f"{step.title}"
            ).encode("utf-8")
        ).hexdigest()[:24]

        step_record = (
            InvestigationStepRecord(
                step_id=(
                    "investigation-step:"
                    f"{step_hash}"
                ),
                plan_id=plan_id,
                incident_id=incident_id,
                sequence=step.sequence,
                title=step.title,
                objective=step.objective,
                command_type=(
                    step.command_type.value
                ),
                command=step.command,
                target=step.target,
                expected_observation=(
                    step.expected_observation
                ),
                success_criteria=(
                    step.success_criteria
                ),
                failure_indication=(
                    step.failure_indication
                ),
                evidence_ids_json=json.dumps(
                    step.evidence_ids
                ),
                status=(
                    InvestigationStepStatus
                    .PENDING.value
                ),
                finding=None,
                responder_notes=None,
                completed_at=None,
                created_at=now,
                updated_at=now,
            )
        )

        session.add(step_record)

    session.commit()

    result = load_investigation_plan(
        session=session,
        plan_id=plan_id,
    )

    if result is None:
        raise RuntimeError(
            "Investigation plan was saved "
            "but could not be reloaded."
        )

    return result


def update_investigation_step(
    session: Session,
    *,
    plan_id: str,
    step_id: str,
    request:
        InvestigationStepUpdateRequest,
) -> InvestigationPlanDetail | None:
    step = session.get(
        InvestigationStepRecord,
        step_id,
    )

    if (
        step is None
        or step.plan_id != plan_id
    ):
        return None

    values = request.model_dump(
        exclude_unset=True
    )

    if "status" in values:
        status_value = values["status"]

        step.status = (
            status_value.value
            if hasattr(
                status_value,
                "value",
            )
            else status_value
        )

        if (
            step.status
            == InvestigationStepStatus
            .COMPLETED.value
        ):
            step.completed_at = utc_now_iso()

        elif (
            step.status
            != InvestigationStepStatus
            .COMPLETED.value
        ):
            step.completed_at = None

    if "finding" in values:
        step.finding = values["finding"]

    if "responder_notes" in values:
        step.responder_notes = (
            values["responder_notes"]
        )

    step.updated_at = utc_now_iso()

    plan = session.get(
        InvestigationPlanRecord,
        plan_id,
    )

    if plan is None:
        return None

    session.flush()

    steps = _load_step_records(
        session=session,
        plan_id=plan_id,
    )

    completed_states = {
        InvestigationStepStatus
        .COMPLETED.value,
        InvestigationStepStatus
        .SKIPPED.value,
    }

    if (
        steps
        and all(
            item.status
            in completed_states
            for item in steps
        )
    ):
        plan.status = (
            InvestigationPlanStatus
            .COMPLETED.value
        )
    else:
        plan.status = (
            InvestigationPlanStatus
            .ACTIVE.value
        )

    plan.updated_at = utc_now_iso()

    session.commit()

    return load_investigation_plan(
        session=session,
        plan_id=plan_id,
    )