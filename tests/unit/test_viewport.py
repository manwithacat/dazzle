"""Unit tests for the viewport assertion framework.

No Playwright required — tests types, patterns, derivation logic, and
assertion matching.
"""

from unittest.mock import MagicMock, patch

import pytest

from dazzle.testing.viewport import (
    ALL_PATTERNS,
    DETAIL_VIEW_PATTERN,
    DRAWER_PATTERN,
    GRID_1_2_3_PATTERN,
    GRID_1_2_PATTERN,
    GRID_1_3_PATTERN,
    GRID_2_3_PATTERN,
    STATS_PATTERN,
    VIEWPORT_MATRIX,
    ViewportAssertion,
    ViewportAssertionResult,
    ViewportReport,
    _matches,
    derive_patterns_from_appspec,
)
from dazzle.testing.viewport_runner import ViewportRunOptions, ViewportRunResult

# ============================================================================
# TestViewportAssertion
# ============================================================================


class TestViewportAssertion:
    """Construction and field validation."""

    def test_create_basic(self) -> None:
        a = ViewportAssertion(
            selector=".foo",
            property="display",
            expected="none",
            viewport="mobile",
            description="Foo hidden on mobile",
        )
        assert a.selector == ".foo"
        assert a.property == "display"
        assert a.expected == "none"
        assert a.viewport == "mobile"
        assert a.description == "Foo hidden on mobile"

    def test_expected_list(self) -> None:
        a = ViewportAssertion(
            selector=".bar",
            property="grid-template-columns",
            expected=["1fr", "1fr 1fr"],
            viewport="tablet",
            description="Bar columns on tablet",
        )
        assert isinstance(a.expected, list)
        assert len(a.expected) == 2

    def test_all_viewports_valid(self) -> None:
        """All built-in assertions reference valid viewport keys."""
        for pattern in ALL_PATTERNS.values():
            for assertion in pattern.assertions:
                assert assertion.viewport in VIEWPORT_MATRIX, (
                    f"Pattern {pattern.name} assertion references unknown viewport "
                    f"{assertion.viewport!r}"
                )


# ============================================================================
# TestComponentPatterns
# ============================================================================


class TestComponentPatterns:
    """Built-in patterns have correct selectors/properties/viewports."""

    def test_pattern_assertion_shapes(self) -> None:
        """Combined: drawer viewports + visibility, grid_1_2_3 has 3 viewports,
        grid_1_2 + grid_1_3 check grid-template-columns."""
        # drawer: mobile + desktop in viewports
        viewports = {a.viewport for a in DRAWER_PATTERN.assertions}
        assert "mobile" in viewports
        assert "desktop" in viewports

        # drawer: transform (geometry) + display in properties (#1295 — was
        # visibility, which couldn't see an off-screen transform; that gap
        # is why the pattern missed #1294).
        props = {a.property for a in DRAWER_PATTERN.assertions}
        assert "transform" in props
        assert "display" in props

        # grid_1_2_3: all three viewports
        assert {a.viewport for a in GRID_1_2_3_PATTERN.assertions} == {
            "mobile",
            "tablet",
            "desktop",
        }

        # grid_1_2 + grid_1_3 only check grid-template-columns
        for pattern in (GRID_1_2_PATTERN, GRID_1_3_PATTERN):
            for a in pattern.assertions:
                assert a.property == "grid-template-columns"

    def test_stats_pattern_checks_flex_direction(self) -> None:
        for a in STATS_PATTERN.assertions:
            assert a.property == "flex-direction"

    def test_detail_view_checks_display(self) -> None:
        for a in DETAIL_VIEW_PATTERN.assertions:
            assert a.property == "display"

    def test_grid_2_3_pattern_exists(self) -> None:
        assert GRID_2_3_PATTERN.name == "grid_2_3"
        viewports = {a.viewport for a in GRID_2_3_PATTERN.assertions}
        assert "mobile" in viewports
        assert "desktop" in viewports

    def test_all_patterns_dict_complete(self) -> None:
        assert "drawer" in ALL_PATTERNS
        assert "grid_1_2_3" in ALL_PATTERNS
        assert "grid_1_2" in ALL_PATTERNS
        assert "grid_1_3" in ALL_PATTERNS
        assert "stats" in ALL_PATTERNS
        assert "detail_view" in ALL_PATTERNS
        assert "grid_2_3" in ALL_PATTERNS

    def test_all_patterns_have_assertions(self) -> None:
        for name, pattern in ALL_PATTERNS.items():
            assert len(pattern.assertions) > 0, f"Pattern {name} has no assertions"


