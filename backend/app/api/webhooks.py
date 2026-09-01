from app.security.tenant_context import TenantContext, require_tenant_context
from fastapi import Depends, Header, Request
from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.db.database import (
    get_session,
)
from app.models.webhooks import (
    WebhookDeliveryStatus,
    WebhookDeliveryView,
    WebhookEndpointCreate,
    WebhookEndpointUpdate,
    WebhookEndpointView,
    WebhookEventType,
    WebhookTestRequest,
)
from app.repositories.webhook_repository import (
    list_webhook_deliveries,
    list_webhook_endpoints,
    load_webhook_endpoint_record,
)
from app.services.webhook_delivery import (
    create_test_event,
    deliver_event_to_endpoint,
)
from app.services.secret_consumers import (
    SecretConsumerError,
    create_webhook_endpoint_secure,
    update_webhook_endpoint_secure,
)

router = APIRouter(
    prefix="/api/v1/integrations",
    tags=["integrations"],
)


@router.post(
    "/webhooks",
    response_model=WebhookEndpointView,
    status_code=status.HTTP_201_CREATED,
)
def create_webhook(
    payload: WebhookEndpointCreate,
    request: Request,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> WebhookEndpointView:
    try:
        store = getattr(request.app.state, "secret_store", None)
        if store is None:
            raise SecretConsumerError("Credential service is unavailable.", 503)
        return create_webhook_endpoint_secure(
            session=session, request=payload, tenant_id=tenant_context.tenant_id,
            actor=tenant_context.authenticated_subject, store=store,
        )
    except SecretConsumerError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get(
    "/webhooks",
    response_model=list[WebhookEndpointView],
)
def get_webhooks(
    active: bool | None = None,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> list[WebhookEndpointView]:
    return list_webhook_endpoints(
        session=session,
        active=active,
        tenant_id=tenant_context.tenant_id,
    )


@router.patch(
    "/webhooks/{webhook_id}",
    response_model=WebhookEndpointView,
)
def patch_webhook(
    webhook_id: str,
    payload: WebhookEndpointUpdate,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> WebhookEndpointView:
    try:
        store = getattr(request.app.state, "secret_store", None)
        if store is None:
            raise SecretConsumerError("Credential service is unavailable.", 503)
        result = update_webhook_endpoint_secure(
            session=session, webhook_id=webhook_id, request=payload,
            tenant_id=tenant_context.tenant_id,
            actor=tenant_context.authenticated_subject, store=store,
            idempotency_key=idempotency_key,
        )
    except SecretConsumerError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Webhook not found: "
                f"{webhook_id}"
            ),
        )

    return result


@router.post(
    "/webhooks/{webhook_id}/test",
    response_model=WebhookDeliveryView,
)
def test_webhook(
    webhook_id: str,
    payload: WebhookTestRequest,
    request: Request,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> WebhookDeliveryView:
    endpoint = load_webhook_endpoint_record(
        session=session,
        webhook_id=webhook_id,
        tenant_id=tenant_context.tenant_id,
    )

    if endpoint is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Webhook not found: "
                f"{webhook_id}"
            ),
        )

    event = create_test_event(
        webhook_id=webhook_id,
        summary=payload.summary,
    )

    return deliver_event_to_endpoint(
        session=session,
        endpoint=endpoint,
        event=event,
        tenant_id=tenant_context.tenant_id,
        secret_store=getattr(request.app.state, "secret_store", None),
    )


@router.get(
    "/deliveries",
    response_model=list[WebhookDeliveryView],
)
def get_deliveries(
    webhook_id: str | None = None,
    delivery_status: WebhookDeliveryStatus | None = Query(
        default=None,
        alias="status",
    ),
    event_type: WebhookEventType | None = None,
    limit: int = Query(
        default=200,
        ge=1,
        le=500,
    ),
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> list[WebhookDeliveryView]:
    return list_webhook_deliveries(
        session=session,
        webhook_id=webhook_id,
        status=(delivery_status.value if delivery_status else None),
        event_type=(event_type.value if event_type else None),
        limit=limit,
        tenant_id=tenant_context.tenant_id,
    )
