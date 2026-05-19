"""Findings type tests — pin the agent-consumption schema."""

from __future__ import annotations

from dazzle.perf.findings.types import (
    BootCost,
    ExceptionFinding,
    Finding,
    FindingsReport,
    NPlusOne,
    RenderFanOut,
    SlowEndpoint,
    SlowPhase,
    SlowQuery,
)


def test_findings_report_round_trips_json() -> None:
    report = FindingsReport(
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
        boot_cost=BootCost(parse_dsl_ms=240.0, route_gen_ms=80.0, total_ms=400.0),
        exceptions=[
            ExceptionFinding(span_name="repo.aggregate", message="bad SQL", count=1),
        ],
    )
    payload = report.model_dump_json()
    revived = FindingsReport.model_validate_json(payload)
    assert revived == report


def test_finding_is_a_union_alias() -> None:
    f: Finding = SlowEndpoint(route="GET /", calls=1, total_ms=1.0, p95_ms=1.0)
    assert isinstance(f, SlowEndpoint)
