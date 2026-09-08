"""Executable PH-5 authorization boundary derived from the frozen PH-5B plan.

Authentication and PH-3 tenant ownership remain independent defenses.  This
module turns their server-derived identities into short-lived, typed authority
contexts and enforces the exact route/operation plans.  Contexts are never
accepted from request payloads and contain no credential or secret material.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import AsyncGenerator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.db import models as db_models
from app.models.principal_identity import PrincipalType
from app.security.approval_authorization import authenticated_principal
from app.security.authorization_plan import (
    AuthorizationIntent,
    operation_authorization_plan,
    route_authorization_plan,
)
from app.security.authorization_policy import Permission
from app.security.principals import AuthPrincipal
from app.security.tenant_context import (
    HUMAN_AUTHENTICATION_TYPES,
    TENANT_HEADER_NAME,
    TenantActorKind,
    TenantContext,
    resolve_tenant_context,
)
from app.repositories.tenant_repository import (
    load_active_human_tenant_context,
    load_service_api_tenant_binding,
    service_principal_tenant_ids,
)
from app.repositories.tenant_scope import tenant_get
from app.security.machine_tenant import machine_tenant_is_active
from app.services.authority_assignments import (
    AuthorityAssignmentError,
    resolve_installation_permissions,
    resolve_service_permissions,
    resolve_tenant_permissions,
)
from app.services.principal_identity import PrincipalIdentityError


class AuthorityKind(StrEnum):
    AUTHENTICATION_SELF_SERVICE = "authentication_self_service"
    HUMAN_TENANT = "human_tenant"
    SERVICE_TENANT = "service_tenant"
    INSTALLATION = "installation"
    AGENT_FIXED_PURPOSE = "agent_fixed_purpose"
    PROVIDER_FIXED_PURPOSE = "provider_fixed_purpose"


class AuthorizationFailure(RuntimeError):
    """A typed internal operation was not authorized."""

    def __init__(
        self,
        code: str,
        *,
        required_permissions: frozenset[Permission] = frozenset(),
    ) -> None:
        super().__init__(code)
        self.code = code
        self.required_permissions = required_permissions


_CONTEXT_CONSTRUCTION_TOKEN = object()


@dataclass(frozen=True, init=False)
class AuthorizationContext:
    """Request-scoped authority created only by this module's resolvers."""

    actor_principal_id: str
    actor_principal_type: str
    authority_kind: AuthorityKind
    tenant_id: str | None
    effective_permissions: frozenset[Permission]
    authentication_provenance: str
    fixed_purpose: str | None
    request_id: str | None

    def __init__(
        self,
        *,
        _construction_token: object,
        actor_principal_id: str,
        actor_principal_type: str,
        authority_kind: AuthorityKind,
        tenant_id: str | None,
        effective_permissions: frozenset[Permission],
        authentication_provenance: str,
        fixed_purpose: str | None = None,
        request_id: str | None = None,
    ) -> None:
        if _construction_token is not _CONTEXT_CONSTRUCTION_TOKEN:
            raise TypeError("AuthorizationContext is server-constructed.")
        object.__setattr__(self, "actor_principal_id", actor_principal_id)
        object.__setattr__(self, "actor_principal_type", actor_principal_type)
        object.__setattr__(self, "authority_kind", authority_kind)
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(self, "effective_permissions", effective_permissions)
        object.__setattr__(self, "authentication_provenance", authentication_provenance)
        object.__setattr__(self, "fixed_purpose", fixed_purpose)
        object.__setattr__(self, "request_id", request_id)


_CURRENT_AUTHORIZATION: ContextVar[AuthorizationContext | None] = ContextVar(
    "topo_authorization_context", default=None
)


def _context(
    principal: AuthPrincipal,
    *,
    authority_kind: AuthorityKind,
    tenant_id: str | None = None,
    permissions: frozenset[Permission] = frozenset(),
    fixed_purpose: str | None = None,
    request_id: str | None = None,
) -> AuthorizationContext:
    if not principal.principal_id or not principal.principal_type:
        raise AuthorizationFailure("AUTHORITY_IDENTITY_UNAVAILABLE")
    return AuthorizationContext(
        _construction_token=_CONTEXT_CONSTRUCTION_TOKEN,
        actor_principal_id=principal.principal_id,
        actor_principal_type=principal.principal_type,
        authority_kind=authority_kind,
        tenant_id=tenant_id,
        effective_permissions=permissions,
        authentication_provenance=principal.authentication_type,
        fixed_purpose=fixed_purpose,
        request_id=request_id,
    )


