"""HTML report renderer for E2E journey testing results.

Phase 4 (v0.67.78): migrated from Jinja `reports/e2e_journey.html` to
inline Python rendering via stdlib `html.escape`. The self-contained
HTML document (including CSS) is emitted directly — no template engine,
no `jinja2` dependency. Closes #1041.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dazzle.agent.journey_models import AnalysisReport, JourneySession
from dazzle.render.html import esc as _esc

_CSS = """
:root {
  --bg: #1a1a2e;
  --bg-card: #16213e;
  --bg-card-alt: #0f3460;
  --text: #e0e0e0;
  --text-muted: #a0a0b0;
  --border: #2a2a4a;
  --pass: #2ecc71;
  --fail: #e74c3c;
  --partial: #f1c40f;
  --blocked: #e67e22;
  --dead-end: #9b59b6;
  --scope-leak: #e74c3c;
  --confusing: #f39c12;
  --nav-break: #e67e22;
  --timeout: #95a5a6;
  --critical: #e74c3c;
  --high: #e67e22;
  --medium: #f1c40f;
  --low: #3498db;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.6;
  padding: 2rem;
}
h1, h2, h3 { color: #fff; }
h1 { font-size: 1.8rem; margin-bottom: 0.5rem; }
h2 { font-size: 1.4rem; margin: 1.5rem 0 0.75rem; border-bottom: 1px solid var(--border); padding-bottom: 0.4rem; }
h3 { font-size: 1.1rem; margin: 1rem 0 0.5rem; }
.header { margin-bottom: 2rem; }
.header .meta { color: var(--text-muted); font-size: 0.9rem; }
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}
.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1rem;
  text-align: center;
}
.stat-card .value { font-size: 2rem; font-weight: 700; color: #fff; }
.stat-card .label { font-size: 0.85rem; color: var(--text-muted); }
.badge {
  display: inline-block;
  padding: 0.15rem 0.55rem;
  border-radius: 4px;
  font-size: 0.8rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.badge-pass { background: var(--pass); color: #000; }
.badge-fail { background: var(--fail); color: #fff; }
.badge-partial { background: var(--partial); color: #000; }
.badge-blocked { background: var(--blocked); color: #fff; }
.badge-dead_end, .badge-dead-end { background: var(--dead-end); color: #fff; }
.badge-scope_leak, .badge-scope-leak { background: var(--scope-leak); color: #fff; }
.badge-confusing { background: var(--confusing); color: #000; }
.badge-nav_break, .badge-nav-break { background: var(--nav-break); color: #fff; }
.badge-timeout { background: var(--timeout); color: #fff; }
.severity-critical { background: var(--critical); color: #fff; }
.severity-high { background: var(--high); color: #fff; }
.severity-medium { background: var(--medium); color: #000; }
.severity-low { background: var(--low); color: #fff; }
.verdict-counts {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin: 0.5rem 0;
}
.verdict-counts .badge { min-width: 3rem; text-align: center; }
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 0.75rem;
}
.card-title { font-weight: 600; margin-bottom: 0.3rem; }
.card-id { color: var(--text-muted); font-size: 0.85rem; font-family: monospace; }
details {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 1rem;
}
details > summary {
  padding: 0.75rem 1rem;
  cursor: pointer;
  font-weight: 600;
  font-size: 1.05rem;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
details > summary::before { content: "\\25b6"; font-size: 0.75rem; transition: transform 0.2s; }
details[open] > summary::before { transform: rotate(90deg); }
details > .content { padding: 0.5rem 1rem 1rem; }
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
  margin-top: 0.5rem;
}
th, td {
  text-align: left;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--border);
}
th { color: var(--text-muted); font-weight: 600; font-size: 0.8rem; text-transform: uppercase; }
tr:hover { background: rgba(255,255,255,0.03); }
.item-list { list-style: none; }
.item-list li { padding: 0.4rem 0; border-bottom: 1px solid var(--border); }
.item-list li:last-child { border-bottom: none; }
.empty-state {
  text-align: center;
  padding: 3rem;
  color: var(--text-muted);
  font-size: 1.1rem;
}
.rec-effort { text-transform: capitalize; }
.evidence-list { margin: 0.3rem 0 0 1.2rem; color: var(--text-muted); font-size: 0.85rem; }
.affected { font-size: 0.85rem; color: var(--text-muted); }
"""


def _render_session(session: JourneySession) -> str:
    persona = _esc(getattr(session, "persona", ""))
    verdict_counts = getattr(session, "verdict_counts", {}) or {}
    pass_count = int(verdict_counts.get("pass", 0) or 0)
    fail_count = int(verdict_counts.get("fail", 0) or 0)
    steps = list(getattr(session, "steps", None) or [])
    stories_covered = getattr(session, "stories_covered", 0)
    stories_attempted = getattr(session, "stories_attempted", 0)

    summary = (
        f"{persona}"
        f'<span class="badge badge-pass">'
        f"{pass_count} pass</span>"
        f'<span class="badge badge-fail">'
        f"{fail_count} fail</span>"
        f" &mdash; {len(steps)} steps, {stories_covered}/{stories_attempted} stories"
    )

    other_counts: list[str] = []
    for verdict, count in verdict_counts.items():
        if int(count or 0) <= 0:
            continue
        v_attr = _esc(verdict, quote=True)
        v_text = _esc(verdict)
        other_counts.append(f'<span class="badge badge-{v_attr}">{v_text}: {int(count)}</span>')

    rows: list[str] = []
    for step in steps:
        verdict_obj = getattr(step, "verdict", None)
        verdict_val = (
            getattr(verdict_obj, "value", str(verdict_obj)) if verdict_obj is not None else ""
        )
        rows.append(
            "<tr>"
            f"<td>{_esc(getattr(step, 'step_number', ''))}</td>"
            f"<td>{_esc(getattr(step, 'action', ''))}</td>"
            f"<td>{_esc(getattr(step, 'target', ''))}</td>"
            f'<td><span class="badge badge-{_esc(verdict_val, quote=True)}">'
            f"{_esc(verdict_val)}</span></td>"
            f"<td>{_esc(getattr(step, 'observation', ''))}</td>"
            "</tr>"
        )

    return (
        "<details>"
        f"<summary>{summary}</summary>"
        '<div class="content">'
        f'<div class="verdict-counts">{"".join(other_counts)}</div>'
        "<table><thead><tr>"
        "<th>#</th><th>Action</th><th>Target</th>"
        "<th>Verdict</th><th>Observation</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
        "</div></details>"
    )


def _render_cross_persona_pattern(pattern: Any) -> str:
    pid = _esc(getattr(pattern, "id", ""))
    title = _esc(getattr(pattern, "title", ""))
    severity = _esc(getattr(pattern, "severity", ""), quote=True)
    severity_text = _esc(getattr(pattern, "severity", ""))
    description = _esc(getattr(pattern, "description", ""))
    affected = ", ".join(_esc(p) for p in (getattr(pattern, "affected_personas", None) or []))
    recommendation = _esc(getattr(pattern, "recommendation", ""))

    evidence_html = ""
    evidence = list(getattr(pattern, "evidence", None) or [])
    if evidence:
        evidence_items = "".join(f"<li>{_esc(ev)}</li>" for ev in evidence)
        evidence_html = f'<ul class="evidence-list">{evidence_items}</ul>'

    return (
        '<div class="card">'
        f'<div class="card-id">{pid}</div>'
        f'<div class="card-title">{title}'
        f'<span class="badge severity-{severity}">{severity_text}</span></div>'
        f"<p>{description}</p>"
        f'<div class="affected">Affected: {affected}</div>'
        f"{evidence_html}"
        f'<p style="margin-top:0.5rem;"><strong>Recommendation:</strong> {recommendation}</p>'
        "</div>"
    )


def _render_dead_end(de: Any) -> str:
    return (
        "<li>"
        f'<span class="card-id">{_esc(getattr(de, "id", ""))}</span> '
        f"<strong>{_esc(getattr(de, 'page', ''))}</strong> "
        f"({_esc(getattr(de, 'persona', ''))})"
        f" — {_esc(getattr(de, 'description', ''))}"
        "</li>"
    )


def _render_nav_break(nb: Any) -> str:
    affected = ", ".join(_esc(p) for p in (getattr(nb, "affected_personas", None) or []))
    workaround = getattr(nb, "workaround", "") or ""
    workaround_html = f"<br><em>Workaround: {_esc(workaround)}</em>" if workaround else ""
    return (
        "<li>"
        f'<span class="card-id">{_esc(getattr(nb, "id", ""))}</span> '
        f"{_esc(getattr(nb, 'description', ''))} "
        f'<span class="affected">Affected: {affected}</span>'
        f"{workaround_html}"
        "</li>"
    )


def _render_recommendation_row(rec: Any) -> str:
    affected = ", ".join(_esc(e) for e in (getattr(rec, "affected_entities", None) or []))
    return (
        "<tr>"
        f"<td>{_esc(getattr(rec, 'priority', ''))}</td>"
        f"<td>{_esc(getattr(rec, 'title', ''))}</td>"
        f"<td>{_esc(getattr(rec, 'description', ''))}</td>"
        f'<td class="rec-effort">{_esc(getattr(rec, "effort", ""))}</td>'
        f"<td>{affected}</td>"
        "</tr>"
    )


def _render_html(sessions: list[JourneySession], analysis: AnalysisReport) -> str:
    """Inline mirror of the legacy `reports/e2e_journey.html` Jinja template."""
    run_id = _esc(getattr(analysis, "run_id", ""))
    dazzle_version = _esc(getattr(analysis, "dazzle_version", ""))
    deployment_url = _esc(getattr(analysis, "deployment_url", ""))
    personas_analysed = int(getattr(analysis, "personas_analysed", 0) or 0)
    total_steps = int(getattr(analysis, "total_steps", 0) or 0)
    total_stories = int(getattr(analysis, "total_stories", 0) or 0)
    verdict_counts = getattr(analysis, "verdict_counts", {}) or {}

    verdict_counts_html = "".join(
        f'<span class="badge badge-{_esc(v, quote=True)}">{_esc(v)}: {int(c or 0)}</span>'
        for v, c in verdict_counts.items()
    )

    sessions_html: str
    if sessions:
        sessions_html = f"<h2>Persona Sessions</h2>{''.join(_render_session(s) for s in sessions)}"
    else:
        sessions_html = '<div class="empty-state">No journey data</div>'

    cross_patterns = list(getattr(analysis, "cross_persona_patterns", None) or [])
    cross_html = ""
    if cross_patterns:
        cross_html = (
            "<h2>Cross-Persona Patterns</h2>"
            f"{''.join(_render_cross_persona_pattern(p) for p in cross_patterns)}"
        )

    dead_ends = list(getattr(analysis, "dead_ends", None) or [])
    dead_ends_html = ""
    if dead_ends:
        dead_ends_html = (
            "<h2>Dead Ends</h2>"
            f'<ul class="item-list">{"".join(_render_dead_end(d) for d in dead_ends)}</ul>'
        )

    nav_breaks = list(getattr(analysis, "nav_breaks", None) or [])
    nav_breaks_html = ""
    if nav_breaks:
        nav_breaks_html = (
            "<h2>Navigation Breaks</h2>"
            f'<ul class="item-list">{"".join(_render_nav_break(n) for n in nav_breaks)}</ul>'
        )

    recommendations = list(getattr(analysis, "recommendations", None) or [])
    recs_html = ""
    if recommendations:
        recs_html = (
            "<h2>Recommendations</h2>"
            "<table><thead><tr>"
            "<th>Priority</th><th>Title</th><th>Description</th>"
            "<th>Effort</th><th>Affected Entities</th>"
            "</tr></thead><tbody>"
            f"{''.join(_render_recommendation_row(r) for r in recommendations)}"
            "</tbody></table>"
        )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f"<title>E2E Journey Report — {run_id}</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n<body>\n"
        '<div class="header">'
        "<h1>E2E Journey Report</h1>"
        f'<div class="meta">'
        f"Run: <strong>{run_id}</strong> "
        f"&middot; Dazzle {dazzle_version} "
        f"&middot; {deployment_url}"
        "</div></div>\n"
        '<div class="summary-grid">'
        f'<div class="stat-card"><div class="value">{personas_analysed}</div>'
        '<div class="label">Personas Analysed</div></div>'
        f'<div class="stat-card"><div class="value">{total_steps}</div>'
        '<div class="label">Total Steps</div></div>'
        f'<div class="stat-card"><div class="value">{total_stories}</div>'
        '<div class="label">Total Stories</div></div>'
        f'<div class="stat-card"><div class="value">{int(verdict_counts.get("pass", 0) or 0)}</div>'
        '<div class="label">Passed</div></div>'
        f'<div class="stat-card"><div class="value">{int(verdict_counts.get("fail", 0) or 0)}</div>'
        '<div class="label">Failed</div></div>'
        "</div>\n"
        "<h2>Verdict Summary</h2>"
        f'<div class="verdict-counts">{verdict_counts_html}</div>\n'
        f"{sessions_html}"
        f"{cross_html}"
        f"{dead_ends_html}"
        f"{nav_breaks_html}"
        f"{recs_html}"
        "</body>\n</html>"
    )


def render_report(
    sessions: list[JourneySession],
    analysis: AnalysisReport,
    output_path: Path,
) -> None:
    """Render an E2E journey HTML report and write it to *output_path*."""
    html = _render_html(sessions, analysis)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
