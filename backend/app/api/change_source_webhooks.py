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


PROVIDER_WEBHOOK_MAX_BODY_BYTES = 1024 * 1024
_PAYLOAD_TOO_LARGE_DETAIL = "Provider webhook payload is too large."


async def _bounded_webhook_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError:
            declared_length = None
        if (
            declared_length is not None
            and declared_length > PROVIDER_WEBHOOK_MAX_BODY_BYTES
        ):
            raise HTTPException(
                status_code=413,
                detail=_PAYLOAD_TOO_LARGE_DETAIL,
            )

    chunks: list[bytes] = []
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > PROVIDER_WEBHOOK_MAX_BODY_BYTES:
            raise HTTPException(
                status_code=413,
                detail=_PAYLOAD_TOO_LARGE_DETAIL,
            )
        if chunk:
            chunks.append(chunk)

    return b"".join(chunks)


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

    body = await _bounded_webhook_body(request)

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
