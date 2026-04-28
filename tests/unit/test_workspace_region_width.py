"""Tests for the v0.61.83 region-level ``width:`` field (#914).

Three layers:
  1. Parser: ``width: <int>`` clamps to 1..12 and parses into the IR's
     ``WorkspaceRegion.width`` field. Default is None ("use stage default").
  2. Renderer: when ``width`` is set, it overrides both the stage-default
     col_span and the kanban auto-promotion to 12. Saved layouts (drag-resize
     via the dashboard builder) still win — verified separately by the
     `apply_layout_to_workspace` plumbing.
  3. The DSL-author proposal motivating this: hero strips and KPI rows
     should set ``width: 3`` (or 4, 6, etc.) without projects having to
     ship `:has()` + `!important` CSS overrides per region name.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.module import ModuleFragment


def _parse(src: str) -> ModuleFragment:
    return parse_dsl(src, Path("test.dsl"))[5]


_BASE_DSL = """module t
app t "Test"
entity Item:
  id: uuid pk
  name: str(50)
workspace dash "Dash":
  hero_strip:
    source: Item
    display: list
"""


# ───────────────────────── parser ──────────────────────────


class TestWidthParser:
    def test_default_is_none(self) -> None:
        """Omitting `width:` keeps the field as None so the runtime
        falls back to the stage default."""
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.width is None

    def test_explicit_value_within_range(self) -> None:
        src = _BASE_DSL + "    width: 3\n"
        region = _parse(src).workspaces[0].regions[0]
        assert region.width == 3

    def test_clamps_below_one(self) -> None:
        """Out-of-range values clamp to the nearest valid bound (1)
        rather than erroring — keeps the parser permissive for downstream
        DSL-author typos."""
        src = _BASE_DSL + "    width: 0\n"
        region = _parse(src).workspaces[0].regions[0]
        assert region.width == 1

    def test_clamps_above_twelve(self) -> None:
        """13+ clamps to 12 (the dashboard grid maxes at 12 columns)."""
        src = _BASE_DSL + "    width: 13\n"
        region = _parse(src).workspaces[0].regions[0]
        assert region.width == 12


# ─────────────────────── renderer plumbing ──────────────────


class TestWidthFlowsToColSpan:
    """The renderer's `_default_col_span` fallback returns 12 for the
    `hero_strip` stage label this fixture uses (no preset rule for that
    name → falls through to default 12). When `width:` is set, the
    explicit value should win regardless."""

    def _render_card_col_span(self, src: str) -> int:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        module = _parse(src)
        workspace = module.workspaces[0]
        ctx = build_workspace_context(workspace)
        # Find the matching card; use the first
        return ctx.regions[0].col_span

    def test_explicit_width_overrides_stage_default(self) -> None:
        """`width: 4` on a region whose stage default would be 12
        should yield col_span == 4."""
        src = _BASE_DSL + "    width: 4\n"
        assert self._render_card_col_span(src) == 4

    def test_omitted_width_falls_back_to_stage_default(self) -> None:
        """No `width:` → behaves exactly as before this feature landed."""
        # `hero_strip` is not in STAGE_DEFAULT_SPANS → returns 12.
        assert self._render_card_col_span(_BASE_DSL) == 12
