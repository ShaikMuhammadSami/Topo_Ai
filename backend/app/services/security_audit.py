"""Central PH-5D construction and persistence for security/admin evidence.

Allowed events join the caller's transaction.  Denials use a short independent
transaction and are deliberately best-effort: an audit outage can never turn a
denial into an allow.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import SecurityAuditEventRecord
from app.models.principal_identity import is_valid_principal_id
from app.models.security_audit import (
    SecurityAuditAction,
    SecurityAuditActorKind,
    SecurityAuditAuthenticationType,
    SecurityAuditAuthorityKind,
    SecurityAuditReason,
    SecurityAuditResourceType,
    SecurityAuditResult,
)
from app.models.tenant import is_valid_tenant_id
from app.repositories.security_audit_repository import append_security_audit_event
from app.security.authorization_policy import Permission


LOGGER = logging.getLogger(__name__)


class SecurityAuditValidationError(ValueError):
    """Trusted audit inputs violate the closed PH-5D contract."""


@dataclass
class _AuditRequestState:
    session_factory: Callable[[], Session]
    denial_recorded: bool = False


_CURRENT_AUDIT_REQUEST: ContextVar[_AuditRequestState | None] = ContextVar(
    "topo_security_audit_request", default=None
)


_AUTHENTICATION_TYPES = {
    "session": SecurityAuditAuthenticationType.BROWSER_SESSION,
    "human_api_token": SecurityAuditAuthenticationType.HUMAN_API_CREDENTIAL,
    "service_api_token": SecurityAuditAuthenticationType.SERVICE_API_CREDENTIAL,
    "api_token": SecurityAuditAuthenticationType.STATIC_BOOTSTRAP,
    "development": SecurityAuditAuthenticationType.DEVELOPMENT,
    "agent_bearer": SecurityAuditAuthenticationType.AGENT_TOKEN,
    "agent_enrollment_token": SecurityAuditAuthenticationType.AGENT_ENROLLMENT,
    "provider_verified": SecurityAuditAuthenticationType.PROVIDER_WEBHOOK,
}

_CONTROL_FREE_BOUNDS = {
    "actor_reference": 255,
    "authentication_type": 64,
    "authority_kind": 40,
    "tenant_id": 255,
    "action": 80,
    "resource_type": 64,
    "resource_id": 255,
    "reason_code": 64,
    "request_id": 255,
}


def bind_security_audit_request(
    session_factory: Callable[[], Session],
) -> Token:
    if not callable(session_factory):
        raise SecurityAuditValidationError("AUDIT_SESSION_FACTORY_REQUIRED")
    return _CURRENT_AUDIT_REQUEST.set(_AuditRequestState(session_factory))


def reset_security_audit_request(token: Token) -> None:
    _CURRENT_AUDIT_REQUEST.reset(token)


def _bounded(value: str | None, *, field: str) -> str | None:
    if value is None:
        return None
    limit = _CONTROL_FREE_BOUNDS[field]
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > limit
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise SecurityAuditValidationError(f"AUDIT_{field.upper()}_INVALID")
    return value


def canonical_permissions(
    permissions: Iterable[Permission | str],
) -> str:
    try:
        values = sorted({Permission(value).value for value in permissions})
    except (TypeError, ValueError) as exc:
        raise SecurityAuditValidationError("AUDIT_PERMISSIONS_INVALID") from exc
    return json.dumps(values, separators=(",", ":"))


def _context_actor(context: object) -> tuple[
    SecurityAuditActorKind,
    str | None,
    str | None,
    SecurityAuditAuthenticationType,
    SecurityAuditAuthorityKind,
    str | None,
    str | None,
]:
    # Lazy import prevents the central authorization module and its audit hook
    # from forming an import cycle.  Its private constructor remains the sole
    # authority for AuthorizationContext instances.
    from app.security.authorization_enforcement import AuthorizationContext

    if not isinstance(context, AuthorizationContext):
        raise SecurityAuditValidationError("AUDIT_AUTHORIZATION_CONTEXT_REQUIRED")
    actor_type = context.actor_principal_type
    if actor_type in {"human", "service"}:
        if not is_valid_principal_id(context.actor_principal_id):
            raise SecurityAuditValidationError("AUDIT_PRINCIPAL_ID_INVALID")
        actor_kind = SecurityAuditActorKind(actor_type)
        principal_id = context.actor_principal_id
        actor_reference = None
    elif actor_type in {"agent", "agent_enrollment"}:
        actor_kind = SecurityAuditActorKind.AGENT
        principal_id = None
        actor_reference = _bounded(
            context.actor_principal_id, field="actor_reference"
        )
    elif actor_type == "provider":
        actor_kind = SecurityAuditActorKind.PROVIDER
        principal_id = None
        actor_reference = _bounded(
            context.actor_principal_id, field="actor_reference"
        )
    else:
        raise SecurityAuditValidationError("AUDIT_ACTOR_KIND_INVALID")
    try:
        authentication_type = _AUTHENTICATION_TYPES[
            context.authentication_provenance
        ]
        authority_kind = SecurityAuditAuthorityKind(context.authority_kind.value)
    except (AttributeError, KeyError, ValueError) as exc:
        raise SecurityAuditValidationError("AUDIT_AUTHORITY_INVALID") from exc
    tenant_id = context.tenant_id
    if tenant_id is not None and not is_valid_tenant_id(tenant_id):
        raise SecurityAuditValidationError("AUDIT_TENANT_ID_INVALID")
    request_id = _bounded(context.request_id, field="request_id")
    return (
        actor_kind,
        principal_id,
        actor_reference,
        authentication_type,
        authority_kind,
        tenant_id,
        request_id,
    )


def _event(
    *,
    actor_kind: SecurityAuditActorKind,
    actor_principal_id: str | None,
    actor_reference: str | None,
    authentication_type: SecurityAuditAuthenticationType,
    authority_kind: SecurityAuditAuthorityKind,
    tenant_id: str | None,
    action: SecurityAuditAction,
    permissions: Iterable[Permission | str],
    resource_type: SecurityAuditResourceType | None,
    resource_id: str | None,
    result: SecurityAuditResult,
    reason: SecurityAuditReason,
    request_id: str | None,
) -> SecurityAuditEventRecord:
    serialized_permissions = canonical_permissions(permissions)
    if tenant_id is not None and not is_valid_tenant_id(tenant_id):
        raise SecurityAuditValidationError("AUDIT_TENANT_ID_INVALID")
    _bounded(authentication_type.value, field="authentication_type")
    _bounded(authority_kind.value, field="authority_kind")
    _bounded(action.value, field="action")
    _bounded(reason.value, field="reason_code")
    _bounded(resource_type.value if resource_type is not None else None, field="resource_type")
    _bounded(resource_id, field="resource_id")
    _bounded(actor_reference, field="actor_reference")
    _bounded(request_id, field="request_id")
    if actor_kind in {SecurityAuditActorKind.HUMAN, SecurityAuditActorKind.SERVICE}:
        if actor_reference is not None or not actor_principal_id:
            raise SecurityAuditValidationError("AUDIT_PRINCIPAL_ACTOR_INVALID")
    elif actor_principal_id is not None:
        raise SecurityAuditValidationError("AUDIT_NONPRINCIPAL_ACTOR_INVALID")
    if result is SecurityAuditResult.ALLOWED and reason is not SecurityAuditReason.COMPLETED:
        raise SecurityAuditValidationError("AUDIT_ALLOWED_REASON_INVALID")
    return SecurityAuditEventRecord(
        audit_event_id=f"audit:{uuid4()}",
        occurred_at=datetime.now(UTC).isoformat(),
        actor_principal_id=actor_principal_id,
        actor_kind=actor_kind.value,
        actor_reference=actor_reference,
        authentication_type=authentication_type.value,
        authority_kind=authority_kind.value,
        tenant_id=tenant_id,
        action=action.value,
        permissions_json=serialized_permissions,
        resource_type=resource_type.value if resource_type is not None else None,
        resource_id=resource_id,
        result=result.value,
        reason_code=reason.value,
        request_id=request_id,
    )


def append_allowed_security_event(
    session: Session,
    *,
    action: SecurityAuditAction,
    permissions: Iterable[Permission | str],
    resource_type: SecurityAuditResourceType | None = None,
    resource_id: str | None = None,
    tenant_id: str | None = None,
    authorization_context: object | None = None,
) -> SecurityAuditEventRecord | None:
    """Append after mutation and before the caller's existing commit.

    Legacy/test-only direct service invocations that have no typed PH-5C
    context cannot truthfully name an actor, so they do not fabricate an event.
    All production HTTP and fixed-purpose machine paths supply such a context.
    """

    if authorization_context is None:
        # The generic authorization context is also used by older direct
        # service/test helpers.  Only consume it implicitly while the HTTP
        # audit boundary is active; otherwise a forgotten caller reset could
        # misattribute a later out-of-request mutation.  Trusted direct callers
        # can still pass an explicit AuthorizationContext.
        if _CURRENT_AUDIT_REQUEST.get() is None:
            return None
        from app.security.authorization_enforcement import current_authorization_context

        authorization_context = current_authorization_context()
    if authorization_context is None:
        return None
    (
        actor_kind,
        actor_principal_id,
        actor_reference,
        authentication_type,
        authority_kind,
        context_tenant_id,
        request_id,
    ) = _context_actor(authorization_context)
    effective_tenant_id = tenant_id if tenant_id is not None else context_tenant_id
    if (
        context_tenant_id is not None
        and effective_tenant_id != context_tenant_id
    ):
        raise SecurityAuditValidationError("AUDIT_TENANT_SCOPE_MISMATCH")
    if (
        context_tenant_id is None
        and effective_tenant_id is not None
        and authority_kind is not SecurityAuditAuthorityKind.INSTALLATION
    ):
        raise SecurityAuditValidationError("AUDIT_TENANT_SCOPE_MISMATCH")
    record = _event(
        actor_kind=actor_kind,
        actor_principal_id=actor_principal_id,
        actor_reference=actor_reference,
        authentication_type=authentication_type,
        authority_kind=authority_kind,
        tenant_id=effective_tenant_id,
        action=SecurityAuditAction(action),
        permissions=permissions,
        resource_type=(
            SecurityAuditResourceType(resource_type)
            if resource_type is not None
            else None
        ),
        resource_id=resource_id,
        result=SecurityAuditResult.ALLOWED,
        reason=SecurityAuditReason.COMPLETED,
        request_id=request_id,
    )
    append_security_audit_event(session, record)
    return record


def append_local_operator_security_event(
    session: Session,
    *,
    action: SecurityAuditAction,
    permissions: Iterable[Permission | str],
    resource_type: SecurityAuditResourceType | None = None,
    resource_id: str | None = None,
    tenant_id: str | None = None,
) -> SecurityAuditEventRecord:
    record = _event(
        actor_kind=SecurityAuditActorKind.LOCAL_OPERATOR,
        actor_principal_id=None,
        actor_reference=None,
        authentication_type=SecurityAuditAuthenticationType.LOCAL_OPERATOR_BOUNDARY,
        authority_kind=SecurityAuditAuthorityKind.LOCAL_OPERATOR,
        tenant_id=tenant_id,
        action=SecurityAuditAction(action),
        permissions=permissions,
        resource_type=(
            SecurityAuditResourceType(resource_type)
            if resource_type is not None
            else None
        ),
        resource_id=resource_id,
        result=SecurityAuditResult.ALLOWED,
        reason=SecurityAuditReason.COMPLETED,
        request_id=None,
    )
    append_security_audit_event(session, record)
    return record


def denial_reason(code: str, *, authority_kind: object | None = None) -> SecurityAuditReason:
    authority_value = getattr(authority_kind, "value", authority_kind)
    if code == "PERMISSION_DENIED":
        if authority_value == SecurityAuditAuthorityKind.INSTALLATION.value:
            return SecurityAuditReason.INSTALLATION_ASSIGNMENT_MISSING
        return SecurityAuditReason.MISSING_PERMISSION
    if code in {
        "AUTHORITY_KIND_MISMATCH",
        "HUMAN_AUTHORITY_REQUIRED",
        "MACHINE_PURPOSE_MISMATCH",
    }:
        return SecurityAuditReason.WRONG_AUTHORITY_KIND
    if code in {"AUTHORITY_SCOPE_MISMATCH", "TENANT_ACCESS_DENIED"}:
        return SecurityAuditReason.MEMBERSHIP_MISSING
    if code in {"SERVICE_PERMISSIONS_UNAVAILABLE", "SERVICE_PERMISSION_MISSING"}:
        return SecurityAuditReason.SERVICE_PERMISSION_MISSING
    if code == "CREDENTIAL_TARGET_DENIED":
        return SecurityAuditReason.CREDENTIAL_TARGET_DENIED
    if code == "V1_EXECUTION_DISABLED":
        return SecurityAuditReason.EXECUTION_DISABLED
    if code in {"UNKNOWN_AUTHORIZATION_OPERATION", "AUTHORIZATION_POLICY_UNAVAILABLE"}:
        return SecurityAuditReason.UNKNOWN_OPERATION
    if code == "RESOURCE_UNAVAILABLE":
        return SecurityAuditReason.RESOURCE_UNAVAILABLE
    return SecurityAuditReason.PRINCIPAL_INACTIVE


def append_authorization_denial(
    *,
    authorization_context: object | None,
    required_permissions: Iterable[Permission | str],
    failure_code: str,
    session_factory: Callable[[], Session] | None = None,
) -> bool:
    """Persist one denial independently; return False without changing denial."""

    if authorization_context is None:
        return False
    state = _CURRENT_AUDIT_REQUEST.get()
    request_scoped = session_factory is None and state is not None
    if request_scoped and state.denial_recorded:
        return False
    factory = session_factory or (state.session_factory if state is not None else None)
    if factory is None:
        return False
    if request_scoped:
        # Mark before I/O so an audit failure cannot trigger repeated attempts.
        state.denial_recorded = True
    try:
        (
            actor_kind,
            actor_principal_id,
            actor_reference,
            authentication_type,
            authority_kind,
            tenant_id,
            request_id,
        ) = _context_actor(authorization_context)
        action = (
            SecurityAuditAction.EXECUTION_DENIED
            if failure_code == "V1_EXECUTION_DISABLED"
            else SecurityAuditAction.AUTHORIZATION_DENIED
        )
        record = _event(
            actor_kind=actor_kind,
            actor_principal_id=actor_principal_id,
            actor_reference=actor_reference,
            authentication_type=authentication_type,
            authority_kind=authority_kind,
            tenant_id=tenant_id,
            action=action,
            permissions=required_permissions,
            resource_type=None,
            resource_id=None,
            result=SecurityAuditResult.DENIED,
            reason=denial_reason(failure_code, authority_kind=authority_kind),
            request_id=request_id,
        )
        with factory() as audit_session:
            append_security_audit_event(audit_session, record)
            audit_session.commit()
        return True
    except Exception:
        # Never stringify the exception: drivers may include bound values or a
        # credential-bearing connection URL.
        LOGGER.error("SECURITY_AUDIT_WRITE_FAILED action=%s", action.value if 'action' in locals() else "authorization.denied")
        return False
