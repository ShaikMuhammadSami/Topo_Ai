from app.security.tenant_context import TenantContext, require_tenant_context
from fastapi import Depends
from fastapi import (
    APIRouter,
    HTTPException,
)

from sqlalchemy.orm import Session


from app.db.database import (
    get_session,
)


from app.models.blast_radius import (
    BlastRadiusResponse,
)


from app.services.blast_radius import (
    calculate_blast_radius,
)

router = APIRouter(
    prefix="/api/v1/incidents",
    tags=[
        "blast-radius"
    ],
)


@router.get(
    "/{incident_id}/blast-radius",
    response_model=(BlastRadiusResponse),
)
def get_blast_radius(
    incident_id: str,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
):

    try:

        return calculate_blast_radius(
            session=session,
            incident_id=incident_id,
            tenant_id=tenant_context.tenant_id,
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )
