"""Feedback operations behind the MCP ``feedback`` tool.

Calls the running Dazzle server's CRUD endpoints via httpx. The
``dazzle feedback`` CLI group is gone (ADR-0057, ship J); the MCP handler
(``mcp/server/handlers/feedback.py``) is the only caller.
"""

import json
from pathlib import Path
from typing import Any

import httpx

from dazzle.core.http_client import async_retrying_request
from dazzle.core.manifest import resolve_site_url


def _get_server_url(project_root: Path | None = None) -> str:
    """Read the running server URL from .dazzle/runtime.json.

    Uses api_port (FastAPI) since /feedbackreports is an API route.
    Falls back to the unified port (ui_port) for single-port deployments.
    """
    root = project_root or Path.cwd().resolve()
    runtime_file = root / ".dazzle" / "runtime.json"
    if runtime_file.exists():
        try:
            data = json.loads(runtime_file.read_text(encoding="utf-8"))
            if "api_url" in data:
                return str(data["api_url"])
            port = data.get("api_port", data.get("ui_port", 3000))
            return f"http://127.0.0.1:{port}"
        except (json.JSONDecodeError, KeyError):
            pass
    return resolve_site_url()


def _auth_cookies(project_root: Path | None = None) -> dict[str, Any]:
    """Read session cookie from .dazzle/session.json if available."""
    root = project_root or Path.cwd().resolve()
    session_file = root / ".dazzle" / "session.json"
    if session_file.exists():
        try:
            return dict(json.loads(session_file.read_text(encoding="utf-8")))
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

    async with httpx.AsyncClient(timeout=30.0) as client:  # DZ-HTTP-NORETRY  one-shot CLI
        resp = await async_retrying_request(
            client,
            "GET",
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
    async with httpx.AsyncClient(timeout=30.0) as client:  # DZ-HTTP-NORETRY  one-shot CLI
        resp = await async_retrying_request(
            client,
            "GET",
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

    async with httpx.AsyncClient(timeout=30.0) as client:  # DZ-HTTP-NORETRY  one-shot CLI
        resp = await async_retrying_request(
            client,
            "PUT",
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

    async with httpx.AsyncClient(timeout=30.0) as client:  # DZ-HTTP-NORETRY  one-shot CLI
        resp = await async_retrying_request(
            client,
            "PUT",
            f"{url}/feedbackreports/{report_id}",
            json=payload,
            cookies=_auth_cookies(project_root),
        )
        resp.raise_for_status()
        return dict(resp.json())