_AGENT_FIXED_PURPOSES = frozenset({
    "app.repositories.agent_repository.enroll_agent",
    "app.api.agents.get_config",
    "app.repositories.agent_repository.record_heartbeat",
    "app.services.agent_snapshot_ingest.persist_agent_snapshot",
    "app.repositories.runtime_observability_repository.record_sensor_heartbeat",
    "app.repositories.runtime_observability_repository.ingest_runtime_event_batch",
    "app.api.agents.submit_change_events",
    "app.api.agents.submit_failure_signals",
})
_PROVIDER_FIXED_PURPOSES = frozenset({
    "app.services.change_source_ingest.ingest_change_source_webhook",
})


def _machine_context(
    *,
    actor_id: str,
    actor_type: str,
    authority_kind: AuthorityKind,
    tenant_id: str,
    authentication_provenance: str,
    fixed_purpose: str,
) -> AuthorizationContext:
    return AuthorizationContext(
        _construction_token=_CONTEXT_CONSTRUCTION_TOKEN,
        actor_principal_id=actor_id,
        actor_principal_type=actor_type,
        authority_kind=authority_kind,
        tenant_id=tenant_id,
        effective_permissions=frozenset(),
        authentication_provenance=authentication_provenance,
        fixed_purpose=fixed_purpose,
    )


def authorize_agent_fixed_purpose(
    session: Session, *, agent: object, fixed_purpose: str
) -> AuthorizationContext:
    if fixed_purpose not in _AGENT_FIXED_PURPOSES:
        raise AuthorizationFailure("MACHINE_PURPOSE_MISMATCH")
    if not isinstance(agent, db_models.TopoAgentRecord):
        raise AuthorizationFailure("AUTHORITY_KIND_MISMATCH")
    if (
        agent.revoked_at is not None
        or not machine_tenant_is_active(session, tenant_id=agent.tenant_id)
    ):
        raise AuthorizationFailure("MACHINE_AUTHORITY_UNAVAILABLE")
    return _machine_context(
        actor_id=agent.agent_id,
        actor_type="agent",
        authority_kind=AuthorityKind.AGENT_FIXED_PURPOSE,
        tenant_id=agent.tenant_id,
        authentication_provenance="agent_bearer",
        fixed_purpose=fixed_purpose,
    )


def authorize_agent_enrollment_fixed_purpose(
    session: Session,
    *,
    enrollment: object,
    reference_time: datetime,
) -> AuthorizationContext:
    """Derive enrollment-only authority from a verified durable token row."""
    if not isinstance(enrollment, db_models.AgentEnrollmentTokenRecord):
        raise AuthorizationFailure("AUTHORITY_KIND_MISMATCH")
    try:
        expires_at = datetime.fromisoformat(
            enrollment.expires_at.replace("Z", "+00:00")
        )
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
    except (AttributeError, TypeError, ValueError) as exc:
        raise AuthorizationFailure("MACHINE_AUTHORITY_UNAVAILABLE") from exc
    if (
        enrollment.revoked_at is not None
        or enrollment.use_count >= enrollment.max_uses
        or expires_at <= (
            reference_time
            if reference_time.tzinfo is not None
            else reference_time.replace(tzinfo=UTC)
        ).astimezone(UTC)
        or not machine_tenant_is_active(
            session, tenant_id=enrollment.tenant_id
        )
    ):
        raise AuthorizationFailure("MACHINE_AUTHORITY_UNAVAILABLE")
    return _machine_context(
        actor_id=enrollment.enrollment_token_id,
        actor_type="agent_enrollment",
        authority_kind=AuthorityKind.AGENT_FIXED_PURPOSE,
        tenant_id=enrollment.tenant_id,
        authentication_provenance="agent_enrollment_token",
        fixed_purpose="app.repositories.agent_repository.enroll_agent",
    )


