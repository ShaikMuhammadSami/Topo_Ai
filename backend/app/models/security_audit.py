"""Frozen PH-5D security/admin audit vocabulary."""

from __future__ import annotations

from enum import StrEnum


class SecurityAuditActorKind(StrEnum):
    HUMAN = "human"
    SERVICE = "service"
    AGENT = "agent"
    PROVIDER = "provider"
    LOCAL_OPERATOR = "local_operator"


class SecurityAuditResult(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"


class SecurityAuditAuthenticationType(StrEnum):
    BROWSER_SESSION = "browser_session"
    HUMAN_API_CREDENTIAL = "human_api_credential"
    SERVICE_API_CREDENTIAL = "service_api_credential"
    STATIC_BOOTSTRAP = "static_bootstrap"
    DEVELOPMENT = "development"
    AGENT_TOKEN = "agent_token"
    AGENT_ENROLLMENT = "agent_enrollment"
    PROVIDER_WEBHOOK = "provider_webhook"
    LOCAL_OPERATOR_BOUNDARY = "local_operator_boundary"


class SecurityAuditAuthorityKind(StrEnum):
    AUTHENTICATION_SELF_SERVICE = "authentication_self_service"
    HUMAN_TENANT = "human_tenant"
    SERVICE_TENANT = "service_tenant"
    INSTALLATION = "installation"
    AGENT_FIXED_PURPOSE = "agent_fixed_purpose"
    PROVIDER_FIXED_PURPOSE = "provider_fixed_purpose"
    LOCAL_OPERATOR = "local_operator"


class SecurityAuditAction(StrEnum):
    AUTHORIZATION_DENIED = "authorization.denied"
    EXECUTION_DENIED = "execution.denied"
    TENANT_CREATED = "tenant.created"
    TENANT_MEMBERSHIP_CREATED = "tenant_membership.created"
    TENANT_MEMBERSHIP_REACTIVATED = "tenant_membership.reactivated"
    TENANT_MEMBERSHIP_DISABLED = "tenant_membership.disabled"
    TENANT_MEMBERSHIP_RECOVERED = "tenant_membership.recovered"
    CHANGE_SOURCE_CREATED = "change_source.created"
    CHANGE_SOURCE_UPDATED = "change_source.updated"
    WEBHOOK_ENDPOINT_CREATED = "webhook_endpoint.created"
    WEBHOOK_ENDPOINT_UPDATED = "webhook_endpoint.updated"
    OWNERSHIP_MAPPING_UPSERTED = "ownership_mapping.upserted"
    IDENTITY_OVERRIDE_UPSERTED = "identity_override.upserted"
    IDENTITY_OVERRIDE_DEACTIVATED = "identity_override.deactivated"
    HUMAN_API_CREDENTIAL_CREATED = "api_credential.human.created"
    HUMAN_API_CREDENTIAL_REVOKED = "api_credential.human.revoked"
    SERVICE_API_CREDENTIAL_CREATED = "api_credential.service.created"
    SERVICE_API_CREDENTIAL_REVOKED = "api_credential.service.revoked"
    SERVICE_API_CREDENTIAL_LISTED = "api_credential.service.listed"
    SERVICE_API_CREDENTIAL_INSPECTED = "api_credential.service.inspected"
    SERVICE_PERMISSIONS_UPDATED = "service_permissions.updated"
    AGENT_ENROLLMENT_TOKEN_CREATED = "agent_enrollment_token.created"
    AGENT_ENROLLED = "agent.enrolled"
    AGENT_REVOKED = "agent.revoked"
    INSTALLATION_OPERATOR_GRANTED = "installation_operator.granted"
    INSTALLATION_OPERATOR_DISABLED = "installation_operator.disabled"
    INSTALLATION_OPERATOR_INSPECTED = "installation_operator.inspected"
    INSTALLATION_SECRET_INSPECTED = "installation_secret.inspected"
    INSTALLATION_SECRET_SET = "installation_secret.set"
    INSTALLATION_SECRET_REPROVISIONED = "installation_secret.reprovisioned"
    INSTALLATION_SECRET_ROTATED = "installation_secret.rotated"
    INSTALLATION_SECRET_IMPORTED = "installation_secret.imported"
    INSTALLATION_SECRET_REVOKED = "installation_secret.revoked"


class SecurityAuditReason(StrEnum):
    COMPLETED = "completed"
    MISSING_PERMISSION = "missing_permission"
    WRONG_AUTHORITY_KIND = "wrong_authority_kind"
    PRINCIPAL_INACTIVE = "principal_inactive"
    MEMBERSHIP_MISSING = "membership_missing"
    SERVICE_PERMISSION_MISSING = "service_permission_missing"
    INSTALLATION_ASSIGNMENT_MISSING = "installation_assignment_missing"
    CREDENTIAL_TARGET_DENIED = "credential_target_denied"
    EXECUTION_DISABLED = "execution_disabled"
    UNKNOWN_OPERATION = "unknown_operation"
    RESOURCE_UNAVAILABLE = "resource_unavailable"


class SecurityAuditResourceType(StrEnum):
    TENANT = "tenant"
    TENANT_MEMBERSHIP = "tenant_membership"
    CHANGE_SOURCE = "change_source"
    WEBHOOK_ENDPOINT = "webhook_endpoint"
    OWNERSHIP_MAPPING = "ownership_mapping"
    IDENTITY_OVERRIDE = "identity_override"
    API_CREDENTIAL = "api_credential"
    SERVICE_PRINCIPAL = "service_principal"
    AGENT_ENROLLMENT_TOKEN = "agent_enrollment_token"
    AGENT = "agent"
    INSTALLATION_OPERATOR_ASSIGNMENT = "installation_operator_assignment"
    SECRET_RECORD = "secret_record"
