"""
MCP handler for the Sentinel failure-mode detection tool.

Operations: scan, findings, suppress, status, history
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .common import extract_progress, handler_error_json, load_project_appspec

# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------


@handler_error_json
def scan_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Run sentinel scan against project DSL."""
    progress = extract_progress(args)
    t0 = time.monotonic()
    progress.log_sync("Loading project DSL...")
    appspec = load_project_appspec(project_path)
    from dazzle.sentinel.models import AgentId, ScanConfig, Severity

    agent_ids = None
    raw_agents = args.get("agents")
    if raw_agents:
        agent_ids = [AgentId(a) for a in raw_agents]

    severity = args.get("severity_threshold", "info")
    config = ScanConfig(
        agents=agent_ids,
        severity_threshold=Severity(severity),
        trigger=args.get("trigger", "manual"),
    )

    from dazzle.sentinel.orchestrator import ScanOrchestrator

    progress.log_sync("Running sentinel scan...")
    orch = ScanOrchestrator(project_path)
    result = orch.run_scan(appspec, config)

    detail = args.get("detail", "issues")
    wall_ms = (time.monotonic() - t0) * 1000

    if detail == "metrics":
        return json.dumps(
            {
                "status": "ok",
                "scan_id": result.scan_id,
                "summary": result.summary.model_dump(),
                "duration_ms": round(wall_ms, 1),
            },
            indent=2,
        )

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

    return json.dumps(out, indent=2)


# ---------------------------------------------------------------------------
# findings
# ---------------------------------------------------------------------------


@handler_error_json
def findings_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Get findings from latest or specific scan."""
    from dazzle.sentinel.store import FindingStore

    store = FindingStore(project_path)

    scan_id = args.get("scan_id")
    if scan_id:
        scan = store.load_scan(scan_id)
        if scan is None:
            return json.dumps({"error": f"Scan '{scan_id}' not found"})
        findings = scan.findings
    else:
        findings = store.load_latest_findings()

    agent_filter = args.get("agent")
    if agent_filter:
        findings = [f for f in findings if f.agent.value == agent_filter]

    severity_filter = args.get("severity")
    if severity_filter:
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        threshold = sev_order.get(severity_filter, 4)
        findings = [f for f in findings if sev_order.get(f.severity.value, 4) <= threshold]

    return json.dumps(
        {
            "findings": [f.model_dump() for f in findings],
            "count": len(findings),
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# suppress
# ---------------------------------------------------------------------------


@handler_error_json
def suppress_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Mark a finding as false_positive."""
    from dazzle.sentinel.store import FindingStore

    finding_id = args.get("finding_id")
    reason = args.get("reason")
    if not finding_id or not reason:
        return json.dumps({"error": "finding_id and reason are required"})

    store = FindingStore(project_path)
    ok = store.suppress_finding(finding_id, reason)
    if ok:
        return json.dumps({"status": "suppressed", "finding_id": finding_id})
    return json.dumps({"error": f"Finding '{finding_id}' not found in latest scan"})


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@handler_error_json
def status_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Return infrastructure status: available agents, last scan info."""
    from dazzle.sentinel.agents import get_all_agents
    from dazzle.sentinel.store import FindingStore

    agents = get_all_agents()
    store = FindingStore(project_path)
    scans = store.list_scans(limit=1)

    return json.dumps(
        {
            "project_path": str(project_path),
            "agents": [
                {"id": a.agent_id.value, "heuristics": len(a.get_heuristics())} for a in agents
            ],
            "last_scan": scans[0] if scans else None,
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------


@handler_error_json
def history_handler(project_path: Path, args: dict[str, Any]) -> str:
    """List recent scans."""
    from dazzle.sentinel.store import FindingStore

    limit = args.get("limit", 10)
    store = FindingStore(project_path)
    scans = store.list_scans(limit=limit)

    return json.dumps({"scans": scans, "count": len(scans)}, indent=2)
