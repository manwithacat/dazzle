"""Model-driven failure-mode risk scoring.

This module implements the deterministic scoring contract described in
``docs/architecture/model-driven-failure-modes.md``. It deliberately does not
scan source files or run live probes; detectors feed their measured evidence
into these pure functions.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DetectorState(StrEnum):
    """Lifecycle state for one detector dimension."""

    ABSENT = "absent"
    DEFINED = "defined"
    LIVE = "live"


DETECTOR_WEIGHTS: Mapping[DetectorState, float] = {
    DetectorState.ABSENT: 0.0,
    DetectorState.DEFINED: 0.4,
    DetectorState.LIVE: 1.0,
}

SEVERITY_WEIGHTS: Mapping[int, float] = {
    1: 0.2,
    2: 0.4,
    3: 0.6,
    4: 0.8,
    5: 1.0,
}


class FailureModeSpec(BaseModel):
    """Stable catalogue entry for one model-driven failure mode."""

    id: str
    name: str
    severity_level: int = Field(ge=1, le=5)
    agent_multiplier: float = Field(ge=1.0, le=1.3)
    required_dimensions: tuple[str, ...]
    rationale: str

    model_config = ConfigDict(frozen=True)

    @property
    def severity(self) -> float:
        """Normalised severity weight used by the scoring formula."""
        return SEVERITY_WEIGHTS[self.severity_level]


CATALOGUE: tuple[FailureModeSpec, ...] = (
    FailureModeSpec(
        id="MDF-01",
        name="essential complexity hidden",
        severity_level=5,
        agent_multiplier=1.15,
        required_dimensions=("static", "behaviour", "traceability"),
        rationale="Hidden essential complexity invalidates the whole model.",
    ),
    FailureModeSpec(
        id="MDF-02",
        name="model/runtime drift",
        severity_level=5,
        agent_multiplier=1.15,
        required_dimensions=("static", "runtime", "traceability"),
        rationale="Drift destroys trust in DSL as source of truth.",
    ),
    FailureModeSpec(
        id="MDF-03",
        name="opaque generation",
        severity_level=4,
        agent_multiplier=1.3,
        required_dimensions=("traceability", "runtime"),
        rationale="Debug opacity slows every fix and raises comprehension debt.",
    ),
    FailureModeSpec(
        id="MDF-04",
        name="escape-hatch collapse",
        severity_level=5,
        agent_multiplier=1.3,
        required_dimensions=("static", "runtime"),
        rationale="Unsafe escape hatches bypass core guarantees.",
    ),
    FailureModeSpec(
        id="MDF-05",
        name="metamodel overgrowth",
        severity_level=4,
        agent_multiplier=1.3,
        required_dimensions=("static", "traceability"),
        rationale="Metamodel bloat creates long-term framework drag.",
    ),
    FailureModeSpec(
        id="MDF-06",
        name="version-control impedance",
        severity_level=3,
        agent_multiplier=1.0,
        required_dimensions=("static",),
        rationale="Text DSL mitigates this, but generated artefacts can still rot.",
    ),
    FailureModeSpec(
        id="MDF-07",
        name="database abstraction inversion",
        severity_level=5,
        agent_multiplier=1.15,
        required_dimensions=("static", "runtime"),
        rationale="Losing Postgres-native semantics undermines correctness.",
    ),
    FailureModeSpec(
        id="MDF-08",
        name="integration/conformity blind spot",
        severity_level=4,
        agent_multiplier=1.15,
        required_dimensions=("static", "behaviour"),
        rationale="Integration side channels are frequent production failure points.",
    ),
    FailureModeSpec(
        id="MDF-09",
        name="round-trip engineering loss",
        severity_level=4,
        agent_multiplier=1.15,
        required_dimensions=("static", "runtime"),
        rationale="Round-trip loss recreates classic generated-code failure.",
    ),
    FailureModeSpec(
        id="MDF-10",
        name="tool maturity gap",
        severity_level=4,
        agent_multiplier=1.3,
        required_dimensions=("behaviour", "orthogonal", "traceability"),
        rationale="Immature tooling blocks adoption even when the idea is sound.",
    ),
    FailureModeSpec(
        id="MDF-11",
        name="adoption fantasy",
        severity_level=3,
        agent_multiplier=1.15,
        required_dimensions=("behaviour", "traceability"),
        rationale="Adoption friction is serious but usually recoverable.",
    ),
    FailureModeSpec(
        id="MDF-12",
        name="correlated QA blind spots",
        severity_level=4,
        agent_multiplier=1.3,
        required_dimensions=("orthogonal", "behaviour"),
        rationale="Correlated QA gives false confidence.",
    ),
    FailureModeSpec(
        id="MDF-13",
        name="demo cliff",
        severity_level=5,
        agent_multiplier=1.3,
        required_dimensions=("behaviour", "runtime", "orthogonal"),
        rationale="Demo cliff blocks real deployment.",
    ),
    FailureModeSpec(
        id="MDF-14",
        name="agent-amplified abstraction debt",
        severity_level=4,
        agent_multiplier=1.3,
        required_dimensions=("static", "traceability"),
        rationale="Agent-speed debt compounds unless made inspectable.",
    ),
)

CATALOGUE_BY_ID: Mapping[str, FailureModeSpec] = {entry.id: entry for entry in CATALOGUE}


class FailureModeEvidence(BaseModel):
    """Measured evidence for one failure mode.

    Detectors should pass bounded ratios and counts here. This model does not
    infer exposure from raw repository facts; that stays with the detector that
    knows how to count its surface.
    """

    mode_id: str
    exposure: float = Field(ge=0.0, le=1.0)
    detectors: dict[str, DetectorState] = Field(default_factory=dict)
    serious_findings_90d: int = Field(default=0, ge=0)
    serious_findings_that_slipped_live_detectors_90d: int = Field(default=0, ge=0)
    evidence: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)

    @field_validator("mode_id")
    @classmethod
    def _known_mode(cls, value: str) -> str:
        if value not in CATALOGUE_BY_ID:
            raise ValueError(f"unknown model-driven failure mode: {value}")
        return value

    @model_validator(mode="after")
    def _slipped_not_more_than_findings(self) -> FailureModeEvidence:
        if self.serious_findings_that_slipped_live_detectors_90d > self.serious_findings_90d:
            raise ValueError(
                "serious_findings_that_slipped_live_detectors_90d cannot exceed "
                "serious_findings_90d"
            )
        return self


class FailureModeScore(BaseModel):
    """Computed risk score for one failure mode."""

    id: str
    name: str
    severity: float
    exposure: float
    raw_detector_coverage: float
    escape_penalty: float
    detector_coverage: float
    detection_gap: float
    agent_multiplier: float
    risk: int
    evidence: dict[str, Any] = Field(default_factory=dict)
    detectors: dict[str, DetectorState] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class RiskReport(BaseModel):
    """Aggregate model-driven failure-mode risk report."""

    generated_at: datetime
    project_root: str | None = None
    scores: list[FailureModeScore]
    overall: dict[str, int]

    model_config = ConfigDict(frozen=True)


def score_failure_mode(
    spec: FailureModeSpec,
    evidence: FailureModeEvidence | None = None,
) -> FailureModeScore:
    """Calculate the residual risk score for one catalogue entry."""
    if evidence is None:
        evidence = FailureModeEvidence(mode_id=spec.id, exposure=0.0)
    elif evidence.mode_id != spec.id:
        raise ValueError(f"evidence for {evidence.mode_id} cannot score {spec.id}")

    raw_coverage = _raw_detector_coverage(spec.required_dimensions, evidence.detectors)
    escape_penalty = _escape_penalty(
        evidence.serious_findings_90d,
        evidence.serious_findings_that_slipped_live_detectors_90d,
    )
    detector_coverage = raw_coverage * (1.0 - escape_penalty)
    detection_gap = max(0.05, 1.0 - detector_coverage)
    base = spec.severity * evidence.exposure * detection_gap
    risk = round(100 * min(1.0, base * spec.agent_multiplier))

    return FailureModeScore(
        id=spec.id,
        name=spec.name,
        severity=spec.severity,
        exposure=evidence.exposure,
        raw_detector_coverage=raw_coverage,
        escape_penalty=escape_penalty,
        detector_coverage=detector_coverage,
        detection_gap=detection_gap,
        agent_multiplier=spec.agent_multiplier,
        risk=risk,
        evidence=evidence.evidence,
        detectors=evidence.detectors,
    )


def build_report(
    evidence: Iterable[FailureModeEvidence],
    *,
    project_root: Path | str | None = None,
    generated_at: datetime | None = None,
) -> RiskReport:
    """Build a complete risk report over every catalogue entry."""
    evidence_by_id = {item.mode_id: item for item in evidence}
    scores = [score_failure_mode(spec, evidence_by_id.get(spec.id)) for spec in CATALOGUE]
    risks = [score.risk for score in scores]
    max_risk = max(risks, default=0)
    high_risk_count = sum(1 for risk in risks if risk >= 60)
    mean_risk = round(sum(risks) / len(risks)) if risks else 0
    overall_score = min(100, round(max_risk + 5 * max(0, high_risk_count - 1)))
    root = str(project_root) if project_root is not None else None

    return RiskReport(
        generated_at=generated_at or datetime.now(UTC),
        project_root=root,
        scores=scores,
        overall={
            "score": overall_score,
            "max_risk": max_risk,
            "mean_risk": mean_risk,
            "high_risk_count": high_risk_count,
        },
    )


def _raw_detector_coverage(
    required_dimensions: tuple[str, ...],
    detectors: Mapping[str, DetectorState],
) -> float:
    if not required_dimensions:
        return 0.0
    total = 0.0
    for dimension in required_dimensions:
        total += DETECTOR_WEIGHTS[detectors.get(dimension, DetectorState.ABSENT)]
    return total / len(required_dimensions)


def _escape_penalty(serious_findings: int, slipped: int) -> float:
    if serious_findings <= 0:
        return 0.0
    return slipped / max(1, serious_findings)
