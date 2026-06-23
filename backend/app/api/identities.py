from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.identity import (
    IdentityOverrideCreate,
    IdentityOverrideView,
    IdentityResolutionResult,
    IdentityResolutionSummary,
)
from app.repositories.identity_repository import (
    deactivate_identity_override,
    identity_resolution_summary,
    list_identity_overrides,
    load_identity_resolution,
    save_identity_resolution,
    upsert_identity_override,
)
from app.repositories.snapshot_repository import (
    load_snapshot,
)
from app.services.identity_override_service import (
    apply_identity_overrides,
)
from app.services.identity_resolver import (
    resolve_kubernetes_identities,
)


router = APIRouter(
    prefix="/api/v1/identities",
    tags=["identities"],
)


def load_snapshot_or_404(
    session: Session,
    snapshot_id: str,
):
    snapshot = load_snapshot(
        session=session,
        snapshot_id=snapshot_id,
    )

    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Snapshot not found: "
                f"{snapshot_id}"
            ),
        )

    return snapshot


@router.get(
    "/resolve",
    response_model=IdentityResolutionResult,
)
def resolve_snapshot_identities(
    snapshot_id: str = Query(
        description=(
            "Stored topology snapshot to resolve."
        )
    ),
    session: Session = Depends(get_session),
) -> IdentityResolutionResult:
    """
    Run automatic identity resolution without
    persisting the result or applying overrides.
    """
    snapshot = load_snapshot_or_404(
        session=session,
        snapshot_id=snapshot_id,
    )

    return resolve_kubernetes_identities(
        snapshot=snapshot
    )


@router.post(
    "/materialize",
    response_model=IdentityResolutionSummary,
)
def materialize_snapshot_identities(
    snapshot_id: str = Query(
        description=(
            "Stored topology snapshot to resolve "
            "and persist."
        )
    ),
    session: Session = Depends(get_session),
) -> IdentityResolutionSummary:
    """
    Resolve identities, apply active overrides,
    and persist the final result.
    """
    snapshot = load_snapshot_or_404(
        session=session,
        snapshot_id=snapshot_id,
    )

    cluster_name = snapshot.scope.get(
        "cluster"
    )

    if not cluster_name:
        raise HTTPException(
            status_code=422,
            detail=(
                "Snapshot does not contain a "
                "cluster scope."
            ),
        )

    snapshot_namespace = (
        snapshot.scope.get("namespace")
    )

    override_namespace = (
        None
        if snapshot_namespace in {
            None,
            "*",
        }
        else snapshot_namespace
    )

    overrides = list_identity_overrides(
        session=session,
        cluster_name=cluster_name,
        namespace=override_namespace,
        active_only=True,
    )

    automatic_result = (
        resolve_kubernetes_identities(
            snapshot=snapshot
        )
    )

    final_result = apply_identity_overrides(
        snapshot=snapshot,
        automatic_result=automatic_result,
        overrides=overrides,
    )

    record = save_identity_resolution(
        session=session,
        result=final_result,
    )

    return identity_resolution_summary(
        record
    )


@router.get(
    "/stored",
    response_model=IdentityResolutionResult,
)
def get_stored_identity_resolution(
    snapshot_id: str,
    session: Session = Depends(get_session),
) -> IdentityResolutionResult:
    result = load_identity_resolution(
        session=session,
        snapshot_id=snapshot_id,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No persisted identity resolution "
                f"exists for snapshot {snapshot_id}."
            ),
        )

    return result


@router.post(
    "/overrides",
    response_model=IdentityOverrideView,
    status_code=status.HTTP_201_CREATED,
)
def create_identity_override(
    request: IdentityOverrideCreate,
    session: Session = Depends(get_session),
) -> IdentityOverrideView:
    return upsert_identity_override(
        session=session,
        request=request,
    )


@router.get(
    "/overrides",
    response_model=list[IdentityOverrideView],
)
def get_identity_overrides(
    cluster_name: str | None = None,
    namespace: str | None = None,
    active_only: bool = True,
    session: Session = Depends(get_session),
) -> list[IdentityOverrideView]:
    return list_identity_overrides(
        session=session,
        cluster_name=cluster_name,
        namespace=namespace,
        active_only=active_only,
    )


@router.delete(
    "/overrides/{override_id}",
)
def delete_identity_override(
    override_id: str,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    removed = deactivate_identity_override(
        session=session,
        override_id=override_id,
    )

    if not removed:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Override not found: "
                f"{override_id}"
            ),
        )

    return {
        "status": "deactivated",
        "override_id": override_id,
    }