# ============================================================================
# TestExpectedMatching
# ============================================================================


class TestExpectedMatching:
    """Single string vs list[str] expected values."""

    @pytest.mark.parametrize(
        "expected,actual,result",
        [
            ("hidden", "hidden", True),  # test_exact_match_passes
            ("hidden", "visible", False),  # test_exact_match_fails
            (["flex", "inline-flex"], "flex", True),  # test_list_match_first
            (["flex", "inline-flex"], "inline-flex", True),  # test_list_match_second
            (["flex", "inline-flex"], "block", False),  # test_list_match_fails
            ("hidden", None, False),  # test_none_actual_always_fails_string
            (["flex", "block"], None, False),  # test_none_actual_always_fails_list
            ("", "", True),  # test_empty_string_matches
            ([], "anything", False),  # test_empty_list_fails
        ],
        ids=[
            "test_exact_match_passes",
            "test_exact_match_fails",
            "test_list_match_first",
            "test_list_match_second",
            "test_list_match_fails",
            "test_none_actual_always_fails_string",
            "test_none_actual_always_fails_list",
            "test_empty_string_matches",
            "test_empty_list_fails",
        ],
    )
    def test_matches(self, expected: object, actual: object, result: bool) -> None:
        assert _matches(expected, actual) is result


# ============================================================================
# TestViewportReport
# ============================================================================


class TestViewportReport:
    """Result aggregation, pass/fail counting."""

    def _make_assertion(self, viewport: str = "mobile") -> ViewportAssertion:
        return ViewportAssertion(
            selector=".test",
            property="display",
            expected="block",
            viewport=viewport,
            description="test assertion",
        )

    def test_report_counts(self) -> None:
        results = [
            ViewportAssertionResult(assertion=self._make_assertion(), actual="block", passed=True),
            ViewportAssertionResult(
                assertion=self._make_assertion(),
                actual="none",
                passed=False,
                error="Expected 'block', got 'none'",
            ),
            ViewportAssertionResult(assertion=self._make_assertion(), actual="block", passed=True),
        ]
        report = ViewportReport(
            surface_or_page="/test",
            viewport="mobile",
            viewport_size={"width": 375, "height": 812},
            results=results,
            passed=2,
            failed=1,
            duration_ms=100.0,
        )
        assert report.passed == 2
        assert report.failed == 1
        assert len(report.results) == 3

    def test_all_pass(self) -> None:
        results = [
            ViewportAssertionResult(assertion=self._make_assertion(), actual="block", passed=True),
        ]
        report = ViewportReport(
            surface_or_page="/",
            viewport="desktop",
            viewport_size={"width": 1280, "height": 720},
            results=results,
            passed=1,
            failed=0,
            duration_ms=50.0,
        )
        assert report.failed == 0

    def test_empty_report(self) -> None:
        report = ViewportReport(
            surface_or_page="/empty",
            viewport="mobile",
            viewport_size={"width": 375, "height": 812},
            results=[],
            passed=0,
            failed=0,
            duration_ms=0.0,
        )
        assert report.passed == 0
        assert report.failed == 0


# ============================================================================
# TestDerivePatterns
# ============================================================================


