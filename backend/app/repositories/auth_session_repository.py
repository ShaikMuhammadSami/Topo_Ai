from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuthSessionRecord


def add_auth_session(
    session: Session,
    record: AuthSessionRecord,
) -> None:
    session.add(record)


def load_auth_session_by_secret_digest(
    session: Session,
    secret_digest: str,
) -> AuthSessionRecord | None:
    statement = select(AuthSessionRecord).where(
        AuthSessionRecord.session_secret_digest == secret_digest
    )
    return session.scalars(statement).one_or_none()


def load_auth_session(
    session: Session,
    session_id: str,
) -> AuthSessionRecord | None:
    return session.get(AuthSessionRecord, session_id)
