"""Tests for Sentinel Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

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

# =============================================================================
# Enums
# =============================================================================


class TestSeverityEnum:
    def test_values(self) -> None:
        assert Severity.CRITICAL == "critical"
        assert Severity.HIGH == "high"
        assert Severity.MEDIUM == "medium"
        assert Severity.LOW == "low"
        assert Severity.INFO == "info"

    def test_construction_from_string(self) -> None:
        assert Severity("critical") is Severity.CRITICAL


class TestAgentIdEnum:
    def test_all_agent_ids(self) -> None:
        assert AgentId.DI == "DI"
        assert AgentId.AA == "AA"
        assert AgentId.MT == "MT"
        assert AgentId.BL == "BL"


class TestFindingStatusEnum:
    def test_values(self) -> None:
        assert FindingStatus.OPEN == "open"
        assert FindingStatus.FALSE_POSITIVE == "false_positive"
        assert FindingStatus.CLOSED == "closed"


# =============================================================================
# Evidence
# =============================================================================


class TestEvidence:
    def test_minimal(self) -> None:
        e = Evidence(evidence_type="ir_pattern", location="entity.Task.id")
        assert e.evidence_type == "ir_pattern"
        assert e.snippet is None
        assert e.context == ""

    def test_frozen(self) -> None:
        e = Evidence(evidence_type="ir_pattern", location="x")
        with pytest.raises((TypeError, ValidationError)):
            e.location = "y"  # type: ignore[misc]


# =============================================================================
# Finding
# =============================================================================


class TestFinding:
    def test_auto_generated_id(self) -> None:
        f = Finding(
            agent=AgentId.DI,
            heuristic_id="DI-01",
            category="data_integrity",
            subcategory="cascade_delete",
            severity=Severity.HIGH,
            title="test",
            description="test desc",
        )
        assert len(f.finding_id) == 12

    def test_dedup_key(self) -> None:
        f = Finding(
            agent=AgentId.DI,
            heuristic_id="DI-01",
            category="cat",
            subcategory="sub",
            severity=Severity.HIGH,
            title="test",
            description="desc",
            entity_name="Task",
            surface_name="task_list",
            construct_type="entity",
        )
        assert f.dedup_key == ("DI-01", "Task", "task_list", "entity")

    def test_dedup_key_minimal(self) -> None:
        f = Finding(
            agent=AgentId.AA,
            heuristic_id="AA-01",
            category="auth",
            subcategory="access",
            severity=Severity.MEDIUM,
            title="t",
            description="d",
        )
        assert f.dedup_key == ("AA-01", None, None, None)

    def test_defaults(self) -> None:
        f = Finding(
            agent=AgentId.DI,
            heuristic_id="DI-01",
            category="cat",
            subcategory="sub",
            severity=Severity.LOW,
            title="t",
            description="d",
        )
        assert f.status == FindingStatus.OPEN
        assert f.confidence == Confidence.CONFIRMED
        assert f.scan_trigger == ScanTrigger.MANUAL
        assert f.suppression_reason is None
        assert f.evidence == []
        assert f.remediation is None

    def test_frozen(self) -> None:
        f = Finding(
            agent=AgentId.DI,
            heuristic_id="DI-01",
            category="c",
            subcategory="s",
            severity=Severity.LOW,
            title="t",
            description="d",
        )
        with pytest.raises((TypeError, ValidationError)):
            f.title = "changed"  # type: ignore[misc]


# =============================================================================
# Remediation
# =============================================================================


class TestRemediation:
    def test_minimal(self) -> None:
        r = Remediation(summary="Fix it")
        assert r.summary == "Fix it"
        assert r.effort == RemediationEffort.SMALL
        assert r.guidance == ""
        assert r.dsl_example is None

    def test_full(self) -> None:
        r = Remediation(
            summary="Add cascade",
            effort=RemediationEffort.TRIVIAL,
            guidance="See docs",
            dsl_example="  items: has_many OrderItem cascade",
            references=["https://example.com"],
        )
        assert r.references == ["https://example.com"]


# =============================================================================
# ScanConfig
# =============================================================================


class TestScanConfig:
    def test_defaults(self) -> None:
        c = ScanConfig()
        assert c.agents is None
        assert c.severity_threshold == Severity.INFO
        assert c.entity_filter is None
        assert c.trigger == ScanTrigger.MANUAL
        assert c.include_suppressed is False

    def test_with_agents(self) -> None:
        c = ScanConfig(agents=[AgentId.DI, AgentId.AA])
        assert len(c.agents) == 2  # type: ignore[arg-type]


# =============================================================================
# AgentResult
# =============================================================================


class TestAgentResult:
    def test_defaults(self) -> None:
        r = AgentResult(agent=AgentId.DI)
        assert r.findings == []
        assert r.heuristics_run == 0
        assert r.duration_ms == 0.0
        assert r.errors == []


# =============================================================================
# ScanSummary
# =============================================================================


class TestScanSummary:
    def test_defaults(self) -> None:
        s = ScanSummary()
        assert s.total_findings == 0
        assert s.by_severity == {}
        assert s.new_findings == 0
        assert s.resolved == 0


# =============================================================================
# ScanResult
# =============================================================================


class TestScanResult:
    def test_auto_id_and_timestamp(self) -> None:
        r = ScanResult()
        assert len(r.scan_id) == 12
        assert "T" in r.timestamp  # ISO format

    def test_defaults(self) -> None:
        r = ScanResult()
        assert r.trigger == ScanTrigger.MANUAL
        assert r.agent_results == []
        assert r.findings == []
        assert r.duration_ms == 0.0
