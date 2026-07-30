from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    Query,
)
from sqlalchemy.orm import Session

from app.db.database import (
    get_session,
)
from app.models.clouds import (
    CloudAccountView,
    CloudResourceView,
    CloudTopologyResponse,
)
from app.repositories.cloud_repository import (
    latest_cloud_topology,
    list_cloud_accounts,
    list_cloud_resources,
)


router = APIRouter(
    prefix="/api/v1/clouds",
    tags=["clouds"],
)


@router.get(
    "/accounts",
    response_model=list[
        CloudAccountView
    ],
)
def get_cloud_accounts(
    provider: str | None = Query(
        default=None,
    ),
    session: Session = Depends(
        get_session
    ),
) -> list[CloudAccountView]:
    return list_cloud_accounts(
        session=session,
        provider=provider,
    )


@router.get(
    "/resources",
    response_model=list[
        CloudResourceView
    ],
)
def get_cloud_resources(
    provider: str | None = Query(
        default="aws",
    ),
    account_id: str | None = Query(
        default=None,
    ),
    region: str | None = Query(
        default=None,
    ),
    resource_type:
        str | None = Query(
            default=None,
        ),
    tag_key: str | None = Query(
        default=None,
    ),
    tag_value: str | None = Query(
        default=None,
    ),
    limit: int = Query(
        default=500,
        ge=1,
        le=5000,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    session: Session = Depends(
        get_session
    ),
) -> list[CloudResourceView]:
    return list_cloud_resources(
        session=session,
        provider=provider,
        account_id=account_id,
        region=region,
        resource_type=(
            resource_type
        ),
        tag_key=tag_key,
        tag_value=tag_value,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/topology",
    response_model=(
        CloudTopologyResponse
    ),
)
def get_cloud_topology(
    provider: str = Query(
        default="aws",
    ),
    account_id: str | None = Query(
        default=None,
    ),
    region: str | None = Query(
        default=None,
    ),
    session: Session = Depends(
        get_session
    ),
) -> CloudTopologyResponse:
    return latest_cloud_topology(
        session=session,
        provider=provider,
        account_id=account_id,
        region=region,
    )