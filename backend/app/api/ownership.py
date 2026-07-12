from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.db.database import (
    get_session,
)
from app.models.ownership import (
    EntityOwnershipResolution,
    IncidentOwnershipImpact,
    OwnershipMappingCreate,
    OwnershipMappingView,
)
from app.repositories.ownership_repository import (
    list_ownership_mappings,
)
from app.services.business_impact import (
    calculate_incident_ownership_impact,
)
from app.services.ownership_resolver import (
    create_ownership_mapping,
    resolve_ownership_by_ids,
)


router = APIRouter(
    prefix="/api/v1",
    tags=["ownership"],
)


@router.post(
    "/ownership/mappings",
    response_model=OwnershipMappingView,
    status_code=status.HTTP_201_CREATED,
)
def create_mapping(
    request: OwnershipMappingCreate,
    session: Session = Depends(
        get_session
    ),
) -> OwnershipMappingView:
    return create_ownership_mapping(
        session=session,
        request=request,
    )


@router.get(
    "/ownership/mappings",
    response_model=list[
        OwnershipMappingView
    ],
)
def get_mappings(
    owner_team: str | None = None,
    namespace: str | None = None,
    active: bool | None = True,
    limit: int = Query(
        default=200,
        ge=1,
        le=500,
    ),
    session: Session = Depends(
        get_session
    ),
) -> list[OwnershipMappingView]:
    return list_ownership_mappings(
        session=session,
        owner_team=owner_team,
        namespace=namespace,
        active=active,
        limit=limit,
    )


@router.get(
    "/ownership/resolve",
    response_model=(
        EntityOwnershipResolution
    ),
)
def resolve_ownership(
    snapshot_id: str,
    entity_id: str,
    session: Session = Depends(
        get_session
    ),
) -> EntityOwnershipResolution:
    try:
        return resolve_ownership_by_ids(
            session=session,
            snapshot_id=snapshot_id,
            entity_id=entity_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.get(
    "/incidents/{incident_id}/ownership-impact",
    response_model=(
        IncidentOwnershipImpact
    ),
)
def get_incident_ownership_impact(
    incident_id: str,
    session: Session = Depends(
        get_session
    ),
) -> IncidentOwnershipImpact:
    try:
        return (
            calculate_incident_ownership_impact(
                session=session,
                incident_id=incident_id,
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc