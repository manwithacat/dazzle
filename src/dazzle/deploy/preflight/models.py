"""
Data models for the pre-flight validation system.

These models define the structure of preflight configuration,
stage results, findings, and the final report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class PreflightMode(StrEnum):
    """Pre-flight execution modes."""

    STATIC_ONLY = "static_only"  # No AWS credentials required
    PLAN_ONLY = "plan_only"  # AWS calls allowed, no changes executed
    SANDBOX_APPLY = "sandbox_apply"  # Deploy to sandbox, smoke test, teardown


class StageStatus(StrEnum):
    """Status of a preflight stage."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class FindingSeverity(StrEnum):
    """Severity levels for preflight findings."""

    INFO = "info"
    WARN = "warn"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Finding:
    """A single finding from a preflight check."""

    severity: FindingSeverity
    code: str  # Rule/check identifier (e.g., "NO_PUBLIC_RDS")
    message: str
    resource: str | None = None  # Logical resource ID or path
    remediation: str | None = None  # Suggested fix
    stage: str | None = None  # Which stage produced this finding
    file_path: str | None = None  # Source file if applicable
    line_number: int | None = None  # Line number if applicable

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "resource": self.resource,
            "remediation": self.remediation,
            "stage": self.stage,
            "file_path": self.file_path,
            "line_number": self.line_number,
        }


@dataclass
class StageResult:
    """Result from a single preflight stage."""

    name: str
    status: StageStatus = StageStatus.PENDING
    duration_ms: int = 0
    findings: list[Finding] = field(default_factory=list)
    artifacts: list[dict[str, str]] = field(default_factory=list)
    error_message: str | None = None

    @property
    def passed(self) -> bool:
        """Check if stage passed."""
        return self.status == StageStatus.PASSED

    @property
    def failed(self) -> bool:
        """Check if stage failed."""
        return self.status == StageStatus.FAILED

    def add_finding(self, finding: Finding) -> None:
        """Add a finding to this stage."""
        finding.stage = self.name
        self.findings.append(finding)

    def add_artifact(self, artifact_type: str, path: str) -> None:
        """Add an artifact reference."""
        self.artifacts.append({"type": artifact_type, "path": path})

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "findings": [f.to_dict() for f in self.findings],
            "artifacts": self.artifacts,
            "error_message": self.error_message,
        }


@dataclass
class PreflightSummary:
    """Summary of preflight results."""

    status: str  # "passed", "failed", "blocked"
    total_findings: int = 0
    critical_count: int = 0
    high_count: int = 0
    warn_count: int = 0
    info_count: int = 0
    stages_passed: int = 0
    stages_failed: int = 0
    stages_skipped: int = 0
    next_actions: list[str] = field(default_factory=list)

    @property
    def can_proceed(self) -> bool:
        """Check if deployment can proceed based on findings."""
        return self.critical_count == 0 and self.high_count == 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status,
            "total_findings": self.total_findings,
            "counts_by_severity": {
                "critical": self.critical_count,
                "high": self.high_count,
                "warn": self.warn_count,
                "info": self.info_count,
            },
            "stages": {
                "passed": self.stages_passed,
                "failed": self.stages_failed,
                "skipped": self.stages_skipped,
            },
            "can_proceed": self.can_proceed,
            "next_actions": self.next_actions,
        }


@dataclass
class PreflightReport:
    """Complete pre-flight report."""

    run_id: str
    timestamp_utc: str
    app_name: str
    app_version: str
    commit_sha: str | None
    env_name: str
    account_id: str | None
    region: str
    mode: PreflightMode
    stages: list[StageResult] = field(default_factory=list)
    summary: PreflightSummary | None = None
    toolchain: dict[str, str] = field(default_factory=dict)

    def compute_summary(self) -> PreflightSummary:
        """Compute summary from stage results."""
        summary = PreflightSummary(status="passed")

        for stage in self.stages:
            if stage.status == StageStatus.PASSED:
                summary.stages_passed += 1
            elif stage.status == StageStatus.FAILED:
                summary.stages_failed += 1
            elif stage.status == StageStatus.SKIPPED:
                summary.stages_skipped += 1

            for finding in stage.findings:
                summary.total_findings += 1
                if finding.severity == FindingSeverity.CRITICAL:
                    summary.critical_count += 1
                elif finding.severity == FindingSeverity.HIGH:
                    summary.high_count += 1
                elif finding.severity == FindingSeverity.WARN:
                    summary.warn_count += 1
                else:
                    summary.info_count += 1

        # Determine overall status
        if summary.stages_failed > 0 or summary.critical_count > 0:
            summary.status = "failed"
        elif summary.high_count > 0:
            summary.status = "blocked"
        else:
            summary.status = "passed"

        # Suggest next actions
        if summary.critical_count > 0:
            summary.next_actions.append(
                f"Fix {summary.critical_count} CRITICAL finding(s) before proceeding"
            )
        if summary.high_count > 0:
            summary.next_actions.append(f"Fix or allowlist {summary.high_count} HIGH finding(s)")
        if summary.status == "passed":
            summary.next_actions.append("Ready for deployment")

        self.summary = summary
        return summary

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        if self.summary is None:
            self.compute_summary()

        return {
            "run_id": self.run_id,
            "timestamp_utc": self.timestamp_utc,
            "app": {
                "name": self.app_name,
                "version": self.app_version,
                "commit_sha": self.commit_sha,
            },
            "env": {
                "name": self.env_name,
                "account_id": self.account_id,
                "region": self.region,
            },
            "mode": self.mode.value,
            "toolchain": self.toolchain,
            "stages": [s.to_dict() for s in self.stages],
            "summary": self.summary.to_dict() if self.summary else None,
        }


@dataclass
class PreflightConfig:
    """Configuration for preflight execution."""

    mode: PreflightMode = PreflightMode.STATIC_ONLY
    infra_dir: Path | None = None  # Generated CDK directory
    output_dir: Path | None = None  # Where to write reports/artifacts
    fail_on_high: bool = True
    fail_on_warn: bool = False
    skip_stages: list[str] = field(default_factory=list)
    allowlist_path: Path | None = None
    policy_paths: list[Path] = field(default_factory=list)

    # Toolchain version requirements (optional pinning)
    required_cdk_version: str | None = None
    required_python_version: str | None = None
    required_node_version: str | None = None

    def get_output_dir(self, project_root: Path) -> Path:
        """Get the output directory for reports."""
        if self.output_dir:
            return self.output_dir
        return project_root / "reports"

    def get_artifacts_dir(self, project_root: Path) -> Path:
        """Get the artifacts directory."""
        return project_root / "artifacts"


# Stage names as constants
STAGE_BOOTSTRAP = "bootstrap"
STAGE_SYNTH = "synth"
STAGE_ASSERTIONS = "assertions"
STAGE_LINT = "lint"
STAGE_GUARDRAILS = "guardrails"
STAGE_TIGERBEETLE = "tigerbeetle"
STAGE_IAM_VALIDATE = "iam_validate"
STAGE_DIFF = "diff"
STAGE_CHANGESET = "changeset"
STAGE_SANDBOX = "sandbox"
