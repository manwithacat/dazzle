"""Tests for Sentinel Pydantic models.

The enum values are the wire format of persisted scans (``.dazzle/sentinel``),
and the defaults are what a heuristic gets when it omits a field, so both are
pinned as tables. Constructor round-trips are not tested.
"""

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from dazzle.sentinel.models import (
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


def _finding(**overrides: Any) -> Finding:
    fields: dict[str, Any] = {
        "agent": AgentId.DI,
        "heuristic_id": "DI-01",
        "category": "cat",
        "subcategory": "sub",
        "severity": Severity.LOW,
        "title": "t",
        "description": "d",
    }
    return Finding(**{**fields, **overrides})


@pytest.mark.parametrize(
    ("enum_cls", "expected"),
    [
        pytest.param(
            Severity,
            {
                "CRITICAL": "critical",
                "HIGH": "high",
                "MEDIUM": "medium",
                "LOW": "low",
                "INFO": "info",
            },
            id="severity",
        ),
        pytest.param(
            FindingStatus,
            {"OPEN": "open", "FALSE_POSITIVE": "false_positive", "CLOSED": "closed"},
            id="finding-status",
        ),
        pytest.param(
            AgentId,
            {"DI": "DI", "AA": "AA", "MT": "MT", "BL": "BL"},
            id="agent-id",
        ),
    ],
)
def test_enum_wire_values(enum_cls: type, expected: dict[str, str]) -> None:
    for name, value in expected.items():
        member = enum_cls[name]
        assert member == value
        assert enum_cls(value) is member


@pytest.mark.parametrize(
    ("build", "expected"),
    [
        pytest.param(
            lambda: Evidence(evidence_type="ir_pattern", location="entity.Task.id"),
            {"snippet": None, "context": ""},
            id="evidence",
        ),
        pytest.param(
            _finding,
            {
                "status": FindingStatus.OPEN,
                "confidence": Confidence.CONFIRMED,
                "scan_trigger": ScanTrigger.MANUAL,
                "suppression_reason": None,
                "evidence": [],
                "remediation": None,
                "catalogue_entry": None,
            },
            id="finding",
        ),
        pytest.param(
            lambda: Remediation(summary="Fix it"),
            {"effort": RemediationEffort.SMALL, "guidance": "", "dsl_example": None},
            id="remediation",
        ),
        pytest.param(
            ScanConfig,
            {
                "agents": None,
                "severity_threshold": Severity.INFO,
                "entity_filter": None,
                "trigger": ScanTrigger.MANUAL,
                "include_suppressed": False,
            },
            id="scan-config",
        ),
        pytest.param(
            lambda: AgentResult(agent=AgentId.DI),
            {"findings": [], "heuristics_run": 0, "duration_ms": 0.0, "errors": []},
            id="agent-result",
        ),
        pytest.param(
            ScanSummary,
            {"total_findings": 0, "by_severity": {}, "new_findings": 0, "resolved": 0},
            id="scan-summary",
        ),
        pytest.param(
            ScanResult,
            {
                "trigger": ScanTrigger.MANUAL,
                "agent_results": [],
                "findings": [],
                "duration_ms": 0.0,
            },
            id="scan-result",
        ),
    ],
)
def test_defaults(build: Any, expected: dict[str, Any]) -> None:
    model = build()
    assert {key: getattr(model, key) for key in expected} == expected


def test_generated_ids() -> None:
    assert len(_finding().finding_id) == 12
    assert _finding().finding_id != _finding().finding_id
    scan = ScanResult()
    assert len(scan.scan_id) == 12
    assert "T" in scan.timestamp  # ISO 8601


@pytest.mark.parametrize(
    ("finding", "key"),
    [
        pytest.param(
            _finding(entity_name="Task", surface_name="task_list", construct_type="entity"),
            ("DI-01", "Task", "task_list", "entity"),
            id="full",
        ),
        pytest.param(_finding(), ("DI-01", None, None, None), id="minimal"),
    ],
)
def test_dedup_key(finding: Finding, key: tuple) -> None:
    assert finding.dedup_key == key


@pytest.mark.parametrize(
    ("model", "field"),
    [
        pytest.param(Evidence(evidence_type="ir_pattern", location="x"), "location", id="evidence"),
        pytest.param(_finding(), "title", id="finding"),
    ],
)
def test_frozen(model: BaseModel, field: str) -> None:
    with pytest.raises((TypeError, ValidationError)):
        setattr(model, field, "changed")
