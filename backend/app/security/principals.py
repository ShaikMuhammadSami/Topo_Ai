from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthPrincipal:
    subject: str
    display_name: str
    roles: tuple[str, ...]
    authentication_type: str
    principal_id: str | None = None
    principal_type: str | None = None
    external_issuer: str | None = None
    external_subject: str | None = None
