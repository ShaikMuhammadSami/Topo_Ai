"""Fixed installation-scoped outbound credential bindings and runtime use."""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.models.secret_store import (
    SecretBinding,
    SecretPurpose,
    SecretScope,
    SecretStoreError,
)
from app.services.secret_runtime import runtime_secret_session, runtime_secret_store


@dataclass(frozen=True)
class InstallationIntegration:
    owner_id: str
    purpose: SecretPurpose


INSTALLATION_INTEGRATIONS = {
    "openai": InstallationIntegration("openai", SecretPurpose.OPENAI_API),
    "groq": InstallationIntegration("groq", SecretPurpose.GROQ_API),
    "github": InstallationIntegration("github", SecretPurpose.GITHUB_API),
}


def installation_binding(
    integration: str,
    *,
    installation_id: str | None = None,
) -> SecretBinding:
    definition = INSTALLATION_INTEGRATIONS.get(integration)
    if definition is None:
        raise SecretStoreError("SECRET_OWNER_PURPOSE_INVALID")
    scope_id = installation_id or os.environ.get("TOPO_INSTALLATION_ID")
    if not scope_id:
        raise SecretStoreError("SECRET_SCOPE_INVALID")
    return SecretBinding(
        scope=SecretScope("installation", scope_id, None),
        owner_type="installation_integration",
        owner_id=definition.owner_id,
        purpose=definition.purpose,
    )


def installation_secret_is_configured(integration: str) -> bool:
    try:
        store = runtime_secret_store()
        with runtime_secret_session() as session:
            descriptor = store.describe_for_binding(
                session,
                installation_binding(integration),
            )
        return descriptor.status == "active"
    except SecretStoreError:
        return False


def installation_secret_text(integration: str) -> str | None:
    """Decrypt one active outbound credential at its final use boundary."""
    try:
        store = runtime_secret_store()
        with runtime_secret_session() as session:
            values = store.get_for_binding(session, installation_binding(integration))
        if len(values) != 1:
            raise SecretStoreError("SECRET_DECRYPT_FAILED")
        return values[0].reveal().decode("utf-8")
    except (SecretStoreError, UnicodeDecodeError):
        return None
