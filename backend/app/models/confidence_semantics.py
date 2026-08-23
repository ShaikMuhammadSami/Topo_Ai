from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


CONFIDENCE_SEMANTICS_VERSION = "tc5.v1"


class CausalScoreType(str, Enum):
    HEURISTIC_RANKING = "heuristic_ranking"


class CausalCalibrationStatus(str, Enum):
    NOT_CALIBRATED = "not_calibrated"


class LegacyConfidenceSemantics(str, Enum):
    NORMALIZED_HEURISTIC_RANKING_SCORE = (
        "legacy_normalized_heuristic_ranking_score"
    )


class CausalRankingStrength(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CausalEvidenceCompleteness(str, Enum):
    COMPLETE_FOR_CURRENT_MODEL = "complete_for_current_model"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class CausalEvidenceState(str, Enum):
    SUPPORTED_UNDER_CURRENT_MODEL = "supported_under_current_model"
    CONTESTED = "contested"
    INCOMPLETE = "incomplete"
    CONTESTED_WITH_GAPS = "contested_with_gaps"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    LEGACY_UNKNOWN = "legacy_unknown"


class CausalEvidenceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supporting_count: int = Field(ge=0)
    contradicting_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)


class CausalConfidenceSemantics(BaseModel):
    """Interpretation contract for the existing 13C ranking output.

    This model deliberately has no probability-producing method. The only
    supported V1 calibration state is ``not_calibrated`` and calibrated
    probability is always null.
    """

    model_config = ConfigDict(extra="forbid")

    semantics_version: str = CONFIDENCE_SEMANTICS_VERSION
    ranking_algorithm_version: str
    score_type: CausalScoreType = CausalScoreType.HEURISTIC_RANKING
    ranking_score: float | None = Field(default=None, ge=0.0, le=100.0)
    score_minimum: float = 0.0
    score_maximum: float = 100.0
    ranking_strength: CausalRankingStrength | None = None
    legacy_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    legacy_confidence_semantics: LegacyConfidenceSemantics = (
        LegacyConfidenceSemantics.NORMALIZED_HEURISTIC_RANKING_SCORE
    )
    evidence_summary: CausalEvidenceSummary
    evidence_completeness: CausalEvidenceCompleteness
    evidence_state: CausalEvidenceState
    calibration_status: CausalCalibrationStatus = (
        CausalCalibrationStatus.NOT_CALIBRATED
    )
    calibrated_probability: None = Field(
        default=None,
        description=(
            "Unavailable in V1. The 13C heuristic ranking score has not "
            "been empirically calibrated as a probability."
        ),
    )
    interpretation: str
