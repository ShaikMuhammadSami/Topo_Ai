"""Atomic provider-source and outbound-webhook SecretStore integration."""

from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ChangeSourceRecord,
    SecretRecord,
    WebhookEndpointRecord,
    utc_now_iso,
)
from app.models.change_sources import ChangeSourceCreate, ChangeSourceUpdate, ChangeSourceView
from app.models.security_audit import SecurityAuditAction, SecurityAuditResourceType
from app.models.secret_store import SecretBinding, SecretMaterial, SecretPurpose, SecretStoreError
from app.models.webhooks import WebhookEndpointCreate, WebhookEndpointUpdate, WebhookEndpointView
from app.repositories.change_source_repository import (
    change_source_view,
    load_change_source,
    new_change_source_id,
)
from app.repositories.tenant_scope import DomainTenant, tenant_commit, tenant_value
from app.repositories.webhook_repository import _endpoint_to_view, load_webhook_endpoint_record
from app.services.secret_consumer_policy import (
    ProviderPolicyError,
    deserialize_protected_headers,
    serialize_protected_headers,
    source_binding,
    validate_protected_headers,
    validate_provider_configuration,
    validate_webhook_url,
    webhook_binding,
)
from app.services.secret_store import SecretStore
from app.services.security_audit import append_allowed_security_event
from app.security.authorization_policy import Permission
from app.security.authorization_enforcement import (
    AuthorizationContext,
    require_authorization_permissions,
)
from app.security.egress_policy import (
    EgressPolicyError,
    EgressPurpose,
    Resolver,
    canonicalize_destination,
)


class SecretConsumerError(ValueError):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _operation_id(owner_id: str, action: str, idempotency_key: str) -> str:
    if (
        not isinstance(idempotency_key, str)
        or not 1 <= len(idempotency_key) <= 255
        or idempotency_key != idempotency_key.strip()
    ):
        raise SecretConsumerError("Idempotency-Key is required for credential changes.")
    digest = hashlib.sha256(
        f"v1|{owner_id}|{action}|{idempotency_key}".encode("utf-8")
    ).hexdigest()
    return f"consumer:{digest}"


def _material(value, *, minimum: int = 1) -> SecretMaterial:
    try:
        raw = value.get_secret_value().encode("utf-8")
        if len(raw) < minimum:
            raise ValueError()
        return SecretMaterial(raw)
    except (AttributeError, UnicodeEncodeError, ValueError, SecretStoreError):
        raise SecretConsumerError("Credential value is invalid.") from None


def _translate_secret_error(exc: SecretStoreError) -> SecretConsumerError:
    if str(exc) in {
        "SECRET_STORE_UNAVAILABLE",
        "SECRET_STORE_DISABLED",
        "SECRET_DECRYPT_FAILED",
        "SECRET_REQUIRED_KEY_MISSING",
    }:
        return SecretConsumerError("Credential service is unavailable.", 503)
    if str(exc) in {
        "SECRET_OPERATION_CONFLICT",
        "SECRET_CONCURRENT_MODIFICATION",
        "SECRET_REVOKED",
    }:
        return SecretConsumerError("Credential operation conflicts with current state.", 409)
    return SecretConsumerError("Credential operation failed.")


def _binding_record(session: Session, binding: SecretBinding) -> SecretRecord | None:
    return session.scalar(
        select(SecretRecord).where(
            SecretRecord.scope_kind == binding.scope.kind,
            SecretRecord.scope_id == binding.scope.scope_id,
            SecretRecord.tenant_id == binding.scope.tenant_id,
            SecretRecord.owner_type == binding.owner_type,
            SecretRecord.owner_id == binding.owner_id,
            SecretRecord.purpose == binding.purpose.value,
        )
    )


def _put_or_reprovision(
    session: Session,
    store: SecretStore,
    binding: SecretBinding,
    material: SecretMaterial,
    *,
    operation_id: str,
    actor: str,
):
    existing = _binding_record(session, binding)
    if existing is None:
        return store.put(
            session, binding, material, operation_id=operation_id, actor=actor
        )
    if existing.status != "revoked":
        raise SecretStoreError("SECRET_OPERATION_CONFLICT")
    return store.reprovision(
        session,
        binding,
        existing.secret_ref,
        material,
        operation_id=operation_id,
        actor=actor,
        expected_row_version=existing.row_version,
    )


