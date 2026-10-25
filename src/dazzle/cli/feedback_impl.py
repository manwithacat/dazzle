"""Feedback operations behind the MCP ``feedback`` tool.

Calls a Dazzle server's ``/feedbackreports`` endpoints via httpx. The
``dazzle feedback`` CLI group is gone (ADR-0057, ship J); the MCP handler
(``mcp/server/handlers/feedback.py``) is the only caller.

Target resolution (#1854):

* ``DAZZLE_FEEDBACK_URL`` — base URL of the server to read; wins over
  ``.dazzle/runtime.json`` (the locally running ``dazzle serve``). This is
  how an agent reads the review notes left on a *deployed* app.
* ``DAZZLE_FEEDBACK_COOKIE`` — one session cookie as ``name=value``; wins
  over ``.dazzle/session.json``.
"""

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

from dazzle.core.http_client import async_retrying_request
from dazzle.core.manifest import resolve_site_url

FEEDBACK_URL_ENV = "DAZZLE_FEEDBACK_URL"
FEEDBACK_COOKIE_ENV = "DAZZLE_FEEDBACK_COOKIE"

_JSON_FIELDS = ("anchor", "context")
_SUMMARY_DESCRIPTION_CHARS = 240
_SUMMARY_LATEST = 3


def _get_server_url(project_root: Path | None = None) -> str:
    """Resolve the server base URL.

    ``DAZZLE_FEEDBACK_URL`` wins; otherwise ``.dazzle/runtime.json`` (api_url,
    else api_port / ui_port) and finally the manifest's site URL.
    """
    remote = os.environ.get(FEEDBACK_URL_ENV, "").strip()
    if remote:
        return remote.rstrip("/")
    root = project_root or Path.cwd().resolve()
    runtime_file = root / ".dazzle" / "runtime.json"
    if runtime_file.exists():
        try:
            data = json.loads(runtime_file.read_text(encoding="utf-8"))
            if "api_url" in data:
                return str(data["api_url"]).rstrip("/")
            port = data.get("api_port", data.get("ui_port", 3000))
            return f"http://127.0.0.1:{port}"
        except (json.JSONDecodeError, KeyError):
            pass
    return resolve_site_url()


