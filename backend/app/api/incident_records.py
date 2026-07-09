from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from sqlalchemy.orm import Session

from app.db.database import (
    get_session,
)
from app.models.incident_records import (
    IncidentRelatedSignals,
    IncidentRecordSummary,
    IncidentRecordView,
    IncidentSeverity,
    IncidentStatus,
    IncidentStatusUpdate,
)
from app.repositories.incident_record_repository import (
    list_incident_records,
    load_incident_record,
    update_incident_status,
)
from app.repositories.signal_repository import (
    list_signals_by_incident_fingerprint,
)


router = APIRouter(
    prefix="/api/v1/incident-records",
    tags=["incident-records"],
)


@router.get(
    "",
    response_model=list[
        IncidentRecordSummary
    ],
)
def get_incident_records(
    status: IncidentStatus | None = None,
    severity: IncidentSeverity | None = None,
    namespace: str | None = None,
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    session: Session = Depends(
        get_session
    ),
) -> list[IncidentRecordSummary]:
    return list_incident_records(
        session=session,
        status=(
            status.value
            if status
            else None
        ),
        severity=(
            severity.value
            if severity
            else None
        ),
        namespace=namespace,
        limit=limit,
    )

@router.get(
    "/{incident_id}/signals",
    response_model=IncidentRelatedSignals,
)
def get_incident_related_signals(
    incident_id: str,
    limit: int = Query(
        default=200,
        ge=1,
        le=500,
    ),
    session: Session = Depends(
        get_session
    ),
) -> IncidentRelatedSignals:
    incident = load_incident_record(
        session=session,
        incident_id=incident_id,
    )

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Incident not found: "
                f"{incident_id}"
            ),
        )

    signals = (
        list_signals_by_incident_fingerprint(
            session=session,
            cluster_name=(
                incident.cluster_name
            ),
            namespace=incident.namespace,
            fingerprint=(
                incident.fingerprint
            ),
            limit=limit,
        )
    )

    return IncidentRelatedSignals(
        incident_id=incident.incident_id,
        fingerprint=incident.fingerprint,
        signal_count=len(signals),
        signals=signals,
    )

@router.get(
    "/{incident_id}",
    response_model=IncidentRecordView,
)
def get_incident_record(
    incident_id: str,
    session: Session = Depends(
        get_session
    ),
) -> IncidentRecordView:
    incident = load_incident_record(
        session=session,
        incident_id=incident_id,
    )

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Incident not found: "
                f"{incident_id}"
            ),
        )

    return incident


@router.patch(
    "/{incident_id}/status",
    response_model=IncidentRecordView,
)
def patch_incident_status(
    incident_id: str,
    request: IncidentStatusUpdate,
    session: Session = Depends(
        get_session
    ),
) -> IncidentRecordView:
    incident = update_incident_status(
        session=session,
        incident_id=incident_id,
        status=request.status,
        note=request.note,
    )

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Incident not found: "
                f"{incident_id}"
            ),
        )

    return incident