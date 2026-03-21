"""Tests for runtime contract monitoring (#602).

Tests the ConformanceMonitor audit sink integration and comparison logic.
"""

from __future__ import annotations

from dazzle.conformance.models import ConformanceCase, ScopeOutcome
from dazzle.conformance.monitor import (
    ConformanceMonitor,
    Discrepancy,
    MonitorReport,
    _case_expects_allow,
)
from dazzle.rbac.audit import (
    AccessDecisionRecord,
    NullAuditSink,
    get_audit_sink,
    set_audit_sink,
)

# =============================================================================
# Helpers
# =============================================================================


def _make_case(
    entity: str = "Task",
    persona: str = "viewer",
    operation: str = "list",
    expected_status: int = 200,
    scope_type: ScopeOutcome = ScopeOutcome.ALL,
    row_target: str | None = None,
) -> ConformanceCase:
    return ConformanceCase(
        entity=entity,
        persona=persona,
        operation=operation,
        expected_status=expected_status,
        scope_type=scope_type,
        row_target=row_target,
    )


def _make_record(
    entity: str = "Task",
    operation: str = "list",
    roles: list[str] | None = None,
    allowed: bool = True,
    matched_rule: str = "permit_viewer_list",
) -> AccessDecisionRecord:
    return AccessDecisionRecord(
        timestamp="2026-03-21T12:00:00Z",
        request_id="req-1",
        user_id="user-1",
        roles=roles or ["viewer"],
        entity=entity,
        operation=operation,
        allowed=allowed,
        effect="permit" if allowed else "deny",
        matched_rule=matched_rule,
        record_id=None,
        tier="unit",
    )


# =============================================================================
# _case_expects_allow tests
# =============================================================================


class TestCaseExpectsAllow:
    def test_200_is_allow(self) -> None:
        assert _case_expects_allow(_make_case(expected_status=200))

    def test_201_is_allow(self) -> None:
        assert _case_expects_allow(_make_case(expected_status=201))

    def test_403_is_deny(self) -> None:
        assert not _case_expects_allow(_make_case(expected_status=403))

    def test_401_is_deny(self) -> None:
        assert not _case_expects_allow(_make_case(expected_status=401))

    def test_404_is_deny(self) -> None:
        assert not _case_expects_allow(_make_case(expected_status=404))


# =============================================================================
# Discrepancy tests
# =============================================================================


class TestDiscrepancy:
    def test_repr(self) -> None:
        d = Discrepancy(
            entity="Task",
            operation="list",
            persona="viewer",
            expected_decision="allow",
            actual_decision="deny",
            details="test",
        )
        assert "Task.list" in repr(d)
        assert "viewer" in repr(d)


# =============================================================================
# MonitorReport tests
# =============================================================================


class TestMonitorReport:
    def test_pass_rate_no_cases(self) -> None:
        report = MonitorReport()
        assert report.pass_rate == 1.0
        assert report.passed

    def test_pass_rate_all_matched(self) -> None:
        report = MonitorReport(total_cases=5, matched=5)
        assert report.pass_rate == 1.0
        assert report.passed

    def test_pass_rate_with_discrepancy(self) -> None:
        d = Discrepancy("T", "l", "v", "allow", "deny", "x")
        report = MonitorReport(total_cases=5, matched=4, discrepancies=[d])
        assert report.pass_rate == 0.8
        assert not report.passed

    def test_to_dict(self) -> None:
        report = MonitorReport(total_observations=10, total_cases=5, matched=5)
        d = report.to_dict()
        assert d["total_observations"] == 10
        assert d["pass_rate"] == 1.0
        assert d["discrepancies"] == []


# =============================================================================
# ConformanceMonitor tests
# =============================================================================


