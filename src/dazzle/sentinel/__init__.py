"""
SaaS Sentinel — failure-mode detection for Dazzle applications.

Public API:
    from dazzle.sentinel import ScanOrchestrator, ScanConfig, ScanResult
"""

from __future__ import annotations

from .models import (
    AgentId,
    AgentResult,
    Confidence,
    Evidence,
    Finding,
    FindingStatus,
    Remediation,
    RemediationEffort,
    ScanConfig,
    ScanResult,
    ScanSummary,
    ScanTrigger,
    Severity,
)
from .orchestrator import ScanOrchestrator
from .store import FindingStore

__all__ = [
    "AgentId",
    "AgentResult",
    "Confidence",
    "Evidence",
    "Finding",
    "FindingStatus",
    "FindingStore",
    "Remediation",
    "RemediationEffort",
    "ScanConfig",
    "ScanOrchestrator",
    "ScanResult",
    "ScanSummary",
    "ScanTrigger",
    "Severity",
]