def authorize_provider_fixed_purpose(
    session: Session, *, source: object, fixed_purpose: str
) -> AuthorizationContext:
    if fixed_purpose not in _PROVIDER_FIXED_PURPOSES:
        raise AuthorizationFailure("MACHINE_PURPOSE_MISMATCH")
    if not isinstance(source, db_models.ChangeSourceRecord) or not source.enabled:
        raise AuthorizationFailure("MACHINE_AUTHORITY_UNAVAILABLE")
    if not machine_tenant_is_active(session, tenant_id=source.tenant_id):
        raise AuthorizationFailure("MACHINE_AUTHORITY_UNAVAILABLE")
    return _machine_context(
        actor_id=source.source_id,
        actor_type="provider",
        authority_kind=AuthorityKind.PROVIDER_FIXED_PURPOSE,
        tenant_id=source.tenant_id,
        authentication_provenance="provider_verified",
        fixed_purpose=fixed_purpose,
    )


def _require_permissions(
    effective: frozenset[Permission], required: frozenset[Permission]
) -> None:
    if not required.issubset(effective):
        raise AuthorizationFailure(
            "PERMISSION_DENIED", required_permissions=required
        )


def authorize_tenant(
    session: Session,
    *,
    principal: AuthPrincipal,
    tenant_context: TenantContext,
    required_permissions: frozenset[Permission],
) -> AuthorizationContext:
    """Resolve current human/service authority for one proven tenant context."""
    if principal.principal_id != tenant_context.principal_id:
        raise AuthorizationFailure("AUTHORITY_SCOPE_MISMATCH")
    if tenant_context.actor_kind is TenantActorKind.HUMAN:
        if principal.principal_type != PrincipalType.HUMAN.value:
            raise AuthorizationFailure("AUTHORITY_KIND_MISMATCH")
        resolved = load_active_human_tenant_context(
            session,
            tenant_id=tenant_context.tenant_id,
            principal_id=principal.principal_id or "",
        )
        if (
            resolved is None
            or tenant_context.membership_id is None
            or resolved[1].membership_id != tenant_context.membership_id
        ):
            raise AuthorizationFailure("AUTHORITY_SCOPE_MISMATCH")
        effective = resolve_tenant_permissions(
            session,
            principal_id=principal.principal_id or "",
            tenant_id=tenant_context.tenant_id,
        )
        kind = AuthorityKind.HUMAN_TENANT
    elif tenant_context.actor_kind is TenantActorKind.SERVICE:
        if (
            principal.principal_type != PrincipalType.SERVICE.value
            or principal.authentication_type != "service_api_token"
        ):
            raise AuthorizationFailure("AUTHORITY_KIND_MISMATCH")
        if service_principal_tenant_ids(
            session, principal.principal_id or ""
        ) != {tenant_context.tenant_id}:
            raise AuthorizationFailure("AUTHORITY_SCOPE_MISMATCH")
        effective = resolve_service_permissions(
            session, principal_id=principal.principal_id or ""
        )
        kind = AuthorityKind.SERVICE_TENANT
    else:  # pragma: no cover - enum closes this branch
        raise AuthorizationFailure("AUTHORITY_KIND_MISMATCH")
    _require_permissions(effective, required_permissions)
    return _context(
        principal,
        authority_kind=kind,
        tenant_id=tenant_context.tenant_id,
        permissions=effective,
    )


def authorize_installation(
    session: Session,
    *,
    principal: AuthPrincipal,
    required_permissions: frozenset[Permission],
) -> AuthorizationContext:
    if principal.principal_type != PrincipalType.HUMAN.value:
        raise AuthorizationFailure("AUTHORITY_KIND_MISMATCH")
    effective = resolve_installation_permissions(
        session, principal_id=principal.principal_id or ""
    )
    _require_permissions(effective, required_permissions)
    return _context(
        principal,
        authority_kind=AuthorityKind.INSTALLATION,
        permissions=effective,
    )


def authorize_authentication_self_service(
    principal: AuthPrincipal,
) -> AuthorizationContext:
    return _context(
        principal,
        authority_kind=AuthorityKind.AUTHENTICATION_SELF_SERVICE,
    )


def require_human_authenticator_caller(request: Request) -> AuthPrincipal:
    """Credential-policy callers are humans; roles and memberships add nothing."""
    principal = authenticated_principal(request)
    if (
        principal.principal_type != PrincipalType.HUMAN.value
        or principal.authentication_type not in HUMAN_AUTHENTICATION_TYPES
    ):
        raise _forbidden(AuthorizationFailure("HUMAN_AUTHORITY_REQUIRED"))
    return principal


