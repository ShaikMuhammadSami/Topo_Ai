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
from app.models.predeployment import (
    PreDeploymentImpactRequest,
    PreDeploymentImpactResponse,
)
from app.services.predeployment_impact import (
    PreDeploymentNotFoundError,
    PreDeploymentValidationError,
    analyze_predeployment_impact,
)
from app.models.predeployment import (
    ChangeRiskLevel,
)
from app.models.webhooks import (
    WebhookEventType,
)
from app.services.webhook_delivery import (
    build_webhook_event,
    publish_event_safely,
)

router = APIRouter(
    prefix="/api/v1/predeployment",
    tags=["predeployment"],
)


@router.post(
    "/analyze",
    response_model=(PreDeploymentImpactResponse),
)
def analyze_planned_change(
    request: PreDeploymentImpactRequest,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> PreDeploymentImpactResponse:
    try:
        result = analyze_predeployment_impact(
            session=session,
            request=request,
            tenant_id=tenant_context.tenant_id,
        )
        if result.risk_level in {ChangeRiskLevel.HIGH,ChangeRiskLevel.CRITICAL,}:

        
            event = build_webhook_event(
               event_type=(
                 WebhookEventType
                 .CHANGE_RISK_DETECTED
                ),
            resource_type=(
               "predeployment_analysis"
            ),
            resource_id=(
                result.analysis_id
            ),
            summary=(
              "High-risk planned change "
               f"detected for "
               f"{result.root_entity_name}."
            ),
            severity=(
               result.risk_level.value
            ),
            dedupe_key=(
               result.analysis_id
            ),
            payload={
               "analysis_id": (
                 result.analysis_id
                ),
              "snapshot_id": (
                 result.snapshot_id
                ),
              "root_entity_id": (
                 result.root_entity_id
                ),
              "root_entity_name": (
                 result.root_entity_name
                ),
               "change_type": (
                 result.change_type.value
                ),
              "risk_score": (
                 result.risk_score
                ),
              "risk_level": (
                 result.risk_level.value
                ),
             "deployment_decision": (
                 result
                 .deployment_decision
                 .value
                ),
             "affected_entity_count": (
                 result
                 .affected_entity_count
                ),
             "recommendation": (
                 result.recommendation
               ),
            },
        )

        publish_event_safely(
            session=session,
            event=event,
            tenant_id=tenant_context.tenant_id,
        )

    except PreDeploymentNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except PreDeploymentValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    return result
