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

    request.state.agent_id = (
        record.agent_id
    )

    return record