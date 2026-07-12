from fastapi import (
    APIRouter,
    Depends,
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
    create_webhook_endpoint,
    list_webhook_deliveries,
    list_webhook_endpoints,
    load_webhook_endpoint_record,
    update_webhook_endpoint,
)
from app.services.webhook_delivery import (
    create_test_event,
    deliver_event_to_endpoint,
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
    request: WebhookEndpointCreate,
    session: Session = Depends(
        get_session
    ),
) -> WebhookEndpointView:
    return create_webhook_endpoint(
        session=session,
        request=request,
    )


@router.get(
    "/webhooks",
    response_model=list[
        WebhookEndpointView
    ],
)
def get_webhooks(
    active: bool | None = None,
    session: Session = Depends(
        get_session
    ),
) -> list[WebhookEndpointView]:
    return list_webhook_endpoints(
        session=session,
        active=active,
    )


@router.patch(
    "/webhooks/{webhook_id}",
    response_model=WebhookEndpointView,
)
def patch_webhook(
    webhook_id: str,
    request: WebhookEndpointUpdate,
    session: Session = Depends(
        get_session
    ),
) -> WebhookEndpointView:
    result = update_webhook_endpoint(
        session=session,
        webhook_id=webhook_id,
        request=request,
    )

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
    request: WebhookTestRequest,
    session: Session = Depends(
        get_session
    ),
) -> WebhookDeliveryView:
    endpoint = (
        load_webhook_endpoint_record(
            session=session,
            webhook_id=webhook_id,
        )
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
        summary=request.summary,
    )

    return deliver_event_to_endpoint(
        session=session,
        endpoint=endpoint,
        event=event,
    )


@router.get(
    "/deliveries",
    response_model=list[
        WebhookDeliveryView
    ],
)
def get_deliveries(
    webhook_id: str | None = None,
    delivery_status: (
        WebhookDeliveryStatus | None
    ) = Query(
        default=None,
        alias="status",
    ),
    event_type: (
        WebhookEventType | None
    ) = None,
    limit: int = Query(
        default=200,
        ge=1,
        le=500,
    ),
    session: Session = Depends(
        get_session
    ),
) -> list[WebhookDeliveryView]:
    return list_webhook_deliveries(
        session=session,
        webhook_id=webhook_id,
        status=(
            delivery_status.value
            if delivery_status
            else None
        ),
        event_type=(
            event_type.value
            if event_type
            else None
        ),
        limit=limit,
    )