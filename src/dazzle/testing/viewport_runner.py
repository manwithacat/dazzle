"""Playwright-based viewport assertion runner.

Launches a headless (or headed) Chromium browser, iterates over the
viewport matrix, and checks computed CSS properties against expected values.

Separate from :mod:`dazzle.testing.e2e_runner` — viewport assertions have no
flows, steps, fixtures, or state.  They assert CSS properties only.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dazzle.testing.viewport import (
    VIEWPORT_MATRIX,
    ComponentPattern,
    ViewportAssertionResult,
    ViewportReport,
    _matches,
)

# ---------------------------------------------------------------------------
# Options / result types
# ---------------------------------------------------------------------------


@dataclass
class ViewportRunOptions:
    """Configuration for a viewport assertion run."""

    headless: bool = True
    viewports: list[str] | None = None  # Keys from VIEWPORT_MATRIX; None → all
    base_url: str = "http://localhost:3000"
    timeout: int = 10_000


@dataclass
class ViewportRunResult:
    """Top-level result of a viewport assertion run."""

    project_name: str
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    reports: list[ViewportReport] = field(default_factory=list)
    total_assertions: int = 0
    total_passed: int = 0
    total_failed: int = 0
    error: str | None = None

    def to_json(self) -> str:
        """Serialise the run result to JSON."""
        return json.dumps(
            {
                "project_name": self.project_name,
                "started_at": self.started_at.isoformat(),
                "completed_at": self.completed_at.isoformat() if self.completed_at else None,
                "total_assertions": self.total_assertions,
                "total_passed": self.total_passed,
                "total_failed": self.total_failed,
                "error": self.error,
                "reports": [
                    {
                        "surface_or_page": r.surface_or_page,
                        "viewport": r.viewport,
                        "viewport_size": r.viewport_size,
                        "passed": r.passed,
                        "failed": r.failed,
                        "duration_ms": r.duration_ms,
                        "results": [
                            {
                                "selector": res.assertion.selector,
                                "property": res.assertion.property,
                                "expected": res.assertion.expected,
                                "actual": res.actual,
                                "passed": res.passed,
                                "description": res.assertion.description,
                                "error": res.error,
                            }
                            for res in r.results
                        ],
                    }
                    for r in self.reports
                ],
            },
            indent=2,
        )

    def to_markdown(self) -> str:
        """Render a human-friendly markdown summary."""
        lines: list[str] = []
        status = "PASS" if self.total_failed == 0 else "FAIL"
        lines.append(f"# Viewport Assertion Report — {status}")
        lines.append("")
        lines.append(f"**{self.total_passed}/{self.total_assertions}** assertions passed")
        if self.error:
            lines.append(f"\n> Error: {self.error}")
        lines.append("")

        for report in self.reports:
            marker = "+" if report.failed == 0 else "-"
            lines.append(
                f"## [{marker}] {report.surface_or_page} @ {report.viewport} "
                f"({report.viewport_size['width']}x{report.viewport_size['height']})"
            )
            for res in report.results:
                icon = "pass" if res.passed else "FAIL"
                lines.append(f"  [{icon}] {res.assertion.description}")
                if not res.passed:
                    lines.append(f"         expected={res.assertion.expected}  actual={res.actual}")
                    if res.error:
                        lines.append(f"         error: {res.error}")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# JavaScript evaluation helper
# ---------------------------------------------------------------------------

_JS_BATCH_EVAL = """
(specs) => specs.map(s => {
    const el = document.querySelector(s.selector);
    if (!el) return { selector: s.selector, property: s.property, actual: null };
    const style = window.getComputedStyle(el);
    return { selector: s.selector, property: s.property,
             actual: style.getPropertyValue(s.property) };
})
""".strip()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class ViewportRunner:
    """Run viewport assertions using Playwright's synchronous API."""

    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path

    def run(
        self,
        patterns: dict[str, list[ComponentPattern]],
        options: ViewportRunOptions | None = None,
    ) -> ViewportRunResult:
        """Execute viewport assertions across the matrix.

        Parameters
        ----------
        patterns:
            ``{page_path: [ComponentPattern, ...]}`` — typically produced by
            :func:`~dazzle.testing.viewport.derive_patterns_from_appspec`.
        options:
            Run configuration.  Defaults to headless with all viewports.

        Returns
        -------
        ViewportRunResult
            Aggregated report with pass/fail for every assertion.
        """
        if options is None:
            options = ViewportRunOptions()

        result = ViewportRunResult(
            project_name=self.project_path.name,
        )

        viewports_to_test = options.viewports or list(VIEWPORT_MATRIX.keys())

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            result.error = (
                "playwright is not installed. "
                "Run: pip install playwright && playwright install chromium"
            )
            result.completed_at = datetime.now(UTC)
            return result

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=options.headless)
                try:
                    self._run_matrix(browser, patterns, viewports_to_test, options, result)
                finally:
                    browser.close()
        except Exception as exc:
            result.error = str(exc)

        result.completed_at = datetime.now(UTC)
        return result

    def _run_matrix(
        self,
        browser: Any,
        patterns: dict[str, list[ComponentPattern]],
        viewports: list[str],
        options: ViewportRunOptions,
        result: ViewportRunResult,
    ) -> None:
        """Iterate viewports × pages and evaluate assertions."""
        for vp_name in viewports:
            vp_size = VIEWPORT_MATRIX.get(vp_name)
            if vp_size is None:
                continue

            context = browser.new_context(
                viewport={"width": vp_size["width"], "height": vp_size["height"]}
            )
            page = context.new_page()
            page.set_default_timeout(options.timeout)

            try:
                for page_path, pattern_list in patterns.items():
                    # Collect assertions relevant to this viewport
                    assertions_for_page = []
                    for pattern in pattern_list:
                        for assertion in pattern.assertions:
                            if assertion.viewport == vp_name:
                                assertions_for_page.append(assertion)

                    if not assertions_for_page:
                        continue

                    url = f"{options.base_url.rstrip('/')}{page_path}"
                    t0 = time.monotonic()
                    page.goto(url, wait_until="networkidle")

                    # Batch evaluate computed styles
                    specs = [
                        {"selector": a.selector, "property": a.property}
                        for a in assertions_for_page
                    ]
                    raw_results: list[dict[str, Any]] = page.evaluate(_JS_BATCH_EVAL, specs)

                    duration_ms = (time.monotonic() - t0) * 1000

                    assertion_results: list[ViewportAssertionResult] = []
                    for assertion, raw in zip(assertions_for_page, raw_results, strict=True):
                        actual = raw.get("actual")
                        passed = _matches(assertion.expected, actual)
                        assertion_results.append(
                            ViewportAssertionResult(
                                assertion=assertion,
                                actual=actual,
                                passed=passed,
                                error=None
                                if passed
                                else (
                                    "Element not found"
                                    if actual is None
                                    else f"Expected {assertion.expected!r}, got {actual!r}"
                                ),
                            )
                        )

                    passed_count = sum(1 for r in assertion_results if r.passed)
                    failed_count = len(assertion_results) - passed_count

                    report = ViewportReport(
                        surface_or_page=page_path,
                        viewport=vp_name,
                        viewport_size=vp_size,
                        results=assertion_results,
                        passed=passed_count,
                        failed=failed_count,
                        duration_ms=duration_ms,
                    )
                    result.reports.append(report)
                    result.total_assertions += len(assertion_results)
                    result.total_passed += passed_count
                    result.total_failed += failed_count

            finally:
                context.close()