def _auth_cookies(project_root: Path | None = None) -> dict[str, Any]:
    """Resolve the session cookie.

    ``DAZZLE_FEEDBACK_COOKIE`` (``name=value``) wins; otherwise the cookie
    jar in ``.dazzle/session.json``.
    """
    env_cookie = os.environ.get(FEEDBACK_COOKIE_ENV, "").strip()
    if env_cookie:
        name, sep, value = env_cookie.partition("=")
        if sep and name.strip():
            return {name.strip(): value.strip()}
    root = project_root or Path.cwd().resolve()
    session_file = root / ".dazzle" / "session.json"
    if session_file.exists():
        try:
            return dict(json.loads(session_file.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, KeyError):
            pass
    return {}


def _client(cookies: dict[str, Any]) -> httpx.AsyncClient:
    """One-shot client carrying the session cookie.

    Tests swap this for one on an ``httpx.MockTransport``.
    """
    return httpx.AsyncClient(timeout=30.0, cookies=cookies)  # DZ-HTTP-NORETRY  one-shot CLI


def _parse_json_field(value: Any) -> Any:
    """Return ``anchor`` / ``context`` as an object.

    Newer servers hand back JSON objects; older ones a string holding JSON.
    A string that is not JSON is returned unchanged.
    """
    if isinstance(value, str):
        text = value.strip()
        if text[:1] in ("{", "["):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return value
    return value


def _parse_report(row: dict[str, Any]) -> dict[str, Any]:
    for key in _JSON_FIELDS:
        if key in row:
            row[key] = _parse_json_field(row[key])
    return row


def _normalise_csv(value: str | None) -> str | None:
    """``"new, triaged"`` → ``"new,triaged"``; empty → ``None``."""
    if not value:
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return ",".join(parts) or None


async def _fetch_reports(
    project_root: Path | None,
    params: dict[str, str | int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """GET /feedbackreports → (parsed items, envelope).

    The envelope is ``{items, total, page, page_size}``; a server that
    returns a bare list is wrapped into the same shape.
    """
    url = _get_server_url(project_root)
    async with _client(_auth_cookies(project_root)) as client:
        resp = await async_retrying_request(
            client,
            "GET",
            f"{url}/feedbackreports",
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()
    if isinstance(data, list):
        data = {"items": data, "total": len(data), "page": 1, "page_size": len(data)}
    items = [_parse_report(dict(row)) for row in data.get("items") or []]
    data["items"] = items
    return items, dict(data)


def _group_by_review_session(items: list[dict[str, Any]], total: int) -> dict[str, Any] | None:
    """Group by ``review_session`` when any item carries one; else ``None``."""
    if not any(item.get("review_session") for item in items):
        return None
    sessions: dict[str, list[dict[str, Any]]] = {}
    ungrouped: list[dict[str, Any]] = []
    for item in items:
        key = item.get("review_session")
        if key:
            sessions.setdefault(str(key), []).append(item)
        else:
            ungrouped.append(item)
    return {
        "sessions": [
            {"review_session": key, "count": len(rows), "items": rows}
            for key, rows in sessions.items()
        ],
        "ungrouped": ungrouped,
        "total": total,
    }


async def feedback_list(
    project_root: Path | None = None,
    *,
    status: str | None = None,
    category: str | None = None,
    severity: str | None = None,
    limit: int = 20,
    since: str | None = None,
    surface: str | None = None,
    review_session: str | None = None,
    page_url: str | None = None,
) -> dict[str, Any]:
    """List feedback reports with optional filters.

    ``status`` is a comma list (``"new,triaged"``); ``since`` is ISO 8601
    (``created_at >=``). When any returned report carries a
    ``review_session`` the result is grouped:
    ``{"sessions": [{"review_session", "count", "items"}], "ungrouped": [...], "total"}``;
    otherwise the server envelope ``{items, total, page, page_size}`` is
    returned with ``anchor`` / ``context`` parsed on every item.
    """
    filters: dict[str, str | None] = {
        "status": _normalise_csv(status),
        "category": category,
        "severity": severity,
        "surface": surface,
        "review_session": review_session,
        "page_url": page_url,
        "since": since,
    }
    params: dict[str, str | int] = {"page_size": limit}
    params.update({k: v for k, v in filters.items() if v})
    items, envelope = await _fetch_reports(project_root, params)
    total = int(envelope.get("total", len(items)) or 0)
    grouped = _group_by_review_session(items, total)
    return grouped if grouped is not None else envelope


async def feedback_get(
    report_id: str,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Get a single feedback report by ID, with ``anchor`` / ``context`` parsed."""
    url = _get_server_url(project_root)
    async with _client(_auth_cookies(project_root)) as client:
        resp = await async_retrying_request(
            client,
            "GET",
            f"{url}/feedbackreports/{report_id}",
        )
        resp.raise_for_status()
        return _parse_report(dict(resp.json()))


def _surface_of(item: dict[str, Any]) -> str:
    surface = item.get("surface")
    if not surface:
        context = item.get("context")
        if isinstance(context, dict):
            surface = context.get("surface")
    return str(surface) if surface else "(no surface)"


def _latest(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    newest = sorted(items, key=lambda i: str(i.get("created_at") or ""), reverse=True)
    out: list[dict[str, Any]] = []
    for item in newest[:_SUMMARY_LATEST]:
        text = str(item.get("description") or "")
        if len(text) > _SUMMARY_DESCRIPTION_CHARS:
            text = text[: _SUMMARY_DESCRIPTION_CHARS - 1] + "…"
        out.append(
            {
                "id": item.get("id"),
                "severity": item.get("severity"),
                "category": item.get("category"),
                "status": item.get("status"),
                "created_at": item.get("created_at"),
                "review_session": item.get("review_session"),
                "description": text,
            }
        )
    return out


def summarise_reports(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group reports by surface, then severity: counts and the newest three notes.

    Surfaces are ordered by count (desc) then name; ``by_severity`` likewise.
    """
    by_surface: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_surface.setdefault(_surface_of(item), []).append(item)
    surfaces: list[dict[str, Any]] = []
    for name, rows in by_surface.items():
        counts = Counter(str(r.get("severity") or "unknown") for r in rows)
        surfaces.append(
            {
                "surface": name,
                "count": len(rows),
                "by_severity": dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))),
                "latest": _latest(rows),
            }
        )
    surfaces.sort(key=lambda s: (-s["count"], s["surface"]))
    return surfaces


async def feedback_summarise(
    project_root: Path | None = None,
    *,
    status: str | None = "new,triaged",
    since: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Summarise open notes: grouped by surface then severity.

    Returns ``{"status", "since", "total", "fetched", "surfaces": [{"surface",
    "count", "by_severity": {sev: n}, "latest": [three newest notes]}]}``.
    ``total`` is the server's count; ``fetched`` is how many this summary
    covers (raise ``limit`` when they differ).
    """
    status = _normalise_csv(status)
    params: dict[str, str | int] = {"page_size": limit}
    if status:
        params["status"] = status
    if since:
        params["since"] = since
    items, envelope = await _fetch_reports(project_root, params)
    return {
        "status": status,
        "since": since,
        "total": int(envelope.get("total", len(items)) or 0),
        "fetched": len(items),
        "surfaces": summarise_reports(items),
    }


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

    async with _client(_auth_cookies(project_root)) as client:
        resp = await async_retrying_request(
            client,
            "PUT",
            f"{url}/feedbackreports/{report_id}",
            json=payload,
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

    async with _client(_auth_cookies(project_root)) as client:
        resp = await async_retrying_request(
            client,
            "PUT",
            f"{url}/feedbackreports/{report_id}",
            json=payload,
        )
        resp.raise_for_status()
        return dict(resp.json())
