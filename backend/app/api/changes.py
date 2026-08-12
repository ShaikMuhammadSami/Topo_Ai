from collections import Counter

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.changes import (
    ChangeCategory,
    ChangeImportance,
    ChangeIngestionResult,
    ChangeSummary,
    NormalizedChange,
)
from app.repositories.change_repository import (
    list_changes,
    load_change,
    save_changes,
)
from app.repositories.snapshot_repository import (
    load_snapshot,
)
from app.services.change_normalizer import (
    normalize_snapshot_changes,
)
from app.services.change_event_bridge import (
    promote_normalized_changes,
)

router = APIRouter(
    prefix="/api/v1/changes",
    tags=["changes"],
)


@router.post(
    "/from-diff",
    response_model=ChangeIngestionResult,
    status_code=status.HTTP_201_CREATED,
)
def ingest_snapshot_changes(
    from_snapshot_id: str,
    to_snapshot_id: str,
    session: Session = Depends(
        get_session
    ),
) -> ChangeIngestionResult:
    before = load_snapshot(
        session=session,
        snapshot_id=from_snapshot_id,
    )

    after = load_snapshot(
        session=session,
        snapshot_id=to_snapshot_id,
    )

    if before is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Starting snapshot was not "
                f"found: {from_snapshot_id}"
            ),
        )

    if after is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Ending snapshot was not "
                f"found: {to_snapshot_id}"
            ),
        )

    before_cluster = before.scope.get(
        "cluster"
    )

    after_cluster = after.scope.get(
        "cluster"
    )

    if before_cluster != after_cluster:
        raise HTTPException(
            status_code=422,
            detail=(
                "Snapshots must belong to "
                "the same cluster."
            ),
        )

    before_namespace = (
        before.scope.get("namespace")
    )

    after_namespace = (
        after.scope.get("namespace")
    )

    if (
        before_namespace
        != after_namespace
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Snapshots must use the same "
                "namespace scope."
            ),
        )

    changes = (
        normalize_snapshot_changes(
            before=before,
            after=after,
        )
    )

    created_count, updated_count = (
        save_changes(
            session=session,
            changes=changes,
        )
    )
    event_summary = (
     promote_normalized_changes(
         session,
         changes=changes,
        )
    )
    
    type_counts = Counter(
        change.change_type.value
        for change in changes
    )

    category_counts = Counter(
        change.category.value
        for change in changes
    )

    importance_counts = Counter(
        change.importance.value
        for change in changes
    )

    namespace = (
        None
        if after_namespace in (
            None,
            "*",
        )
        else after_namespace
    )

    return ChangeIngestionResult(
        from_snapshot_id=(
            from_snapshot_id
        ),
        to_snapshot_id=(
            to_snapshot_id
        ),
        cluster_name=(
            after_cluster or "unknown"
        ),
        namespace=namespace,
        detected_count=len(changes),
        created_count=created_count,
        updated_count=updated_count,
        type_counts=dict(type_counts),
        category_counts=dict(
            category_counts
        ),
        importance_counts=dict(
            importance_counts
        ),
    )


@router.get(
    "",
    response_model=list[
        ChangeSummary
    ],
)
def get_changes(
    cluster_name: str | None = None,
    namespace: str | None = None,
    category: ChangeCategory | None = None,
    importance: ChangeImportance | None = None,
    limit: int = Query(
        default=200,
        ge=1,
        le=500,
    ),
    session: Session = Depends(
        get_session
    ),
) -> list[ChangeSummary]:
    return list_changes(
        session=session,
        cluster_name=cluster_name,
        namespace=namespace,
        category=(
            category.value
            if category
            else None
        ),
        importance=(
            importance.value
            if importance
            else None
        ),
        limit=limit,
    )


@router.get(
    "/{change_id}",
    response_model=NormalizedChange,
)
def get_change(
    change_id: str,
    session: Session = Depends(
        get_session
    ),
) -> NormalizedChange:
    change = load_change(
        session=session,
        change_id=change_id,
    )

    if change is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Change not found: "
                f"{change_id}"
            ),
        )

    return change