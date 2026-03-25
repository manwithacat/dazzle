"""Shared feedback operations for CLI and MCP handler.

Calls the running Dazzle server's CRUD endpoints via httpx.
Both the CLI (``dazzle feedback``) and MCP handler (``feedback`` tool)
import from here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx


def _get_server_url(project_root: Path | None = None) -> str:
    """Read the running server URL from .dazzle/runtime.json.

    Uses api_port (FastAPI) since /feedbackreports is an API route.
    Falls back to the unified port (ui_port) for single-port deployments.
    """
    root = project_root or Path.cwd().resolve()
    runtime_file = root / ".dazzle" / "runtime.json"
    if runtime_file.exists():
        try:
            data = json.loads(runtime_file.read_text())
            if "api_url" in data:
                return str(data["api_url"])
            port = data.get("api_port", data.get("ui_port", 3000))
            return f"http://127.0.0.1:{port}"
        except (json.JSONDecodeError, KeyError):
            pass
    return "http://127.0.0.1:3000"


def _auth_cookies(project_root: Path | None = None) -> dict[str, Any]:
    """Read session cookie from .dazzle/session.json if available."""
    root = project_root or Path.cwd().resolve()
    session_file = root / ".dazzle" / "session.json"
    if session_file.exists():
        try:
            return dict(json.loads(session_file.read_text()))
        except (json.JSONDecodeError, KeyError):
            pass
    return {}


async def feedback_list(
    project_root: Path | None = None,
    *,
    status: str | None = None,
    category: str | None = None,
    severity: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List feedback reports with optional filters."""
    url = _get_server_url(project_root)
    params: dict[str, str | int] = {"page_size": limit}
    if status:
        params["status"] = status
    if category:
        params["category"] = category
    if severity:
        params["severity"] = severity

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{url}/feedbackreports",
            params=params,
            cookies=_auth_cookies(project_root),
        )
        resp.raise_for_status()
        return dict(resp.json())


async def feedback_get(
    report_id: str,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Get a single feedback report by ID."""
    url = _get_server_url(project_root)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{url}/feedbackreports/{report_id}",
            cookies=_auth_cookies(project_root),
        )
        resp.raise_for_status()
        return dict(resp.json())


async def feedback_triage(
    report_id: str,
    project_root: Path | None = None,
    *,
    agent_notes: str | None = None,
    agent_classification: str | None = None,
    assigned_to: str | None = None,
) -> dict[str, Any]:
    """Triage a feedback report (new -> triaged)."""
    url = _get_server_url(project_root)
    payload: dict[str, str] = {"status": "triaged"}
    if agent_notes:
        payload["agent_notes"] = agent_notes
    if agent_classification:
        payload["agent_classification"] = agent_classification
    if assigned_to:
        payload["assigned_to"] = assigned_to

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.put(
            f"{url}/feedbackreports/{report_id}",
            json=payload,
            cookies=_auth_cookies(project_root),
        )
        resp.raise_for_status()
        return dict(resp.json())


async def feedback_resolve(
    report_id: str,
    project_root: Path | None = None,
    *,
    agent_notes: str | None = None,
    resolved_by: str | None = None,
) -> dict[str, Any]:
    """Resolve a feedback report (triaged/in_progress -> resolved)."""
    url = _get_server_url(project_root)
    payload: dict[str, str] = {"status": "resolved"}
    if agent_notes:
        payload["agent_notes"] = agent_notes
    if resolved_by:
        payload["resolved_by"] = resolved_by

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.put(
            f"{url}/feedbackreports/{report_id}",
            json=payload,
            cookies=_auth_cookies(project_root),
        )
        resp.raise_for_status()
        return dict(resp.json())


async def feedback_delete(
    report_id: str,
    project_root: Path | None = None,
) -> bool:
    """Delete a feedback report. Returns True on success."""
    url = _get_server_url(project_root)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.delete(
            f"{url}/feedbackreports/{report_id}",
            cookies=_auth_cookies(project_root),
        )
        resp.raise_for_status()
        return True


async def feedback_stats(
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Compute feedback statistics by status, category, and severity."""
    data = await feedback_list(project_root, limit=1000)
    items = data.get("items", [])

    by_status: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_severity: dict[str, int] = {}

    for item in items:
        s = item.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1
        c = item.get("category", "unknown")
        by_category[c] = by_category.get(c, 0) + 1
        v = item.get("severity", "unknown")
        by_severity[v] = by_severity.get(v, 0) + 1

    return {
        "total": len(items),
        "by_status": by_status,
        "by_category": by_category,
        "by_severity": by_severity,
    }