def authorize_service_credential_scope(
    request: Request,
    session: Session,
    *,
    principal: AuthPrincipal,
    required_permission: Permission,
    operation: str,
    expected_tenant_id: str | None = None,
) -> tuple[TenantContext, AuthorizationContext]:
    """Resolve current human membership and service-admin permission."""
    selected_tenant_id = _selected_tenant_id(request, principal)
    tenant_context = resolve_tenant_context(
        session,
        principal=principal,
        selected_tenant_id=selected_tenant_id,
        credential_id=None,
    )
    if (
        tenant_context.actor_kind is not TenantActorKind.HUMAN
        or (
            expected_tenant_id is not None
            and expected_tenant_id != tenant_context.tenant_id
        )
    ):
        raise _forbidden(AuthorizationFailure("TENANT_ACCESS_DENIED"))
    try:
        context = authorize_tenant(
            session,
            principal=principal,
            tenant_context=tenant_context,
            required_permissions=frozenset({required_permission}),
        )
    except AuthorizationFailure as exc:
        raise _forbidden(exc) from exc
    request.state.tenant_context = tenant_context
    request.state.authorization_context = context
    _CURRENT_AUTHORIZATION.set(context)
    authorize_service_operation(
        f"authenticator.service.{operation}",
        authorization_context=context,
    )
    return tenant_context, context


def authorize_persisted_credential_target(
    request: Request,
    session: Session,
    *,
    record: object,
    operation: str,
) -> AuthorizationContext:
    """Apply the frozen human-self/service-tenant target policy to one record."""
    principal = require_human_authenticator_caller(request)
    caller_type = getattr(record, "caller_type", None)
    target_principal_id = getattr(record, "principal_id", None)
    credential_id = getattr(record, "credential_id", None)
    if caller_type == "human_api":
        if target_principal_id != principal.principal_id:
            raise HTTPException(status_code=404, detail="API credential not found.")
        context = authorize_authentication_self_service(principal)
        authorize_service_operation(
            f"authenticator.human.{operation}",
            authorization_context=context,
        )
        return context
    if caller_type != "service_api" or not isinstance(credential_id, str):
        raise HTTPException(status_code=404, detail="API credential not found.")
    # Binding is checked before permission denial so a foreign and nonexistent
    # identifier retain the same public 404 behavior.
    selected_tenant_id = _selected_tenant_id(request, principal)
    tenant_context = resolve_tenant_context(
        session,
        principal=principal,
        selected_tenant_id=selected_tenant_id,
        credential_id=None,
    )
    binding = load_service_api_tenant_binding(session, credential_id)
    if binding is None or binding.tenant_id != tenant_context.tenant_id:
        raise HTTPException(status_code=404, detail="API credential not found.")
    permission = (
        Permission.CREDENTIAL_METADATA_READ
        if operation in {"get", "list"}
        else Permission.CREDENTIAL_ROTATE
    )
    try:
        context = authorize_tenant(
            session,
            principal=principal,
            tenant_context=tenant_context,
            required_permissions=frozenset({permission}),
        )
    except AuthorizationFailure as exc:
        raise _forbidden(exc) from exc
    request.state.tenant_context = tenant_context
    request.state.authorization_context = context
    _CURRENT_AUTHORIZATION.set(context)
    authorize_service_operation(
        f"authenticator.service.{operation}",
        authorization_context=context,
    )
    return context


def current_authorization_context() -> AuthorizationContext | None:
    return _CURRENT_AUTHORIZATION.get()


def bind_authorization_context(context: AuthorizationContext) -> Token:
    if not isinstance(context, AuthorizationContext):
        raise AuthorizationFailure("AUTHORIZATION_CONTEXT_REQUIRED")
    return _CURRENT_AUTHORIZATION.set(context)


def reset_authorization_context(token: Token) -> None:
    _CURRENT_AUTHORIZATION.reset(token)


