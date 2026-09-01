"""Process-local access to the already initialized SecretStore instance.

This is not a credential cache. It only makes the configured store object
available to background service calls that do not have a FastAPI Request.
"""

from __future__ import annotations

from app.models.secret_store import SecretStoreError
from app.services.secret_store import SecretStore


_runtime_store: SecretStore | None = None


def configure_runtime_secret_store(store: SecretStore | None) -> None:
    global _runtime_store
    _runtime_store = store


def runtime_secret_store() -> SecretStore:
    if _runtime_store is None:
        raise SecretStoreError("SECRET_STORE_UNAVAILABLE")
    return _runtime_store
