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
        whatever the IR carries (`LIST`, `METRICS`, etc.)."""
        text = TEMPLATE_PATH.read_text()
        assert "(r.display or 'list') | lower" in text


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

    def test_min_height_reservations_for_known_display_modes(self) -> None:
        """Each well-known display mode gets a min-height reservation
        scoped to its `data-display` attribute. If the framework
        adds a new display mode, this list grows."""
        text = self._css()
        # The display modes are paired with min-height; we just
        # verify each appears in the CSS as a data-display selector.
        for mode in (
            "summary",
            "metrics",
            "chart",
            "kanban",
            "diagram",
            "profile_card",
        ):
            sel = f'.dz-card-body[data-display="{mode}"]'
            assert sel in text, f"missing min-height reservation for {mode}"


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
