"""Findings formatters (skeleton — implemented in Task 15)."""

from __future__ import annotations

from dazzle.perf.findings.types import FindingsReport


def render_markdown(report: FindingsReport) -> str:
    raise NotImplementedError


def render_json(report: FindingsReport) -> str:
    return report.model_dump_json(indent=2)
