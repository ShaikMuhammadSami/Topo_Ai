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
from app.models.investigation_plan import (
    InvestigationPlanDetail,
    InvestigationPlanGenerateRequest,
    InvestigationPlanSummary,
    InvestigationStepUpdateRequest,
)
from app.repositories.investigation_plan_repository import (
    list_incident_investigation_plans,
    load_investigation_plan,
    update_investigation_step,
)
from app.services.investigation_planner import (
    InvestigationPlanGenerationError,
    generate_investigation_plan,
)

router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["investigation-plans"],
)


@router.post(
    "/{incident_id}/investigation-plans",
    response_model=InvestigationPlanDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_plan(
    incident_id: str,
    request: InvestigationPlanGenerateRequest,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> InvestigationPlanDetail:
    try:
        return generate_investigation_plan(
            session=session,
            incident_id=incident_id,
            request=request,
            tenant_id=tenant_context.tenant_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except InvestigationPlanGenerationError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@router.get(
    "/{incident_id}/investigation-plans",
    response_model=list[InvestigationPlanSummary],
)
def get_plans(
    incident_id: str,
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> list[InvestigationPlanSummary]:
    return list_incident_investigation_plans(
        session=session,
        incident_id=incident_id,
        limit=limit,
        offset=offset,
        tenant_id=tenant_context.tenant_id,
    )


@router.get(
    "/{incident_id}/investigation-plans/{plan_id}",
    response_model=InvestigationPlanDetail,
)
def get_plan(
    incident_id: str,
    plan_id: str,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> InvestigationPlanDetail:
    result = load_investigation_plan(
        session=session,
        plan_id=plan_id,
        tenant_id=tenant_context.tenant_id,
    )

    if (
        result is None
        or result.incident_id
        != incident_id
    ):
        raise HTTPException(
            status_code=404,
            detail=(
                "Investigation plan not found."
            ),
        )

    return result


@router.patch(
    ("/{incident_id}/" "investigation-plans/{plan_id}/" "steps/{step_id}"),
    response_model=InvestigationPlanDetail,
)
def patch_step(
    incident_id: str,
    plan_id: str,
    step_id: str,
    request: InvestigationStepUpdateRequest,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> InvestigationPlanDetail:
    result = update_investigation_step(
        session=session,
        plan_id=plan_id,
        step_id=step_id,
        request=request,
        tenant_id=tenant_context.tenant_id,
    )

    if (
        result is None
        or result.incident_id
        != incident_id
    ):
        raise HTTPException(
            status_code=404,
            detail=(
                "Investigation plan step "
                "not found."
            ),
        )

    return result
