from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import (
    AuthApiCredentialRecord,
    ServiceApiTenantBindingRecord,
)
from app.models.principal_identity import LEGACY_LOCAL_ISSUER, PrincipalType
from app.models.auth import (
    ApiCredentialCallerType,
    ApiCredentialCreate,
    ApiCredentialCreated,
    ApiCredentialView,
)
from app.models.security_audit import SecurityAuditAction, SecurityAuditResourceType
from app.repositories.auth_api_credential_repository import (
    active_human_credentials,
    add_auth_api_credential,
    load_auth_api_credential_by_digest,
    update_auth_api_credential_last_used,
)
from app.repositories import tenant_repository
from app.repositories import principal_identity_repository
from app.security.principals import AuthPrincipal
from app.services.authority_assignments import (
    AuthorityAssignmentError,
    create_service_permission_assignment,
    resolve_service_permissions,
)
from app.security.authorization_policy import Permission
from app.services.security_audit import append_allowed_security_event
from app.services.principal_identity import (
    PrincipalIdentityError,
    PrincipalNotProvisionedError,
    PrincipalTypeMismatchError,
    create_service_principal,
    provision_external_human_principal,
    require_active_principal,
)


API_CREDENTIAL_PREFIX = "topo_api_"
MAX_GENERATION_ATTEMPTS = 3


class AuthApiCredentialPersistenceError(RuntimeError):
    """A named API-credential persistence operation failed closed."""


class InactiveAuthApiCredentialError(RuntimeError):
    """A digest matched a named credential that is not active."""


class ServiceTenantAccessError(RuntimeError):
    """The creator cannot bind a service credential to the requested tenant."""


@dataclass(frozen=True)
class ResolvedApiCredential:
    record: AuthApiCredentialRecord
    principal: AuthPrincipal


