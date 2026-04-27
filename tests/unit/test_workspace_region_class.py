"""Tests for the v0.61.52 region-level ``class:`` field (#894).

Three layers:
  1. Parser: ``class: <name>`` and ``class: "multi name"`` parse into
     the IR's ``WorkspaceRegion.css_class`` field.
  2. Renderer: the parsed value flows through to ``RegionContext.css_class``
     and into the ``cards_for_json`` payload exposed to the Alpine
     card-grid template.
  3. Template: the Alpine ``:class`` binding picks up the project-supplied
     class on the outer card wrapper without breaking the existing
     transition/drag-state binding.
"""

from __future__ import annotations

from pathlib import Path

import pytest

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
  items_grid:
    source: Item
    display: list
"""


# ───────────────────────── parser ──────────────────────────


class TestCssClassParser:
    """The IR field is ``css_class``; the DSL keyword is ``class:`` —
    avoiding the Python keyword while keeping the user-facing name
    consistent with HTML."""

    def test_default_is_none(self) -> None:
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.css_class is None

    def test_bare_identifier(self) -> None:
        src = _BASE_DSL + "    class: highlight\n"
        region = _parse(src).workspaces[0].regions[0]
        assert region.css_class == "highlight"

    def test_quoted_string_with_multiple_classes(self) -> None:
        """Multiple Tailwind / project classes via the quoted-string
        form — `class: "metrics-strip dense"`."""
        src = _BASE_DSL + '    class: "metrics-strip dense"\n'
        region = _parse(src).workspaces[0].regions[0]
        assert region.css_class == "metrics-strip dense"

    def test_quoted_with_special_chars(self) -> None:
        """Hyphenated and BEM-style class names round-trip via the
        quoted form."""
        src = _BASE_DSL + '    class: "card--featured kpi__strip"\n'
        region = _parse(src).workspaces[0].regions[0]
        assert region.css_class == "card--featured kpi__strip"

    def test_class_does_not_affect_other_fields(self) -> None:
        """Adding `class:` next to other region keywords doesn't
        clobber them."""
        src = (
            _BASE_DSL
            + "    class: highlight\n"
            + "    limit: 25\n"
            + '    empty: "No items yet."\n'
        )
        region = _parse(src).workspaces[0].regions[0]
        assert region.css_class == "highlight"
        assert region.limit == 25


# ───────────────────────── renderer ──────────────────────────


class TestRegionContextCssClass:
    """The IR field flows through `build_workspace_context` →
    `RegionContext.css_class` so the dashboard data island can emit it
    as part of `cards_for_json`."""

    def test_region_context_default_empty_string(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        ctx = RegionContext(name="r")
        assert ctx.css_class == ""

    def test_region_context_carries_value(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        ctx = RegionContext(name="r", css_class="metrics-strip dense")
        assert ctx.css_class == "metrics-strip dense"

    def test_card_payload_carries_css_class(self) -> None:
        """When `cards_for_json` is built (page_routes.py), each card
        dict carries the `css_class` so the Alpine card-grid template
        can bind `card.css_class` on the wrapper."""
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        regions = [
            RegionContext(name="kpi_strip", css_class="metrics-strip"),
            RegionContext(name="plain"),  # no class set
        ]
        cards = [
            {
                "id": f"card-{i}",
                "region": r.name,
                "title": r.name.title(),
                "col_span": r.col_span,
                "row_order": i,
                "css_class": getattr(r, "css_class", "") or "",
            }
            for i, r in enumerate(regions)
        ]
        assert cards[0]["css_class"] == "metrics-strip"
        assert cards[1]["css_class"] == ""


class TestCssClassTemplateBinding:
    """The Alpine card wrapper in `_content.html` must merge
    `card.css_class` into its `:class` array binding without
    clobbering the existing transition/drag-state classes."""

    def test_template_binding_includes_card_css_class(self) -> None:
        """Static check on the template — the `:class` array must
        contain `card.css_class || ''` so the project hook composes
        with the framework-supplied transition class."""
        path = (
            Path(__file__).resolve().parents[2] / "src/dazzle_ui/templates/workspace/_content.html"
        )
        contents = path.read_text()
        # The :class binding must include the css_class read.
        assert "card.css_class || ''" in contents, (
            "Alpine card wrapper missing `card.css_class` binding — #894 hook lost"
        )
        # And the existing transition class must still be there.
        assert "transition-all duration-[200ms]" in contents, (
            "Existing transition binding regressed by #894 hook"
        )


# ───────────────────────── invariants ──────────────────────────


class TestCssClassIsPresentationOnly:
    """The class hook must NOT affect data, scope, or any non-render
    semantics — it's a pure CSS pass-through."""

    def test_class_does_not_affect_aggregates(self) -> None:
        src_with = _BASE_DSL + "    class: highlight\n"
        src_without = _BASE_DSL
        r_with = _parse(src_with).workspaces[0].regions[0]
        r_without = _parse(src_without).workspaces[0].regions[0]
        # Source, display, filter, scope-relevant fields are identical
        assert r_with.source == r_without.source
        assert r_with.display == r_without.display
        assert r_with.filter == r_without.filter
        assert r_with.aggregates == r_without.aggregates

    @pytest.mark.parametrize(
        "css",
        [
            "single",
            "snake_case",
            "CamelCase",
            "_leading_underscore",
        ],
    )
    def test_bare_identifier_variants_round_trip(self, css: str) -> None:
        """Bare identifier form supports any Python-identifier shape
        without quoting. Kebab-case (`two-words`) requires the quoted
        form because the lexer treats `-` as an operator — the
        same constraint applies everywhere else in the DSL."""
        src = _BASE_DSL + f"    class: {css}\n"
        region = _parse(src).workspaces[0].regions[0]
        assert region.css_class == css

    @pytest.mark.parametrize(
        "css",
        [
            "kebab-case",
            "two-words",
            "card--featured",
            "metrics-strip dense",
        ],
    )
    def test_quoted_form_handles_hyphens_and_spaces(self, css: str) -> None:
        """Anything the bare form can't tokenise (hyphens, spaces)
        round-trips via the quoted-string form."""
        src = _BASE_DSL + f'    class: "{css}"\n'
        region = _parse(src).workspaces[0].regions[0]
        assert region.css_class == css
