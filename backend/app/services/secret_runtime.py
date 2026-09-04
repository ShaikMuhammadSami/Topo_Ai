"""Process-local access to the already initialized SecretStore instance.

This is not a credential cache. It only makes the configured store object
available to background service calls that do not have a FastAPI Request.
"""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Callable, Iterator

from app.models.secret_store import SecretStoreError
from app.services.secret_store import SecretStore

try:
    from sqlalchemy.orm import Session
except ImportError:  # pragma: no cover - backend always supplies SQLAlchemy
    Session = object  # type: ignore[assignment,misc]


_runtime_store: SecretStore | None = None
_runtime_session_factory: Callable[[], Session] | None = None


def configure_runtime_secret_store(
    store: SecretStore | None,
    session_factory: Callable[[], Session] | None = None,
) -> None:
    global _runtime_store, _runtime_session_factory
    _runtime_store = store
    _runtime_session_factory = session_factory


def runtime_secret_store() -> SecretStore:
    if _runtime_store is None:
        raise SecretStoreError("SECRET_STORE_UNAVAILABLE")
    return _runtime_store


@contextmanager
def runtime_secret_session() -> Iterator[Session]:
    if _runtime_session_factory is None:
        raise SecretStoreError("SECRET_STORE_UNAVAILABLE")
    with _runtime_session_factory() as session:
        yield session