def _mock_appspec(
    workspaces: list[dict] | None = None,
    surfaces: list[dict] | None = None,
) -> MagicMock:
    """Build a mock AppSpec with the given workspaces and surfaces."""
    spec = MagicMock()

    ws_mocks = []
    for ws_def in workspaces or []:
        ws = MagicMock()
        ws.name = ws_def.get("name", "test_ws")
        ws.stage = ws_def.get("stage")
        regions = []
        for r_def in ws_def.get("regions", []):
            r = MagicMock()
            r.display = r_def.get("display", "LIST")
            regions.append(r)
        ws.regions = regions
        ws_mocks.append(ws)
    spec.workspaces = ws_mocks

    s_mocks = []
    for s_def in surfaces or []:
        s = MagicMock()
        s.name = s_def.get("name", "test_surface")
        s.mode = s_def.get("mode", "view")
        s_mocks.append(s)
    spec.surfaces = s_mocks

    return spec


class TestDerivePatterns:
    """Mock AppSpec with different workspace stages → correct patterns derived."""

    def test_empty_appspec(self) -> None:
        spec = _mock_appspec()
        result = derive_patterns_from_appspec(spec)
        assert result == {}

    def test_drawer_on_root_with_workspaces(self) -> None:
        spec = _mock_appspec(workspaces=[{"name": "dashboard"}])
        result = derive_patterns_from_appspec(spec)
        assert "/" in result
        assert DRAWER_PATTERN in result["/"]

    def test_drawer_on_root_with_surfaces(self) -> None:
        spec = _mock_appspec(surfaces=[{"name": "tasks", "mode": "list"}])
        result = derive_patterns_from_appspec(spec)
        assert "/" in result
        assert DRAWER_PATTERN in result["/"]

    @pytest.mark.parametrize(
        ("workspace", "path", "expected_pattern"),
        [
            ({"name": "orders", "stage": "dual_pane_flow"}, "/orders", "grid_1_2"),
            ({"name": "status", "stage": "monitor_wall"}, "/status", "grid_2_3"),
            (
                {
                    "name": "items",
                    "stage": "focus_metric",
                    "regions": [{"display": "GRID"}],
                },
                "/items",
                "grid_1_2_3",
            ),
            (
                {
                    "name": "dash",
                    "stage": "focus_metric",
                    "regions": [{"display": "METRICS"}],
                },
                "/dash",
                "stats",
            ),
            (
                {
                    "name": "detail",
                    "stage": "focus_metric",
                    "regions": [{"display": "DETAIL"}],
                },
                "/detail",
                "detail_view",
            ),
        ],
        ids=[
            "test_dual_pane_flow_stage",
            "test_monitor_wall_stage",
            "test_region_grid_display",
            "test_region_metrics_display",
            "test_region_detail_display",
        ],
    )
    def test_workspace_pattern(self, workspace, path, expected_pattern) -> None:
        spec = _mock_appspec(workspaces=[workspace])
        result = derive_patterns_from_appspec(spec)
        assert path in result
        pattern_names = [p.name for p in result[path]]
        assert expected_pattern in pattern_names

    def test_focus_metric_stage_no_grid_pattern(self) -> None:
        spec = _mock_appspec(workspaces=[{"name": "home", "stage": "focus_metric"}])
        result = derive_patterns_from_appspec(spec)
        # focus_metric has no grid patterns, only drawer
        assert "/home" in result
        pattern_names = [p.name for p in result["/home"]]
        assert "drawer" in pattern_names
        assert "grid_1_2" not in pattern_names

    def test_list_surface_gets_grid_1_2(self) -> None:
        spec = _mock_appspec(surfaces=[{"name": "tasks", "mode": "list"}])
        result = derive_patterns_from_appspec(spec)
        assert "/tasks" in result
        pattern_names = [p.name for p in result["/tasks"]]
        assert "grid_1_2" in pattern_names

    def test_non_list_surface_no_pattern(self) -> None:
        spec = _mock_appspec(surfaces=[{"name": "create_task", "mode": "create"}])
        result = derive_patterns_from_appspec(spec)
        # Root gets drawer
        assert "/" in result
        # But create surface itself doesn't get a pattern
        assert "/create_task" not in result

    def test_no_duplicate_patterns(self) -> None:
        spec = _mock_appspec(
            workspaces=[
                {
                    "name": "dash",
                    "stage": "dual_pane_flow",
                    "regions": [
                        {"display": "LIST"},
                        {"display": "LIST"},
                    ],
                }
            ]
        )
        result = derive_patterns_from_appspec(spec)
        # dual_pane_flow adds grid_1_2, but LIST regions shouldn't duplicate it
        pattern_names = [p.name for p in result["/dash"]]
        assert pattern_names.count("grid_1_2") == 1

    def test_workspace_gets_drawer(self) -> None:
        spec = _mock_appspec(workspaces=[{"name": "ops", "stage": "scanner_table"}])
        result = derive_patterns_from_appspec(spec)
        assert "/ops" in result
        pattern_names = [p.name for p in result["/ops"]]
        assert "drawer" in pattern_names


