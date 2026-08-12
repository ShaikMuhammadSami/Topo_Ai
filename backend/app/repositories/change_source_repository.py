from __future__ import annotations

import hashlib
import json
import re
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ChangeSourceDeadLetterRecord,
    ChangeSourceDeliveryRecord,
    ChangeSourceRecord,
    utc_now_iso,
)
from app.models.change_sources import (
    ChangeSourceCreate,
    ChangeSourceDeadLetterView,
    ChangeSourceDeliveryView,
    ChangeSourceType,
    ChangeSourceUpdate,
    ChangeSourceView,
)


SECRET_REF_PATTERN = re.compile(
    r"^[A-Z][A-Z0-9_]{2,254}$"
)


def _source_id(
    source_type: str,
    name: str,
) -> str:
    raw = (
        f"{source_type}|"
        f"{name}|"
        f"{uuid4().hex}"
    )

    digest = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:24]

    return (
        f"change-source:"
        f"{source_type}:"
        f"{digest}"
    )


def _json_dict(
    value: str,
) -> dict:
    try:
        result = json.loads(
            value or "{}"
        )

    except json.JSONDecodeError:
        return {}

    return (
        result
        if isinstance(result, dict)
        else {}
    )


def change_source_view(
    record: ChangeSourceRecord,
) -> ChangeSourceView:
    return ChangeSourceView(
        source_id=record.source_id,
        name=record.name,
        source_type=(
            ChangeSourceType(
                record.source_type
            )
        ),
        enabled=record.enabled,
        secret_ref=(
            record.secret_ref or ""
        ),
        status=record.status,
        config=_json_dict(
            record.config_json
        ),
        filters=_json_dict(
            record.filters_json
        ),
        delivery_count=(
            record.delivery_count
        ),
        failure_count=(
            record.failure_count
        ),
        last_event_at=(
            record.last_event_at
        ),
        last_success_at=(
            record.last_success_at
        ),
        last_error_at=(
            record.last_error_at
        ),
        last_error=record.last_error,
        receiver_path=(
            "/api/v1/"
            "change-source-webhooks/"
            + record.source_id
        ),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def delivery_view(
    record: ChangeSourceDeliveryRecord,
) -> ChangeSourceDeliveryView:
    try:
        event_ids = json.loads(
            record.event_ids_json
            or "[]"
        )

    except json.JSONDecodeError:
        event_ids = []

    return ChangeSourceDeliveryView(
        delivery_id=(
            record.delivery_id
        ),
        source_id=record.source_id,
        source_delivery_id=(
            record.source_delivery_id
        ),
        event_type=record.event_type,
        status=record.status,
        payload_sha256=(
            record.payload_sha256
        ),
        event_ids=event_ids,
        error=record.error,
        received_at=record.received_at,
        processed_at=(
            record.processed_at
        ),
    )


def dead_letter_view(
    record: ChangeSourceDeadLetterRecord,
) -> ChangeSourceDeadLetterView:
    return ChangeSourceDeadLetterView(
        dead_letter_id=(
            record.dead_letter_id
        ),
        source_id=record.source_id,
        delivery_id=(
            record.delivery_id
        ),
        event_type=record.event_type,
        reason=record.reason,
        attempt_count=(
            record.attempt_count
        ),
        status=record.status,
        last_attempt_at=(
            record.last_attempt_at
        ),
        replayed_at=(
            record.replayed_at
        ),
        created_at=record.created_at,
    )


def create_change_source(
    session: Session,
    *,
    request: ChangeSourceCreate,
) -> ChangeSourceView:
    if not SECRET_REF_PATTERN.fullmatch(
        request.secret_ref
    ):
        raise ValueError(
            "secret_ref must be an "
            "environment-variable name."
        )

    now = utc_now_iso()

    record = ChangeSourceRecord(
        source_id=_source_id(
            request.source_type.value,
            request.name,
        ),
        name=request.name,
        source_type=(
            request.source_type.value
        ),
        enabled=request.enabled,
        secret_ref=request.secret_ref,
        config_json=json.dumps(
            request.config,
            default=str,
        ),
        filters_json=json.dumps(
            request.filters,
            default=str,
        ),
        status=(
            "configured"
            if request.enabled
            else "disabled"
        ),
        delivery_count=0,
        failure_count=0,
        created_at=now,
        updated_at=now,
    )

    session.add(record)
    session.commit()

    return change_source_view(
        record
    )


def load_change_source(
    session: Session,
    *,
    source_id: str,
) -> ChangeSourceRecord | None:
    return session.get(
        ChangeSourceRecord,
        source_id,
    )


def get_change_source(
    session: Session,
    *,
    source_id: str,
) -> ChangeSourceView | None:
    record = load_change_source(
        session,
        source_id=source_id,
    )

    if record is None:
        return None

    return change_source_view(record)


def list_change_sources(
    session: Session,
) -> list[ChangeSourceView]:
    statement = (
        select(ChangeSourceRecord)
        .order_by(
            ChangeSourceRecord.name.asc()
        )
    )

    return [
        change_source_view(record)
        for record
        in session.scalars(
            statement
        ).all()
    ]


def update_change_source(
    session: Session,
    *,
    source_id: str,
    request: ChangeSourceUpdate,
) -> ChangeSourceView:
    record = load_change_source(
        session,
        source_id=source_id,
    )

    if record is None:
        raise ValueError(
            "Change source not found."
        )

    if request.secret_ref is not None:
        if not SECRET_REF_PATTERN.fullmatch(
            request.secret_ref
        ):
            raise ValueError(
                "Invalid secret_ref."
            )

        record.secret_ref = (
            request.secret_ref
        )

    if request.config is not None:
        record.config_json = json.dumps(
            request.config,
            default=str,
        )

    if request.filters is not None:
        record.filters_json = json.dumps(
            request.filters,
            default=str,
        )

    if request.enabled is not None:
        record.enabled = (
            request.enabled
        )

        record.status = (
            "configured"
            if request.enabled
            else "disabled"
        )

    record.updated_at = utc_now_iso()

    session.commit()

    return change_source_view(record)


def list_deliveries(
    session: Session,
    *,
    source_id: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[ChangeSourceDeliveryView]:
    statement = select(
        ChangeSourceDeliveryRecord
    )

    if source_id:
        statement = statement.where(
            ChangeSourceDeliveryRecord
            .source_id
            == source_id
        )

    if status:
        statement = statement.where(
            ChangeSourceDeliveryRecord
            .status
            == status
        )

    statement = (
        statement
        .order_by(
            ChangeSourceDeliveryRecord
            .received_at
            .desc()
        )
        .limit(limit)
    )

    return [
        delivery_view(record)
        for record
        in session.scalars(
            statement
        ).all()
    ]


def list_dead_letters(
    session: Session,
    *,
    source_id: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[
    ChangeSourceDeadLetterView
]:
    statement = select(
        ChangeSourceDeadLetterRecord
    )

    if source_id:
        statement = statement.where(
            ChangeSourceDeadLetterRecord
            .source_id
            == source_id
        )

    if status:
        statement = statement.where(
            ChangeSourceDeadLetterRecord
            .status
            == status
        )

    statement = (
        statement
        .order_by(
            ChangeSourceDeadLetterRecord
            .created_at
            .desc()
        )
        .limit(limit)
    )

    return [
        dead_letter_view(record)
        for record
        in session.scalars(
            statement
        ).all()
    ]