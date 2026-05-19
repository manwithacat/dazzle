"""Findings package — heuristics + formatters over the perf SQLite store."""

from __future__ import annotations

from dazzle.perf.findings.extractor import build_findings
from dazzle.perf.findings.render import render_json, render_markdown
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

__all__ = [
    "build_findings",
    "render_json",
    "render_markdown",
    "Finding",
    "FindingsReport",
    "BootCost",
    "ExceptionFinding",
    "NPlusOne",
    "RenderFanOut",
    "SlowEndpoint",
    "SlowPhase",
    "SlowQuery",
]
