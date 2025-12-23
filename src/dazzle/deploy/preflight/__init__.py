"""
AWS CDK Pre-Flight Validation System.

Validates generated CDK code before deployment using a multi-stage
pipeline of static checks, policy guardrails, and optional AWS calls.

Modes:
- static_only: No AWS credentials required
- plan_only: AWS calls allowed, no changes executed
- sandbox_apply: Deploy to sandbox, smoke test, teardown
"""

from .models import (
    Finding,
    FindingSeverity,
    PreflightConfig,
    PreflightMode,
    PreflightReport,
    PreflightSummary,
    StageResult,
    StageStatus,
)
from .report import ReportGenerator, generate_report
from .runner import PreflightRunner, run_preflight

__all__ = [
    # Models
    "Finding",
    "FindingSeverity",
    "PreflightConfig",
    "PreflightMode",
    "PreflightReport",
    "PreflightSummary",
    "StageResult",
    "StageStatus",
    # Runner
    "PreflightRunner",
    "run_preflight",
    # Report
    "ReportGenerator",
    "generate_report",
]