def credential_secret_digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_utc(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return _as_utc(parsed)


def _record_roles(record: AuthApiCredentialRecord) -> tuple[str, ...] | None:
    try:
        value = json.loads(record.roles_json)
    except (TypeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(value, list)
        or any(
            not isinstance(role, str) or not role or role != role.strip()
            for role in value
        )
        or len(set(value)) != len(value)
    ):
        return None
    return tuple(value)


def _active_resolution(
    session: Session,
    record: AuthApiCredentialRecord,
    *,
    now: datetime,
) -> ResolvedApiCredential | None:
    if record.revoked_at is not None:
        return None
    if (
        not record.subject
        or record.subject != record.subject.strip()
        or record.subject.lower() == "unknown"
        or not record.display_name
    ):
        return None
    expiry = _parse_utc(record.expires_at)
    roles = _record_roles(record)
    if expiry is None or now >= expiry or roles is None:
        return None
    try:
        caller_type = ApiCredentialCallerType(record.caller_type)
    except ValueError:
        return None
    authentication_type = (
        "human_api_token"
        if caller_type is ApiCredentialCallerType.HUMAN_API
        else "service_api_token"
    )
    expected_type = (
        PrincipalType.HUMAN
        if caller_type is ApiCredentialCallerType.HUMAN_API
        else PrincipalType.SERVICE
    )
    try:
        durable_principal = require_active_principal(
            session,
            principal_id=record.principal_id,
            principal_type=expected_type,
        )
    except (
        PrincipalNotProvisionedError,
        PrincipalTypeMismatchError,
    ):
        return None
    identities = (
        principal_identity_repository.list_external_identities_for_principal(
            session,
            durable_principal.principal_id,
        )
        if expected_type is PrincipalType.HUMAN
        else []
    )
    identity = identities[0] if identities else None
    return ResolvedApiCredential(
        record=record,
        principal=AuthPrincipal(
            principal_id=durable_principal.principal_id,
            principal_type=durable_principal.principal_type,
            subject=record.subject,
            display_name=durable_principal.display_name,
            roles=roles,
            authentication_type=authentication_type,
            external_issuer=identity.issuer if identity is not None else None,
            external_subject=identity.subject if identity is not None else None,
        ),
    )


def create_auth_api_credential(
    session: Session,
    *,
    request: ApiCredentialCreate,
    created_by_subject: str,
    created_by_principal_id: str | None = None,
    now: datetime | None = None,
) -> ApiCredentialCreated:
    if (
        not created_by_subject
        or created_by_subject != created_by_subject.strip()
        or created_by_subject.lower() == "unknown"
    ):
        raise ValueError("A stable creator subject is required.")
    created_at = _as_utc(now or _utc_now())
    expires_at = created_at + timedelta(days=request.expires_in_days)
    if created_by_principal_id is None:
        creator = provision_external_human_principal(
            session,
            issuer=LEGACY_LOCAL_ISSUER,
            subject=created_by_subject,
            display_name=created_by_subject,
            authentication_type="api_token",
        )
        created_by_principal_id = creator.principal_id
    if created_by_principal_id is None:
        raise AuthApiCredentialPersistenceError("Principal identity is unavailable.")
    require_active_principal(
        session,
        principal_id=created_by_principal_id,
        principal_type=PrincipalType.HUMAN,
    )

    if request.caller_type is ApiCredentialCallerType.HUMAN_API:
        if request.principal_id is None:
            if request.subject is None:
                raise ValueError("Human credential identity is required.")
            target = provision_external_human_principal(
                session,
                issuer=LEGACY_LOCAL_ISSUER,
                subject=request.subject,
                display_name=request.display_name or request.subject,
                authentication_type="human_api_token",
                roles=tuple(request.roles),
                now=created_at,
            )
            target_principal_id = target.principal_id
            subject_metadata = request.subject
            display_name = target.display_name
        else:
            target_record = require_active_principal(
                session,
                principal_id=request.principal_id,
                principal_type=PrincipalType.HUMAN,
            )
            identities = principal_identity_repository.list_external_identities_for_principal(
                session,
                target_record.principal_id,
            )
            if not identities:
                raise PrincipalNotProvisionedError("PRINCIPAL_NOT_PROVISIONED")
            if request.subject is not None:
                matching = next(
                    (
                        identity
                        for identity in identities
                        if identity.issuer == LEGACY_LOCAL_ISSUER
                        and identity.subject == request.subject
                    ),
                    None,
                )
                if matching is None:
                    raise PrincipalNotProvisionedError("PRINCIPAL_NOT_PROVISIONED")
                subject_metadata = matching.subject
            else:
                subject_metadata = identities[0].subject
            target_principal_id = target_record.principal_id
            display_name = target_record.display_name
    else:
        if request.principal_id is None:
            target_record = create_service_principal(
                session,
                display_name=request.display_name or request.subject or request.name,
                now=created_at,
            )
        else:
            target_record = require_active_principal(
                session,
                principal_id=request.principal_id,
                principal_type=PrincipalType.SERVICE,
            )
            target_record = (
                principal_identity_repository.load_active_principal_for_update(
                    session,
                    target_record.principal_id,
                )
            )
            if target_record is None:
                raise PrincipalNotProvisionedError("PRINCIPAL_NOT_PROVISIONED")
        target_principal_id = target_record.principal_id
        display_name = target_record.display_name
        subject_metadata = request.subject or target_record.display_name

    tenant_id = request.tenant_id
    if request.caller_type is ApiCredentialCallerType.SERVICE_API:
        if (
            tenant_id is None
            or tenant_repository.load_active_tenant(session, tenant_id) is None
            or tenant_repository.load_active_tenant_membership(
                session,
                tenant_id=tenant_id,
                principal_id=created_by_principal_id,
            )
            is None
        ):
            raise ServiceTenantAccessError(
                "Service credential tenant access is not permitted."
            )
        existing_tenant_ids = tenant_repository.service_principal_tenant_ids(
            session,
            target_principal_id,
        )
        if existing_tenant_ids and existing_tenant_ids != {tenant_id}:
            raise ServiceTenantAccessError(
                "Service principal tenant binding cannot be changed."
            )
        if request.principal_id is None:
            # Flush-only: principal, authority, credential, and fixed binding
            # become durable together in the credential transaction below.
            create_service_permission_assignment(
                session,
                principal_id=target_principal_id,
                permissions=request.permissions,
                now=created_at,
            )
        else:
            existing_permissions = resolve_service_permissions(
                session, principal_id=target_principal_id,
            )
            if (
                request.permissions is not None
                and set(request.permissions) != existing_permissions
            ):
                raise AuthorityAssignmentError(
                    "SERVICE_PERMISSION_ASSIGNMENT_CONFLICT"
                )

    for attempt in range(MAX_GENERATION_ATTEMPTS):
        raw_secret = API_CREDENTIAL_PREFIX + secrets.token_urlsafe(48)
        record = AuthApiCredentialRecord(
            credential_id=f"api-credential:{uuid4()}",
            credential_secret_digest=credential_secret_digest(raw_secret),
            credential_hint=raw_secret[-8:],
            name=request.name,
            caller_type=request.caller_type.value,
            principal_id=target_principal_id,
            subject=subject_metadata,
            display_name=display_name,
            roles_json=json.dumps(request.roles, separators=(",", ":")),
            created_at=created_at.isoformat(),
            created_by_subject=created_by_subject,
            expires_at=expires_at.isoformat(),
            revoked_at=None,
            revoked_by_subject=None,
            last_used_at=None,
            updated_at=created_at.isoformat(),
        )
        try:
            # Retry a generated ID/secret collision without discarding the new
            # principal and assignment that belong to this outer transaction.
            with session.begin_nested():
                add_auth_api_credential(session, record)
                session.flush()
                if tenant_id is not None:
                    tenant_repository.add_service_api_tenant_binding(
                        session,
                        ServiceApiTenantBindingRecord(
                            binding_id=f"service-tenant-binding:{uuid4()}",
                            credential_id=record.credential_id,
                            tenant_id=tenant_id,
                            created_at=created_at.isoformat(),
                            created_by_subject=created_by_subject,
                        ),
                    )
                session.flush()
            append_allowed_security_event(
                session,
                action=(
                    SecurityAuditAction.HUMAN_API_CREDENTIAL_CREATED
                    if request.caller_type is ApiCredentialCallerType.HUMAN_API
                    else SecurityAuditAction.SERVICE_API_CREDENTIAL_CREATED
                ),
                permissions=(
                    []
                    if request.caller_type is ApiCredentialCallerType.HUMAN_API
                    else [Permission.CREDENTIAL_ROTATE]
                ),
                resource_type=SecurityAuditResourceType.API_CREDENTIAL,
                resource_id=record.credential_id,
                tenant_id=tenant_id,
            )
            session.commit()
            return credential_created_view(
                record,
                raw_secret,
                tenant_id=tenant_id,
            )
        except IntegrityError as exc:
            if attempt + 1 == MAX_GENERATION_ATTEMPTS:
                session.rollback()
                raise AuthApiCredentialPersistenceError(
                    "API credential generation failed safely."
                ) from exc
        except SQLAlchemyError as exc:
            session.rollback()
            raise AuthApiCredentialPersistenceError(
                "API credential persistence failed."
            ) from exc
    raise AuthApiCredentialPersistenceError(
        "API credential generation failed safely."
    )


def resolve_auth_api_credential_by_digest(
    session: Session,
    *,
    digest: str,
    now: datetime | None = None,
) -> ResolvedApiCredential | None:
    record = load_auth_api_credential_by_digest(session, digest)
    if record is None:
        return None
    return _active_resolution(session, record, now=_as_utc(now or _utc_now()))


def authenticate_auth_api_credential(
    session: Session,
    *,
    raw_secret: str,
    now: datetime | None = None,
) -> ResolvedApiCredential | None:
    reference_time = _as_utc(now or _utc_now())
    digest = credential_secret_digest(raw_secret)
    record = load_auth_api_credential_by_digest(session, digest)
    if record is None:
        return None
    resolved = _active_resolution(session, record, now=reference_time)
    if resolved is None:
        raise InactiveAuthApiCredentialError(
            "The named API credential is inactive."
        )
    observed_at = reference_time.isoformat()
    try:
        update_auth_api_credential_last_used(
            session,
            credential_id=resolved.record.credential_id,
            observed_at=observed_at,
        )
        session.commit()
        resolved.record.last_used_at = observed_at
        resolved.record.updated_at = observed_at
    except SQLAlchemyError as exc:
        session.rollback()
        raise AuthApiCredentialPersistenceError(
            "API credential usage persistence failed."
        ) from exc
    return resolved


def revoke_auth_api_credential(
    session: Session,
    *,
    record: AuthApiCredentialRecord,
    revoked_by_subject: str,
    now: datetime | None = None,
) -> None:
    if (
        not revoked_by_subject
        or revoked_by_subject != revoked_by_subject.strip()
        or revoked_by_subject.lower() == "unknown"
    ):
        raise ValueError("A stable revoker subject is required.")
    if record.revoked_at is not None:
        return
    revoked_at = _as_utc(now or _utc_now()).isoformat()
    record.revoked_at = revoked_at
    record.revoked_by_subject = revoked_by_subject
    record.updated_at = revoked_at
    try:
        binding = tenant_repository.load_service_api_tenant_binding(
            session, record.credential_id
        )
        append_allowed_security_event(
            session,
            action=(
                SecurityAuditAction.HUMAN_API_CREDENTIAL_REVOKED
                if record.caller_type == ApiCredentialCallerType.HUMAN_API.value
                else SecurityAuditAction.SERVICE_API_CREDENTIAL_REVOKED
            ),
            permissions=(
                []
                if record.caller_type == ApiCredentialCallerType.HUMAN_API.value
                else [Permission.CREDENTIAL_ROTATE]
            ),
            resource_type=SecurityAuditResourceType.API_CREDENTIAL,
            resource_id=record.credential_id,
            tenant_id=binding.tenant_id if binding is not None else None,
        )
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise AuthApiCredentialPersistenceError(
            "API credential revocation failed."
        ) from exc


def credential_view(
    record: AuthApiCredentialRecord,
    *,
    tenant_id: str | None = None,
) -> ApiCredentialView:
    roles = _record_roles(record)
    if roles is None:
        raise AuthApiCredentialPersistenceError(
            "API credential metadata is invalid."
        )
    try:
        caller_type = ApiCredentialCallerType(record.caller_type)
    except ValueError as exc:
        raise AuthApiCredentialPersistenceError(
            "API credential metadata is invalid."
        ) from exc
    return ApiCredentialView(
        credential_id=record.credential_id,
        credential_hint=record.credential_hint,
        name=record.name,
        caller_type=caller_type,
        principal_id=record.principal_id,
        principal_type=(
            PrincipalType.HUMAN.value
            if caller_type is ApiCredentialCallerType.HUMAN_API
            else PrincipalType.SERVICE.value
        ),
        subject=record.subject,
        display_name=record.display_name,
        roles=list(roles),
        created_at=record.created_at,
        created_by_subject=record.created_by_subject,
        expires_at=record.expires_at,
        revoked_at=record.revoked_at,
        revoked_by_subject=record.revoked_by_subject,
        last_used_at=record.last_used_at,
        updated_at=record.updated_at,
        tenant_id=tenant_id,
    )


def credential_created_view(
    record: AuthApiCredentialRecord,
    raw_secret: str,
    *,
    tenant_id: str | None = None,
) -> ApiCredentialCreated:
    return ApiCredentialCreated(
        **credential_view(record, tenant_id=tenant_id).model_dump(),
        api_credential=raw_secret,
    )


def has_active_human_admin_credential(
    session: Session,
    *,
    now: datetime | None = None,
) -> bool:
    reference_time = _as_utc(now or _utc_now())
    records = active_human_credentials(
        session,
        reference_time=reference_time.isoformat(),
    )
    return any(
        (resolved := _active_resolution(session, record, now=reference_time)) is not None
        and "admin" in resolved.principal.roles
        for record in records
    )
