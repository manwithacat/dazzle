"""Unit tests for the viewport assertion framework.

No Playwright required — tests types, patterns, derivation logic, and
assertion matching.
"""

from unittest.mock import MagicMock, patch

import pytest

from dazzle.testing.viewport import (
    ACTION_GRID_PATTERN,
    ALL_PATTERNS,
    DRAWER_PATTERN,
    GRID_PATTERN,
    METRICS_PATTERN,
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

    def test_drawer_geometry_property_model(self) -> None:
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

    def test_region_grids_use_column_count_property(self) -> None:
        # #1295 — region grids assert the synthetic `grid-column-count`, not
        # raw `grid-template-columns` (which getComputedStyle resolves to px
        # tracks, never the authored value — a guaranteed false negative).
        for pattern in (GRID_PATTERN, METRICS_PATTERN, ACTION_GRID_PATTERN):
            for a in pattern.assertions:
                assert a.property == "grid-column-count", (
                    f"{pattern.name} assertion uses {a.property!r}, expected grid-column-count"
                )
                assert isinstance(a.expected, str) and a.expected.isdigit()

    def test_region_grids_target_fragment_classes(self) -> None:
        # #1295 — selectors must be the real Fragment region classes, not the
        # retired DaisyUI ones. The freshness guard below proves these match
        # actual rendered markup. (No dashboard_grid: it's a uniform 12-track
        # grid at every viewport — not viewport-column-count-assertable.)
        expected = {
            "grid": ".dz-grid-list",
            "metrics": ".dz-metrics-grid",
            "action_grid": ".dz-action-grid",
        }
        for name, sel in expected.items():
            assert {a.selector for a in ALL_PATTERNS[name].assertions} == {sel}

    def test_grid_column_counts_match_css_breakpoints(self) -> None:
        # Column counts read from regions.css (40/64rem). The real
        # viewport-responsive region grids change track count by breakpoint;
        # `.dz-dashboard-grid` does NOT (always 12 tracks) so it has no pattern.
        def counts(pattern):
            return {a.viewport: a.expected for a in pattern.assertions}

        assert counts(GRID_PATTERN) == {"mobile": "1", "tablet": "2", "desktop": "3"}
        assert counts(METRICS_PATTERN) == {"mobile": "1", "tablet": "2", "desktop": "4"}
        assert counts(ACTION_GRID_PATTERN) == {"mobile": "1", "tablet": "2", "desktop": "3"}

    def test_all_patterns_dict_complete(self) -> None:
        assert set(ALL_PATTERNS) == {"drawer", "grid", "metrics", "action_grid"}

    def test_all_patterns_have_assertions(self) -> None:
        for name, pattern in ALL_PATTERNS.items():
            assert len(pattern.assertions) > 0, f"Pattern {name} has no assertions"

    def test_no_legacy_daisyui_selectors(self) -> None:
        # #1295 — guard against the rot recurring: no pattern may target a
        # Tailwind/DaisyUI escaped selector (`\\:`) or the retired `.stats`.
        for pattern in ALL_PATTERNS.values():
            for a in pattern.assertions:
                assert "\\:" not in a.selector, (
                    f"{pattern.name} uses a legacy escaped selector {a.selector!r}"
                )
                assert a.selector != ".stats"


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
        # entity_ref drives the /app/<entity> list path (#1295); default None
        # so the derivation falls back to the surface name. (Unset MagicMock
        # attrs auto-create truthy mocks, so set it explicitly.)
        s.entity_ref = s_def.get("entity_ref")
        s_mocks.append(s)
    spec.surfaces = s_mocks

    return spec


class TestDerivePatterns:
    """Mock AppSpec with different workspace stages → correct patterns derived."""

    def test_empty_appspec(self) -> None:
        spec = _mock_appspec()
        result = derive_patterns_from_appspec(spec)
        assert result == {}

    def test_drawer_on_workspace_app_page(self) -> None:
        # #1295 — workspaces are app-shell pages at /app/workspaces/<name>;
        # DRAWER attaches there, NOT on "/" (the marketing root has no shell).
        spec = _mock_appspec(workspaces=[{"name": "dashboard"}])
        result = derive_patterns_from_appspec(spec)
        assert "/" not in result
        assert "/app/workspaces/dashboard" in result
        assert DRAWER_PATTERN in result["/app/workspaces/dashboard"]

    def test_drawer_on_list_surface_app_page(self) -> None:
        # List surfaces are app-shell pages at /app/<entity> (entity_ref →
        # slug, fallback to surface name).
        spec = _mock_appspec(surfaces=[{"name": "tasks", "mode": "list"}])
        result = derive_patterns_from_appspec(spec)
        assert "/" not in result
        assert "/app/tasks" in result
        assert DRAWER_PATTERN in result["/app/tasks"]

    def test_list_surface_uses_entity_slug(self) -> None:
        spec = _mock_appspec(
            surfaces=[{"name": "ticket_list", "mode": "list", "entity_ref": "Ticket"}]
        )
        result = derive_patterns_from_appspec(spec)
        assert "/app/ticket" in result  # entity_ref lowercased, not surface name

    @pytest.mark.parametrize(
        ("workspace", "path", "expected_patterns"),
        [
            # #1295 — stages no longer add a per-stage grid pattern, and the
            # `.dz-dashboard-grid` container is NOT asserted (uniform 12-track
            # grid at every viewport; responsiveness is card-span based). Every
            # workspace gets drawer; region display modes add their own
            # viewport-responsive grids.
            (
                {"name": "orders", "stage": "dual_pane_flow"},
                "/app/workspaces/orders",
                {"drawer"},
            ),
            (
                {"name": "status", "stage": "monitor_wall"},
                "/app/workspaces/status",
                {"drawer"},
            ),
            (
                {"name": "items", "stage": "focus_metric", "regions": [{"display": "GRID"}]},
                "/app/workspaces/items",
                {"drawer", "grid"},
            ),
            (
                {"name": "dash", "stage": "focus_metric", "regions": [{"display": "METRICS"}]},
                "/app/workspaces/dash",
                {"drawer", "metrics"},
            ),
            (
                {"name": "summ", "stage": "focus_metric", "regions": [{"display": "SUMMARY"}]},
                "/app/workspaces/summ",
                {"drawer", "metrics"},
            ),
            (
                {"name": "acts", "stage": "focus_metric", "regions": [{"display": "ACTION_GRID"}]},
                "/app/workspaces/acts",
                {"drawer", "action_grid"},
            ),
            (
                # DETAIL is container-query driven → no viewport pattern (#1295).
                {"name": "detail", "stage": "focus_metric", "regions": [{"display": "DETAIL"}]},
                "/app/workspaces/detail",
                {"drawer"},
            ),
        ],
        ids=[
            "test_dual_pane_flow_stage",
            "test_monitor_wall_stage",
            "test_region_grid_display",
            "test_region_metrics_display",
            "test_region_summary_display",
            "test_region_action_grid_display",
            "test_region_detail_display_dropped",
        ],
    )
    def test_workspace_pattern(self, workspace, path, expected_patterns) -> None:
        spec = _mock_appspec(workspaces=[workspace])
        result = derive_patterns_from_appspec(spec)
        assert path in result
        assert {p.name for p in result[path]} == expected_patterns

    def test_every_workspace_gets_drawer(self) -> None:
        # #1295 — a bare workspace renders the app-shell chrome (DRAWER). The
        # dashboard-grid container is not asserted (always 12 tracks).
        spec = _mock_appspec(workspaces=[{"name": "home", "stage": "focus_metric"}])
        result = derive_patterns_from_appspec(spec)
        assert {p.name for p in result["/app/workspaces/home"]} == {"drawer"}

    def test_list_surface_gets_drawer_only(self) -> None:
        # #1295 — a list page is a table, not a responsive column grid; DRAWER
        # is the only viewport-assertable pattern.
        spec = _mock_appspec(surfaces=[{"name": "tasks", "mode": "list"}])
        result = derive_patterns_from_appspec(spec)
        assert "/app/tasks" in result
        assert {p.name for p in result["/app/tasks"]} == {"drawer"}

    def test_non_list_surface_no_pattern(self) -> None:
        spec = _mock_appspec(surfaces=[{"name": "create_task", "mode": "create"}])
        result = derive_patterns_from_appspec(spec)
        # A create-only surface (no workspaces, no list surfaces) yields no
        # patterns — no marketing-root drawer anymore (#1295).
        assert result == {}

    def test_no_duplicate_patterns(self) -> None:
        spec = _mock_appspec(
            workspaces=[
                {
                    "name": "dash",
                    "stage": "dual_pane_flow",
                    "regions": [
                        {"display": "GRID"},
                        {"display": "GRID"},
                    ],
                }
            ]
        )
        result = derive_patterns_from_appspec(spec)
        # Two GRID regions must not duplicate the grid pattern, nor the
        # always-attached drawer.
        pattern_names = [p.name for p in result["/app/workspaces/dash"]]
        assert pattern_names.count("grid") == 1
        assert pattern_names.count("drawer") == 1

    def test_workspace_gets_drawer(self) -> None:
        spec = _mock_appspec(workspaces=[{"name": "ops", "stage": "scanner_table"}])
        result = derive_patterns_from_appspec(spec)
        path = "/app/workspaces/ops"
        assert path in result
        pattern_names = [p.name for p in result[path]]
        assert "drawer" in pattern_names


# ============================================================================
# TestGridColumnCounts
# ============================================================================


class TestGridColumnCounts:
    """#1295 — each region grid pattern has exactly one column-count
    assertion per viewport, matching the CSS breakpoints."""

    def test_grid_one_assertion_per_viewport(self) -> None:
        for pattern in (GRID_PATTERN, METRICS_PATTERN, ACTION_GRID_PATTERN):
            viewports = [a.viewport for a in pattern.assertions]
            assert viewports == ["mobile", "tablet", "desktop"]

    def test_metrics_desktop_is_four_cols(self) -> None:
        desktop = [a for a in METRICS_PATTERN.assertions if a.viewport == "desktop"]
        assert len(desktop) == 1
        assert desktop[0].expected == "4"

    def test_no_dashboard_grid_pattern(self) -> None:
        # #1295 — `.dz-dashboard-grid` is a uniform 12-track grid at every
        # viewport (card-span responsiveness), so it is deliberately NOT a
        # pattern. The live CI run caught a mobile=1 assertion failing (got 12).
        assert "dashboard_grid" not in ALL_PATTERNS
        for pattern in ALL_PATTERNS.values():
            for a in pattern.assertions:
                assert a.selector != ".dz-dashboard-grid"


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
    # Match production build_app_chrome_page: chrome + rail toggles (#1602).
    sidebar = Sidebar(
        items=(NavItem(label="Home", href=URL("/app")),),
        show_sidebar_toggle=True,
    )
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


# -- region-grid freshness (#1295) — same discipline for the grid patterns:
# render each region primitive and assert its pattern's selector matches the
# class it actually emits. This verifies the retarget away from the retired
# DaisyUI selectors (`.grid.md:grid-cols-2`, `.stats`, `.sm:grid…`) landed on
# real markup, not just another stale string — library-wide, the rot class
# that let #1294 through.

from dazzle.render.fragment.primitives.data import (  # noqa: E402
    ActionCard,
    ActionGrid,
    GridCell,
    GridRegion,
    MetricsGrid,
    MetricTile,
)


def _class_present(cls: str, html: str) -> bool:
    return bool(_re.search(rf'class="[^"]*\b{_re.escape(cls)}\b[^"]*"', html))


_REGION_FRESHNESS_CASES = [
    (GRID_PATTERN, GridRegion(cells=(GridCell(title="x"),))),
    (METRICS_PATTERN, MetricsGrid(tiles=(MetricTile(label="x", value="1"),))),
    (ACTION_GRID_PATTERN, ActionGrid(cards=(ActionCard(label="x"),))),
]


@pytest.mark.parametrize(
    ("pattern", "primitive"),
    _REGION_FRESHNESS_CASES,
    ids=[p.name for p, _ in _REGION_FRESHNESS_CASES],
)
def test_region_pattern_selectors_match_current_markup(pattern, primitive) -> None:
    """#1295 freshness guard for the region grids — each pattern's selector
    must match the class its region primitive actually renders, so a renderer
    migration can't silently rot the selector back to "Element not found"
    (the failure mode that let #1294 through, this time across the whole
    pattern library)."""
    html = FragmentRenderer().render(primitive)
    for assertion in pattern.assertions:
        sel = assertion.selector
        assert sel.startswith("."), f"freshness guard only validates class selectors; got {sel!r}"
        assert _class_present(sel[1:], html), (
            f"{pattern.name} selector {sel!r} matches no element in the rendered "
            f"{type(primitive).__name__} — the pattern has rotted against the "
            "current Fragment markup (cf. #1294/#1295)."
        )


# ──────────── #1295 — run-viewport must authenticate + skip RBAC pages ────────
# The orthogonal viewport gate was a silent no-op in CI: nothing minted the
# persona session, so every /app page rendered logged-out → all assertions
# "Element not found". The runner now (a) mints the session before navigating,
# (b) skips pages the persona can't reach instead of false-failing them, and
# (c) loudly errors if a persona run evaluated nothing.

from dazzle.testing import session_manager as _session_manager  # noqa: E402
from dazzle.testing import viewport_auth as _viewport_auth  # noqa: E402
from dazzle.testing.viewport_runner import ViewportRunner  # noqa: E402


def test_ensure_persona_session_mints_when_missing(monkeypatch, tmp_path) -> None:
    """Persona requested + no stored session → the runner mints one."""
    exists_seq = iter([False, True])  # missing, then present after mint
    monkeypatch.setattr(_viewport_auth, "ensure_session_exists", lambda *a, **k: next(exists_seq))
    created: list[str] = []

    class _FakeSM:
        def __init__(self, project_path, base_url=None) -> None:
            self.base_url = base_url

        async def create_session(self, persona):  # noqa: ANN001
            created.append(persona)
            return object()

    monkeypatch.setattr(_session_manager, "SessionManager", _FakeSM)

    result = ViewportRunResult(project_name="t")
    ViewportRunner(tmp_path)._ensure_persona_session(ViewportRunOptions(persona_id="agent"), result)
    assert created == ["agent"]
    assert result.error is None


def test_ensure_persona_session_errors_when_auth_fails(monkeypatch, tmp_path) -> None:
    """Persona requested but auth fails → hard error (not a silent anon run)."""
    monkeypatch.setattr(_viewport_auth, "ensure_session_exists", lambda *a, **k: False)

    class _FailSM:
        def __init__(self, *a, **k) -> None: ...

        async def create_session(self, persona):  # noqa: ANN001
            raise RuntimeError("no test endpoint")

    monkeypatch.setattr(_session_manager, "SessionManager", _FailSM)

    result = ViewportRunResult(project_name="t")
    ViewportRunner(tmp_path)._ensure_persona_session(ViewportRunOptions(persona_id="agent"), result)
    assert result.error is not None
    assert "could not authenticate persona 'agent'" in result.error


def test_ensure_persona_session_noop_when_session_exists(monkeypatch, tmp_path) -> None:
    """Existing session → no mint, no error."""
    monkeypatch.setattr(_viewport_auth, "ensure_session_exists", lambda *a, **k: True)

    def _boom(*a, **k):  # SessionManager must not be constructed
        raise AssertionError("should not mint when a session already exists")

    monkeypatch.setattr(_session_manager, "SessionManager", _boom)
    result = ViewportRunResult(project_name="t")
    ViewportRunner(tmp_path)._ensure_persona_session(ViewportRunOptions(persona_id="agent"), result)
    assert result.error is None


def test_skipped_pages_surface_in_json_and_markdown() -> None:
    """RBAC-skipped pages are reported as skipped, not failed (#1295)."""
    import json

    result = ViewportRunResult(
        project_name="t",
        total_assertions=3,
        total_passed=0,
        total_failed=0,
        total_skipped=3,
    )
    result.reports.append(
        ViewportReport(
            surface_or_page="/app/admin_only",
            viewport="desktop",
            viewport_size={"width": 1280, "height": 720},
            results=[],
            passed=0,
            failed=0,
            skipped=3,
            skip_reason="app-shell not rendered (persona lacks access)",
            persona_id="agent",
            duration_ms=12.0,
        )
    )
    data = json.loads(result.to_json())
    assert data["total_skipped"] == 3
    assert data["reports"][0]["skipped"] == 3
    assert data["reports"][0]["skip_reason"]

    md = result.to_markdown()
    assert "SKIPPED" in md
    assert "3 skipped" in md
