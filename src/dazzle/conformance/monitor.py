"""Runtime contract monitoring for conformance verification.

Installs an audit sink that captures access decision records during a
scenario run, then compares observed behavior against derived conformance
cases to detect discrepancies.

Usage::

    monitor = ConformanceMonitor(cases)
    monitor.install()
    try:
        # ... run scenario (HTTP requests, etc.) ...
        report = monitor.compare()
    finally:
        monitor.uninstall()
"""

from __future__ import annotations  # required: forward reference

import logging
from dataclasses import dataclass, field
from typing import Any

from dazzle.rbac.audit import (
    AccessDecisionRecord,
    InMemoryAuditSink,
    get_audit_sink,
    set_audit_sink,
)

from .models import ConformanceCase

logger = logging.getLogger(__name__)


@dataclass
class Discrepancy:
    """A mismatch between expected and observed behavior."""

    entity: str
    operation: str
    persona: str
    expected_decision: str
    actual_decision: str
    details: str

    def __repr__(self) -> str:
        return (
            f"<Discrepancy {self.entity}.{self.operation} "
            f"persona={self.persona} "
            f"expected={self.expected_decision} "
            f"actual={self.actual_decision}>"
        )


@dataclass
class MonitorReport:
    """Result of comparing observed decisions against conformance expectations."""

    total_observations: int = 0
    total_cases: int = 0
    matched: int = 0
    discrepancies: list[Discrepancy] = field(default_factory=list)
    unobserved: list[str] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        if self.total_cases == 0:
            return 1.0
        return self.matched / self.total_cases

    @property
    def passed(self) -> bool:
        return len(self.discrepancies) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_observations": self.total_observations,
            "total_cases": self.total_cases,
            "matched": self.matched,
            "discrepancies": [
                {
                    "entity": d.entity,
                    "operation": d.operation,
                    "persona": d.persona,
                    "expected": d.expected_decision,
                    "actual": d.actual_decision,
                    "details": d.details,
                }
                for d in self.discrepancies
            ],
            "unobserved": self.unobserved,
            "pass_rate": self.pass_rate,
        }


class ConformanceMonitor:
    """Captures runtime access decisions and compares against conformance cases.

    Args:
        cases: Derived conformance cases to verify against.
    """

    def __init__(self, cases: list[ConformanceCase]) -> None:
        self._cases = cases
        self._sink = InMemoryAuditSink()
        self._previous_sink: Any = None
        self._installed = False

        # Build lookup: (entity, operation, persona) → expected decision
        self._expectations: dict[tuple[str, str, str], ConformanceCase] = {}
        for case in cases:
            # Only track the primary case (skip row_target variants for monitoring)
            if case.row_target is not None:
                continue
            key = (case.entity, case.operation, case.persona)
            self._expectations[key] = case

    def install(self) -> None:
        """Install the monitoring audit sink (preserves previous sink)."""
        self._previous_sink = get_audit_sink()
        set_audit_sink(self._sink)
        self._installed = True
        logger.debug("ConformanceMonitor installed")

    def uninstall(self) -> None:
        """Restore the previous audit sink."""
        if self._previous_sink is not None:
            set_audit_sink(self._previous_sink)
        self._installed = False
        logger.debug("ConformanceMonitor uninstalled")

    @property
    def records(self) -> list[AccessDecisionRecord]:
        """Access collected decision records."""
        return self._sink.records

    def clear(self) -> None:
        """Clear collected records."""
        self._sink.clear()

    def compare(self) -> MonitorReport:
        """Compare observed decisions against expected conformance behavior.

        Builds a report showing:
        - How many decisions were observed
        - How many matched expectations
        - Which (entity, operation, persona) triples diverged

        Returns:
            MonitorReport with discrepancies.
        """
        report = MonitorReport(
            total_observations=len(self._sink.records),
            total_cases=len(self._expectations),
        )

        # Group observed decisions by (entity, operation, role)
        observed: dict[tuple[str, str, str], list[AccessDecisionRecord]] = {}
        for record in self._sink.records:
            for role in record.roles:
                key = (record.entity, record.operation, role)
                observed.setdefault(key, []).append(record)

        # Check each expectation against observations
        for key, case in self._expectations.items():
            entity, operation, persona = key
            records = observed.get(key, [])

            if not records:
                report.unobserved.append(case.test_id)
                continue

            # Check: did the decision match the expected outcome?
            expected_allowed = _case_expects_allow(case)

            # Use the most recent observation
            actual = records[-1]
            actual_allowed = actual.allowed

            if actual_allowed == expected_allowed:
                report.matched += 1
            else:
                report.discrepancies.append(
                    Discrepancy(
                        entity=entity,
                        operation=operation,
                        persona=persona,
                        expected_decision="allow" if expected_allowed else "deny",
                        actual_decision="allow" if actual_allowed else "deny",
                        details=(
                            f"Case {case.test_id}: expected status {case.expected_status}, "
                            f"rule matched: {actual.matched_rule}"
                        ),
                    )
                )

        return report


def _case_expects_allow(case: ConformanceCase) -> bool:
    """Determine if a conformance case expects an allow decision."""
    # 2xx status codes are allows, 4xx are denies
    return 200 <= case.expected_status < 300
