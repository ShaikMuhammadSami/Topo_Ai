"""Validate ownership derived from an authenticated machine authority record.

This helper does not authenticate credentials or select tenants. Its callers
must first authenticate an enrollment token, agent secret, or provider source.
Machine request headers and payloads never participate in tenant selection.
"""

from sqlalchemy.orm import Session

from app.models.tenant import is_valid_tenant_id
from app.repositories.tenant_repository import load_active_tenant


def machine_tenant_is_active(session: Session, *, tenant_id: str) -> bool:
    return bool(
        isinstance(tenant_id, str)
        and is_valid_tenant_id(tenant_id)
        and load_active_tenant(session, tenant_id=tenant_id) is not None
    )
