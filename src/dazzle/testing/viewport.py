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


@dataclass
class ComponentPattern:
    """Named collection of viewport assertions for a UI component."""

    name: str
    assertions: list[ViewportAssertion]


@dataclass
class ViewportAssertionResult:
    """Result of evaluating one assertion."""

    assertion: ViewportAssertion
    actual: str | None
    passed: bool
    error: str | None = None


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

# -- Drawer (app_shell.html) ------------------------------------------------

DRAWER_PATTERN = ComponentPattern(
    name="drawer",
    assertions=[
        # Mobile: sidebar hidden, hamburger visible
        ViewportAssertion(
            selector=".drawer-side",
            property="visibility",
            expected="hidden",
            viewport="mobile",
            description="Sidebar hidden on mobile",
        ),
        ViewportAssertion(
            selector='label[for="dz-drawer"].drawer-button',
            property="display",
            expected=["flex", "inline-flex", "block", "inline-block"],
            viewport="mobile",
            description="Hamburger button visible on mobile",
        ),
        # Desktop: sidebar visible when open, navbar toggle hidden
        ViewportAssertion(
            selector=".drawer-side",
            property="visibility",
            expected="visible",
            viewport="desktop",
            description="Sidebar visible on desktop",
        ),
        ViewportAssertion(
            selector='label[for="dz-drawer"].drawer-button',
            property="display",
            expected="none",
            viewport="desktop",
            description="Hamburger button hidden on desktop",
        ),
    ],
)

# -- Workspace card grid (grid.html): 1 → 2 → 3 cols ----------------------

GRID_1_2_3_PATTERN = ComponentPattern(
    name="grid_1_2_3",
    assertions=[
        ViewportAssertion(
            selector=".grid.sm\\:grid-cols-2.lg\\:grid-cols-3",
            property="grid-template-columns",
            expected=["repeat(1, minmax(0, 1fr))", "1fr"],
            viewport="mobile",
            description="Single column grid on mobile",
        ),
        ViewportAssertion(
            selector=".grid.sm\\:grid-cols-2.lg\\:grid-cols-3",
            property="grid-template-columns",
            expected=["repeat(2, minmax(0, 1fr))", "1fr 1fr"],
            viewport="tablet",
            description="Two column grid on tablet",
        ),
        ViewportAssertion(
            selector=".grid.sm\\:grid-cols-2.lg\\:grid-cols-3",
            property="grid-template-columns",
            expected=["repeat(3, minmax(0, 1fr))", "1fr 1fr 1fr"],
            viewport="desktop",
            description="Three column grid on desktop",
        ),
    ],
)

# -- Console entity/surface list: 1 → 2 cols at md -------------------------

GRID_1_2_PATTERN = ComponentPattern(
    name="grid_1_2",
    assertions=[
        ViewportAssertion(
            selector=".grid.md\\:grid-cols-2",
            property="grid-template-columns",
            expected=["repeat(1, minmax(0, 1fr))", "1fr"],
            viewport="mobile",
            description="Single column on mobile",
        ),
        ViewportAssertion(
            selector=".grid.md\\:grid-cols-2",
            property="grid-template-columns",
            expected=["repeat(2, minmax(0, 1fr))", "1fr 1fr"],
            viewport="desktop",
            description="Two columns on desktop",
        ),
    ],
)

# -- Console dashboard stats: 1 → 3 cols at md -----------------------------

GRID_1_3_PATTERN = ComponentPattern(
    name="grid_1_3",
    assertions=[
        ViewportAssertion(
            selector=".grid.md\\:grid-cols-3",
            property="grid-template-columns",
            expected=["repeat(1, minmax(0, 1fr))", "1fr"],
            viewport="mobile",
            description="Single column stats on mobile",
        ),
        ViewportAssertion(
            selector=".grid.md\\:grid-cols-3",
            property="grid-template-columns",
            expected=["repeat(3, minmax(0, 1fr))", "1fr 1fr 1fr"],
            viewport="desktop",
            description="Three column stats on desktop",
        ),
    ],
)

# -- Workspace metrics: vertical → horizontal at lg ------------------------

STATS_PATTERN = ComponentPattern(
    name="stats",
    assertions=[
        ViewportAssertion(
            selector=".stats",
            property="flex-direction",
            expected="column",
            viewport="mobile",
            description="Stats stacked vertically on mobile",
        ),
        ViewportAssertion(
            selector=".stats",
            property="flex-direction",
            expected="row",
            viewport="desktop",
            description="Stats horizontal on desktop",
        ),
    ],
)

# -- Detail view: block → 3-col grid at sm ---------------------------------