def authorize_service_operation(
    operation_id: str,
    *,
    authorization_context: AuthorizationContext | None = None,
) -> AuthorizationContext:
    """Enforce one frozen operation entry; unknown operations fail closed."""
    try:
        plan = operation_authorization_plan(operation_id)
    except KeyError as exc:
        raise AuthorizationFailure("UNKNOWN_AUTHORIZATION_OPERATION") from exc
    if plan.authority.intent is AuthorizationIntent.V1_DORMANT_EXECUTION_DENY:
        raise AuthorizationFailure("V1_EXECUTION_DISABLED")
    context = authorization_context or current_authorization_context()
    if not isinstance(context, AuthorizationContext):
        raise AuthorizationFailure("AUTHORIZATION_CONTEXT_REQUIRED")
    intent = plan.authority.intent
    if intent is AuthorizationIntent.TENANT_PERMISSION:
        if context.authority_kind in {
            AuthorityKind.HUMAN_TENANT,
            AuthorityKind.SERVICE_TENANT,
        }:
            _require_permissions(
                context.effective_permissions, plan.authority.permissions
            )
        elif context.authority_kind in {
            AuthorityKind.AGENT_FIXED_PURPOSE,
            AuthorityKind.PROVIDER_FIXED_PURPOSE,
        }:
            if context.fixed_purpose not in plan.delegated_callers:
                raise AuthorizationFailure("MACHINE_PURPOSE_MISMATCH")
        else:
            raise AuthorizationFailure("AUTHORITY_KIND_MISMATCH")
    elif intent is AuthorizationIntent.INSTALLATION_PERMISSION:
        if context.authority_kind is not AuthorityKind.INSTALLATION:
            raise AuthorizationFailure("AUTHORITY_KIND_MISMATCH")
        _require_permissions(
            context.effective_permissions, plan.authority.permissions
        )
    elif intent is AuthorizationIntent.AUTHENTICATION_SELF_SERVICE:
        if context.authority_kind is not AuthorityKind.AUTHENTICATION_SELF_SERVICE:
            raise AuthorizationFailure("AUTHORITY_KIND_MISMATCH")
    elif intent is AuthorizationIntent.AGENT_FIXED_PURPOSE:
        if (
            context.authority_kind is not AuthorityKind.AGENT_FIXED_PURPOSE
            or context.fixed_purpose != operation_id
        ):
            raise AuthorizationFailure("MACHINE_PURPOSE_MISMATCH")
    elif intent is AuthorizationIntent.PROVIDER_FIXED_PURPOSE:
        if (
            context.authority_kind is not AuthorityKind.PROVIDER_FIXED_PURPOSE
            or context.fixed_purpose != operation_id
        ):
            raise AuthorizationFailure("MACHINE_PURPOSE_MISMATCH")
    else:
        raise AuthorizationFailure("AUTHORITY_KIND_MISMATCH")
    return context


def _forbidden(failure: AuthorizationFailure) -> HTTPException:
    detail: dict[str, object] = {"code": failure.code}
    if failure.required_permissions:
        detail["required_permissions"] = sorted(
            item.value for item in failure.required_permissions
        )
    return HTTPException(status_code=403, detail=detail)


def _selected_tenant_id(request: Request, principal: AuthPrincipal) -> str | None:
    selected = request.headers.get(TENANT_HEADER_NAME)
    if principal.authentication_type == "service_api_token":
        return selected
    if selected is None or not selected:
        # Preserve the accepted PH-3 selector response contract.
        raise HTTPException(status_code=400, detail="TENANT_CONTEXT_REQUIRED")
    return selected


_RESOURCE_PARAMETER_MODELS: dict[str, tuple[str, ...]] = {
    "incident_id": ("IncidentRecord",),
    "analysis_id": ("IncidentAnalysisRecord", "CausalAnalysisRecord"),
    "signal_id": ("SignalRecord",),
    "snapshot_id": ("SnapshotRecord",),
    "change_id": ("ChangeRecord",),
    "event_id": ("ChangeEventRecord",),
    "source_id": ("ChangeSourceRecord",),
    "dead_letter_id": ("ChangeSourceDeadLetterRecord",),
    "webhook_id": ("WebhookEndpointRecord",),
    "membership_id": ("TenantMembershipRecord",),
    "agent_id": ("TopoAgentRecord",),
    "override_id": ("IdentityOverrideRecord",),
    "recommendation_id": ("RecommendationRecord",),
    "verification_id": ("RecoveryVerificationRecord",),
    "session_id": ("CopilotSessionRecord",),
    "plan_id": ("InvestigationPlanRecord",),
    "report_id": ("PostIncidentReportRecord",),
    "action_item_id": ("ReportActionItemRecord",),
}


