from app.security.tenant_context import TenantContext, require_tenant_context
from fastapi import Depends
from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.lifecycle_automation import (
    LifecycleStatusResponse,
)
from app.services.lifecycle_status import (
    build_lifecycle_status,
)

router = APIRouter(
    prefix="/api/v1/automation",
    tags=["automation"],
)


@router.get(
    "/status",
    response_model=LifecycleStatusResponse,
)
def lifecycle_status(
    cluster_name: str | None = None,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> LifecycleStatusResponse:
    return build_lifecycle_status(
        session,
        cluster_name=cluster_name,
        tenant_id=tenant_context.tenant_id,
    )