DETAIL_VIEW_PATTERN = ComponentPattern(
    name="detail_view",
    assertions=[
        ViewportAssertion(
            selector=".sm\\:grid.sm\\:grid-cols-3",
            property="display",
            expected="block",
            viewport="mobile",
            description="Detail fields stacked on mobile",
        ),
        ViewportAssertion(
            selector=".sm\\:grid.sm\\:grid-cols-3",
            property="display",
            expected="grid",
            viewport="tablet",
            description="Detail fields in grid on tablet",
        ),
    ],
)

# -- Monitor wall: 2 → 3 cols at lg ----------------------------------------

GRID_2_3_PATTERN = ComponentPattern(
    name="grid_2_3",
    assertions=[
        ViewportAssertion(
            selector=".grid.lg\\:grid-cols-3",
            property="grid-template-columns",
            expected=["repeat(2, minmax(0, 1fr))", "1fr 1fr"],
            viewport="mobile",
            description="Two column grid on mobile (monitor wall)",
        ),
        ViewportAssertion(
            selector=".grid.lg\\:grid-cols-3",
            property="grid-template-columns",
            expected=["repeat(3, minmax(0, 1fr))", "1fr 1fr 1fr"],
            viewport="desktop",
            description="Three column grid on desktop (monitor wall)",
        ),
    ],
)

ALL_PATTERNS: dict[str, ComponentPattern] = {
    "drawer": DRAWER_PATTERN,
    "grid_1_2_3": GRID_1_2_3_PATTERN,
    "grid_1_2": GRID_1_2_PATTERN,
    "grid_1_3": GRID_1_3_PATTERN,
    "stats": STATS_PATTERN,
    "detail_view": DETAIL_VIEW_PATTERN,
    "grid_2_3": GRID_2_3_PATTERN,
}

# ---------------------------------------------------------------------------
# Stage → pattern mapping (derived from STAGE_GRID_MAP)
# ---------------------------------------------------------------------------

# Maps workspace stage names to the grid patterns they imply.
_STAGE_PATTERN_MAP: dict[str, list[str]] = {
    "focus_metric": [],  # single column, no responsive grid change
    "dual_pane_flow": ["grid_1_2"],  # md:grid-cols-2
    "scanner_table": [],  # single column, full-width table
    "monitor_wall": ["grid_2_3"],  # grid-cols-2 lg:grid-cols-3
    "command_center": [],  # 12-col grid with explicit spans
}

# Maps workspace region display modes to patterns.
_DISPLAY_PATTERN_MAP: dict[str, list[str]] = {
    "GRID": ["grid_1_2_3"],
    "METRICS": ["stats"],
    "SUMMARY": ["stats"],
    "DETAIL": ["detail_view"],
}


# ---------------------------------------------------------------------------
# AppSpec → pattern derivation
# ---------------------------------------------------------------------------


def derive_patterns_from_appspec(
    appspec: AppSpec,
) -> dict[str, list[ComponentPattern]]:
    """Map page paths to their expected responsive component patterns.

    Returns ``{page_path: [ComponentPattern, ...]}``.

    * Every app with workspaces or surfaces gets :data:`DRAWER_PATTERN`
      on ``"/"``.
    * Workspaces contribute stage-level and region-level patterns.
    * Surfaces with ``mode="list"`` that are not embedded in a workspace
      contribute ``GRID_1_2_PATTERN`` (the default list layout).
    """
    result: dict[str, list[ComponentPattern]] = {}

    has_content = bool(appspec.workspaces) or bool(appspec.surfaces)

    # Drawer on root page for any app with navigable content
    if has_content:
        result.setdefault("/", []).append(DRAWER_PATTERN)

    # Workspaces
    for ws in appspec.workspaces:
        path = f"/{ws.name}"

        patterns: list[ComponentPattern] = []

        # Stage-level patterns
        if ws.stage:
            stage_key = ws.stage.lower()
            for pat_name in _STAGE_PATTERN_MAP.get(stage_key, []):
                if pat_name in ALL_PATTERNS:
                    patterns.append(ALL_PATTERNS[pat_name])

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

        if patterns:
            result[path] = patterns

        # Drawer pattern applies to workspace pages too
        result.setdefault(path, [])
        if DRAWER_PATTERN not in result[path]:
            result[path].append(DRAWER_PATTERN)

    # Surfaces (standalone, not in workspaces)
    for surface in appspec.surfaces:
        mode = surface.mode.upper() if hasattr(surface.mode, "upper") else str(surface.mode).upper()
        if mode == "LIST":
            path = f"/{surface.name}"
            result.setdefault(path, []).append(GRID_1_2_PATTERN)

    return result
