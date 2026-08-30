from __future__ import annotations
from app.security.tenant_context import TenantContext, require_tenant_context
from fastapi import Depends

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
from app.models.change_events import (
    ChangeCorrelationRequest,
    ChangeCorrelationResponse,
    ChangeEventCreate,
    ChangeEventReceipt,
    ChangeEventView,
    IncidentChangeAnalysisResponse,
)
from app.repositories.change_event_repository import (
    change_event_view,
    correlate_change_event,
    ingest_change_event,
    list_change_events,
    load_change_event,
)
from app.services.incident_change_analysis import (
    analyze_incident_change_events,
)

router = APIRouter(
    prefix="/api/v1/change-events",
    tags=["change-events"],
)


incident_router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["incident-change-events"],
)


@router.post(
    "",
    response_model=(ChangeEventReceipt),
    status_code=(status.HTTP_201_CREATED),
)
def create_event(
    request: ChangeEventCreate,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> ChangeEventReceipt:
    return ingest_change_event(
        session,
        request=request,
        tenant_id=tenant_context.tenant_id,
    )


@router.get(
    "",
    response_model=list[ChangeEventView],
)
def get_events(
    source: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    environment: str | None = Query(default=None),
    cluster_name: str | None = Query(default=None),
    namespace: str | None = Query(default=None),
    minimum_risk_score: int = Query(
        default=0,
        ge=0,
        le=100,
    ),
    occurred_after: str | None = Query(default=None),
    occurred_before: str | None = Query(default=None),
    limit: int = Query(
        default=100,
        ge=1,
        le=5000,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> list[ChangeEventView]:
    return list_change_events(
        session,
        source=source,
        kind=kind,
        environment=environment,
        cluster_name=cluster_name,
        namespace=namespace,
        minimum_risk_score=(minimum_risk_score),
        occurred_after=occurred_after,
        occurred_before=occurred_before,
        limit=limit,
        offset=offset,
        tenant_id=tenant_context.tenant_id,
    )


@router.get(
    "/{event_id}",
    response_model=ChangeEventView,
)
def get_event(
    event_id: str,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> ChangeEventView:
    record = load_change_event(
        session,
        event_id=event_id,
        tenant_id=tenant_context.tenant_id,
    )

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Change event not found."
            ),
        )

    return change_event_view(
        session,
        record=record,
        tenant_id=tenant_context.tenant_id,
    )


@router.post(
    "/{event_id}/correlate",
    response_model=(ChangeCorrelationResponse),
)
def correlate_event(
    event_id: str,
    request: ChangeCorrelationRequest,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> ChangeCorrelationResponse:
    try:
        return correlate_change_event(
            session,
            event_id=event_id,
            snapshot_id=(request.snapshot_id),
            tenant_id=tenant_context.tenant_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@incident_router.get(
    "/{incident_id}/change-events",
    response_model=(IncidentChangeAnalysisResponse),
)
def incident_change_events(
    incident_id: str,
    lookback_minutes: int = Query(
        default=120,
        ge=1,
        le=10080,
    ),
    after_minutes: int = Query(
        default=10,
        ge=0,
        le=1440,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=1000,
    ),
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> IncidentChangeAnalysisResponse:
    try:
        return analyze_incident_change_events(
            session,
            incident_id=(incident_id),
            lookback_minutes=(lookback_minutes),
            after_minutes=(after_minutes),
            minimum_score=0,
            limit=limit,
            tenant_id=tenant_context.tenant_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@incident_router.get(
    ("/{incident_id}/" "suspected-change-events"),
    response_model=(IncidentChangeAnalysisResponse),
)
def suspected_changes(
    incident_id: str,
    lookback_minutes: int = Query(
        default=120,
        ge=1,
        le=10080,
    ),
    after_minutes: int = Query(
        default=10,
        ge=0,
        le=1440,
    ),
    minimum_score: float = Query(
        default=25,
        ge=0,
        le=100,
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> IncidentChangeAnalysisResponse:
    try:
        return analyze_incident_change_events(
            session,
            incident_id=(incident_id),
            lookback_minutes=(lookback_minutes),
            after_minutes=(after_minutes),
            minimum_score=(minimum_score),
            limit=limit,
            tenant_id=tenant_context.tenant_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
