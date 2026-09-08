from __future__ import annotations

from fastapi import (
    Depends,
    HTTPException,
    Request,
)
from sqlalchemy.orm import Session

from app.db.database import (
    get_session,
)
from app.db.models import (
    TopoAgentRecord,
)
from app.repositories.agent_repository import (
    authenticate_agent,
)
from app.security.authorization_enforcement import (
    AuthorizationFailure,
    authorize_agent_fixed_purpose,
)


_AGENT_ROUTE_PURPOSES = {
    ("GET", "/api/v1/agent/config"): "app.api.agents.get_config",
    ("POST", "/api/v1/agent/heartbeat"): "app.repositories.agent_repository.record_heartbeat",
    ("POST", "/api/v1/agent/snapshots"): "app.services.agent_snapshot_ingest.persist_agent_snapshot",
    ("POST", "/api/v1/agent/runtime/heartbeat"): "app.repositories.runtime_observability_repository.record_sensor_heartbeat",
    ("POST", "/api/v1/agent/runtime/batches"): "app.repositories.runtime_observability_repository.ingest_runtime_event_batch",
    ("POST", "/api/v1/agent/change-events"): "app.api.agents.submit_change_events",
    ("POST", "/api/v1/agent/signals"): "app.api.agents.submit_failure_signals",
}


def require_agent(
    request: Request,
    session: Session = Depends(
        get_session
    ),
) -> TopoAgentRecord:
    authorization = (
        request.headers.get(
            "Authorization",
            "",
        )
    )

    scheme, separator, token = (
        authorization.partition(" ")
    )

    if (
        not separator
        or scheme.lower() != "bearer"
        or not token.strip()
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "A Topo Agent Bearer token "
                "is required."
            ),
            headers={
                "WWW-Authenticate":
                    "Bearer",
            },
        )

    record = authenticate_agent(
        session=session,
        token=token.strip(),
    )

    if record is None:
        raise HTTPException(
            status_code=401,
            detail=(
                "The Topo Agent token is "
                "invalid or revoked."
            ),
            headers={
                "WWW-Authenticate":
                    "Bearer",
            },
        )

    request.state.agent_id = record.agent_id
    purpose = _AGENT_ROUTE_PURPOSES.get((request.method.upper(), request.url.path))
    try:
        context = authorize_agent_fixed_purpose(
            session, agent=record, fixed_purpose=purpose or ""
        )
    except AuthorizationFailure as exc:
        raise HTTPException(
            status_code=403,
            detail={"code": exc.code},
        ) from exc
    request.state.authorization_context = context
    return record