class TestConformanceMonitor:
    def test_install_and_uninstall(self) -> None:
        """Monitor should swap audit sink and restore on uninstall."""
        original = NullAuditSink()
        set_audit_sink(original)

        cases = [_make_case()]
        monitor = ConformanceMonitor(cases)

        monitor.install()
        assert get_audit_sink() is not original
        assert get_audit_sink() is monitor._sink

        monitor.uninstall()
        assert get_audit_sink() is original

    def test_records_collected(self) -> None:
        """Monitor should collect records emitted to the sink."""
        cases = [_make_case()]
        monitor = ConformanceMonitor(cases)
        monitor.install()
        try:
            # Simulate emitting a record
            monitor._sink.emit(_make_record())
            assert len(monitor.records) == 1
        finally:
            monitor.uninstall()

    def test_clear(self) -> None:
        cases = [_make_case()]
        monitor = ConformanceMonitor(cases)
        monitor._sink.emit(_make_record())
        assert len(monitor.records) == 1
        monitor.clear()
        assert len(monitor.records) == 0

    def test_row_target_cases_excluded_from_expectations(self) -> None:
        """Cases with row_target should not be in the expectations map."""
        cases = [
            _make_case(operation="read", row_target="own"),
            _make_case(operation="read", row_target="other"),
            _make_case(operation="list"),
        ]
        monitor = ConformanceMonitor(cases)
        assert len(monitor._expectations) == 1  # Only the list case

    def test_compare_matching(self) -> None:
        """When observed decision matches expectation, report matched."""
        cases = [_make_case(expected_status=200)]
        monitor = ConformanceMonitor(cases)
        monitor._sink.emit(_make_record(allowed=True))

        report = monitor.compare()
        assert report.matched == 1
        assert len(report.discrepancies) == 0
        assert report.passed

    def test_compare_discrepancy(self) -> None:
        """When observed decision differs, report discrepancy."""
        cases = [_make_case(expected_status=200)]  # Expects allow
        monitor = ConformanceMonitor(cases)
        monitor._sink.emit(_make_record(allowed=False))  # Got deny

        report = monitor.compare()
        assert report.matched == 0
        assert len(report.discrepancies) == 1
        assert report.discrepancies[0].expected_decision == "allow"
        assert report.discrepancies[0].actual_decision == "deny"

    def test_compare_unobserved(self) -> None:
        """Cases with no matching observations should be listed as unobserved."""
        cases = [
            _make_case(entity="Task"),
            _make_case(entity="Bug"),
        ]
        monitor = ConformanceMonitor(cases)
        # Only emit for Task
        monitor._sink.emit(_make_record(entity="Task", allowed=True))

        report = monitor.compare()
        assert report.matched == 1
        assert len(report.unobserved) == 1
        assert "Bug" in report.unobserved[0]

    def test_compare_deny_expected_deny(self) -> None:
        """When both expect and observe deny, it should match."""
        cases = [_make_case(expected_status=403, scope_type=ScopeOutcome.ACCESS_DENIED)]
        monitor = ConformanceMonitor(cases)
        monitor._sink.emit(_make_record(allowed=False))

        report = monitor.compare()
        assert report.matched == 1
        assert report.passed

    def test_compare_multiple_observations_uses_latest(self) -> None:
        """When multiple observations exist, use the most recent one."""
        cases = [_make_case(expected_status=200)]
        monitor = ConformanceMonitor(cases)
        # First observation: deny (wrong)
        monitor._sink.emit(_make_record(allowed=False))
        # Second observation: allow (correct)
        monitor._sink.emit(_make_record(allowed=True))

        report = monitor.compare()
        assert report.matched == 1
        assert report.passed

    def test_compare_multiple_personas(self) -> None:
        """Different personas should be tracked independently."""
        cases = [
            _make_case(persona="viewer", expected_status=200),
            _make_case(persona="admin", expected_status=200),
        ]
        monitor = ConformanceMonitor(cases)
        monitor._sink.emit(_make_record(roles=["viewer"], allowed=True))
        monitor._sink.emit(_make_record(roles=["admin"], allowed=True))

        report = monitor.compare()
        assert report.matched == 2
        assert report.passed
