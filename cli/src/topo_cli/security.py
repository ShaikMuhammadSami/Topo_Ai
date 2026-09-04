from __future__ import annotations

import re
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


def safe_error_text(value: str, *, maximum: int = 1000) -> str:
    text = value[: max(maximum, 0) + 512]
    text = _AUTH.sub(lambda match: f"{match.group(1)} [REDACTED]", text)
    text = _TOKEN.sub("[REDACTED]", text)
    text = _ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = _URL.sub(lambda match: _safe_url(match.group(0)), text)
    return text[: max(maximum, 0)]


def validate_api_url(value: str) -> str:
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
            "Server URL must be http(s) without userinfo, query, or fragment."
        ) from None
    return value.rstrip("/")
