"""Narrow append-only persistence for PH-5D security audit events."""

from sqlalchemy.orm import Session

from app.db.models import SecurityAuditEventRecord


def append_security_audit_event(
    session: Session,
    record: SecurityAuditEventRecord,
) -> None:
    """Append one immutable event in the caller-owned transaction."""

    session.add(record)
    session.flush([record])
