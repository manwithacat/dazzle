"""Activity Explorer — lightweight HTTP UI for browsing MCP activity history.

Serves a single-page HTML application backed by JSON API endpoints that
read from the ``activity_events`` and ``activity_sessions`` tables in the
KG SQLite database.

Usage::

    dazzle workshop --explore           # http://127.0.0.1:8877
    dazzle workshop --explore --port 9999
"""

from __future__ import annotations

import json
import sqlite3
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from dazzle.core.paths import project_kg_db


def _open_db(db_path: Path) -> sqlite3.Connection:
    """Open the KG database read-only."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def _json_response(handler: BaseHTTPRequestHandler, data: Any, status: int = 200) -> None:
    body = json.dumps(data, indent=2, default=str).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _html_response(handler: BaseHTTPRequestHandler, html: str) -> None:
    body = html.encode()
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _make_handler_class(db_path: Path) -> type[BaseHTTPRequestHandler]:
    """Create a request handler class with the DB path baked in."""

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            pass  # Suppress default access logging

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            qs = parse_qs(parsed.query)

            if path == "/":
                _html_response(self, _EXPLORER_HTML)
            elif path == "/api/sessions":
                self._handle_sessions()
            elif path == "/api/events":
                self._handle_events(qs)
            elif path == "/api/stats":
                self._handle_stats(qs)
            elif path == "/api/invocations":
                self._handle_invocations(qs)
            else:
                self.send_error(404)

        def _handle_sessions(self) -> None:
            try:
                conn = _open_db(db_path)
                try:
                    rows = conn.execute(
                        "SELECT * FROM activity_sessions ORDER BY started_at DESC LIMIT 50"
                    ).fetchall()
                    _json_response(self, _rows_to_dicts(rows))
                finally:
                    conn.close()
            except Exception as e:
                _json_response(self, {"error": str(e)}, 500)

        def _handle_events(self, qs: dict[str, list[str]]) -> None:
            session_id = qs.get("session_id", [None])[0]
            since_id = int(qs.get("since_id", ["0"])[0])
            limit = min(int(qs.get("limit", ["100"])[0]), 500)

            conditions = ["id > ?"]
            params: list[Any] = [since_id]
            if session_id:
                conditions.append("session_id = ?")
                params.append(session_id)
            params.append(limit)

            try:
                conn = _open_db(db_path)
                try:
                    rows = conn.execute(
                        f"SELECT * FROM activity_events WHERE {' AND '.join(conditions)} "
                        f"ORDER BY id ASC LIMIT ?",
                        params,
                    ).fetchall()
                    _json_response(self, _rows_to_dicts(rows))
                finally:
                    conn.close()
            except Exception as e:
                _json_response(self, {"error": str(e)}, 500)

        def _handle_stats(self, qs: dict[str, list[str]]) -> None:
            session_id = qs.get("session_id", [None])[0]
            where = ""
            params: list[Any] = []
            if session_id:
                where = "WHERE session_id = ?"
                params = [session_id]

            tool_end_where = (
                f"WHERE event_type = 'tool_end'{' AND session_id = ?' if session_id else ''}"
            )
            tool_end_params = [session_id] if session_id else []

            try:
                conn = _open_db(db_path)
                try:
                    total = conn.execute(
                        f"SELECT COUNT(*) FROM activity_events {where}", params
                    ).fetchone()[0]
                    ok = conn.execute(
                        f"SELECT COUNT(*) FROM activity_events {tool_end_where} AND success = 1",
                        tool_end_params,
                    ).fetchone()[0]
                    err = conn.execute(
                        f"SELECT COUNT(*) FROM activity_events {tool_end_where} AND success = 0",
                        tool_end_params,
                    ).fetchone()[0]
                    by_tool = _rows_to_dicts(
                        conn.execute(
                            f"""
                            SELECT tool,
                                   COUNT(*) AS call_count,
                                   SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS error_count,
                                   AVG(duration_ms) AS avg_duration_ms,
                                   MAX(duration_ms) AS max_duration_ms
                            FROM activity_events
                            {tool_end_where}
                            GROUP BY tool ORDER BY call_count DESC
                            """,
                            tool_end_params,
                        ).fetchall()
                    )
                    _json_response(
                        self,
                        {
                            "total_events": total,
                            "tool_calls_ok": ok,
                            "tool_calls_error": err,
                            "by_tool": by_tool,
                        },
                    )
                finally:
                    conn.close()
            except Exception as e:
                _json_response(self, {"error": str(e)}, 500)

        def _handle_invocations(self, qs: dict[str, list[str]]) -> None:
            tool = qs.get("tool", [None])[0]
            limit = min(int(qs.get("limit", ["50"])[0]), 200)
            conditions: list[str] = []
            params: list[Any] = []
            if tool:
                conditions.append("tool_name = ?")
                params.append(tool)
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            params.append(limit)

            try:
                conn = _open_db(db_path)
                try:
                    rows = conn.execute(
                        f"SELECT * FROM tool_invocations {where} ORDER BY created_at DESC LIMIT ?",
                        params,
                    ).fetchall()
                    _json_response(self, _rows_to_dicts(rows))
                finally:
                    conn.close()
            except Exception as e:
                _json_response(self, {"error": str(e)}, 500)

    return _Handler


def run_explorer(
    project_dir: Path,
    *,
    port: int = 8877,
    open_browser: bool = True,
) -> None:
    """Start the explorer HTTP server. Blocks until Ctrl-C."""
    from rich.console import Console

    console = Console()
    db_path = project_kg_db(project_dir)

    if not db_path.exists():
        console.print(f"[red]Database not found:[/red] {db_path}")
        console.print("[dim]Start the MCP server first to create the database.[/dim]")
        return

    handler_class = _make_handler_class(db_path)
    server = HTTPServer(("127.0.0.1", port), handler_class)

    url = f"http://127.0.0.1:{port}"
    console.print(f"[bold yellow]\u2692[/bold yellow]  Activity Explorer at [cyan]{url}[/cyan]")
    console.print("[dim]Press Ctrl-C to stop[/dim]\n")

    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        console.print("\n[dim]Explorer stopped.[/dim]")


# ── Embedded HTML UI ─────────────────────────────────────────────────────────

_EXPLORER_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dazzle Activity Explorer</title>
<style>
  :root {
    --bg: #1a1a2e; --surface: #16213e; --primary: #0f3460;
    --accent: #e94560; --text: #eee; --dim: #888; --ok: #4caf50;
    --err: #f44336; --warn: #ff9800; --border: #333;
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family: 'Menlo','Monaco','Courier New',monospace; font-size:13px;
         background:var(--bg); color:var(--text); padding:16px; }
  h1 { font-size:18px; margin-bottom:4px; }
  h2 { font-size:14px; margin:12px 0 6px; color:var(--accent); }
  .header { display:flex; align-items:baseline; gap:12px; margin-bottom:12px;
            border-bottom:1px solid var(--border); padding-bottom:8px; }
  .header small { color:var(--dim); }
  select { background:var(--surface); color:var(--text); border:1px solid var(--border);
           padding:4px 8px; border-radius:4px; font-family:inherit; font-size:12px; }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:12px; }
  .card { background:var(--surface); border:1px solid var(--border);
          border-radius:6px; padding:10px; }
  .stat { font-size:22px; font-weight:bold; }
  .stat.ok { color:var(--ok); }
  .stat.err { color:var(--err); }
  .stat-label { font-size:11px; color:var(--dim); text-transform:uppercase; }
  .bar-row { display:flex; align-items:center; gap:6px; margin:3px 0; }
  .bar-label { width:100px; text-align:right; font-size:11px; color:var(--dim);
               overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .bar-track { flex:1; height:14px; background:var(--primary); border-radius:3px;
               overflow:hidden; position:relative; }
  .bar-fill { height:100%; border-radius:3px; }
  .bar-fill.ok { background:var(--ok); }
  .bar-fill.err { background:var(--err); }
  .bar-val { width:50px; font-size:11px; color:var(--dim); }
  table { width:100%; border-collapse:collapse; font-size:12px; }
  th { text-align:left; color:var(--dim); font-weight:normal; padding:4px 8px;
       border-bottom:1px solid var(--border); }
  td { padding:4px 8px; border-bottom:1px solid #222; }
  tr.ok td:nth-child(2) { color:var(--ok); }
  tr.err td:nth-child(2) { color:var(--err); }
  .ts { color:var(--dim); }
  .dur { color:var(--dim); }
  .error-msg { color:var(--err); font-size:11px; max-width:300px;
               overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .auto-label { font-size:10px; color:var(--dim); }
  @media (max-width:600px) { .grid { grid-template-columns:1fr; } }
</style>
</head>
<body>

<div class="header">
  <h1>&#9874; Dazzle Activity Explorer</h1>
  <small>Session:</small>
  <select id="session-select"><option value="">Loading...</option></select>
  <small class="auto-label" id="auto-label"></small>
</div>

<div class="grid">
  <div class="card"><div class="stat-label">Total Events</div><div class="stat" id="s-total">-</div></div>
  <div class="card"><div class="stat-label">Success Rate</div><div class="stat ok" id="s-rate">-</div></div>
  <div class="card"><div class="stat-label">OK Calls</div><div class="stat ok" id="s-ok">-</div></div>
  <div class="card"><div class="stat-label">Errors</div><div class="stat err" id="s-err">-</div></div>
</div>

<h2>Tool Usage</h2>
<div id="tool-bars" class="card"></div>

<h2>Timeline</h2>
<div class="card" style="max-height:400px;overflow-y:auto;">
<table>
  <thead><tr><th>Time</th><th>Status</th><th>Tool</th><th>Duration</th><th>Details</th></tr></thead>
  <tbody id="timeline"></tbody>
</table>
</div>

<h2>Errors</h2>
<div class="card" style="max-height:250px;overflow-y:auto;">
<table>
  <thead><tr><th>Time</th><th>Tool</th><th>Error</th></tr></thead>
  <tbody id="errors"></tbody>
</table>
</div>

<script>
const $ = s => document.querySelector(s);
let sid = null, pollId = null, lastId = 0;

async function loadSessions() {
  const res = await fetch('/api/sessions');
  const sessions = await res.json();
  const sel = $('#session-select');
  sel.innerHTML = '<option value="">(all sessions)</option>';
  sessions.forEach((s,i) => {
    const d = new Date(s.started_at * 1000);
    const label = (s.project_name || '?') + ' ' + d.toLocaleString();
    const opt = document.createElement('option');
    opt.value = s.id; opt.textContent = label;
    if (i === 0) opt.selected = true;
    sel.appendChild(opt);
  });
  if (sessions.length) { sid = sessions[0].id; }
  sel.onchange = () => { sid = sel.value || null; lastId = 0; refresh(); };
  refresh();
}

async function refresh() {
  await Promise.all([loadStats(), loadEvents()]);
}

async function loadStats() {
  const url = sid ? '/api/stats?session_id=' + sid : '/api/stats';
  const res = await fetch(url);
  const s = await res.json();
  $('#s-total').textContent = s.total_events;
  $('#s-ok').textContent = s.tool_calls_ok;
  $('#s-err').textContent = s.tool_calls_error;
  const total = s.tool_calls_ok + s.tool_calls_error;
  $('#s-rate').textContent = total ? ((s.tool_calls_ok / total * 100).toFixed(1) + '%') : '-';
  renderBars(s.by_tool || []);
}

function renderBars(tools) {
  const el = $('#tool-bars');
  if (!tools.length) { el.innerHTML = '<span style="color:var(--dim)">No data</span>'; return; }
  const max = Math.max(...tools.map(t => t.call_count));
  el.innerHTML = tools.map(t => {
    const okW = (t.call_count - t.error_count) / max * 100;
    const errW = t.error_count / max * 100;
    const avg = t.avg_duration_ms ? Math.round(t.avg_duration_ms) + 'ms' : '';
    return '<div class="bar-row">' +
      '<span class="bar-label">' + t.tool + '</span>' +
      '<div class="bar-track"><div class="bar-fill ok" style="width:' + okW + '%"></div>' +
      '<div class="bar-fill err" style="width:' + errW + '%;position:absolute;right:0;top:0"></div></div>' +
      '<span class="bar-val">' + t.call_count + ' / ' + avg + '</span></div>';
  }).join('');
}

async function loadEvents() {
  let url = '/api/events?since_id=0&limit=200';
  if (sid) url += '&session_id=' + sid;
  const res = await fetch(url);
  const events = await res.json();
  if (events.length) lastId = events[events.length-1].id;

  const tb = $('#timeline');
  const eb = $('#errors');
  tb.innerHTML = ''; eb.innerHTML = '';

  const toolEnds = events.filter(e => e.event_type === 'tool_end');
  toolEnds.reverse().forEach(e => {
    const ok = e.success;
    const cls = ok ? 'ok' : 'err';
    const ts = (e.ts||'').substring(11,19);
    const label = e.operation ? e.tool + '.' + e.operation : e.tool;
    const dur = e.duration_ms != null ? Math.round(e.duration_ms) + 'ms' : '';
    const detail = ok ? '' : '<span class="error-msg">' + (e.error||'') + '</span>';
    tb.innerHTML += '<tr class="' + cls + '"><td class="ts">' + ts + '</td><td>' +
      (ok ? '&#10004;' : '&#10008;') + '</td><td>' + label + '</td><td class="dur">' +
      dur + '</td><td>' + detail + '</td></tr>';
  });

  const errs = events.filter(e => e.event_type === 'tool_end' && !e.success);
  errs.reverse().forEach(e => {
    const ts = (e.ts||'').substring(11,19);
    const label = e.operation ? e.tool + '.' + e.operation : e.tool;
    eb.innerHTML += '<tr><td class="ts">' + ts + '</td><td>' + label +
      '</td><td class="error-msg">' + (e.error||'failed') + '</td></tr>';
  });

  if (!toolEnds.length) tb.innerHTML = '<tr><td colspan="5" style="color:var(--dim)">No events yet</td></tr>';
  if (!errs.length) eb.innerHTML = '<tr><td colspan="3" style="color:var(--dim)">No errors</td></tr>';
}

async function poll() {
  let url = '/api/events?since_id=' + lastId + '&limit=50';
  if (sid) url += '&session_id=' + sid;
  const res = await fetch(url);
  const events = await res.json();
  if (events.length) { lastId = events[events.length-1].id; refresh(); }
}

loadSessions();
setInterval(poll, 2000);
</script>
</body>
</html>
"""
