"""
MCP handler for the Sentinel failure-mode detection tool.

Operations: scan, findings, suppress, status, history
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .common import error_response, extract_progress, load_project_appspec, wrap_handler_errors

# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------


def sentinel_scan_impl(
    project_path: Path,
    agents: list[str] | None,
    severity_threshold: str,
    trigger: str,
    detail: str,
) -> dict[str, Any]:
    """Run sentinel scan against project DSL. Returns scan result dict."""
    t0 = time.monotonic()
    appspec = load_project_appspec(project_path)
    from dazzle.sentinel.models import AgentId, ScanConfig, Severity

    agent_ids = [AgentId(a) for a in agents] if agents else None
    config = ScanConfig(
        agents=agent_ids,
        severity_threshold=Severity(severity_threshold),
        trigger=trigger,
    )

    from dazzle.sentinel.orchestrator import ScanOrchestrator

    orch = ScanOrchestrator(project_path)
    result = orch.run_scan(appspec, config)

    wall_ms = (time.monotonic() - t0) * 1000

    if detail == "metrics":
        return {
            "status": "ok",
            "scan_id": result.scan_id,
            "summary": result.summary.model_dump(),
            "duration_ms": round(wall_ms, 1),
        }

    findings_data = [f.model_dump() for f in result.findings]
    if detail == "issues":
        # Medium severity and above
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        findings_data = [
            f for f in findings_data if sev_order.get(f.get("severity", "info"), 4) <= 2
        ]

    out: dict[str, Any] = {
        "status": "ok",
        "scan_id": result.scan_id,
        "summary": result.summary.model_dump(),
        "findings": findings_data,
        "duration_ms": round(wall_ms, 1),
    }
    if detail == "full":
        out["agent_results"] = [ar.model_dump() for ar in result.agent_results]

    return out


@wrap_handler_errors
def scan_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Run sentinel scan against project DSL."""
    progress = extract_progress(args)
    progress.log_sync("Loading project DSL...")
    raw_agents = args.get("agents")
    agent_list: list[str] | None = list(raw_agents) if raw_agents else None
    progress.log_sync("Running sentinel scan...")
    out = sentinel_scan_impl(
        project_path=project_path,
        agents=agent_list,
        severity_threshold=args.get("severity_threshold", "info"),
        trigger=args.get("trigger", "manual"),
        detail=args.get("detail", "issues"),
    )
    by_sev = (
        out.get("summary", {}).get("by_severity", {})
        if isinstance(out.get("summary"), dict)
        else {}
    )
    high_sev = by_sev.get("critical", 0) + by_sev.get("high", 0)
    total = (
        out.get("summary", {}).get("total_findings", 0)
        if isinstance(out.get("summary"), dict)
        else 0
    )
    progress.log_sync(f"Scan complete: {total} findings ({high_sev} high-severity)")
    return json.dumps(out, indent=2)


# ---------------------------------------------------------------------------
# findings
# ---------------------------------------------------------------------------


def sentinel_findings_impl(
    project_path: Path,
    scan_id: str | None,
    agent: str | None,
    severity: str | None,
) -> dict[str, Any]:
    """Get findings from latest or specific scan. Returns findings dict."""
    from dazzle.sentinel.store import FindingStore

    store = FindingStore(project_path)

    if scan_id:
        scan = store.load_scan(scan_id)
        if scan is None:
            return {"error": f"Scan '{scan_id}' not found"}
        findings = scan.findings
    else:
        findings = store.load_latest_findings()

    if agent:
        findings = [f for f in findings if f.agent.value == agent]

    if severity:
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        threshold = sev_order.get(severity, 4)
        findings = [f for f in findings if sev_order.get(f.severity.value, 4) <= threshold]

    return {
        "findings": [f.model_dump() for f in findings],
        "count": len(findings),
    }


@wrap_handler_errors
def findings_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Get findings from latest or specific scan."""
    result = sentinel_findings_impl(
        project_path=project_path,
        scan_id=args.get("scan_id"),
        agent=args.get("agent"),
        severity=args.get("severity"),
    )
    if "error" in result:
        return error_response(result["error"])
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# suppress
# ---------------------------------------------------------------------------


def sentinel_suppress_impl(
    project_path: Path,
    finding_id: str,
    reason: str,
) -> dict[str, Any]:
    """Mark a finding as false_positive. Returns status dict."""
    from dazzle.sentinel.store import FindingStore

    store = FindingStore(project_path)
    ok = store.suppress_finding(finding_id, reason)
    if ok:
        return {"status": "suppressed", "finding_id": finding_id}
    return {"error": f"Finding '{finding_id}' not found in latest scan"}


@wrap_handler_errors
def suppress_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Mark a finding as false_positive."""
    finding_id = args.get("finding_id")
    reason = args.get("reason")
    if not finding_id or not reason:
        return error_response("finding_id and reason are required")
    result = sentinel_suppress_impl(
        project_path=project_path,
        finding_id=finding_id,
        reason=reason,
    )
    if "error" in result:
        return error_response(result["error"])
    return json.dumps(result)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def sentinel_status_impl(project_path: Path) -> dict[str, Any]:
    """Return infrastructure status: available agents, last scan info."""
    from dazzle.sentinel.agents import get_all_agents
    from dazzle.sentinel.store import FindingStore

    agents = get_all_agents()
    store = FindingStore(project_path)
    scans = store.list_scans(limit=1)

    return {
        "project_path": str(project_path),
        "agents": [{"id": a.agent_id.value, "heuristics": len(a.get_heuristics())} for a in agents],
        "last_scan": scans[0] if scans else None,
    }


@wrap_handler_errors
def status_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Return infrastructure status: available agents, last scan info."""
    return json.dumps(sentinel_status_impl(project_path), indent=2)


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------


def sentinel_history_impl(project_path: Path, limit: int) -> dict[str, Any]:
    """List recent scans. Returns scans dict."""
    from dazzle.sentinel.store import FindingStore

    store = FindingStore(project_path)
    scans = store.list_scans(limit=limit)
    return {"scans": scans, "count": len(scans)}


@wrap_handler_errors
def history_handler(project_path: Path, args: dict[str, Any]) -> str:
    """List recent scans."""
    return json.dumps(
        sentinel_history_impl(project_path=project_path, limit=args.get("limit", 10)),
        indent=2,
    )