def create_change_source_secure(
    session: Session,
    *,
    request: ChangeSourceCreate,
    tenant_id: DomainTenant,
    actor: str,
    store: SecretStore,
) -> ChangeSourceView:
    try:
        config, filters = validate_provider_configuration(
            request.source_type, request.config, request.filters
        )
        if request.enabled and request.credential is None:
            raise SecretConsumerError("Enabled change source requires a credential.")
        now = utc_now_iso()
        source_id = new_change_source_id(request.source_type.value, request.name)
        record = ChangeSourceRecord(
            tenant_id=tenant_value(tenant_id),
            source_id=source_id,
            name=request.name,
            source_type=request.source_type.value,
            enabled=request.enabled,
            secret_ref=None,
            config_json=json.dumps(config, sort_keys=True, separators=(",", ":")),
            filters_json=json.dumps(filters, sort_keys=True, separators=(",", ":")),
            status="configured" if request.enabled else "disabled",
            delivery_count=0,
            failure_count=0,
            created_at=now,
            updated_at=now,
        )
        if request.credential is not None:
            descriptor = store.put(
                session,
                source_binding(
                    tenant_id=tenant_value(tenant_id),
                    source_id=source_id,
                    source_type=record.source_type,
                    config=config,
                ),
                _material(request.credential),
                operation_id=f"source-create:{source_id}",
                actor=actor,
            )
            record.secret_ref = descriptor.secret_ref
        session.add(record)
        append_allowed_security_event(
            session,
            action=SecurityAuditAction.CHANGE_SOURCE_CREATED,
            permissions=[Permission.INTEGRATION_MANAGE, Permission.CREDENTIAL_ROTATE],
            resource_type=SecurityAuditResourceType.CHANGE_SOURCE,
            resource_id=source_id,
            tenant_id=tenant_value(tenant_id),
        )
        tenant_commit(session, tenant_id=tenant_id)
        return change_source_view(record)
    except SecretConsumerError:
        session.rollback()
        raise
    except ProviderPolicyError as exc:
        session.rollback()
        raise SecretConsumerError(str(exc)) from None
    except SecretStoreError as exc:
        session.rollback()
        raise _translate_secret_error(exc) from None
    except Exception:
        session.rollback()
        raise


