"""Viewport assertion framework for responsive layout testing.

Provides deterministic Playwright-based CSS property assertions across a
viewport matrix (mobile → wide desktop).  No LLM involvement — pure
computed-style checks driven by patterns derived from the DSL AppSpec.

Usage::

    from dazzle.testing.viewport import derive_patterns_from_appspec, VIEWPORT_MATRIX
    from dazzle.testing.viewport_runner import ViewportRunner, ViewportRunOptions

    patterns = derive_patterns_from_appspec(appspec)
    runner = ViewportRunner(project_path)
    result = runner.run(patterns, ViewportRunOptions())
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec

# ---------------------------------------------------------------------------
# Viewport matrix
# ---------------------------------------------------------------------------

VIEWPORT_MATRIX: dict[str, dict[str, int]] = {
    "mobile": {"width": 375, "height": 812},
    "tablet": {"width": 768, "height": 1024},
    "desktop": {"width": 1280, "height": 720},
    "wide": {"width": 1440, "height": 900},
}

# ---------------------------------------------------------------------------
# Core dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ViewportAssertion:
    """A single CSS property assertion at a specific viewport."""

    selector: str
    property: str
    expected: str | list[str]
    viewport: str
    description: str
    # #1494: when the selector targets a *content-dependent* element (a region
    # body grid that only exists when the region has data), its absence is N/A,
    # not a geometry regression — this gate asserts geometry, not DOM presence
    # (an empty / `when_empty`-collapsed region has no grid). The runner then
    # records "Element not found" for this assertion as SKIPPED, not FAILED.
    # Chrome assertions (sidebar/toggle) leave this False — they must be present.
    skip_if_absent: bool = False


@dataclass
class ComponentPattern:
    """Named collection of viewport assertions for a UI component."""

    name: str
    assertions: list[ViewportAssertion]
    # Propagated to every assertion that didn't set it explicitly (#1494).
    skip_if_absent: bool = False

    def __post_init__(self) -> None:
        if self.skip_if_absent:
            for a in self.assertions:
                if not a.skip_if_absent:
                    a.skip_if_absent = True


@dataclass
class ViewportAssertionResult:
    """Result of evaluating one assertion."""

    assertion: ViewportAssertion
    actual: str | None
    passed: bool
    error: str | None = None
    suggestion: str | None = None


@dataclass
class ViewportReport:
    """Aggregated results for one page at one viewport size."""

    surface_or_page: str
    viewport: str
    viewport_size: dict[str, int]
    results: list[ViewportAssertionResult]
    passed: int
    failed: int
    duration_ms: float
    persona_id: str | None = None
    # #1295 — pages the persona can't reach (no app-shell rendered) are
    # skipped, not failed: their assertions would all be false "Element not
    # found". ``skipped`` counts those assertions; ``skip_reason`` explains why.
    skipped: int = 0
    skip_reason: str | None = None


# ---------------------------------------------------------------------------
# Assertion matching
# ---------------------------------------------------------------------------


def _matches(expected: str | list[str], actual: str | None) -> bool:
    """Check whether *actual* satisfies *expected*.

    * Single string → exact match.
    * List of strings → *actual* must match one of them.
    * ``None`` actual always fails.
    """
    if actual is None:
        return False
    if isinstance(expected, list):
        return actual in expected
    return actual == expected


# ---------------------------------------------------------------------------
# Built-in patterns
# ---------------------------------------------------------------------------

# -- App-shell sidebar drawer (Fragment chrome) -----------------------------
#
# #1295 — UPDATED from the retired legacy Jinja `app_shell.html` markup.
# The pre-#1295 pattern targeted `.drawer-side` / `label[for="dz-drawer"]`
# (DaisyUI classes that vanished in the v0.67.44/45 Fragment migration) and
# asserted `visibility` — which cannot see an off-screen `transform`. That
# rot is exactly why this very pattern failed to catch #1294 (sidebar parked
# at translateX(-256px), `visibility: visible`). Now it targets the Fragment
# chrome (`.dz-sidebar` / `.dz-sidebar-toggle`) with a GEOMETRY property
# model: at desktop the open sidebar's transform is the identity matrix
# (on-screen); off-screen reads as matrix(1,0,0,1,-256,0). This is the
# orthogonal dimension — geometry, not DOM presence.

DRAWER_PATTERN = ComponentPattern(
    name="drawer",
    assertions=[
        # Sidebar slid ON-SCREEN at desktop (data-dz-sidebar=open default).
        # Off-screen (the #1294 regression) reads as matrix(1,0,0,1,-256,0).
        ViewportAssertion(
            selector=".dz-sidebar",
            property="transform",
            expected=["none", "matrix(1, 0, 0, 1, 0, 0)"],
            viewport="desktop",
            description="Sidebar on-screen at desktop (transform ≈ identity)",
        ),
        # Toggle present + visible so the nav is reachable/collapsible at
        # both viewports (#1294 affordance; #1602 placement split).
        # Default shell state is data-dz-sidebar=open:
        #   desktop open → rail toggle on sidebar header (chrome hidden)
        #   mobile       → chrome toggle in topbar (rail always hidden)
        # A bare `.dz-sidebar-toggle` matches rail first in DOM order, so on
        # mobile it would read display:none even when chrome is visible.
        ViewportAssertion(
            selector=".dz-sidebar-toggle--rail",
            property="display",
            expected=["flex", "inline-flex", "block", "inline-block"],
            viewport="desktop",
            description="Sidebar rail toggle visible at desktop (open default)",
        ),
        ViewportAssertion(
            selector=".dz-sidebar-toggle--chrome",
            property="display",
            expected=["flex", "inline-flex", "block", "inline-block"],
            viewport="mobile",
            description="Sidebar chrome toggle visible on mobile (nav reachable)",
        ),
    ],
)

# -- Region grids (Fragment substrate) -------------------------------------
#
# #1295 — UPDATED from the retired legacy DaisyUI/Tailwind selectors
# (`.grid.sm:grid-cols-2.lg:grid-cols-3`, `.stats`, `.sm:grid.sm:grid-cols-3`)
# that the Fragment substrate never emitted — so every assertion came back
# "Element not found" (the same silent-rot-after-migration class as DRAWER
# pre-#1294). These now target the real Fragment region classes, verified
# against freshly-rendered primitives by the freshness guard in
# `test_viewport.py`.
#
# PROPERTY MODEL — `grid-column-count`, not raw `grid-template-columns`.
# `getComputedStyle('grid-template-columns')` returns the *resolved* track
# list in px (e.g. "388px 388px"), never the authored "repeat(2, …)" /
# "1fr 1fr" — so a string compare against authored values would be a NEW
# false negative (exactly the property-model mismatch that let #1294 through
# with `visibility` vs `transform`). The runner's JS evaluator computes the
# synthetic `grid-column-count` by counting resolved tracks, which is stable
# across container widths. Breakpoints below are read from
# `components/regions.css` + `components/dashboard.css`: region grids switch
# at 40rem (640px) and 64rem (1024px); the dashboard grid at 48rem (768px).
# The matrix is mobile=375 / tablet=768 / desktop=1280 / wide=1440.

# GRID display → `.dz-grid-list`: 1 → 2 → 3 cols (40rem / 64rem).
GRID_PATTERN = ComponentPattern(
    name="grid",
    skip_if_absent=True,  # region-body grid — absent when the region is empty/collapsed (#1494)
    assertions=[
        ViewportAssertion(
            selector=".dz-grid-list",
            property="grid-column-count",
            expected="1",
            viewport="mobile",
            description="Grid region single-column on mobile (<40rem)",
        ),
        ViewportAssertion(
            selector=".dz-grid-list",
            property="grid-column-count",
            expected="2",
            viewport="tablet",
            description="Grid region two-column on tablet (≥40rem, <64rem)",
        ),
        ViewportAssertion(
            selector=".dz-grid-list",
            property="grid-column-count",
            expected="3",
            viewport="desktop",
            description="Grid region three-column on desktop (≥64rem)",
        ),
    ],
)

# METRICS / SUMMARY display → `.dz-metrics-grid`: 1 → 2 → 4 cols (40rem / 64rem).
METRICS_PATTERN = ComponentPattern(
    name="metrics",
    skip_if_absent=True,  # region-body grid — absent when the region is empty/collapsed (#1494)
    assertions=[
        ViewportAssertion(
            selector=".dz-metrics-grid",
            property="grid-column-count",
            expected="1",
            viewport="mobile",
            description="Metrics tiles single-column on mobile (<40rem)",
        ),
        ViewportAssertion(
            selector=".dz-metrics-grid",
            property="grid-column-count",
            expected="2",
            viewport="tablet",
            description="Metrics tiles two-column on tablet (≥40rem, <64rem)",
        ),
        ViewportAssertion(
            selector=".dz-metrics-grid",
            property="grid-column-count",
            expected="4",
            viewport="desktop",
            description="Metrics tiles four-column on desktop (≥64rem)",
        ),
    ],
)

# ACTION_GRID display → `.dz-action-grid`: 1 → 2 → 3 cols (40rem / 64rem).
ACTION_GRID_PATTERN = ComponentPattern(
    name="action_grid",
    skip_if_absent=True,  # region-body grid — absent when the region is empty/collapsed (#1494)
    assertions=[
        ViewportAssertion(
            selector=".dz-action-grid",
            property="grid-column-count",
            expected="1",
            viewport="mobile",
            description="Action cards single-column on mobile (<40rem)",
        ),
        ViewportAssertion(
            selector=".dz-action-grid",
            property="grid-column-count",
            expected="2",
            viewport="tablet",
            description="Action cards two-column on tablet (≥40rem, <64rem)",
        ),
        ViewportAssertion(
            selector=".dz-action-grid",
            property="grid-column-count",
            expected="3",
            viewport="desktop",
            description="Action cards three-column on desktop (≥64rem)",
        ),
    ],
)

# NOTE — NO dashboard-grid pattern (#1295, removed after the live CI run caught
# it). `.dz-dashboard-grid` is a uniform **12-track** grid at EVERY viewport
# (verified live: `grid-template-columns` resolves to 12 tracks at 375px AND
# 1280px — at mobile the cards span all 12 columns so 11 tracks collapse to
# 0px, giving a single *visual* column). Its responsiveness is card col-span
# based, NOT a column-count change — so `grid-column-count` is always 12 and
# can't express it. This is the same fiction class as the old per-stage
# grid_1_2/grid_2_3 patterns and the container-query DETAIL view: not
# viewport-column-count-assertable, so deliberately excluded. The freshness
# guard still pins that `.dz-dashboard-grid` is emitted; the real
# viewport-responsive grids below (.dz-grid-list / .dz-metrics-grid /
# .dz-action-grid) DO change track count by breakpoint and are asserted.

ALL_PATTERNS: dict[str, ComponentPattern] = {
    "drawer": DRAWER_PATTERN,
    "grid": GRID_PATTERN,
    "metrics": METRICS_PATTERN,
    "action_grid": ACTION_GRID_PATTERN,
}

# ---------------------------------------------------------------------------
# Display-mode → pattern mapping
# ---------------------------------------------------------------------------
#
# Keyed by the UPPER-cased DisplayMode value (region.display.upper()). Only
# modes whose region primitive emits a viewport-media-query-driven responsive
# grid are listed — these are the ones a viewport-width harness can assert
# deterministically. Notable omission: DETAIL (`.dz-detail-row`) switches via
# an `@container (width > 32rem)` query, NOT a viewport media query, so a
# viewport-width assertion can't express it without becoming a false signal —
# it's deliberately excluded (#1295).
_DISPLAY_PATTERN_MAP: dict[str, list[str]] = {
    "GRID": ["grid"],
    "METRICS": ["metrics"],
    "SUMMARY": ["metrics"],
    "ACTION_GRID": ["action_grid"],
}


# ---------------------------------------------------------------------------
# AppSpec → pattern derivation
# ---------------------------------------------------------------------------


def derive_patterns_from_appspec(
    appspec: AppSpec,
) -> dict[str, list[ComponentPattern]]:
    """Map page paths to their expected responsive component patterns.

    Returns ``{page_path: [ComponentPattern, ...]}``.

    * Workspace pages (``/app/workspaces/<name>``) get :data:`DRAWER_PATTERN`
      (app-shell chrome) + one region pattern per region ``display`` mode that
      maps to a viewport-responsive grid (GRID / METRICS / SUMMARY /
      ACTION_GRID). The ``.dz-dashboard-grid`` container itself is NOT asserted
      — it's a uniform 12-track grid at every viewport (responsiveness is
      card-span based, not column-count), so it isn't viewport-assertable (#1295).
    * List surfaces (``/app/<entity>``) get :data:`DRAWER_PATTERN` only — a
      list page renders a table, not a responsive column grid, so asserting
      grid columns there would be a false signal (#1295).
    """
    result: dict[str, list[ComponentPattern]] = {}

    # #1295 — paths must be the real app-shell routes. Pre-fix this derived
    # bare "/<name>" paths (and put DRAWER on "/", the marketing root that
    # has NO app-shell), so `run-viewport` navigated to non-app-shell URLs
    # and every assertion came back "Element not found" (0/37). The app-shell
    # chrome (sidebar + toggle) renders on every /app page; workspaces live
    # at /app/workspaces/<name>, entity-list surfaces at /app/<entity>.

    # Workspaces — app-shell pages at /app/workspaces/<name>
    for ws in appspec.workspaces:
        path = f"/app/workspaces/{ws.name}"

        # Every workspace renders the app-shell chrome; region display modes
        # add their own viewport-responsive grids. The `.dz-dashboard-grid`
        # container is NOT asserted — it's a uniform 12-track grid at every
        # viewport (responsiveness is per-card col-span, not column-count), the
        # same fiction class as the old per-stage grid_1_2 / grid_2_3 patterns
        # (#1295 — confirmed by the live CI run).
        patterns: list[ComponentPattern] = [DRAWER_PATTERN]

        # Region-level patterns (from display mode)
        for region in ws.regions:
            display = (
                region.display.upper()
                if hasattr(region.display, "upper")
                else str(region.display).upper()
            )
            for pat_name in _DISPLAY_PATTERN_MAP.get(display, []):
                # Avoid duplicates
                if pat_name in ALL_PATTERNS and ALL_PATTERNS[pat_name] not in patterns:
                    patterns.append(ALL_PATTERNS[pat_name])

        result[path] = patterns

    # Standalone list surfaces — entity-list pages at /app/<entity>. These
    # are also /app pages, so they carry the app-shell drawer chrome. A list
    # page renders a table, not a responsive column grid, so DRAWER is the
    # only viewport-assertable pattern here (#1295).
    for surface in appspec.surfaces:
        mode = surface.mode.upper() if hasattr(surface.mode, "upper") else str(surface.mode).upper()
        if mode == "LIST":
            entity_slug = (getattr(surface, "entity_ref", "") or surface.name).lower()
            path = f"/app/{entity_slug}"
            result.setdefault(path, [])
            if DRAWER_PATTERN not in result[path]:
                result[path].append(DRAWER_PATTERN)

    return result