def _mask_absent_tenant_resource(
    request: Request, session: Session, *, tenant_id: str
) -> None:
    """Return the accepted absence response before a permission detail leak."""
    for parameter, model_names in _RESOURCE_PARAMETER_MODELS.items():
        identifier = request.path_params.get(parameter)
        if not isinstance(identifier, str):
            continue
        if not any(
            tenant_get(
                session,
                getattr(db_models, model_name),
                identifier,
                tenant_id=tenant_id,
            )
            is not None
            for model_name in model_names
        ):
            raise HTTPException(status_code=404, detail="Resource not found.")


async def require_route_authorization(
    request: Request,
    session: Session = Depends(get_session),
) -> AsyncGenerator[None, None]:
    """Global FastAPI dependency binding every registered production route."""
    if request.method.upper() == "OPTIONS":
        yield
        return
    route = request.scope.get("route")
    path_template = getattr(route, "path", None)
    if path_template in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}:
        yield
        return
    if not isinstance(path_template, str):
        raise _forbidden(AuthorizationFailure("AUTHORIZATION_POLICY_UNAVAILABLE"))
    try:
        plan = route_authorization_plan(request.method.upper(), path_template)
    except KeyError as exc:
        raise _forbidden(
            AuthorizationFailure("AUTHORIZATION_POLICY_UNAVAILABLE")
        ) from exc

    intent = plan.authority.intent
    if intent is AuthorizationIntent.PUBLIC:
        yield
        return
    if intent is AuthorizationIntent.V1_DORMANT_EXECUTION_DENY:
        # Preserve the accepted authentication-before-authorization ordering:
        # anonymous and revoked callers remain 401, while every authenticated
        # V1 authority receives the same bounded disabled-surface denial.
        authenticated_principal(request)
        raise _forbidden(AuthorizationFailure("V1_EXECUTION_DISABLED"))
    if intent in {
        AuthorizationIntent.AGENT_FIXED_PURPOSE,
        AuthorizationIntent.PROVIDER_FIXED_PURPOSE,
    }:
        # Their existing route dependencies/services authenticate the exact
        # enrolled agent or provider proof.  They never become Permissions.
        yield
        return

    principal = authenticated_principal(request)
    token: Token | None = None
    try:
        if intent in {
            AuthorizationIntent.AUTHENTICATION_SELF_SERVICE,
            AuthorizationIntent.AUTHENTICATOR_CREDENTIAL_POLICY,
        }:
            context = authorize_authentication_self_service(principal)
        elif intent is AuthorizationIntent.INSTALLATION_PERMISSION:
            context = authorize_installation(
                session,
                principal=principal,
                required_permissions=plan.authority.permissions,
            )
        elif intent is AuthorizationIntent.TENANT_PERMISSION:
            selected_tenant_id = _selected_tenant_id(request, principal)
            tenant_context = resolve_tenant_context(
                session,
                principal=principal,
                selected_tenant_id=selected_tenant_id,
                credential_id=getattr(
                    request.state, "auth_api_credential_id", None
                ),
            )
            context = authorize_tenant(
                session,
                principal=principal,
                tenant_context=tenant_context,
                required_permissions=frozenset(),
            )
            request.state.tenant_context = tenant_context
            try:
                _require_permissions(
                    context.effective_permissions, plan.authority.permissions
                )
            except AuthorizationFailure:
                _mask_absent_tenant_resource(
                    request,
                    session,
                    tenant_id=tenant_context.tenant_id,
                )
                raise
        else:  # pragma: no cover - frozen enum and registry close this branch
            raise AuthorizationFailure("AUTHORIZATION_POLICY_UNAVAILABLE")
        request.state.authorization_context = context
        token = bind_authorization_context(context)
        yield
    except AuthorizationFailure as exc:
        raise _forbidden(exc) from exc
    except (AuthorityAssignmentError, PrincipalIdentityError) as exc:
        raise _forbidden(AuthorizationFailure("AUTHORITY_UNAVAILABLE")) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503, detail="Authorization service is unavailable."
        ) from exc
    finally:
        if token is not None:
            reset_authorization_context(token)