def update_change_source_secure(
    session: Session,
    *,
    source_id: str,
    request: ChangeSourceUpdate,
    tenant_id: DomainTenant,
    actor: str,
    store: SecretStore,
    idempotency_key: str | None,
) -> ChangeSourceView:
    try:
        record = load_change_source(session, source_id=source_id, tenant_id=tenant_id)
        if record is None:
            raise SecretConsumerError("Change source not found.", 404)
        current_config = json.loads(record.config_json or "{}")
        current_filters = json.loads(record.filters_json or "{}")
        config, filters = validate_provider_configuration(
            record.source_type,
            request.config if request.config is not None else current_config,
            request.filters if request.filters is not None else current_filters,
        )
        old_binding = source_binding(
            tenant_id=tenant_value(tenant_id), source_id=source_id,
            source_type=record.source_type, config=current_config,
        )
        new_binding = source_binding(
            tenant_id=tenant_value(tenant_id), source_id=source_id,
            source_type=record.source_type, config=config,
        )
        mutation = request.credential
        purpose_changed = old_binding.purpose != new_binding.purpose
        if purpose_changed and (
            mutation is None
            or mutation.action not in {"replace", "reprovision"}
            or mutation.credential is None
        ):
            raise SecretConsumerError(
                "Authentication mode change requires a new credential."
            )
        if mutation is not None:
            action = mutation.action
            if action in {"rotate", "replace", "reprovision"}:
                if mutation.credential is None:
                    raise SecretConsumerError("Credential value is required.")
                operation_id = _operation_id(source_id, action, idempotency_key or "")
                material = _material(mutation.credential)
                if purpose_changed:
                    descriptor = _put_or_reprovision(
                        session, store, new_binding, material,
                        operation_id=operation_id, actor=actor,
                    )
                    if record.secret_ref:
                        old = store.describe(session, old_binding, record.secret_ref)
                        store.revoke(
                            session, old_binding, record.secret_ref, actor=actor,
                            expected_row_version=old.row_version,
                        )
                elif action == "rotate":
                    if not record.secret_ref:
                        raise SecretConsumerError("Credential is not configured.", 409)
                    old = store.describe(session, new_binding, record.secret_ref)
                    descriptor = store.rotate(
                        session, new_binding, record.secret_ref, material,
                        operation_id=operation_id, actor=actor,
                        expected_row_version=old.row_version,
                        overlap_seconds=mutation.overlap_seconds,
                    )
                elif record.secret_ref:
                    old = store.describe(session, new_binding, record.secret_ref)
                    if old.status == "revoked":
                        descriptor = store.reprovision(
                            session, new_binding, record.secret_ref, material,
                            operation_id=operation_id, actor=actor,
                            expected_row_version=old.row_version,
                        )
                    else:
                        descriptor = store.rotate(
                            session, new_binding, record.secret_ref, material,
                            operation_id=operation_id, actor=actor,
                            expected_row_version=old.row_version,
                            overlap_seconds=0,
                        )
                else:
                    descriptor = _put_or_reprovision(
                        session, store, new_binding, material,
                        operation_id=operation_id, actor=actor,
                    )
                record.secret_ref = descriptor.secret_ref
            elif action == "revoke":
                if mutation.credential is not None:
                    raise SecretConsumerError("Credential value is not accepted for revoke.")
                if record.secret_ref:
                    old = store.describe(session, old_binding, record.secret_ref)
                    store.revoke(
                        session, old_binding, record.secret_ref, actor=actor,
                        expected_row_version=old.row_version,
                    )
                record.secret_ref = None
                record.enabled = False
            else:
                raise SecretConsumerError("Credential mutation is invalid.")
        if request.enabled is not None:
            record.enabled = request.enabled
        if record.enabled and not record.secret_ref:
            raise SecretConsumerError("Enabled change source requires a credential.")
        record.config_json = json.dumps(config, sort_keys=True, separators=(",", ":"))
        record.filters_json = json.dumps(filters, sort_keys=True, separators=(",", ":"))
        record.status = "configured" if record.enabled else "disabled"
        record.updated_at = utc_now_iso()
        append_allowed_security_event(
            session,
            action=SecurityAuditAction.CHANGE_SOURCE_UPDATED,
            permissions=[Permission.INTEGRATION_MANAGE, Permission.CREDENTIAL_ROTATE],
            resource_type=SecurityAuditResourceType.CHANGE_SOURCE,
            resource_id=source_id,
            tenant_id=tenant_value(tenant_id),
        )
        tenant_commit(session, tenant_id=tenant_id)
        return change_source_view(record)
    except SecretConsumerError:
        session.rollback()
        raise
    except (ProviderPolicyError, json.JSONDecodeError):
        session.rollback()
        raise SecretConsumerError("PROVIDER_CONFIGURATION_INVALID") from None
    except SecretStoreError as exc:
        session.rollback()
        raise _translate_secret_error(exc) from None
    except Exception:
        session.rollback()
        raise


def _header_values(request_headers: dict) -> dict[str, str]:
    try:
        return validate_protected_headers(
            {name: value.get_secret_value() for name, value in request_headers.items()}
        )
    except (AttributeError, ProviderPolicyError):
        raise SecretConsumerError("WEBHOOK_HEADERS_INVALID") from None


def _replace_outbound(
    session: Session, store: SecretStore, binding: SecretBinding,
    current_ref: str | None, material: SecretMaterial, *, operation_id: str, actor: str,
):
    if current_ref:
        current = store.describe(session, binding, current_ref)
        return store.rotate(
            session, binding, current_ref, material, operation_id=operation_id,
            actor=actor, expected_row_version=current.row_version, overlap_seconds=0,
        )
    return _put_or_reprovision(
        session, store, binding, material, operation_id=operation_id, actor=actor
    )


def _clear_outbound(
    session: Session, store: SecretStore, binding: SecretBinding,
    current_ref: str | None, *, actor: str,
) -> None:
    if current_ref:
        current = store.describe(session, binding, current_ref)
        store.revoke(
            session, binding, current_ref, actor=actor,
            expected_row_version=current.row_version,
        )