# ============================================================================
# TestGridPatternDerivation
# ============================================================================


class TestGridPatternDerivation:
    """Stage grid patterns → correct grid column assertions."""

    def test_grid_1_2_3_mobile_single_col(self) -> None:
        mobile = [a for a in GRID_1_2_3_PATTERN.assertions if a.viewport == "mobile"]
        assert len(mobile) == 1
        assert isinstance(mobile[0].expected, list)
        assert "1fr" in mobile[0].expected

    def test_grid_1_2_3_tablet_two_cols(self) -> None:
        tablet = [a for a in GRID_1_2_3_PATTERN.assertions if a.viewport == "tablet"]
        assert len(tablet) == 1
        assert isinstance(tablet[0].expected, list)

    def test_grid_1_2_3_desktop_three_cols(self) -> None:
        desktop = [a for a in GRID_1_2_3_PATTERN.assertions if a.viewport == "desktop"]
        assert len(desktop) == 1
        assert isinstance(desktop[0].expected, list)

    def test_grid_2_3_mobile_two_cols(self) -> None:
        """Monitor wall: 2 cols on mobile."""
        mobile = [a for a in GRID_2_3_PATTERN.assertions if a.viewport == "mobile"]
        assert len(mobile) == 1
        assert isinstance(mobile[0].expected, list)

    def test_grid_2_3_desktop_three_cols(self) -> None:
        """Monitor wall: 3 cols on desktop."""
        desktop = [a for a in GRID_2_3_PATTERN.assertions if a.viewport == "desktop"]
        assert len(desktop) == 1
        assert isinstance(desktop[0].expected, list)


# ============================================================================
# TestViewportRunner
# ============================================================================


class TestViewportRunner:
    """Mock page.evaluate returns → assertion matching logic works."""

    def test_run_result_json_serialisation(self) -> None:
        result = ViewportRunResult(project_name="test_project")
        json_str = result.to_json()
        import json

        data = json.loads(json_str)
        assert data["project_name"] == "test_project"
        assert data["total_assertions"] == 0
        assert data["total_passed"] == 0
        assert data["total_failed"] == 0

    def test_run_result_markdown_pass(self) -> None:
        result = ViewportRunResult(project_name="test_project")
        md = result.to_markdown()
        assert "PASS" in md

    def test_run_result_markdown_fail(self) -> None:
        assertion = ViewportAssertion(
            selector=".test",
            property="display",
            expected="none",
            viewport="mobile",
            description="Test hidden on mobile",
        )
        result = ViewportRunResult(project_name="test_project", total_failed=1)
        result.reports.append(
            ViewportReport(
                surface_or_page="/",
                viewport="mobile",
                viewport_size={"width": 375, "height": 812},
                results=[
                    ViewportAssertionResult(
                        assertion=assertion,
                        actual="block",
                        passed=False,
                        error="Expected 'none', got 'block'",
                    )
                ],
                passed=0,
                failed=1,
                duration_ms=50.0,
            )
        )
        md = result.to_markdown()
        assert "FAIL" in md
        assert "Test hidden on mobile" in md

    def test_run_options_defaults(self) -> None:
        opts = ViewportRunOptions()
        assert opts.headless is True
        assert opts.viewports is None
        assert opts.base_url == "http://localhost:3000"
        assert opts.timeout == 10_000

    def test_run_options_custom_viewports(self) -> None:
        opts = ViewportRunOptions(viewports=["mobile", "desktop"])
        assert opts.viewports == ["mobile", "desktop"]

    def test_missing_playwright_returns_error(self) -> None:
        """When playwright is not importable, runner returns an error."""
        from pathlib import Path

        from dazzle.testing.viewport_runner import ViewportRunner

        runner = ViewportRunner(Path("/tmp/test"))
        patterns = {"/": [DRAWER_PATTERN]}

        # Mock the import to fail
        import builtins

        real_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "playwright.sync_api":
                raise ImportError("No playwright")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            result = runner.run(patterns)
            assert result.error is not None
            assert "playwright" in result.error.lower()


