"""Format a :class:`FindingsReport` for human or agent consumption.

Markdown is the default — designed to paste straight into a Claude
conversation. Empty sections are omitted so the output stays short
when nothing's wrong.

JSON output uses Pydantic's standard serialisation; the schema is
pinned in ``docs/reference/perf-findings-schema.md``.
"""

from __future__ import annotations

from dazzle.perf.findings.types import FindingsReport


def render_json(report: FindingsReport) -> str:
    return report.model_dump_json(indent=2)


def render_markdown(report: FindingsReport) -> str:
    lines: list[str] = []
    header = f"# Perf report — {report.run_id}"
    if report.app_name:
        header += f" ({report.app_name})"
    lines.append(header)
    lines.append(f"Started: {report.started_at} — Ended: {report.ended_at or '(running)'}")
    lines.append("")

    if report.slow_endpoints:
        lines.append("## Slow endpoints")
        lines.append("| Route | Calls | Total (ms) | p95 (ms) |")
        lines.append("|---|---|---|---|")
        for e in report.slow_endpoints:
            lines.append(f"| `{e.route}` | {e.calls} | {e.total_ms:.1f} | {e.p95_ms:.1f} |")
        lines.append("")

    if report.slow_queries:
        lines.append("## Slow queries")
        lines.append("| Statement | Calls | Total (ms) |")
        lines.append("|---|---|---|")
        for q in report.slow_queries:
            lines.append(f"| `{q.statement}` | {q.calls} | {q.total_ms:.1f} |")
        lines.append("")

    if report.n_plus_one:
        lines.append("## Suspected N+1 patterns")
        lines.append("| Parent span | Child query | Repetitions |")
        lines.append("|---|---|---|")
        for n in report.n_plus_one:
            lines.append(f"| `{n.parent_span}` | `{n.child_statement}` | {n.repetitions} |")
        lines.append("")

    if report.slow_phases:
        lines.append("## Dazzle hot phases")
        lines.append("| Phase | Calls | Total (ms) | Max single (ms) |")
        lines.append("|---|---|---|---|")
        for p in report.slow_phases:
            lines.append(f"| `{p.name}` | {p.calls} | {p.total_ms:.1f} | {p.max_ms:.1f} |")
        lines.append("")

    if report.render_fanout:
        lines.append("## Render fan-out")
        lines.append("| Route | Region renders | Total (ms) |")
        lines.append("|---|---|---|")
        for r in report.render_fanout:
            lines.append(f"| `{r.route}` | {r.region_renders} | {r.total_ms:.1f} |")
        lines.append("")

    if report.boot_cost is not None:
        bc = report.boot_cost
        lines.append("## Boot cost")
        lines.append(
            f"- `dsl.parse`: {bc.parse_dsl_ms:.1f} ms · "
            f"`route.gen`: {bc.route_gen_ms:.1f} ms · "
            f"total: {bc.total_ms:.1f} ms"
        )
        lines.append("")

    if report.exceptions:
        lines.append("## Errors / exceptions")
        lines.append("| Span | Message | Count |")
        lines.append("|---|---|---|")
        for x in report.exceptions:
            lines.append(f"| `{x.span_name}` | {x.message} | {x.count} |")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
