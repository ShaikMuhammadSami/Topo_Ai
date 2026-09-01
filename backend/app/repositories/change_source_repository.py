from __future__ import annotations
from app.repositories.tenant_scope import tenant_get, tenant_value, tenant_commit
from app.repositories.tenant_scope import (
    DomainTenant,
    tenant_predicate,
)

import hashlib
import json
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

def new_change_source_id(
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
        credential_configured=bool(record.secret_ref),
        credential_status="configured" if record.secret_ref else "unconfigured",
        credential_updated_at=record.updated_at if record.secret_ref else None,
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
    tenant_id: DomainTenant,
) -> ChangeSourceView:
    raise ValueError("SecretStore consumer service is required.")


def load_change_source(
    session: Session,
    *,
    source_id: str,
    tenant_id: DomainTenant,
) -> ChangeSourceRecord | None:
    return tenant_get(
        session, ChangeSourceRecord, source_id, tenant_id=tenant_id,
    )


def get_change_source(
    session: Session,
    *,
    source_id: str,
    tenant_id: DomainTenant,
) -> ChangeSourceView | None:
    record = load_change_source(
        session,
        source_id=source_id,
        tenant_id=tenant_id,
    )

    if record is None:
        return None

    return change_source_view(record)


def list_change_sources(
    session: Session,
    *,
    tenant_id: DomainTenant,
) -> list[ChangeSourceView]:
    statement = (
        select(ChangeSourceRecord).where(
                tenant_predicate(ChangeSourceRecord, tenant_id)
            )
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
    tenant_id: DomainTenant,
) -> ChangeSourceView:
    raise ValueError("SecretStore consumer service is required.")


def list_deliveries(
    session: Session,
    *,
    source_id: str | None = None,
    status: str | None = None,
    limit: int = 200,
    tenant_id: DomainTenant,
) -> list[ChangeSourceDeliveryView]:
    statement = select(ChangeSourceDeliveryRecord).where(
        tenant_predicate(ChangeSourceDeliveryRecord, tenant_id)
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
    tenant_id: DomainTenant,
) -> list[ChangeSourceDeadLetterView]:
    statement = select(ChangeSourceDeadLetterRecord).where(
        tenant_predicate(ChangeSourceDeadLetterRecord, tenant_id)
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


def load_change_source_for_authentication(
    session: Session, *, source_id: str,
) -> ChangeSourceRecord | None:
    """MACHINE_AUTH_DERIVATION_LOOKUP: exact provider receiver ID only.

    Not an administration loader. Caller must verify the provider credential
    before parsing, persisting, or deriving the active tenant from this row.
    """
    return session.scalar(
        select(ChangeSourceRecord).where(ChangeSourceRecord.source_id == source_id)
    )
