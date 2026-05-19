"""Formatter tests — Markdown shape pinned for agent paste-in."""

from __future__ import annotations

from dazzle.perf.findings.render import render_json, render_markdown
from dazzle.perf.findings.types import (
    BootCost,
    ExceptionFinding,
    FindingsReport,
    NPlusOne,
    RenderFanOut,
    SlowEndpoint,
    SlowPhase,
    SlowQuery,
)


def _full_report() -> FindingsReport:
    return FindingsReport(
        run_id="r1",
        app_name="examples/simple_task",
        started_at="2026-05-19T20:00:00Z",
        ended_at="2026-05-19T20:00:05Z",
        slow_endpoints=[
            SlowEndpoint(route="GET /tasks", calls=12, total_ms=4200.0, p95_ms=380.0),
        ],
        slow_queries=[
            SlowQuery(statement="SELECT FROM task", calls=12, total_ms=1100.0),
        ],
        n_plus_one=[
            NPlusOne(parent_span="GET /tasks", child_statement="SELECT FROM user", repetitions=24),
        ],
        slow_phases=[
            SlowPhase(name="aggregate.build_sql", calls=8, total_ms=120.0, max_ms=30.0),
        ],
        render_fanout=[
            RenderFanOut(route="GET /tasks", region_renders=18, total_ms=600.0),
        ],
        boot_cost=BootCost(parse_dsl_ms=240.0, route_gen_ms=80.0, total_ms=320.0),
        exceptions=[
            ExceptionFinding(span_name="repo.aggregate", message="bad SQL", count=1),
        ],
    )


def test_render_markdown_contains_each_section() -> None:
    out = render_markdown(_full_report())
    assert "# Perf report — r1" in out
    assert "## Slow endpoints" in out
    assert "GET /tasks" in out
    assert "## Slow queries" in out
    assert "## Suspected N+1 patterns" in out
    assert "## Dazzle hot phases" in out
    assert "## Render fan-out" in out
    assert "## Boot cost" in out
    assert "## Errors / exceptions" in out


def test_render_markdown_omits_empty_sections() -> None:
    report = FindingsReport(
        run_id="r1",
        app_name=None,
        started_at="2026-05-19T20:00:00Z",
        ended_at=None,
    )
    out = render_markdown(report)
    assert "# Perf report — r1" in out
    assert "## Slow endpoints" not in out
    assert "## Suspected N+1 patterns" not in out


def test_render_json_round_trips() -> None:
    report = _full_report()
    payload = render_json(report)
    assert '"run_id": "r1"' in payload
    revived = FindingsReport.model_validate_json(payload)
    assert revived == report
