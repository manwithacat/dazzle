"""Tests for #962 — workspace card-body height reservation prevents CLS.

The htmx region fetch lands content asynchronously; pre-#962 the card
body started with the skeleton's natural height and grew to the
content's actual height when the swap landed, pushing every card
below it down the page. Web Vitals reported CLS scores of 0.18-0.37
on AegisMark workspaces (>0.1 = "needs improvement"; >0.25 = "poor").

Fix: per-display-mode `min-height` on `.dz-card-body`, set via a
`data-display` attribute the template populates from
`RegionContext.display`. The card's parent reserves the height
before the fetch lands, so when content arrives, only the card's
own internal layout shifts (bounded), not the surrounding cards.

These tests pin both ends of that contract:
- The template emits `data-display` correctly per region
- The CSS reserves a `min-height` for every well-known display mode
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = REPO_ROOT / "src/dazzle_ui/templates/workspace/_content.html"
DASHBOARD_CSS = REPO_ROOT / "src/dazzle_ui/runtime/static/css/components/dashboard.css"
DASHBOARD_JS = REPO_ROOT / "src/dazzle_ui/runtime/static/js/dashboard-builder.js"


class TestTemplateEmitsDataDisplay:
    def test_card_body_carries_data_display_attribute(self) -> None:
        text = TEMPLATE_PATH.read_text()
        # Generic check: the card body div emits a data-display
        assert 'data-display="' in text

    def test_data_display_is_lowercased(self) -> None:
        """The CSS rules match lowercase; the template must lower
        whatever the IR carries (`LIST`, `METRICS`, etc.).
        `RegionContext.display` is always set (Pydantic default
        \"LIST\"), so no `or 'list'` fallback is needed in the
        template — the `| lower` filter is the only transform."""
        text = TEMPLATE_PATH.read_text()
        assert "r.display | lower" in text


class TestCssReservesMinHeight:
    def _css(self) -> str:
        return DASHBOARD_CSS.read_text()

    def test_default_min_height_set(self) -> None:
        """The default `.dz-card-body` rule reserves height for the
        common list/table shape so unknown display values fall
        through to a safe value."""
        text = self._css()
        # Match "min-height: NNNpx" inside the .dz-card-body rule
        idx = text.index(".dz-card-body {")
        end = text.index("}", idx)
        block = text[idx:end]
        assert "min-height:" in block

    def test_every_display_mode_has_min_height_or_falls_through(self) -> None:
        """Every value of `DisplayMode` either gets its own
        `data-display=\"X\"` reservation OR is acknowledged to fall
        through to the 280px default. The allow-list below
        enumerates the latter so a new display mode added to the
        enum without a CSS rule trips this gate.

        Rationale: the pre-#962 fix's hardcoded six-element check
        was a sample, not a gate — half the enum values were
        invisible to it. Iterating the enum with an explicit
        fall-through allow-list converts this into a real
        regression check."""
        from dazzle.core.ir.workspaces import DisplayMode

        text = self._css()

        # Modes that are intentionally OK to inherit the 280px
        # default (small KPIs / niche surfaces / list-shaped
        # display modes that match the default already). Adding a
        # new mode? Either give it its own min-height in
        # dashboard.css or add it here with a one-line rationale.
        fall_through_ok = {
            "list",  # default 280px is for list shape
            "grid",  # tile-style content; 280px ok
            "tabbed_list",  # list-shaped, 280px ok
            "queue",  # list-shaped review queue
            "tree",  # variable-height; 280px is a reasonable middle
            "map",  # rare; 280px placeholder until real adopters surface
            "detail",  # single-record card; tighter than list but acceptable
            "progress",  # progress bar; tighter, but rare
            "activity_feed",  # list-shaped
            "sparkline",  # compact KPI row; small but rare alone
            "histogram",  # chart-like; the chart bucket already covers it implicitly
            "box_plot",  # same — chart-like
            "area_chart",  # chart-shaped, 280px is right
            "confirm_action_panel",  # rare modal-style content
        }

        missing: list[str] = []
        for mode in DisplayMode:
            value = mode.value
            sel = f'.dz-card-body[data-display="{value}"]'
            if sel in text or value in fall_through_ok:
                continue
            missing.append(value)

        assert not missing, (
            f"DisplayMode values without a CSS reservation AND not in "
            f"the fall-through allow-list: {sorted(missing)}\n"
            "Either add a `min-height` rule in dashboard.css for the "
            "new mode, or extend `fall_through_ok` here with a reason."
        )


class TestRenderedHtmlHasDataDisplay:
    """End-to-end check: render the workspace template with a region
    and verify the rendered HTML carries the data-display attribute."""

    @pytest.fixture
    def jinja_env(self):
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        return create_jinja_env()

    def test_rendered_card_body_has_data_display(self, jinja_env) -> None:
        from dazzle_ui.runtime.template_renderer import render_fragment
        from dazzle_ui.runtime.workspace_renderer import (
            RegionContext,
            WorkspaceContext,
        )

        ws = WorkspaceContext(
            name="test_ws",
            title="Test",
            regions=[
                RegionContext(name="r1", title="R1", display="METRICS"),
                RegionContext(name="r2", title="R2", display="LIST"),
            ],
        )
        html = render_fragment("workspace/_content.html", workspace=ws, primary_actions=[])
        assert 'data-display="metrics"' in html
        assert 'data-display="list"' in html

    def test_rendered_card_body_defaults_to_list_when_display_missing(self, jinja_env) -> None:
        from dazzle_ui.runtime.template_renderer import render_fragment
        from dazzle_ui.runtime.workspace_renderer import (
            RegionContext,
            WorkspaceContext,
        )

        ws = WorkspaceContext(
            name="test_ws",
            title="Test",
            regions=[
                # RegionContext.display defaults to "LIST" — verify
                # the lowercase form lands in the rendered HTML.
                RegionContext(name="r1", title="R1"),
            ],
        )
        html = render_fragment("workspace/_content.html", workspace=ws, primary_actions=[])
        assert 'data-display="list"' in html


class TestDashboardBuilderJs:
    """Runtime-added cards (via `addCard`) must also set the
    `data-display` attribute so the same reservation applies to
    cards inserted after first paint."""

    def test_build_card_sets_data_display(self) -> None:
        text = DASHBOARD_JS.read_text()
        assert 'setAttribute("data-display"' in text
