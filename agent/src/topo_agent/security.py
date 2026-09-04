from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_AUTH = re.compile(r"(?i)\b(Bearer|Basic)\s+[^\s,;]+")
_TOKEN = re.compile(
    r"(?i)\b(?:sk-|gsk_|ghp_|github_pat_|topo_(?:api|agent|enroll)_)[A-Za-z0-9._~-]{8,}"
)
_URL = re.compile(r"https?://[^\s<>\"']+")
_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token|"
    r"password|passwd|authorization|cookie|signing[_-]?secret)\s*[:=]\s*"
    r"([^\s,;]+)"
)
_original_factory = logging.getLogRecordFactory()
_installed = False


def _safe_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return "[UNAVAILABLE]"
        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port is not None else ""
        return urlunsplit((parsed.scheme, f"{host}{port}", parsed.path[:1000], "", ""))
    except (TypeError, ValueError):
        return "[UNAVAILABLE]"


def safe_text(value: str, maximum: int = 2000) -> str:
    text = value[: max(maximum, 0) + 512]
    text = _AUTH.sub(lambda match: f"{match.group(1)} [REDACTED]", text)
    text = _TOKEN.sub("[REDACTED]", text)
    text = _ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = _URL.sub(lambda match: _safe_url(match.group(0)), text)
    return text[: max(maximum, 0)]


def safe_exception_message(exc: BaseException, prefix: str = "Operation failed") -> str:
    return f"{prefix} ({type(exc).__name__})."


def _safe_log_value(value: Any) -> Any:
    if isinstance(value, BaseException):
        return safe_exception_message(value)
    if isinstance(value, str):
        return safe_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return f"<{type(value).__name__}>"


def _record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
    record = _original_factory(*args, **kwargs)
    original_message = record.msg
    if isinstance(record.args, Mapping):
        record.args = {
            str(key)[:200]: _safe_log_value(value)
            for key, value in list(record.args.items())[:100]
        }
    elif isinstance(record.args, tuple):
        record.args = tuple(_safe_log_value(item) for item in record.args)
    if isinstance(original_message, str):
        if record.args:
            try:
                original_message = original_message % record.args
            except (KeyError, TypeError, ValueError):
                pass
            record.args = ()
        record.msg = safe_text(original_message)
    else:
        record.msg = f"<{type(original_message).__name__}>"
        record.args = ()
    if record.exc_info:
        error_type = record.exc_info[0]
        record.exc_info = None
        record.exc_text = error_type.__name__ if error_type else "Exception"
    return record


def install_logging_redaction() -> None:
    global _installed
    if not _installed:
        logging.setLogRecordFactory(_record_factory)
        _installed = True
    for name in ("httpx", "httpcore", "urllib3", "botocore", "azure", "google.auth"):
        logging.getLogger(name).setLevel(logging.WARNING)
