"""Tests for the v0.61.54 action_grid display mode (#891).

Three layers:
  1. Parser: ``display: action_grid`` + ``actions:`` indented dash-list
     of ``{label, icon, count_aggregate, action, tone}`` entries
     parses into the IR.
  2. Renderer: ``ActionCardSpec`` IR flows through to
     ``RegionContext.action_cards`` with `action` resolved to a URL via
     `_action_to_url`. Per-card count_aggregate stays as a string for
     the runtime branch to fire.
  3. Template: ``action_grid.html`` renders one card per entry with
     tone-mapped palette tokens, optional icon, optional count badge,
     and tag-by-condition wrapper (anchor when card has a URL, div
     otherwise — never interpolated tag names).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import DisplayMode
from dazzle.core.ir.module import ModuleFragment
from dazzle.core.ir.workspaces import ActionCardSpec


def _parse(src: str) -> ModuleFragment:
    return parse_dsl(src, Path("test.dsl"))[5]


_BASE_DSL = """module t
app t "Test"
entity Task:
  id: uuid pk
  status: enum[todo,doing,done]
workspace dash "Dash":
  end_of_day:
    display: action_grid
    actions:
      - label: "Triage open tasks"
        icon: "clipboard-check"
        count_aggregate: count(Task where status = todo)
        action: task_list
        tone: warning
"""


# ───────────────────────── parser ──────────────────────────


class TestActionGridParser:
    def test_minimal_action_grid(self) -> None:
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.display == DisplayMode.ACTION_GRID
        assert len(region.action_cards) == 1
        card = region.action_cards[0]
        assert card.label == "Triage open tasks"
        assert card.icon == "clipboard-check"
        assert card.count_aggregate == "count ( Task where status = todo )"
        assert card.action == "task_list"
        assert card.tone == "warning"

    def test_label_only_card(self) -> None:
        """Only ``label:`` is required — other fields default."""
        src = """module t
app t "Test"
workspace dash "Dash":
  cards:
    display: action_grid
    actions:
      - label: "Just a label"
"""
        region = _parse(src).workspaces[0].regions[0]
        assert len(region.action_cards) == 1
        c = region.action_cards[0]
        assert c.label == "Just a label"
        assert c.icon == ""
        assert c.count_aggregate == ""
        assert c.action == ""
        assert c.tone == "neutral"

    def test_multiple_cards_preserve_order(self) -> None:
        src = """module t
app t "Test"
workspace dash "Dash":
  cards:
    display: action_grid
    actions:
      - label: "First"
      - label: "Second"
      - label: "Third"
"""
        region = _parse(src).workspaces[0].regions[0]
        labels = [c.label for c in region.action_cards]
        assert labels == ["First", "Second", "Third"]

    def test_action_accepts_quoted_string_with_query(self) -> None:
        """The issue example uses ``action: "marking_result_list?status=flagged"``
        — quoted-string form is required because `?` doesn't
        tokenise as part of an identifier."""
        src = """module t
app t "Test"
workspace dash "Dash":
  cards:
    display: action_grid
    actions:
      - label: "Flagged review"
        action: "marking_result_list?status=flagged"
"""
        region = _parse(src).workspaces[0].regions[0]
        assert region.action_cards[0].action == "marking_result_list?status=flagged"

    def test_action_accepts_bare_identifier(self) -> None:
        src = """module t
app t "Test"
workspace dash "Dash":
  cards:
    display: action_grid
    actions:
      - label: "Create"
        action: task_create
"""
        region = _parse(src).workspaces[0].regions[0]
        assert region.action_cards[0].action == "task_create"

    def test_invalid_tone_raises(self) -> None:
        from dazzle.core.errors import ParseError

        src = """module t
app t "Test"
workspace dash "Dash":
  cards:
    display: action_grid
    actions:
      - label: "X"
        tone: rainbow
"""
        with pytest.raises(ParseError, match="tone must be one of"):
            _parse(src)

    def test_unknown_key_raises(self) -> None:
        from dazzle.core.errors import ParseError

        src = """module t
app t "Test"
workspace dash "Dash":
  cards:
    display: action_grid
    actions:
      - label: "X"
        bogus: yes
