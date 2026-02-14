"""
Scan orchestrator: runs agents, deduplicates findings, builds summary.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .models import (
    AgentResult,
    Finding,
    FindingStatus,
    ScanConfig,
    ScanResult,
    ScanSummary,
    Severity,
)
from .store import FindingStore

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec

_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}


class ScanOrchestrator:
    """Run sentinel agents against an AppSpec and manage findings lifecycle."""

    def __init__(self, project_path: Path) -> None:
        self._store = FindingStore(project_path)

    def run_scan(self, appspec: AppSpec, config: ScanConfig | None = None) -> ScanResult:
        config = config or ScanConfig()
        t0 = time.monotonic()
        now_iso = datetime.now(UTC).isoformat()

        # Select agents
        from .agents import get_all_agents

        agents = get_all_agents()
        if config.agents:
            wanted = set(config.agents)
            agents = [a for a in agents if a.agent_id in wanted]

        # Run each agent
        agent_results: list[AgentResult] = []
        all_findings: list[Finding] = []
        for agent in agents:
            result = agent.run(appspec)
            agent_results.append(result)
            all_findings.extend(result.findings)

        # Stamp trigger + timestamps on each finding
        stamped: list[Finding] = []
        for f in all_findings:
            stamped.append(
                f.model_copy(
                    update={
                        "scan_trigger": config.trigger,
                        "first_detected": now_iso,
                        "last_checked": now_iso,
                    }
                )
            )

        # Deduplicate against previous scan
        previous = self._store.load_latest_findings()
        stamped = self._deduplicate(stamped, previous)

        # Detect resolved findings
        resolved_count = self._count_resolved(stamped, previous)

        # Filter by severity threshold
        threshold_idx = _SEVERITY_ORDER.get(config.severity_threshold, 4)
        if not config.include_suppressed:
            stamped = [
                f
                for f in stamped
                if _SEVERITY_ORDER.get(f.severity, 4) <= threshold_idx
                and f.status != FindingStatus.FALSE_POSITIVE
            ]
        else:
            stamped = [f for f in stamped if _SEVERITY_ORDER.get(f.severity, 4) <= threshold_idx]

        # Build summary
        summary = self._build_summary(stamped, resolved_count)

        elapsed = (time.monotonic() - t0) * 1000
        scan = ScanResult(
            trigger=config.trigger,
            agent_results=agent_results,
            findings=stamped,
            summary=summary,
            duration_ms=round(elapsed, 2),
            config=config,
        )
        self._store.save_scan(scan)
        return scan

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def _deduplicate(self, current: list[Finding], previous: list[Finding]) -> list[Finding]:
        prev_map: dict[tuple[str, str | None, str | None, str | None], Finding] = {}
        for f in previous:
            prev_map[f.dedup_key] = f

        deduped: list[Finding] = []
        for f in current:
            prev = prev_map.get(f.dedup_key)
            if prev is not None:
                # Carry forward status / first_detected / suppression_reason
                f = f.model_copy(
                    update={
                        "status": prev.status,
                        "first_detected": prev.first_detected,
                        "suppression_reason": prev.suppression_reason,
                    }
                )
            deduped.append(f)
        return deduped

    def _count_resolved(self, current: list[Finding], previous: list[Finding]) -> int:
        current_keys = {f.dedup_key for f in current}
        return sum(
            1
            for f in previous
            if f.dedup_key not in current_keys
            and f.status not in (FindingStatus.CLOSED, FindingStatus.FALSE_POSITIVE)
        )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _build_summary(self, findings: list[Finding], resolved: int) -> ScanSummary:
        by_severity: dict[str, int] = {}
        by_agent: dict[str, int] = {}
        by_status: dict[str, int] = {}
        new = 0

        for f in findings:
            by_severity[f.severity.value] = by_severity.get(f.severity.value, 0) + 1
            by_agent[f.agent.value] = by_agent.get(f.agent.value, 0) + 1
            by_status[f.status.value] = by_status.get(f.status.value, 0) + 1
            if f.status == FindingStatus.OPEN:
                new += 1

        return ScanSummary(
            total_findings=len(findings),
            by_severity=by_severity,
            by_agent=by_agent,
            by_status=by_status,
            new_findings=new,
            resolved=resolved,
        )
