from app.repositories.tenant_scope import (
    tenant_commit,
    DomainTenant,
    tenant_value,
    tenant_predicate,
    tenant_get,
    require_record_owner,
)
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    WebhookDeliveryRecord,
    WebhookEndpointRecord,
    utc_now_iso,
)
from app.models.webhooks import (
    WebhookDeliveryStatus,
    WebhookDeliveryView,
    WebhookEndpointCreate,
    WebhookEndpointUpdate,
    WebhookEndpointView,
    WebhookEventType,
)


def _endpoint_to_view(
    record: WebhookEndpointRecord,
) -> WebhookEndpointView:
    return WebhookEndpointView(
        webhook_id=record.webhook_id,
        name=record.name,
        url=record.url,
        event_types=[
            WebhookEventType(value)
            for value in json.loads(
                record.event_types_json
            )
        ],
        headers=json.loads(
            record.headers_json
        ),
        has_signing_secret=bool(
            record.signing_secret
        ),
        active=record.active,
        timeout_seconds=(
            record.timeout_seconds
        ),
        max_attempts=record.max_attempts,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _delivery_to_view(
    record: WebhookDeliveryRecord,
    webhook_name: str | None = None,
) -> WebhookDeliveryView:
    return WebhookDeliveryView(
        delivery_id=record.delivery_id,
        webhook_id=record.webhook_id,
        webhook_name=webhook_name,
        event_id=record.event_id,
        event_type=WebhookEventType(
            record.event_type
        ),
        resource_type=(
            record.resource_type
        ),
        resource_id=record.resource_id,
        status=WebhookDeliveryStatus(
            record.status
        ),
        attempt_count=record.attempt_count,
        response_status=(
            record.response_status
        ),
        response_body=(
            record.response_body
        ),
        error_message=(
            record.error_message
        ),
        requested_at=record.requested_at,
        completed_at=record.completed_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def create_webhook_endpoint(
    session: Session,
    request: WebhookEndpointCreate,
    *,
    tenant_id: DomainTenant,
) -> WebhookEndpointView:
    now = utc_now_iso()

    record = WebhookEndpointRecord(
        webhook_id=(f"webhook:{uuid4().hex}"),
        name=request.name,
        url=request.url,
        event_types_json=json.dumps([value.value for value in request.event_types]),
        headers_json=json.dumps(request.headers),
        signing_secret=(request.signing_secret),
        active=request.active,
        timeout_seconds=(request.timeout_seconds),
        max_attempts=(request.max_attempts),
        created_at=now,
        updated_at=now,
        tenant_id=tenant_value(tenant_id),
    )

    session.add(record)
    tenant_commit(session, tenant_id=tenant_id)
    session.refresh(record)

    return _endpoint_to_view(record)


def load_webhook_endpoint_record(
    session: Session,
    webhook_id: str,
    *,
    tenant_id: DomainTenant,
) -> WebhookEndpointRecord | None:
    return tenant_get(
        session,
        WebhookEndpointRecord,
        webhook_id,
        tenant_id=tenant_id,
    )


def load_webhook_endpoint(
    session: Session,
    webhook_id: str,
    *,
    tenant_id: DomainTenant,
) -> WebhookEndpointView | None:
    record = load_webhook_endpoint_record(
        session=session,
        webhook_id=webhook_id,
        tenant_id=tenant_id,
    )

    if record is None:
        return None

    return _endpoint_to_view(record)


def list_webhook_endpoint_records(
    session: Session,
    active: bool | None = None,
    *,
    tenant_id: DomainTenant,
) -> list[WebhookEndpointRecord]:
    statement = select(WebhookEndpointRecord).where(
        tenant_predicate(WebhookEndpointRecord, tenant_id)
    )

    if active is not None:
        statement = statement.where(
            WebhookEndpointRecord.active
            == active
        )

    statement = statement.order_by(
        WebhookEndpointRecord
        .updated_at
        .desc()
    )

    return list(
        session.scalars(
            statement
        ).all()
    )


def list_webhook_endpoints(
    session: Session,
    active: bool | None = None,
    *,
    tenant_id: DomainTenant,
) -> list[WebhookEndpointView]:
    return [
        _endpoint_to_view(record)
        for record in list_webhook_endpoint_records(
            session=session,
            active=active,
            tenant_id=tenant_id,
        )
    ]


def update_webhook_endpoint(
    session: Session,
    webhook_id: str,
    request: WebhookEndpointUpdate,
    *,
    tenant_id: DomainTenant,
) -> WebhookEndpointView | None:
    record = load_webhook_endpoint_record(
        session=session,
        webhook_id=webhook_id,
        tenant_id=tenant_id,
    )

    if record is None:
        return None

    values = request.model_dump(
        exclude_unset=True
    )

    if "name" in values:
        record.name = values["name"]

    if "url" in values:
        record.url = values["url"]

    if "event_types" in values:
        record.event_types_json = (
            json.dumps(
                [
                    value.value
                    if hasattr(value, "value")
                    else value
                    for value in
                    values["event_types"]
                ]
            )
        )

    if "headers" in values:
        record.headers_json = json.dumps(
            values["headers"]
        )

    if "signing_secret" in values:
        record.signing_secret = (
            values["signing_secret"]
        )

    if "active" in values:
        record.active = values["active"]

    if "timeout_seconds" in values:
        record.timeout_seconds = (
            values["timeout_seconds"]
        )

    if "max_attempts" in values:
        record.max_attempts = (
            values["max_attempts"]
        )

    record.updated_at = utc_now_iso()

    tenant_commit(session, tenant_id=tenant_id)
    session.refresh(record)

    return _endpoint_to_view(record)


def find_delivery_record(
    session: Session,
    webhook_id: str,
    event_id: str,
    *,
    tenant_id: DomainTenant,
) -> WebhookDeliveryRecord | None:
    statement = (
        select(WebhookDeliveryRecord)
        .where(tenant_predicate(WebhookDeliveryRecord, tenant_id))
        .where(
            WebhookDeliveryRecord.webhook_id == webhook_id,
            WebhookDeliveryRecord.event_id == event_id,
        )
    )

    return session.scalars(
        statement
    ).first()


def save_delivery_result(
    session: Session,
    record: WebhookDeliveryRecord,
    *,
    tenant_id: DomainTenant,
) -> WebhookDeliveryView:
    require_record_owner(record, tenant_id=tenant_id)
    existing = find_delivery_record(
        session=session,
        webhook_id=record.webhook_id,
        event_id=record.event_id,
        tenant_id=tenant_id,
    )

    if existing is None:
        session.add(record)
        tenant_commit(session, tenant_id=tenant_id)
        session.refresh(record)

        endpoint = load_webhook_endpoint_record(
            session=session,
            webhook_id=(record.webhook_id),
            tenant_id=tenant_id,
        )

        return _delivery_to_view(
            record,
            endpoint.name
            if endpoint
            else None,
        )

    existing.status = record.status
    existing.attempt_count = (
        record.attempt_count
    )
    existing.response_status = (
        record.response_status
    )
    existing.response_body = (
        record.response_body
    )
    existing.error_message = (
        record.error_message
    )
    existing.requested_at = (
        record.requested_at
    )
    existing.completed_at = (
        record.completed_at
    )
    existing.payload_json = (
        record.payload_json
    )
    existing.updated_at = utc_now_iso()

    tenant_commit(session, tenant_id=tenant_id)
    session.refresh(existing)

    endpoint = load_webhook_endpoint_record(
        session=session,
        webhook_id=existing.webhook_id,
        tenant_id=tenant_id,
    )

    return _delivery_to_view(
        existing,
        endpoint.name
        if endpoint
        else None,
    )


def list_webhook_deliveries(
    session: Session,
    webhook_id: str | None = None,
    status: str | None = None,
    event_type: str | None = None,
    limit: int = 200,
    *,
    tenant_id: DomainTenant,
) -> list[WebhookDeliveryView]:
    statement = select(WebhookDeliveryRecord).where(
        tenant_predicate(WebhookDeliveryRecord, tenant_id)
    )

    if webhook_id:
        statement = statement.where(
            WebhookDeliveryRecord.webhook_id
            == webhook_id
        )

    if status:
        statement = statement.where(
            WebhookDeliveryRecord.status
            == status
        )

    if event_type:
        statement = statement.where(
            WebhookDeliveryRecord.event_type
            == event_type
        )

    statement = (
        statement
        .order_by(
            WebhookDeliveryRecord
            .requested_at
            .desc()
        )
        .limit(limit)
    )

    records = list(
        session.scalars(
            statement
        ).all()
    )

    endpoint_names = {
        endpoint.webhook_id: endpoint.name
        for endpoint in list_webhook_endpoint_records(
            session=session,
            active=None,
            tenant_id=tenant_id,
        )
    }

    return [
        _delivery_to_view(
            record,
            endpoint_names.get(
                record.webhook_id
            ),
        )
        for record in records
    ]
