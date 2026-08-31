from __future__ import annotations
from app.security.tenant_context import TenantContext, require_tenant_context
from fastapi import Depends

import os

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
from app.models.change_sources import (
    ChangeSourceCreate,
    ChangeSourceDeadLetterView,
    ChangeSourceDeliveryView,
    ChangeSourceDoctorResponse,
    ChangeSourceReplayResponse,
    ChangeSourceUpdate,
    ChangeSourceView,
)
from app.repositories.change_source_repository import (
    create_change_source,
    get_change_source,
    list_change_sources,
    list_dead_letters,
    list_deliveries,
    load_change_source,
    update_change_source,
)
from app.services.change_source_ingest import (
    replay_dead_letter,
)

router = APIRouter(
    prefix="/api/v1/change-sources",
    tags=["change-sources"],
)


@router.post(
    "",
    response_model=ChangeSourceView,
    status_code=(
        status.HTTP_201_CREATED
    ),
)
def create(
    request: ChangeSourceCreate,
    session: Session = Depends(
        get_session
    ),
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> ChangeSourceView:
    try:
        return create_change_source(
            session,
            tenant_id=tenant_context.tenant_id,
            request=request,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=list[
        ChangeSourceView
    ],
)
def list_all(
    session: Session = Depends(
        get_session
    ),
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> list[ChangeSourceView]:
    return list_change_sources(
        session, tenant_id=tenant_context.tenant_id,
    )


@router.get(
    "/deliveries",
    response_model=list[ChangeSourceDeliveryView],
)
def deliveries(
    source_id: str | None = None,
    delivery_status: str | None = Query(
        default=None,
        alias="status",
    ),
    limit: int = Query(
        default=200,
        ge=1,
        le=1000,
    ),
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> list[ChangeSourceDeliveryView]:
    return list_deliveries(
        session,
        source_id=source_id,
        status=delivery_status,
        limit=limit,
        tenant_id=tenant_context.tenant_id,
    )


@router.get(
    "/dead-letters",
    response_model=list[ChangeSourceDeadLetterView],
)
def dead_letters(
    source_id: str | None = None,
    dead_letter_status: str | None = Query(
        default=None,
        alias="status",
    ),
    limit: int = Query(
        default=200,
        ge=1,
        le=1000,
    ),
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> list[ChangeSourceDeadLetterView]:
    return list_dead_letters(
        session,
        source_id=source_id,
        status=dead_letter_status,
        limit=limit,
        tenant_id=tenant_context.tenant_id,
    )


@router.post(
    "/dead-letters/{dead_letter_id}/replay",
    response_model=(ChangeSourceReplayResponse),
)
def replay(
    dead_letter_id: str,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> ChangeSourceReplayResponse:
    try:
        return replay_dead_letter(
            session,
            dead_letter_id=(dead_letter_id),
            tenant_id=tenant_context.tenant_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.get(
    "/{source_id}",
    response_model=ChangeSourceView,
)
def get_one(
    source_id: str,
    session: Session = Depends(
        get_session
    ),
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> ChangeSourceView:
    value = get_change_source(
        session,
        tenant_id=tenant_context.tenant_id,
        source_id=source_id,
    )

    if value is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Change source not found."
            ),
        )

    return value


@router.patch(
    "/{source_id}",
    response_model=ChangeSourceView,
)
def patch(
    source_id: str,
    request: ChangeSourceUpdate,
    session: Session = Depends(
        get_session
    ),
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> ChangeSourceView:
    try:
        return update_change_source(
            session,
            tenant_id=tenant_context.tenant_id,
            source_id=source_id,
            request=request,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.get(
    "/{source_id}/doctor",
    response_model=(
        ChangeSourceDoctorResponse
    ),
)
def doctor(
    source_id: str,
    session: Session = Depends(
        get_session
    ),
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> ChangeSourceDoctorResponse:
    record = load_change_source(
        session,
        tenant_id=tenant_context.tenant_id,
        source_id=source_id,
    )

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Change source not found."
            ),
        )

    secret_available = bool(
        record.secret_ref
        and os.getenv(
            record.secret_ref
        )
    )

    return (
        ChangeSourceDoctorResponse(
            source_id=source_id,
            ready=(
                record.enabled
                and secret_available
            ),
            checks={
                "enabled":
                    record.enabled,
                "source_type":
                    record.source_type,
                "secret_ref":
                    record.secret_ref,
                "secret_available":
                    secret_available,
                "receiver_path":
                    (
                        "/api/v1/"
                        "change-source-webhooks/"
                        + source_id
                    ),
            },
        )
    )
