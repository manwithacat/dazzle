"""Playwright-based viewport assertion runner.

Launches a headless (or headed) Chromium browser, iterates over the
viewport matrix, and checks computed CSS properties against expected values.

Separate from :mod:`dazzle.testing.e2e_runner` — viewport assertions have no
flows, steps, fixtures, or state.  They assert CSS properties only.
"""

from __future__ import annotations  # required: forward reference

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dazzle.core.manifest import resolve_api_url, resolve_site_url
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
    base_url: str = field(default_factory=resolve_site_url)
    timeout: int = 10_000
    include_suggestions: bool = True
    persona_id: str | None = None
    api_base_url: str = field(default_factory=resolve_api_url)
    capture_screenshots: bool = False
    update_baselines: bool = False
    screenshot_threshold: float = 0.01


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
    total_skipped: int = 0  # #1295 — assertions on persona-unreachable pages
    error: str | None = None
    visual_results: list[Any] = field(default_factory=list)  # list[ScreenshotResult]

    def to_json(self) -> str:
        """Serialise the run result to JSON."""
        data: dict[str, Any] = {
            "project_name": self.project_name,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_assertions": self.total_assertions,
            "total_passed": self.total_passed,
            "total_failed": self.total_failed,
            "total_skipped": self.total_skipped,
            "error": self.error,
            "reports": [
                {
                    "surface_or_page": r.surface_or_page,
                    "viewport": r.viewport,
                    "viewport_size": r.viewport_size,
                    "passed": r.passed,
                    "failed": r.failed,
                    "skipped": r.skipped,
                    "skip_reason": r.skip_reason,
                    "duration_ms": r.duration_ms,
                    "persona_id": r.persona_id,
                    "results": [
                        {
                            "selector": res.assertion.selector,
                            "property": res.assertion.property,
                            "expected": res.assertion.expected,
                            "actual": res.actual,
                            "passed": res.passed,
                            "description": res.assertion.description,
                            "error": res.error,
                            "suggestion": res.suggestion,
                        }
                        for res in r.results
                    ],
                }
                for r in self.reports
            ],
        }
        if self.visual_results:
            data["visual_results"] = [
                {
                    "page_path": vr.page_path,
                    "viewport": vr.viewport,
                    "screenshot_path": str(vr.screenshot_path) if vr.screenshot_path else None,
                    "baseline_path": str(vr.baseline_path) if vr.baseline_path else None,
                    "diff_path": str(vr.diff_path) if vr.diff_path else None,
                    "is_new_baseline": vr.is_new_baseline,
                    "pixel_diff_pct": vr.pixel_diff_pct,
                    "passed": vr.passed,
                }
                for vr in self.visual_results
            ]
        return json.dumps(data, indent=2)

    def to_markdown(self) -> str:
        """Render a human-friendly markdown summary."""
        lines: list[str] = []
        status = "PASS" if self.total_failed == 0 else "FAIL"
        lines.append(f"# Viewport Assertion Report — {status}")
        lines.append("")
        summary = f"**{self.total_passed}/{self.total_assertions}** assertions passed"
        if self.total_skipped:
            summary += f" · {self.total_skipped} skipped (persona-unreachable pages)"
        lines.append(summary)
        if self.error:
            lines.append(f"\n> Error: {self.error}")
        lines.append("")

        for report in self.reports:
            if report.skipped and not report.results:
                lines.append(
                    f"## [~] {report.surface_or_page} @ {report.viewport} "
                    f"({report.viewport_size['width']}x{report.viewport_size['height']}) "
                    f"— SKIPPED ({report.skipped}): {report.skip_reason or 'unreachable'}"
                )
                lines.append("")
                continue
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
                    if res.suggestion:
                        lines.append(f"         suggestion: add class '{res.suggestion}'")
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
    // #1295 — synthetic `grid-column-count`: getComputedStyle resolves
    // `grid-template-columns` to a px track list (e.g. "388px 388px"),
    // never the authored "repeat(2, …)" / "1fr 1fr", so a string compare
    // would always fail. Count the resolved tracks instead — stable across
    // container widths. A non-grid element (`none`/empty) reads as "0".
    if (s.property === 'grid-column-count') {
        const tracks = style.getPropertyValue('grid-template-columns').trim();
        const count = (!tracks || tracks === 'none') ? 0 : tracks.split(/\\s+/).length;
        return { selector: s.selector, property: s.property, actual: String(count) };
    }
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
            import playwright  # noqa: F401
        except ImportError:
            result.error = (
                "playwright is not installed. "
                "Run: pip install playwright && playwright install chromium"
            )
            result.completed_at = datetime.now(UTC)
            return result

        # #1295 — authenticate as the persona BEFORE navigating. The runner
        # reads a stored session cookie (viewport_auth.load_persona_cookies); if
        # nothing minted it, every /app page renders logged-out and every
        # app-shell assertion comes back "Element not found" — a silent no-op
        # that masked the whole orthogonal gate in CI. Mint it now via the same
        # test-mode endpoint the contract harness uses. A requested-but-
        # unauthenticatable persona is a hard error, not a silent anon run.
        if options.persona_id:
            self._ensure_persona_session(options, result)
            if result.error:
                result.completed_at = datetime.now(UTC)
                return result

        from dazzle.testing.browser_gate import get_browser_gate

        try:
            with get_browser_gate().sync_browser(headless=options.headless) as browser:
                self._run_matrix(browser, patterns, viewports_to_test, options, result)
        except Exception as exc:
            result.error = str(exc)

        # #1295 — loud guard against a silent wash: if a persona was requested
        # but NOTHING evaluated (every page skipped for lack of an app-shell),
        # the run proved nothing — surface it instead of reporting a green
        # "0 failed". This is the failure mode that hid the unauthenticated
        # harness behind a passing badge.
        evaluated = result.total_passed + result.total_failed
        if options.persona_id and evaluated == 0 and result.total_skipped > 0 and not result.error:
            result.error = (
                f"0 of {result.total_skipped} viewport assertions evaluated — every page was "
                f"skipped (no app-shell rendered) as persona '{options.persona_id}'. The run "
                "proved nothing; likely an auth or page-access problem."
            )

        result.completed_at = datetime.now(UTC)
        return result

    def _ensure_persona_session(
        self, options: ViewportRunOptions, result: ViewportRunResult
    ) -> None:
        """Ensure a stored session exists for ``options.persona_id``, minting
        one via the test-mode auth endpoint if absent (#1295).

        Sets ``result.error`` if a persona was requested but could not be
        authenticated — viewport assertions are meaningless against logged-out
        /app pages, so that is a hard failure rather than a silent anon run.
        """
        from dazzle.testing.viewport_auth import ensure_session_exists

        persona = options.persona_id
        if not persona:  # only called when a persona is requested; narrows type
            return
        if ensure_session_exists(self.project_path, persona, options.base_url):
            return

        import asyncio

        from dazzle.testing.session_manager import SessionManager

        auth_url = options.api_base_url or options.base_url
        try:
            manager = SessionManager(self.project_path, base_url=auth_url)
            asyncio.run(manager.create_session(persona))
        except Exception as exc:  # noqa: BLE001 — surfaced as a run-level error
            result.error = (
                f"could not authenticate persona '{persona}' at {auth_url}: {exc}. "
                "Viewport assertions need an authenticated session to reach /app pages; "
                "ensure the app is running with --test-mode."
            )
            return

        if not ensure_session_exists(self.project_path, persona, options.base_url):
            result.error = (
                f"persona '{persona}' session was not created at {auth_url} "
                "(no session token returned). Cannot run authenticated viewport assertions."
            )

    def _run_matrix(
        self,
        browser: Any,
        patterns: dict[str, list[ComponentPattern]],
        viewports: list[str],
        options: ViewportRunOptions,
        result: ViewportRunResult,
    ) -> None:
        """Iterate viewports × pages and evaluate assertions.

        Uses a single browser context + page, resizing the viewport for each
        breakpoint instead of creating a new context per viewport.
        """
        if not viewports:
            return

        # Find largest viewport for initial context size
        max_w, max_h = 0, 0
        for vp_name in viewports:
            vp_size = VIEWPORT_MATRIX.get(vp_name)
            if vp_size:
                max_w = max(max_w, vp_size["width"])
                max_h = max(max_h, vp_size["height"])
        if max_w == 0:
            return

        context = browser.new_context(viewport={"width": max_w, "height": max_h})

        # Inject persona cookies once
        if options.persona_id:
            from dazzle.testing.viewport_auth import load_persona_cookies

            cookies = load_persona_cookies(
                self.project_path,
                options.persona_id,
                options.base_url,
            )
            if cookies:
                context.add_cookies(cookies)

        page = context.new_page()
        page.set_default_timeout(options.timeout)

        try:
            for vp_name in viewports:
                vp_size = VIEWPORT_MATRIX.get(vp_name)
                if vp_size is None:
                    continue

                page.set_viewport_size({"width": vp_size["width"], "height": vp_size["height"]})

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

                    # #1295 — skip pages the persona can't reach. Every derived
                    # pattern targets an /app page that renders inside
                    # `.dz-app-shell`; if the shell is absent the page 403'd /
                    # redirected (RBAC) or errored, so the assertions would all
                    # be false "Element not found". Record as skipped, not failed,
                    # so a persona-access boundary doesn't read as a regression.
                    try:
                        shell_present = bool(
                            page.evaluate("() => !!document.querySelector('.dz-app-shell')")
                        )
                    except Exception:
                        shell_present = False
                    if not shell_present:
                        result.reports.append(
                            ViewportReport(
                                surface_or_page=page_path,
                                viewport=vp_name,
                                viewport_size=vp_size,
                                results=[],
                                passed=0,
                                failed=0,
                                skipped=len(assertions_for_page),
                                skip_reason=(
                                    "app-shell not rendered (persona lacks access "
                                    "or page redirected)"
                                ),
                                persona_id=options.persona_id,
                                duration_ms=(time.monotonic() - t0) * 1000,
                            )
                        )
                        result.total_skipped += len(assertions_for_page)
                        continue

                    # Batch evaluate computed styles
                    specs = [
                        {"selector": a.selector, "property": a.property}
                        for a in assertions_for_page
                    ]
                    try:
                        raw_results: list[dict[str, Any]] = page.evaluate(_JS_BATCH_EVAL, specs)
                    except Exception:
                        # JS evaluation failed — treat all actuals as None
                        raw_results = [
                            {"selector": s["selector"], "property": s["property"], "actual": None}
                            for s in specs
                        ]

                    duration_ms = (time.monotonic() - t0) * 1000

                    assertion_results: list[ViewportAssertionResult] = []
                    for assertion, raw in zip(assertions_for_page, raw_results, strict=True):
                        actual = raw.get("actual")
                        passed = _matches(assertion.expected, actual)
                        # #1494: a content-dependent selector that's absent is N/A,
                        # not a geometry regression — this gate asserts geometry of
                        # PRESENT elements, not DOM presence. An empty / `when_empty`-
                        # collapsed region has no body grid to measure, so skip it.
                        skipped_absent = (
                            (not passed) and actual is None and assertion.skip_if_absent
                        )
                        if skipped_absent:
                            error = (
                                "skipped: element absent (content-dependent — empty / "
                                "when_empty-collapsed region has no grid; geometry N/A)"
                            )
                        elif passed:
                            error = None
                        elif actual is None:
                            error = "Element not found"
                        else:
                            error = f"Expected {assertion.expected!r}, got {actual!r}"
                        assertion_results.append(
                            ViewportAssertionResult(
                                assertion=assertion,
                                actual=actual,
                                passed=passed,
                                error=error,
                            )
                        )

                    # Attach suggestions to failed assertions
                    if options.include_suggestions:
                        from dazzle.testing.viewport_suggestions import suggest_fix

                        for res in assertion_results:
                            _is_skipped = res.actual is None and res.assertion.skip_if_absent
                            if not res.passed and not _is_skipped:
                                suggestion = suggest_fix(
                                    selector=res.assertion.selector,
                                    property=res.assertion.property,
                                    expected=res.assertion.expected,
                                    actual=res.actual,
                                    viewport=vp_name,
                                )
                                if suggestion is not None:
                                    res.suggestion = suggestion.suggested_class

                    # Capture screenshots if configured
                    if options.capture_screenshots:
                        from dazzle.testing.viewport_screenshot import run_visual_regression

                        vr = run_visual_regression(
                            page,
                            page_path,
                            vp_name,
                            self.project_path,
                            update_baselines=options.update_baselines,
                            threshold=options.screenshot_threshold,
                        )
                        result.visual_results.append(vr)

                    passed_count = sum(1 for r in assertion_results if r.passed)
                    # #1494: absent content-dependent selectors are skipped, not failed.
                    skipped_count = sum(
                        1
                        for r in assertion_results
                        if (not r.passed) and r.actual is None and r.assertion.skip_if_absent
                    )
                    failed_count = len(assertion_results) - passed_count - skipped_count

                    report = ViewportReport(
                        surface_or_page=page_path,
                        viewport=vp_name,
                        viewport_size=vp_size,
                        results=assertion_results,
                        passed=passed_count,
                        failed=failed_count,
                        skipped=skipped_count,
                        skip_reason=(
                            "content-dependent selector(s) absent (empty / "
                            "when_empty-collapsed region — geometry N/A)"
                            if skipped_count
                            else None
                        ),
                        persona_id=options.persona_id,
                        duration_ms=duration_ms,
                    )
                    result.reports.append(report)
                    result.total_assertions += len(assertion_results)
                    result.total_passed += passed_count
                    result.total_failed += failed_count
                    result.total_skipped += skipped_count

        finally:
            context.close()
