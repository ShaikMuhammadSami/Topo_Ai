from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BrowserSessionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    display_name: str
    roles: list[str] = Field(default_factory=list)
    authentication_type: str
    absolute_expires_at: str | None = None