# ============================================================================
# TestViewportMatrix
# ============================================================================


class TestViewportMatrix:
    """Verify the viewport matrix is well-formed."""

    def test_all_viewports_have_width_and_height(self) -> None:
        for name, size in VIEWPORT_MATRIX.items():
            assert "width" in size, f"{name} missing width"
            assert "height" in size, f"{name} missing height"
            assert isinstance(size["width"], int)
            assert isinstance(size["height"], int)

    def test_mobile_smallest(self) -> None:
        assert VIEWPORT_MATRIX["mobile"]["width"] < VIEWPORT_MATRIX["tablet"]["width"]

    def test_wide_largest(self) -> None:
        assert VIEWPORT_MATRIX["wide"]["width"] > VIEWPORT_MATRIX["desktop"]["width"]

    def test_four_viewports(self) -> None:
        assert len(VIEWPORT_MATRIX) == 4
        assert set(VIEWPORT_MATRIX.keys()) == {"mobile", "tablet", "desktop", "wide"}


# ──────────── #1295 — pattern-freshness guard (browser-free) ────────────
# The orthogonal viewport dimension is only useful if its selectors match
# the markup the renderer ACTUALLY produces. Pre-#1295, DRAWER_PATTERN
# silently pointed at retired legacy `.drawer-side`/`dz-drawer` markup after
# the Fragment migration, so it could never have caught #1294. This guard
# renders the current Fragment app-shell and asserts each DRAWER_PATTERN
# selector matches a real element — deterministic, unit-suite, no browser.

import re as _re  # noqa: E402

from dazzle.render.fragment.escape import RawHTML  # noqa: E402
from dazzle.render.fragment.htmx import URL  # noqa: E402
from dazzle.render.fragment.primitives.containers import AppShell  # noqa: E402
from dazzle.render.fragment.primitives.navigation import (  # noqa: E402
    NavItem,
    Sidebar,
    Topbar,
)
from dazzle.render.fragment.renderer import FragmentRenderer  # noqa: E402


def _render_app_shell_chrome() -> str:
    sidebar = Sidebar(items=(NavItem(label="Home", href=URL("/app")),))
    shell = AppShell(
        body=RawHTML("<p>content</p>"),
        sidebar=sidebar,
        header=Topbar(title="App", show_sidebar_toggle=True),
        sidebar_state="open",
    )
    return FragmentRenderer().render(shell)


def test_drawer_pattern_selectors_match_current_markup() -> None:
    """#1295 freshness guard — every DRAWER_PATTERN class selector must match
    an element the Fragment chrome actually renders, so the pattern can't
    silently rot against retired markup the way it did before #1294."""
    html = _render_app_shell_chrome()
    for assertion in DRAWER_PATTERN.assertions:
        sel = assertion.selector
        assert sel.startswith("."), (
            f"freshness guard only validates class selectors; got {sel!r} — "
            "extend the guard if DRAWER_PATTERN gains non-class selectors"
        )
        cls = sel[1:]
        assert _re.search(rf'class="[^"]*\b{_re.escape(cls)}\b[^"]*"', html), (
            f"DRAWER_PATTERN selector {sel!r} ({assertion.description!r}) matches "
            "no element in the rendered Fragment app-shell — the pattern has "
            "rotted against the current markup (cf. #1294/#1295)."
        )
