import json
from uuid import uuid4

from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.orm import Session

from app.db.models import (
    CopilotMessageRecord,
    CopilotSessionRecord,
    utc_now_iso,
)
from app.models.incident_copilot import (
    CopilotAnswerStatus,
    CopilotMessageRole,
    CopilotMessageView,
    CopilotSessionDetail,
    CopilotSessionStatus,
    CopilotSessionSummary,
)
from app.models.incident_explanation import (
    ExplanationProvider,
    GroundingEvidence,
)


def _message_to_view(
    record: CopilotMessageRecord,
) -> CopilotMessageView:
    return CopilotMessageView(
        message_id=record.message_id,
        session_id=record.session_id,
        incident_id=record.incident_id,
        role=CopilotMessageRole(
            record.role
        ),
        content=record.content,
        provider=(
            ExplanationProvider(
                record.provider
            )
            if record.provider
            else None
        ),
        answer_status=(
            CopilotAnswerStatus(
                record.answer_status
            )
            if record.answer_status
            else None
        ),
        confidence=(
            float(record.confidence)
            if record.confidence
            is not None
            else None
        ),
        evidence_ids=json.loads(
            record.evidence_ids_json
        ),
        suggested_questions=json.loads(
            record
            .suggested_questions_json
        ),
        warning=record.warning,
        created_at=record.created_at,
    )


def _message_count(
    session: Session,
    session_id: str,
) -> int:
    statement = (
        select(
            func.count(
                CopilotMessageRecord
                .message_id
            )
        )
        .where(
            CopilotMessageRecord
            .session_id
            == session_id
        )
    )

    return int(
        session.scalar(statement) or 0
    )


def _session_to_summary(
    session: Session,
    record: CopilotSessionRecord,
) -> CopilotSessionSummary:
    return CopilotSessionSummary(
        session_id=record.session_id,
        incident_id=record.incident_id,
        title=record.title,
        provider=ExplanationProvider(
            record.provider
        ),
        model_name=record.model_name,
        status=CopilotSessionStatus(
            record.status
        ),
        message_count=_message_count(
            session=session,
            session_id=record.session_id,
        ),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def create_copilot_session_record(
    session: Session,
    *,
    incident_id: str,
    title: str,
    provider: ExplanationProvider,
    model_name: str | None,
) -> CopilotSessionDetail:
    now = utc_now_iso()

    record = CopilotSessionRecord(
        session_id=(
            f"copilot-session:"
            f"{uuid4().hex}"
        ),
        incident_id=incident_id,
        title=title,
        provider=provider.value,
        model_name=model_name,
        status=(
            CopilotSessionStatus
            .ACTIVE.value
        ),
        created_at=now,
        updated_at=now,
    )

    session.add(record)
    session.commit()
    session.refresh(record)

    summary = _session_to_summary(
        session=session,
        record=record,
    )

    return CopilotSessionDetail(
        **summary.model_dump(),
        messages=[],
    )


def load_copilot_session_record(
    session: Session,
    session_id: str,
) -> CopilotSessionRecord | None:
    return session.get(
        CopilotSessionRecord,
        session_id,
    )


def list_copilot_messages(
    session: Session,
    session_id: str,
    limit: int = 200,
) -> list[CopilotMessageView]:
    statement = (
        select(
            CopilotMessageRecord
        )
        .where(
            CopilotMessageRecord
            .session_id
            == session_id
        )
        .order_by(
            CopilotMessageRecord
            .created_at
            .asc(),
            CopilotMessageRecord
            .message_id
            .asc(),
        )
        .limit(limit)
    )

    records = list(
        session.scalars(
            statement
        ).all()
    )

    return [
        _message_to_view(record)
        for record in records
    ]


def load_copilot_session_detail(
    session: Session,
    session_id: str,
) -> CopilotSessionDetail | None:
    record = load_copilot_session_record(
        session=session,
        session_id=session_id,
    )

    if record is None:
        return None

    summary = _session_to_summary(
        session=session,
        record=record,
    )

    return CopilotSessionDetail(
        **summary.model_dump(),
        messages=list_copilot_messages(
            session=session,
            session_id=session_id,
        ),
    )


def list_incident_copilot_sessions(
    session: Session,
    incident_id: str,
    limit: int = 50,
) -> list[CopilotSessionSummary]:
    statement = (
        select(
            CopilotSessionRecord
        )
        .where(
            CopilotSessionRecord
            .incident_id
            == incident_id
        )
        .order_by(
            CopilotSessionRecord
            .updated_at
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
        _session_to_summary(
            session=session,
            record=record,
        )
        for record in records
    ]


def save_copilot_message(
    session: Session,
    *,
    session_id: str,
    incident_id: str,
    role: CopilotMessageRole,
    content: str,
    provider: (
        ExplanationProvider | None
    ) = None,
    answer_status: (
        CopilotAnswerStatus | None
    ) = None,
    confidence: float | None = None,
    evidence: list[
        GroundingEvidence
    ] | None = None,
    evidence_ids: list[str] | None = None,
    suggested_questions: (
        list[str] | None
    ) = None,
    warning: str | None = None,
) -> CopilotMessageView:
    now = utc_now_iso()

    record = CopilotMessageRecord(
        message_id=(
            f"copilot-message:"
            f"{uuid4().hex}"
        ),
        session_id=session_id,
        incident_id=incident_id,
        role=role.value,
        content=content,
        provider=(
            provider.value
            if provider
            else None
        ),
        answer_status=(
            answer_status.value
            if answer_status
            else None
        ),
        confidence=(
            str(confidence)
            if confidence is not None
            else None
        ),
        evidence_ids_json=json.dumps(
            evidence_ids or []
        ),
        evidence_json=json.dumps(
            [
                item.model_dump(
                    mode="json"
                )
                for item in (
                    evidence or []
                )
            ]
        ),
        suggested_questions_json=(
            json.dumps(
                suggested_questions or []
            )
        ),
        warning=warning,
        created_at=now,
    )

    session.add(record)

    session_record = (
        load_copilot_session_record(
            session=session,
            session_id=session_id,
        )
    )

    if session_record:
        session_record.updated_at = now

    session.commit()
    session.refresh(record)

    return _message_to_view(record)