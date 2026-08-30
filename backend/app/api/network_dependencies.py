from app.security.tenant_context import TenantContext, require_tenant_context
from fastapi import Depends
from fastapi import (
    APIRouter,
    HTTPException,
    Query,
)
from sqlalchemy.orm import Session

from app.db.database import (
    get_session,
)
from app.models.network_dependency import (
    NetworkDependencyAnalysisResponse,
)
from app.services.network_dependency_analysis import (
    analyze_network_dependencies,
)

router = APIRouter(
    prefix="/api/v1/snapshots",
    tags=["network-dependencies"],
)


@router.get(
    "/{snapshot_id}/network-dependencies",
    response_model=(NetworkDependencyAnalysisResponse),
)
def get_network_dependencies(
    snapshot_id: str,
    max_depth: int = Query(
        default=5,
        ge=1,
        le=10,
    ),
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> NetworkDependencyAnalysisResponse:
    try:
        return analyze_network_dependencies(
            session=session,
            snapshot_id=snapshot_id,
            max_depth=max_depth,
            tenant_id=tenant_context.tenant_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
