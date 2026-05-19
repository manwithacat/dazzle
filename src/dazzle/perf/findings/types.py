"""Findings schema — the agent-consumption contract.

JSON serialisation of :class:`FindingsReport` is the source of truth
that downstream tools (CLI `--format json`, MCP `perf.report`) emit.
The contract is documented in
``docs/reference/perf-findings-schema.md`` — when fields change here,
update that doc in the same commit.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SlowEndpoint(BaseModel):
    route: str
    calls: int
    total_ms: float
    p95_ms: float
    model_config = ConfigDict(frozen=True)


class SlowQuery(BaseModel):
    statement: str
    calls: int
    total_ms: float
    model_config = ConfigDict(frozen=True)


class NPlusOne(BaseModel):
    parent_span: str
    child_statement: str
    repetitions: int
    model_config = ConfigDict(frozen=True)


class SlowPhase(BaseModel):
    name: str
    calls: int
    total_ms: float
    max_ms: float
    model_config = ConfigDict(frozen=True)


class RenderFanOut(BaseModel):
    route: str
    region_renders: int
    total_ms: float
    model_config = ConfigDict(frozen=True)


class BootCost(BaseModel):
    parse_dsl_ms: float
    route_gen_ms: float
    total_ms: float
    model_config = ConfigDict(frozen=True)


class ExceptionFinding(BaseModel):
    span_name: str
    message: str
    count: int
    model_config = ConfigDict(frozen=True)


Finding = (
    SlowEndpoint | SlowQuery | NPlusOne | SlowPhase | RenderFanOut | BootCost | ExceptionFinding
)


class FindingsReport(BaseModel):
    run_id: str
    app_name: str | None
    started_at: str
    ended_at: str | None
    slow_endpoints: list[SlowEndpoint] = []
    slow_queries: list[SlowQuery] = []
    n_plus_one: list[NPlusOne] = []
    slow_phases: list[SlowPhase] = []
    render_fanout: list[RenderFanOut] = []
    boot_cost: BootCost | None = None
    exceptions: list[ExceptionFinding] = []
    model_config = ConfigDict(frozen=True)
