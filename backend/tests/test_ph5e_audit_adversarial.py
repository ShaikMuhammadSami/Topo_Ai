"""PH-5E adversarial proof for durable audit truth and non-authority."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import SecurityAuditEventRecord
from app.models.security_audit import (
    SecurityAuditAction,
    SecurityAuditResourceType,
)
from app.security.authorization_enforcement import (
    AuthorizationFailure,
    authorize_service_operation,
)
from app.security.authorization_policy import Permission
from app.services.security_audit import (
    SecurityAuditValidationError,
    append_authorization_denial,
    append_local_operator_security_event,
    bind_security_audit_request,
    reset_security_audit_request,
)
from test_security_admin_audit import TENANT_ID, _authorized_context, audit_factory


def test_hostile_audit_evidence_never_changes_viewer_authority(
    audit_factory,
) -> None:
    with audit_factory() as session:
        context = _authorized_context(session, role="tenant_viewer")
        hostile = SecurityAuditEventRecord(
            audit_event_id="audit:00000000-0000-0000-0000-000000000001",
            occurred_at="2026-09-09T12:00:00+00:00",
            actor_principal_id=context.actor_principal_id,
            actor_kind="human",
            actor_reference=None,
            authentication_type="human_api_credential",
            authority_kind="human_tenant",
            tenant_id=TENANT_ID,
            action="authorization.denied",
            permissions_json='["credential.rotate","member.manage"]',
            resource_type="tenant_membership",
            resource_id="tenant-membership:claimed-admin",
            result="allowed",
            reason_code="completed",
            request_id="ph5e-hostile-audit",
        )
        session.add(hostile)
        session.commit()

        with pytest.raises(AuthorizationFailure, match="PERMISSION_DENIED"):
            authorize_service_operation(
                "app.services.tenant_service.add_or_reactivate_tenant_membership",
                authorization_context=context,
            )
        hostile.permissions_json = '["tenant.settings.manage"]'
        hostile.action = "tenant.created"
        session.commit()
        with pytest.raises(AuthorizationFailure) as still_denied:
            authorize_service_operation(
                "app.services.tenant_service.create_tenant_with_creator_membership",
                authorization_context=context,
            )
        assert still_denied.value.code == "AUTHORITY_KIND_MISMATCH"


def test_audit_builder_rejects_control_oversize_and_credential_bearing_url(
    audit_factory,
) -> None:
    credential_url = "https://" + "audit-user" + ":" + "audit-password" + "@example.test/path"
    hostile_values = (
        "line\nforge",
        "x" * 256,
        credential_url,
    )
    with audit_factory() as session:
        for value in hostile_values:
            with pytest.raises(
                SecurityAuditValidationError, match="AUDIT_RESOURCE_ID_INVALID"
            ):
                append_local_operator_security_event(
                    session,
                    action=SecurityAuditAction.INSTALLATION_SECRET_INSPECTED,
                    permissions=[Permission.INSTALLATION_STATUS_READ],
                    resource_type=SecurityAuditResourceType.SECRET_RECORD,
                    resource_id=value,
                )
            session.rollback()
        assert session.scalar(select(SecurityAuditEventRecord)) is None


def test_one_request_has_one_semantic_denial_with_required_permissions_only(
    audit_factory,
) -> None:
    with audit_factory() as session:
        context = _authorized_context(session, role="tenant_viewer")
    token = bind_security_audit_request(audit_factory)
    try:
        first = append_authorization_denial(
            authorization_context=context,
            required_permissions=[Permission.CREDENTIAL_ROTATE],
            failure_code="PERMISSION_DENIED",
        )
        second = append_authorization_denial(
            authorization_context=context,
            required_permissions=[Permission.MEMBER_MANAGE],
            failure_code="PERMISSION_DENIED",
        )
    finally:
        reset_security_audit_request(token)
    assert first is True and second is False
    with audit_factory() as session:
        events = list(session.scalars(select(SecurityAuditEventRecord)))
    assert len(events) == 1
    assert events[0].permissions_json == '["credential.rotate"]'
    assert events[0].request_id is None