def create_webhook_endpoint_secure(
    session: Session,
    *,
    request: WebhookEndpointCreate,
    tenant_id: DomainTenant,
    actor: str,
    store: SecretStore,
    resolver: Resolver | None = None,
) -> WebhookEndpointView:
    try:
        url = validate_webhook_url(request.url, resolver=resolver)
        webhook_id = f"webhook:{uuid4().hex}"
        signing_ref = None
        header_ref = None
        names: list[str] = []
        if request.signing_secret is not None:
            descriptor = store.put(
                session,
                webhook_binding(
                    tenant_id=tenant_value(tenant_id), webhook_id=webhook_id,
                    purpose=SecretPurpose.WEBHOOK_SIGNING,
                ),
                _material(request.signing_secret, minimum=16),
                operation_id=f"webhook-create-signing:{webhook_id}", actor=actor,
            )
            signing_ref = descriptor.secret_ref
        if request.headers:
            headers = _header_values(request.headers)
            descriptor = store.put(
                session,
                webhook_binding(
                    tenant_id=tenant_value(tenant_id), webhook_id=webhook_id,
                    purpose=SecretPurpose.WEBHOOK_HEADERS,
                ),
                SecretMaterial(serialize_protected_headers(headers)),
                operation_id=f"webhook-create-headers:{webhook_id}", actor=actor,
            )
            header_ref = descriptor.secret_ref
            names = sorted(headers, key=str.lower)
        now = utc_now_iso()
        record = WebhookEndpointRecord(
            webhook_id=webhook_id, name=request.name, url=url,
            event_types_json=json.dumps([value.value for value in request.event_types]),
            signing_secret_ref=signing_ref,
            protected_headers_secret_ref=header_ref,
            protected_header_names_json=json.dumps(names, separators=(",", ":")),
            active=request.active, timeout_seconds=request.timeout_seconds,
            max_attempts=request.max_attempts, created_at=now, updated_at=now,
            tenant_id=tenant_value(tenant_id),
        )
        session.add(record)
        append_allowed_security_event(
            session,
            action=SecurityAuditAction.WEBHOOK_ENDPOINT_CREATED,
            permissions=[Permission.INTEGRATION_MANAGE, Permission.CREDENTIAL_ROTATE],
            resource_type=SecurityAuditResourceType.WEBHOOK_ENDPOINT,
            resource_id=webhook_id,
            tenant_id=tenant_value(tenant_id),
        )
        tenant_commit(session, tenant_id=tenant_id)
        return _endpoint_to_view(record)
    except SecretConsumerError:
        session.rollback()
        raise
    except ProviderPolicyError as exc:
        session.rollback()
        raise SecretConsumerError(str(exc)) from None
    except SecretStoreError as exc:
        session.rollback()
        raise _translate_secret_error(exc) from None
    except Exception:
        session.rollback()
        raise


