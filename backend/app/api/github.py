from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.connectors.github_connector import (
    GitHubConnector,
    GitHubConnectorError,
    GitHubSettings,
)
from app.db.database import get_session
from app.models.github import (
    GitHubConnectionInfo,
    GitHubEnrichmentResult,
)
from app.repositories.snapshot_repository import (
    load_snapshot,
    save_snapshot,
)
from app.services.github_graph import (
    augment_snapshot_with_github,
)


router = APIRouter(
    prefix="/api/v1/github",
    tags=["github"],
)


def create_connector() -> GitHubConnector:
    try:
        settings = (
            GitHubSettings
            .from_environment()
        )

        return GitHubConnector(
            settings=settings
        )

    except (
        RuntimeError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.get(
    "/connection",
    response_model=GitHubConnectionInfo,
)
def check_github_connection(
) -> GitHubConnectionInfo:
    connector = create_connector()

    try:
        information = (
            connector
            .connection_information()
        )

        return GitHubConnectionInfo(
            **information
        )

    except GitHubConnectorError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@router.post(
    "/enrich",
    response_model=GitHubEnrichmentResult,
    status_code=status.HTTP_201_CREATED,
)
def enrich_snapshot_with_github(
    snapshot_id: str = Query(
        description=(
            "Stored Kubernetes snapshot "
            "to enrich."
        )
    ),
    commit_limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),
    session: Session = Depends(
        get_session
    ),
) -> GitHubEnrichmentResult:
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

    connector = create_connector()

    try:
        repository = (
            connector.get_repository()
        )

        commits = connector.list_commits(
            limit=commit_limit
        )

    except GitHubConnectorError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    enriched_snapshot, stats = (
        augment_snapshot_with_github(
            snapshot=snapshot,
            repository=repository,
            commits=commits,
            api_url=(
                connector
                .settings
                .api_url
            ),
        )
    )

    save_snapshot(
        session=session,
        snapshot=enriched_snapshot,
    )

    return GitHubEnrichmentResult(
        base_snapshot_id=snapshot_id,
        enriched_snapshot_id=(
            enriched_snapshot.snapshot_id
        ),
        repository=str(
            repository.get("full_name")
            or connector
            .settings
            .full_name
        ),
        commits_collected=(
            stats.commits_collected
        ),
        mapped_commit_count=(
            stats.mapped_commit_count
        ),
        mapped_image_count=(
            stats.mapped_image_count
        ),
        commit_image_relationship_count=(
            stats.relationship_count
        ),
        unresolved_image_count=(
            stats.unresolved_image_count
        ),
        warnings=stats.warnings,
    )