"""Central secret-safe formatting for logs and public error boundaries.

Redaction is defense in depth. Callers handling credentials must still avoid
putting raw material into exceptions, logs, or persisted diagnostic fields.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, SecretStr

REDACTED = "[REDACTED]"
TRUNCATED = "[TRUNCATED]"
UNAVAILABLE = "[UNAVAILABLE]"
MAX_DEPTH = 6
MAX_ITEMS = 100
MAX_TEXT = 5000

_SAFE_KEYS = frozenset({
    "credentialid", "secretref", "tokenbudget", "tokencount", "tokenhint",
})
_SENSITIVE_KEYS = frozenset({
    "authorization", "proxyauthorization", "cookie", "setcookie",
    "password", "passwd", "secret", "clientsecret", "privatekey", "apikey",
    "accesstoken", "refreshtoken", "bearertoken", "sessionsecret", "csrf",
    "signingsecret", "enrollmenttoken", "agenttoken", "apicredential",
    "token", "credential", "apitoken", "xapikey",
    "xhubsignature256", "xgitlabtoken", "webhooksignature",
    "xtfenotificationsignature", "xtoposignature256", "xtopocsrf",
})
_SAFE_LOG_HEADERS = frozenset({
    "accept", "contentlength", "contenttype", "date", "etag", "host",
    "ifmatch", "ifnonematch", "lastmodified", "location", "retryafter",
    "useragent", "xrequestid",
})
_LOG_RECORD_FIELDS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName",
})

_AUTH_TEXT = re.compile(r"(?i)\b(Bearer|Basic)\s+[^\s,;]+")
_TOKEN_PREFIX = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9_-]{8,}|gsk_[A-Za-z0-9_-]{8,}|"
    r"ghp_[A-Za-z0-9_-]{8,}|github_pat_[A-Za-z0-9_-]{8,}|"
    r"topo_(?:api|agent|enroll)_[A-Za-z0-9._~-]{8,})\b"
)
_URL_TEXT = re.compile(r"https?://[^\s<>\"']+")
_DATABASE_URL_TEXT = re.compile(
    r"(?i)\bpostgres(?:ql)?(?:\+[a-z0-9_.-]+)?://[^\s<>\"']+"
)
_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token|"
    r"password|passwd|authorization|cookie|signing[_-]?secret)\s*[:=]\s*"
    r"([^\s,;]+)"
)


def _normalized_key(value: object) -> str:
    return re.sub(
        r"[^a-z0-9]",
        "",
        value.lower() if isinstance(value, str) else "",
    )


def is_sensitive_key(value: object) -> bool:
    normalized = _normalized_key(value)
    return bool(normalized) and normalized not in _SAFE_KEYS and normalized in _SENSITIVE_KEYS


def safe_url(value: str, *, include_path: bool = True) -> str:
    """Return a bounded diagnostic URL without userinfo, query, or fragment."""
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return UNAVAILABLE
        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port is not None else ""
        path = parsed.path[:1000] if include_path else ""
        return urlunsplit((parsed.scheme, f"{host}{port}", path, "", ""))
    except (TypeError, ValueError):
        return UNAVAILABLE


def validate_service_base_url(value: str, *, label: str = "Service URL") -> str:
    """Validate a credential-bearing service base URL, not an arbitrary URL."""
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError()
        parsed.port
    except (TypeError, ValueError):
        raise ValueError(
            f"{label} must be an http(s) base URL without userinfo, query, or fragment."
        ) from None
    return value.rstrip("/")


def safe_text(value: str, *, maximum: int = MAX_TEXT) -> str:
    text = value[: max(maximum, 0) + 1024]
    text = _AUTH_TEXT.sub(lambda match: f"{match.group(1)} {REDACTED}", text)
    text = _TOKEN_PREFIX.sub(REDACTED, text)
    text = _ASSIGNMENT.sub(lambda match: f"{match.group(1)}={REDACTED}", text)
    text = _DATABASE_URL_TEXT.sub(UNAVAILABLE, text)
    text = _URL_TEXT.sub(lambda match: safe_url(match.group(0)), text)
    return text[: max(maximum, 0)]


def sanitize_headers(headers: Mapping[object, object]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in list(headers.items())[:MAX_ITEMS]:
        name = str(key)[:200]
        normalized = _normalized_key(name)
        if is_sensitive_key(name) or normalized not in _SAFE_LOG_HEADERS:
            result[name] = REDACTED
        elif normalized == "location" and isinstance(value, str):
            result[name] = safe_url(value)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            result[name] = safe_text(str(value), maximum=1000)
        else:
            result[name] = UNAVAILABLE
    return result


def safe_response_headers(
    headers: Mapping[str, str] | None,
) -> dict[str, str] | None:
    if not headers:
        return None
    result: dict[str, str] = {}
    for key, value in list(headers.items())[:MAX_ITEMS]:
        if is_sensitive_key(key):
            continue
        result[key[:200]] = safe_text(value, maximum=1000)
    return result


def sanitize_structured(value: Any, *, depth: int = 0) -> Any:
    if depth >= MAX_DEPTH:
        return TRUNCATED
    if isinstance(value, (SecretStr,)):
        return REDACTED
    if isinstance(value, BaseException):
        return {"error_type": type(value).__name__}
    if isinstance(value, Enum):
        return sanitize_structured(value.value, depth=depth + 1)
    if isinstance(value, BaseModel):
        return sanitize_structured(value.model_dump(mode="json"), depth=depth + 1)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in list(value.items())[:MAX_ITEMS]:
            name = (
                safe_text(key, maximum=200)
                if isinstance(key, str)
                else f"<{type(key).__name__}>"
            )
            result[name] = REDACTED if is_sensitive_key(name) else sanitize_structured(
                item, depth=depth + 1
            )
        if len(value) > MAX_ITEMS:
            result[TRUNCATED] = TRUNCATED
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = list(value[:MAX_ITEMS]) if hasattr(value, "__getitem__") else list(value)[:MAX_ITEMS]
        result = [sanitize_structured(item, depth=depth + 1) for item in items]
        if len(value) > MAX_ITEMS:
            result.append(TRUNCATED)
        return result
    if isinstance(value, (set, frozenset)):
        return [sanitize_structured(item, depth=depth + 1) for item in list(value)[:MAX_ITEMS]]
    if isinstance(value, str):
        return safe_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return REDACTED
    return f"<{type(value).__name__}>"


def safe_exception_metadata(exc: BaseException) -> dict[str, str]:
    return {"error_type": type(exc).__name__}


def safe_exception_code(exc: BaseException, *, prefix: str = "OPERATION_FAILED") -> str:
    del exc
    return prefix


def safe_validation_errors(errors: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in list(errors)[:MAX_ITEMS]:
        location = item.get("loc", ())
        if isinstance(location, (list, tuple)):
            safe_location = [
                safe_text(str(part), maximum=200)
                for part in location[:20]
            ]
        else:
            safe_location = []
        result.append({
            "loc": safe_location,
            "msg": safe_text(str(item.get("msg", "Invalid value.")), maximum=500),
            "type": safe_text(str(item.get("type", "validation_error")), maximum=200),
        })
    return result


_original_factory = logging.getLogRecordFactory()
_logging_installed = False


def _safe_log_record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
    record = _original_factory(*args, **kwargs)
    original_message = record.msg
    if isinstance(record.args, Mapping):
        record.args = sanitize_structured(record.args)
    elif isinstance(record.args, tuple):
        record.args = tuple(sanitize_structured(item) for item in record.args)
    if isinstance(original_message, str):
        if record.args:
            try:
                original_message = original_message % record.args
            except (KeyError, TypeError, ValueError):
                pass
            record.args = ()
        record.msg = safe_text(original_message)
    else:
        record.msg = sanitize_structured(original_message)
        record.args = ()
    for name, value in list(vars(record).items()):
        if name in _LOG_RECORD_FIELDS:
            continue
        setattr(
            record,
            name,
            REDACTED if is_sensitive_key(name) else sanitize_structured(value),
        )
    if record.exc_info:
        exception_type = record.exc_info[0]
        record.exc_info = None
        record.exc_text = f"{exception_type.__name__}" if exception_type else "Exception"
    return record


def install_logging_redaction() -> None:
    global _logging_installed
    if not _logging_installed:
        logging.setLogRecordFactory(_safe_log_record_factory)
        _logging_installed = True
    for logger_name in ("httpx", "httpcore", "openai", "groq", "sqlalchemy.engine"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