def update_webhook_endpoint_secure(
    session: Session,
    *,
    webhook_id: str,
    request: WebhookEndpointUpdate,
    tenant_id: DomainTenant,
    actor: str,
    store: SecretStore,
    idempotency_key: str | None,
    resolver: Resolver | None = None,
    authorization_context: AuthorizationContext | None = None,
) -> WebhookEndpointView:
    try:
        record = load_webhook_endpoint_record(
            session, webhook_id, tenant_id=tenant_id
        )
        if record is None:
            raise SecretConsumerError("Webhook not found.", 404)
        fields = request.model_fields_set
        required_permissions = {Permission.INTEGRATION_MANAGE}
        next_url = record.url
        if "url" in fields:
            if request.url is None:
                raise SecretConsumerError("Webhook URL is required.")
            try:
                current_origin = canonicalize_destination(
                    record.url, purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY
                ).origin
            except EgressPolicyError:
                # A pre-PH-6B legacy destination is never trusted, but an
                # authorized rotation may replace it with a valid authority.
                current_origin = None
            try:
                candidate = canonicalize_destination(
                    request.url, purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY
                )
            except EgressPolicyError as exc:
                raise SecretConsumerError(exc.code.value) from None
            next_url = candidate.url
            if current_origin != candidate.origin:
                required_permissions.add(Permission.CREDENTIAL_ROTATE)
        if {"signing_secret", "headers"} & fields:
            required_permissions.add(Permission.CREDENTIAL_ROTATE)
        if authorization_context is not None:
            require_authorization_permissions(
                frozenset(required_permissions),
                authorization_context=authorization_context,
            )
        if "url" in fields:
            # Check data-dependent authority before controlled DNS so an
            # under-authorized caller cannot use this route as a resolver
            # oracle. Egress denial remains a distinct, bounded failure.
            next_url = validate_webhook_url(next_url, resolver=resolver)
        if request.name is not None:
            record.name = request.name
        if "url" in fields:
            record.url = next_url
        if request.event_types is not None:
            record.event_types_json = json.dumps([value.value for value in request.event_types])
        if request.active is not None:
            record.active = request.active
        if request.timeout_seconds is not None:
            record.timeout_seconds = request.timeout_seconds
        if request.max_attempts is not None:
            record.max_attempts = request.max_attempts
        if "signing_secret" in fields:
            binding = webhook_binding(
                tenant_id=tenant_value(tenant_id), webhook_id=webhook_id,
                purpose=SecretPurpose.WEBHOOK_SIGNING,
            )
            if request.signing_secret is None:
                _clear_outbound(
                    session, store, binding, record.signing_secret_ref, actor=actor
                )
                record.signing_secret_ref = None
            else:
                operation_id = _operation_id(
                    webhook_id, "replace-signing", idempotency_key or ""
                )
                descriptor = _replace_outbound(
                    session, store, binding, record.signing_secret_ref,
                    _material(request.signing_secret, minimum=16),
                    operation_id=operation_id, actor=actor,
                )
                record.signing_secret_ref = descriptor.secret_ref
        if "headers" in fields:
            binding = webhook_binding(
                tenant_id=tenant_value(tenant_id), webhook_id=webhook_id,
                purpose=SecretPurpose.WEBHOOK_HEADERS,
            )
            if not request.headers:
                _clear_outbound(
                    session, store, binding, record.protected_headers_secret_ref,
                    actor=actor,
                )
                record.protected_headers_secret_ref = None
                record.protected_header_names_json = "[]"
            else:
                operation_id = _operation_id(
                    webhook_id, "replace-headers", idempotency_key or ""
                )
                headers = _header_values(request.headers)
                descriptor = _replace_outbound(
                    session, store, binding, record.protected_headers_secret_ref,
                    SecretMaterial(serialize_protected_headers(headers)),
                    operation_id=operation_id, actor=actor,
                )
                record.protected_headers_secret_ref = descriptor.secret_ref
                record.protected_header_names_json = json.dumps(
                    sorted(headers, key=str.lower), separators=(",", ":")
                )
        record.updated_at = utc_now_iso()
        append_allowed_security_event(
            session,
            action=SecurityAuditAction.WEBHOOK_ENDPOINT_UPDATED,
            permissions=sorted(required_permissions, key=lambda value: value.value),
            resource_type=SecurityAuditResourceType.WEBHOOK_ENDPOINT,
            resource_id=webhook_id,
            tenant_id=tenant_value(tenant_id),
        )
        tenant_commit(session, tenant_id=tenant_id)
        return _endpoint_to_view(record)
    except SecretConsumerError:
        session.rollback()
        raise
    except ProviderPolicyError as exc:
        session.rollback()
        raise SecretConsumerError(str(exc)) from None
    except SecretStoreError as exc:
        session.rollback()
        raise _translate_secret_error(exc) from None
    except Exception:
        session.rollback()
        raise


def load_webhook_secrets(
    session: Session,
    *,
    endpoint: WebhookEndpointRecord,
    tenant_id: DomainTenant,
    store: SecretStore,
) -> tuple[str | None, dict[str, str], tuple[str, ...]]:
    """Decrypt active-only outbound material at the final use boundary."""
    try:
        signing = None
        sensitive: list[str] = []
        if endpoint.signing_secret_ref:
            material = store.get_for_use(
                session,
                webhook_binding(
                    tenant_id=tenant_value(tenant_id), webhook_id=endpoint.webhook_id,
                    purpose=SecretPurpose.WEBHOOK_SIGNING,
                ),
                endpoint.signing_secret_ref,
            )
            if len(material) != 1:
                raise SecretStoreError("SECRET_DECRYPT_FAILED")
            signing = material[0].reveal().decode("utf-8")
            sensitive.append(signing)
        headers: dict[str, str] = {}
        if endpoint.protected_headers_secret_ref:
            material = store.get_for_use(
                session,
                webhook_binding(
                    tenant_id=tenant_value(tenant_id), webhook_id=endpoint.webhook_id,
                    purpose=SecretPurpose.WEBHOOK_HEADERS,
                ),
                endpoint.protected_headers_secret_ref,
            )
            if len(material) != 1:
                raise SecretStoreError("SECRET_DECRYPT_FAILED")
            headers = deserialize_protected_headers(material[0].reveal())
            sensitive.extend(headers.values())
        return signing, headers, tuple(sensitive)
    except (UnicodeDecodeError, ProviderPolicyError, SecretStoreError):
        raise SecretConsumerError("Credential service is unavailable.", 503) from None
