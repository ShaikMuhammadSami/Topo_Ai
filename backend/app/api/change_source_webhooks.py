from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from sqlalchemy.orm import Session

from app.db.database import (
    get_session,
)
from app.models.change_sources import (
    ChangeSourceDeliveryReceipt,
)
from app.repositories.change_source_repository import (
    load_change_source_for_authentication,
)
from app.services.change_source_ingest import (
    ingest_change_source_webhook,
)
from app.services.webhook_security import (
    WebhookAuthenticationError,
    WebhookAuthenticationUnavailableError,
)


router = APIRouter(
    prefix=(
        "/api/v1/"
        "change-source-webhooks"
    ),
    tags=[
        "change-source-webhooks"
    ],
)


@router.post(
    "/{source_id}",
    response_model=(
        ChangeSourceDeliveryReceipt
    ),
)
async def receive(
    source_id: str,
    request: Request,
    session: Session = Depends(
        get_session
    ),
) -> ChangeSourceDeliveryReceipt:
    source = load_change_source_for_authentication(
        session,
        source_id=source_id,
    )

    if source is None:
        raise HTTPException(
            status_code=401,
            detail="Change-source authentication failed.",
        )

    body = await request.body()

    headers = {
        str(key): str(value)
        for key, value
        in request.headers.items()
    }

    try:
        return (
            ingest_change_source_webhook(
                session,
                source=source,
                body=body,
                headers=headers,
                secret_store=getattr(request.app.state, "secret_store", None),
            )
        )

    except WebhookAuthenticationUnavailableError:
        raise HTTPException(
            status_code=503,
            detail="Change-source authentication is unavailable.",
        )

    except WebhookAuthenticationError:
        raise HTTPException(
            status_code=401,
            detail=(
                "Change-source "
                "authentication failed."
            ),
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Authenticated change "
                "source delivery failed."
            ),
        ) from exc
