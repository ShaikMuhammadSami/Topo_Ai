from app.security.tenant_context import TenantContext, require_tenant_context
from fastapi import Depends
from fastapi import (
    APIRouter,
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
    GitHubActionsEnrichmentResult,
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
from app.services.github_actions_artifact_lineage import (
    enrich_snapshot_with_github_actions_provider_evidence,
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
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
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
    snapshot_id: str = Query(description=("Stored Kubernetes snapshot " "to enrich.")),
    commit_limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> GitHubEnrichmentResult:
    snapshot = load_snapshot(
        session=session,
        snapshot_id=snapshot_id,
        tenant_id=tenant_context.tenant_id,
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
        tenant_id=tenant_context.tenant_id,
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


@router.post(
    "/actions/enrich",
    response_model=(GitHubActionsEnrichmentResult),
    status_code=status.HTTP_201_CREATED,
)
def enrich_snapshot_with_actions(
    snapshot_id: str = Query(
        description=(
            "GitHub-enriched snapshot that "
            "already contains repository and "
            "commit entities."
        )
    ),
    run_limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> GitHubActionsEnrichmentResult:
    snapshot = load_snapshot(
        session=session,
        snapshot_id=snapshot_id,
        tenant_id=tenant_context.tenant_id,
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

        workflow_runs = (
            connector.list_workflow_runs(
                limit=run_limit
            )
        )

    except GitHubConnectorError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    repository_full_name = str(
        repository.get("full_name")
        or connector.settings.full_name
    )

    try:
        enriched_snapshot, stats, _lineage_stats = (
            enrich_snapshot_with_github_actions_provider_evidence(
                session=session,
                snapshot=snapshot,
                connector=connector,
                repository=repository,
                workflow_runs=workflow_runs,
                tenant_id=tenant_context.tenant_id,
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    save_snapshot(
        session=session,
        snapshot=enriched_snapshot,
        tenant_id=tenant_context.tenant_id,
    )

    return GitHubActionsEnrichmentResult(
        base_snapshot_id=snapshot_id,
        enriched_snapshot_id=(
            enriched_snapshot.snapshot_id
        ),
        repository=repository_full_name,
        workflow_runs_collected=(
            stats[
                "workflow_runs_collected"
            ]
        ),
        commit_run_relationship_count=(
            stats[
                "commit_run_relationship_count"
            ]
        ),
        run_image_relationship_count=(
            stats[
                "run_image_relationship_count"
            ]
        ),
        mapped_run_count=(
            stats["mapped_run_count"]
        ),
        mapped_image_count=(
            stats["mapped_image_count"]
        ),
        unresolved_run_count=(
            stats["unresolved_run_count"]
        ),
        warnings=stats["warnings"],
    )
