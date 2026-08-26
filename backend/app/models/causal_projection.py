from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


CAUSAL_HYPOTHESIS_PROJECTION_POLICY_VERSION = (
    "causal-hypothesis-projection-v1"
)


class DiagnosticProjectionReason(str, Enum):
    INCLUDED_BY_CAUSAL_ORDER = "included_by_existing_causal_order"
    DIAGNOSTIC_CAP_REACHED = "diagnostic_projection_cap_reached"


class SupportedProjectionReason(str, Enum):
    INCLUDED_AFTER_SUPPORT_QUALIFICATION = (
        "included_after_support_qualification"
    )
    SUPPORT_GATE_NOT_SATISFIED = "support_gate_not_satisfied"
    SUPPORTED_CAP_REACHED = "supported_projection_cap_reached"


class CausalHypothesisProjectionAudit(BaseModel):
    """Lightweight projection membership for one canonical hypothesis."""

    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str
    diagnostic_projection_included: bool
    diagnostic_projection_rank: int | None = Field(default=None, ge=1)
    diagnostic_projection_reason: DiagnosticProjectionReason
    supported_projection_included: bool
    supported_projection_rank: int | None = Field(default=None, ge=1)
    supported_projection_reason: SupportedProjectionReason

    @model_validator(mode="after")
    def validate_projection_ranks(self) -> "CausalHypothesisProjectionAudit":
        if self.diagnostic_projection_included != (
            self.diagnostic_projection_rank is not None
        ):
            raise ValueError(
                "Diagnostic projection inclusion and rank must agree."
            )
        if self.supported_projection_included != (
            self.supported_projection_rank is not None
        ):
            raise ValueError(
                "Supported projection inclusion and rank must agree."
            )
        return self


class CausalHypothesisProjectionSummary(BaseModel):
    """Bounded diagnostic and evidence-supported projection totals."""

    model_config = ConfigDict(extra="forbid")

    policy_version: str = CAUSAL_HYPOTHESIS_PROJECTION_POLICY_VERSION
    diagnostic_projection_limit: int = Field(ge=1)
    supported_projection_limit: int = Field(ge=1)
    evaluated_hypothesis_count: int = Field(ge=0)
    diagnostic_projection_count: int = Field(ge=0)
    supported_projection_count: int = Field(ge=0)
    support_qualified_hypothesis_count: int = Field(ge=0)
    projection_dropped_supported_count: int = Field(ge=0)
    supported_projection_cap_excluded_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_projection_invariant(self) -> "CausalHypothesisProjectionSummary":
        if self.projection_dropped_supported_count != 0:
            raise ValueError(
                "Supported hypotheses cannot be dropped by unsupported "
                "projection members."
            )
        if self.diagnostic_projection_count > self.diagnostic_projection_limit:
            raise ValueError("Diagnostic projection exceeds its limit.")
        if self.supported_projection_count > self.supported_projection_limit:
            raise ValueError("Supported projection exceeds its limit.")
        if (
            self.supported_projection_count
            + self.supported_projection_cap_excluded_count
            != self.support_qualified_hypothesis_count
        ):
            raise ValueError(
                "Supported projection totals do not account for every "
                "support-qualified hypothesis."
            )
        return self
