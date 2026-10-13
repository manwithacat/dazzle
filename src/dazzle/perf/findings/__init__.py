"""Findings package — heuristics + formatters over the perf SQLite store."""

from __future__ import annotations

from dazzle.perf.findings.extractor import build_findings
from dazzle.perf.findings.render import render_json, render_markdown

__all__ = [
    "build_findings",
    "render_json",
    "render_markdown",
]
