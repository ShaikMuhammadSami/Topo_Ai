from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from fastapi.responses import (
    JSONResponse,
)
from sqlalchemy.orm import Session

from app.db.database import (
    get_session,
)
from app.models.post_incident_report import (
    PostIncidentReportDetail,
    PostIncidentReportGenerateRequest,
    PostIncidentReportSummary,
    PostIncidentReportUpdateRequest,
    ReportActionItemUpdateRequest,
    ReportExportFormat,
)
from app.repositories.post_incident_report_repository import (
    list_post_incident_reports,
    load_post_incident_report,
    update_post_incident_report,
    update_report_action_item,
)
from app.services.post_incident_report import (
    PostIncidentReportGenerationError,
    generate_post_incident_report,
    render_post_incident_report_markdown,
)


router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["post-incident-reports"],
)


@router.post(
    "/{incident_id}/reports",
    response_model=PostIncidentReportDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_report(
    incident_id: str,
    request:
        PostIncidentReportGenerateRequest,
    session: Session = Depends(
        get_session
    ),
) -> PostIncidentReportDetail:
    try:
        return generate_post_incident_report(
            session=session,
            incident_id=incident_id,
            request=request,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except (
        PostIncidentReportGenerationError
    ) as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@router.get(
    "/{incident_id}/reports",
    response_model=list[
        PostIncidentReportSummary
    ],
)
def get_reports(
    incident_id: str,
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),
    session: Session = Depends(
        get_session
    ),
) -> list[PostIncidentReportSummary]:
    return list_post_incident_reports(
        session=session,
        incident_id=incident_id,
        limit=limit,
    )


@router.get(
    "/{incident_id}/reports/{report_id}",
    response_model=PostIncidentReportDetail,
)
def get_report(
    incident_id: str,
    report_id: str,
    session: Session = Depends(
        get_session
    ),
) -> PostIncidentReportDetail:
    result = load_post_incident_report(
        session=session,
        report_id=report_id,
    )

    if (
        result is None
        or result.incident_id
        != incident_id
    ):
        raise HTTPException(
            status_code=404,
            detail=(
                "Post-incident report "
                "not found."
            ),
        )

    return result


@router.patch(
    "/{incident_id}/reports/{report_id}",
    response_model=PostIncidentReportDetail,
)
def patch_report(
    incident_id: str,
    report_id: str,
    request:
        PostIncidentReportUpdateRequest,
    session: Session = Depends(
        get_session
    ),
) -> PostIncidentReportDetail:
    existing = load_post_incident_report(
        session=session,
        report_id=report_id,
    )

    if (
        existing is None
        or existing.incident_id
        != incident_id
    ):
        raise HTTPException(
            status_code=404,
            detail=(
                "Post-incident report "
                "not found."
            ),
        )

    try:
        result = update_post_incident_report(
            session=session,
            report_id=report_id,
            request=request,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Post-incident report "
                "not found."
            ),
        )

    return result


@router.patch(
    (
        "/{incident_id}/reports/{report_id}/"
        "actions/{action_item_id}"
    ),
    response_model=PostIncidentReportDetail,
)
def patch_action_item(
    incident_id: str,
    report_id: str,
    action_item_id: str,
    request:
        ReportActionItemUpdateRequest,
    session: Session = Depends(
        get_session
    ),
) -> PostIncidentReportDetail:
    existing = load_post_incident_report(
        session=session,
        report_id=report_id,
    )

    if (
        existing is None
        or existing.incident_id
        != incident_id
    ):
        raise HTTPException(
            status_code=404,
            detail=(
                "Post-incident report "
                "not found."
            ),
        )

    result = update_report_action_item(
        session=session,
        report_id=report_id,
        action_item_id=action_item_id,
        request=request,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Corrective action item "
                "not found."
            ),
        )

    return result


@router.get(
    (
        "/{incident_id}/reports/{report_id}/"
        "export"
    ),
)
def export_report(
    incident_id: str,
    report_id: str,
    export_format: ReportExportFormat = Query(
        default=ReportExportFormat.MARKDOWN,
        alias="format",
    ),
    session: Session = Depends(
        get_session
    ),
) -> Response:
    report = load_post_incident_report(
        session=session,
        report_id=report_id,
    )

    if (
        report is None
        or report.incident_id
        != incident_id
    ):
        raise HTTPException(
            status_code=404,
            detail=(
                "Post-incident report "
                "not found."
            ),
        )

    if (
        export_format
        == ReportExportFormat.JSON
    ):
        return JSONResponse(
            content=report.model_dump(
                mode="json"
            ),
            headers={
                "Content-Disposition": (
                    "attachment; filename="
                    f"topo-report-v"
                    f"{report.version}.json"
                )
            },
        )

    markdown = (
        render_post_incident_report_markdown(
            report
        )
    )

    return Response(
        content=markdown,
        media_type=(
            "text/markdown; charset=utf-8"
        ),
        headers={
            "Content-Disposition": (
                "attachment; filename="
                f"topo-report-v"
                f"{report.version}.md"
            )
        },
    )