"""
        with pytest.raises(ParseError, match="Unknown actions key"):
            _parse(src)

    def test_must_start_with_label(self) -> None:
        """When the dash-list entry doesn't lead with `label:`, the
        parser rejects. Two error paths reach this — `label_kw != "label"`
        for non-keyword tokens, OR the lexer's "reserved keyword" check
        for keywords like `icon`/`action`/`tone`. Either failure mode
        is acceptable; this test pins that an error IS raised."""
        from dazzle.core.errors import ParseError

        src = """module t
app t "Test"
workspace dash "Dash":
  cards:
    display: action_grid
    actions:
      - other_field: "x"
        label: "X"
"""
        with pytest.raises(ParseError, match="must start with `label:`"):
            _parse(src)


# ───────────────────────── _action_to_url ──────────────────────────


class TestActionToUrl:
    """The helper resolves a card's `action:` value to a URL."""

    def test_empty_returns_empty(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import _action_to_url

        assert _action_to_url("") == ""

    def test_bare_identifier_slugifies(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import _action_to_url

        assert _action_to_url("task_create") == "/app/task-create"
        assert _action_to_url("Parents_Evening_Notes") == "/app/parents-evening-notes"

    def test_literal_url_passes_through(self) -> None:
        """When the value starts with `/` it's used as-is — author's
        explicit choice."""
        from dazzle_ui.runtime.workspace_renderer import _action_to_url

        assert (
            _action_to_url("/app/parents-evening/create?step=1")
            == "/app/parents-evening/create?step=1"
        )

    def test_bare_with_query_preserves_query(self) -> None:
        """``marking_result_list?status=flagged`` → slugify the name,
        keep the query verbatim."""
        from dazzle_ui.runtime.workspace_renderer import _action_to_url

        assert (
            _action_to_url("marking_result_list?status=flagged")
            == "/app/marking-result-list?status=flagged"
        )


# ───────────────────────── RegionContext + cards ──────────────────────────


class TestActionGridContext:
    def test_region_context_default_empty(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        ctx = RegionContext(name="r")
        assert ctx.action_cards == []

    def test_region_context_carries_cards(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        ctx = RegionContext(
            name="r",
            action_cards=[
                {
                    "label": "Test",
                    "icon": "clock",
                    "count_aggregate": "count(Task)",
                    "url": "/app/task",
                    "tone": "accent",
                }
            ],
        )
        assert len(ctx.action_cards) == 1
        assert ctx.action_cards[0]["url"] == "/app/task"

    def test_action_card_spec_defaults(self) -> None:
        c = ActionCardSpec(label="Hello")
        assert c.icon == ""
        assert c.count_aggregate == ""
        assert c.action == ""
        assert c.tone == "neutral"


# ───────────────────────── template wiring ──────────────────────────


class TestActionGridTemplateWiring:
    def test_template_map_includes_action_grid(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert "ACTION_GRID" in DISPLAY_TEMPLATE_MAP
        assert DISPLAY_TEMPLATE_MAP["ACTION_GRID"] == "workspace/regions/action_grid.html"

    def test_template_file_exists(self) -> None:
        path = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/templates/workspace/regions/action_grid.html"
        )
        assert path.is_file()

    def test_template_uses_region_card_macro(self) -> None:
        path = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/templates/workspace/regions/action_grid.html"
        )
        contents = path.read_text()
        assert "{% call region_card" in contents

    def test_template_does_not_interpolate_tag_name(self) -> None:
        """Security guard: the wrapper must use explicit if/else with
        literal `<a>` and `<div>` tags, never `<{{ _Tag }}>` style
        interpolation. Semgrep flagged the original draft for the
        latter; this test pins the safer pattern."""
        path = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/templates/workspace/regions/action_grid.html"
        )
        contents = path.read_text()
        assert "<{{" not in contents, (
            "action_grid.html must not interpolate HTML tag names — XSS surface"
        )
        assert "</{{" not in contents
        # Both branches must be present
        assert "<a href=" in contents
        assert '<div class="dz-action-card' in contents


# ───────────────────────── invariants ──────────────────────────


class TestActionGridIsCountOnly:
    """Per the issue's MVP scope: action_grid only supports count(...)
    aggregates, not avg/sum/min/max. The runtime branch silently skips
    non-count expressions (card renders without a count badge)."""

    def test_action_card_spec_accepts_any_aggregate_text(self) -> None:
        """The IR doesn't reject avg/sum/min/max — the runtime branch
        gates count-only support. That keeps the IR forward-compatible
        for when scalar aggregates land."""
        c = ActionCardSpec(label="X", count_aggregate="avg(score)")
        assert c.count_aggregate == "avg(score)"
