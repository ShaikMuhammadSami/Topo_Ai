from __future__ import annotations
from app.security.tenant_context import TenantContext, require_tenant_context
from fastapi import Depends

from fastapi import (
    APIRouter,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.db.database import (
    get_session,
)
from app.models.causal_rca import (
    CausalAnalysisRequest,
    CausalAnalysisResponse,
)
from app.repositories.causal_analysis_repository import (
    latest_causal_analysis,
    load_causal_analysis,
)
from app.services.causal_rca import (
    analyze_causal_rca,
)

incident_router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["causal-rca"],
)


router = APIRouter(
    prefix="/api/v1/causal-analyses",
    tags=["causal-rca"],
)


@incident_router.post(
    "/{incident_id}/causal-rca",
    response_model=(CausalAnalysisResponse),
    status_code=(status.HTTP_201_CREATED),
)
def analyze(
    incident_id: str,
    request: CausalAnalysisRequest,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> CausalAnalysisResponse:
    try:
        return analyze_causal_rca(
            session,
            incident_id=incident_id,
            request=request,
            persist=True,
            tenant_id=tenant_context.tenant_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@incident_router.get(
    "/{incident_id}/causal-rca/latest",
    response_model=(CausalAnalysisResponse),
)
def latest(
    incident_id: str,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> CausalAnalysisResponse:
    result = latest_causal_analysis(
        session,
        incident_id=incident_id,
        tenant_id=tenant_context.tenant_id,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No causal analysis "
                "exists for this "
                "incident."
            ),
        )

    return result


@router.get(
    "/{analysis_id}",
    response_model=(CausalAnalysisResponse),
)
def get_analysis(
    analysis_id: str,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> CausalAnalysisResponse:
    result = load_causal_analysis(
        session,
        analysis_id=analysis_id,
        tenant_id=tenant_context.tenant_id,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Causal analysis "
                "not found."
            ),
        )

    return result
