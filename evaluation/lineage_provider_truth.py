from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_SECRET_KEY = re.compile(
    r"(?:authorization|bearer|cookie|credential|password|passwd|private[_-]?key|"
    r"secret|token|dockerconfigjson)",
    re.IGNORECASE,
)
_SECRET_QUERY_KEYS = {
    "access_token",
    "auth",
    "authorization",
    "code",
    "key",
    "signature",
    "sig",
    "token",
    "x-amz-credential",
    "x-amz-signature",
    "x-goog-credential",
    "x-goog-signature",
}


def _safe_component(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip())


def _kind_token(value: str) -> str:
    result = value.strip()
    if result.casefold().startswith("kubernetes"):
        result = result[len("Kubernetes") :]
    return _safe_component(result).lower()


def github_repository_canonical_id(
    *, api_url: str, repository_native_id: str | int
) -> str:
    host = _safe_component(urlsplit(api_url).hostname or "github")
    return f"github:{host}:repository:{str(repository_native_id).strip()}"


def github_commit_canonical_id(
    *, repository_canonical_id: str, sha: str
) -> str:
    return f"{repository_canonical_id}:commit:{sha.strip().lower()}"


def github_workflow_run_canonical_id(*, api_url: str, run_id: str | int) -> str:
    host = _safe_component(urlsplit(api_url).hostname or "github")
    return f"github:{host}:workflow-run:{str(run_id).strip()}"


def container_image_canonical_id(digest: str) -> str:
    return f"artifact:container-image:{digest.strip().lower()}"


def kubernetes_canonical_id(
    *, cluster: str, kind: str, uid: str
) -> str:
    return (
        f"k8s:{_safe_component(cluster)}:{_kind_token(kind)}:"
        f"{uid.strip()}"
    )


def kubernetes_signal_id(*, cluster: str, event_uid: str) -> str:
    return (
        f"signal:kubernetes-event:{_safe_component(cluster)}:"
        f"{event_uid.strip()}"
    )


def provider_identity(
    *,
    provider: str,
    kind: str,
    native_id: str | int,
    canonical_id: str | None,
    name: str | None = None,
    scope: dict[str, Any] | None = None,
    immutable_digest: str | None = None,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "kind": kind,
        "native_id": str(native_id),
        "canonical_id": canonical_id,
        "name": name,
        "scope": deepcopy(scope or {}),
        "immutable_digest": immutable_digest.lower() if immutable_digest else None,
    }


def _sanitize_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    if not parts.scheme or not parts.netloc or not parts.query:
        return value
    safe_query = [
        (key, "[REDACTED]" if key.casefold() in _SECRET_QUERY_KEYS else item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(safe_query), parts.fragment)
    )


def sanitize_provider_receipt(value: Any) -> Any:
    """Deep-copy and redact secret-shaped keys and signed URL parameters."""

    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            result[str(key)] = (
                "[REDACTED]"
                if _SECRET_KEY.search(str(key))
                else sanitize_provider_receipt(item)
            )
        return result
    if isinstance(value, list):
        return [sanitize_provider_receipt(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_provider_receipt(item) for item in value]
    if isinstance(value, str):
        return _sanitize_url(value)
    return value


def contains_unredacted_secret_like_fields(value: Any) -> bool:
    """Return True only when a secret-shaped value has not been redacted."""

    if isinstance(value, dict):
        return any(
            (
                bool(_SECRET_KEY.search(str(key)))
                and item != "[REDACTED]"
            )
            or contains_unredacted_secret_like_fields(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(contains_unredacted_secret_like_fields(item) for item in value)
    if isinstance(value, str):
        try:
            parts = urlsplit(value)
        except ValueError:
            return False
        if parts.query:
            return any(
                key.casefold() in _SECRET_QUERY_KEYS and item != "[REDACTED]"
                for key, item in parse_qsl(parts.query, keep_blank_values=True)
            )
    return False


# Backward-friendly evaluation helper name. This does not touch product code.
contains_secret_like_fields = contains_unredacted_secret_like_fields


def stable_value_hash(value: Any) -> str:
    from evaluation.lineage_contracts import deterministic_json

    return hashlib.sha256(deterministic_json(value).encode("utf-8")).hexdigest()
