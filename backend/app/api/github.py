from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
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
from app.security.tenant_context import TenantContext, require_tenant_context
from app.services.github_actions_artifact_lineage import (
    enrich_snapshot_with_github_actions_provider_evidence,
)
from app.services.github_graph import (
    augment_snapshot_with_github,
)
from app.services.github_source_authority import (
    REPOSITORY_AMBIGUOUS,
    REPOSITORY_INVALID,
    REPOSITORY_REQUIRED,
    SOURCE_NOT_FOUND,
    SOURCE_PROVIDER_INVALID,
    SOURCE_UNAVAILABLE,
    GitHubSourceAuthorityError,
    resolve_github_source_settings,
)

router = APIRouter(
    prefix="/api/v1/github",
    tags=["github"],
)


def create_connector(
    settings: GitHubSettings | None = None,
) -> GitHubConnector:
    try:
        resolved_settings = settings or GitHubSettings.from_environment()

        return GitHubConnector(
            settings=resolved_settings
        )

    except (
        RuntimeError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


def _source_scoped_connector(
    *,
    request: Request,
    session: Session,
    tenant_context: TenantContext,
    source_id: str | None,
) -> GitHubConnector:
    if source_id is None:
        return create_connector()

    store = getattr(request.app.state, "secret_store", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=SOURCE_UNAVAILABLE,
        )
    try:
        settings = resolve_github_source_settings(
            session,
            tenant_id=tenant_context.tenant_id,
            source_id=source_id,
            secret_store=store,
        )
    except GitHubSourceAuthorityError as exc:
        code = str(exc)
        if code == SOURCE_NOT_FOUND:
            status_code = status.HTTP_404_NOT_FOUND
        elif code == SOURCE_UNAVAILABLE:
            status_code = status.HTTP_409_CONFLICT
        elif code in {
            SOURCE_PROVIDER_INVALID,
            REPOSITORY_REQUIRED,
            REPOSITORY_AMBIGUOUS,
            REPOSITORY_INVALID,
        }:
            status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
        else:  # pragma: no cover - all service errors are enumerated above
            status_code = status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=code) from None
    return create_connector(settings)


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
    request: Request,
    snapshot_id: str = Query(description=("Stored Kubernetes snapshot " "to enrich.")),
    source_id: str | None = Query(
        default=None,
        description="Tenant-owned GitHub change source repository authority.",
    ),
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

    connector = _source_scoped_connector(
        request=request,
        session=session,
        tenant_context=tenant_context,
        source_id=source_id,
    )

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
    request: Request,
    snapshot_id: str = Query(
        description=(
            "GitHub-enriched snapshot that "
            "already contains repository and "
            "commit entities."
        )
    ),
    source_id: str | None = Query(
        default=None,
        description="Tenant-owned GitHub change source repository authority.",
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

    connector = _source_scoped_connector(
        request=request,
        session=session,
        tenant_context=tenant_context,
        source_id=source_id,
    )

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
