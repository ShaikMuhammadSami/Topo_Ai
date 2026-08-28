from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthPrincipal:
    subject: str
    display_name: str
    roles: tuple[str, ...]
    authentication_type: str
