"""Risk-scoring helpers for Dazzle architecture gates."""

from dazzle.risk.model_driven import (
    CATALOGUE,
    DetectorState,
    FailureModeEvidence,
    FailureModeScore,
    RiskReport,
    build_report,
    score_failure_mode,
)

__all__ = [
    "CATALOGUE",
    "DetectorState",
    "FailureModeEvidence",
    "FailureModeScore",
    "RiskReport",
    "build_report",
    "score_failure_mode",
]
