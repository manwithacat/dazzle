"""
Pydantic models for the SaaS Sentinel failure-mode detection system.

All models use frozen=True per codebase convention.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Confidence(StrEnum):
    CONFIRMED = "confirmed"
    LIKELY = "likely"
    POSSIBLE = "possible"


class FindingStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    MITIGATED = "mitigated"
    CLOSED = "closed"
    FALSE_POSITIVE = "false_positive"


class ScanTrigger(StrEnum):
    MANUAL = "manual"
    PIPELINE = "pipeline"
    SCHEDULED = "scheduled"
    COMMIT = "commit"
    DEPLOYMENT = "deployment"
    DEPENDENCY_UPDATE = "dependency_update"


class AgentId(StrEnum):
    DI = "DI"
    AA = "AA"
    MT = "MT"
    ID = "ID"
    DS = "DS"
    PR = "PR"
    OP = "OP"
    BL = "BL"


class RemediationEffort(StrEnum):
    TRIVIAL = "trivial"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    SIGNIFICANT = "significant"


# ---------------------------------------------------------------------------
# Core models
# ---------------------------------------------------------------------------


class Evidence(BaseModel):
    evidence_type: str  # ir_pattern, config_value, missing_construct
    location: str
    snippet: str | None = None
    context: str = ""

    model_config = ConfigDict(frozen=True)


class Remediation(BaseModel):
    summary: str
    effort: RemediationEffort = RemediationEffort.SMALL
    guidance: str = ""
    dsl_example: str | None = None
    references: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class Finding(BaseModel):
    finding_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    agent: AgentId
    heuristic_id: str
    category: str
    subcategory: str
    severity: Severity
    confidence: Confidence = Confidence.CONFIRMED
    title: str
    description: str
    evidence: list[Evidence] = Field(default_factory=list)
    remediation: Remediation | None = None
    status: FindingStatus = FindingStatus.OPEN
    first_detected: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    last_checked: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    scan_trigger: ScanTrigger = ScanTrigger.MANUAL
    suppression_reason: str | None = None
    entity_name: str | None = None
    surface_name: str | None = None
    construct_type: str | None = None

    model_config = ConfigDict(frozen=True)

    @property
    def dedup_key(self) -> tuple[str, str | None, str | None, str | None]:
        return (self.heuristic_id, self.entity_name, self.surface_name, self.construct_type)


# ---------------------------------------------------------------------------
# Scan configuration & results
# ---------------------------------------------------------------------------


class ScanConfig(BaseModel):
    agents: list[AgentId] | None = None
    severity_threshold: Severity = Severity.INFO
    entity_filter: str | None = None
    surface_filter: str | None = None
    trigger: ScanTrigger = ScanTrigger.MANUAL
    include_suppressed: bool = False

    model_config = ConfigDict(frozen=True)


class AgentResult(BaseModel):
    agent: AgentId
    findings: list[Finding] = Field(default_factory=list)
    heuristics_run: int = 0
    duration_ms: float = 0.0
    errors: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class ScanSummary(BaseModel):
    total_findings: int = 0
    by_severity: dict[str, int] = Field(default_factory=dict)
    by_agent: dict[str, int] = Field(default_factory=dict)
    by_status: dict[str, int] = Field(default_factory=dict)
    new_findings: int = 0
    resolved: int = 0

    model_config = ConfigDict(frozen=True)


class ScanResult(BaseModel):
    scan_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    trigger: ScanTrigger = ScanTrigger.MANUAL
    agent_results: list[AgentResult] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    summary: ScanSummary = Field(default_factory=ScanSummary)
    duration_ms: float = 0.0
    config: ScanConfig = Field(default_factory=ScanConfig)

    model_config = ConfigDict(frozen=True)
