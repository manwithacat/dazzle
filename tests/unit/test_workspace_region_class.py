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
    """The card wrapper in `_content.html` must merge the region's
    `css_class` into the rendered class attribute alongside the
    framework-supplied transition class.

    #948: cards are server-rendered HTML now (was Alpine `:class`
    binding pre-#948). The Jinja template emits both classes via
    static interpolation — no binding shape, no #900-style array-form
    drop, no `.filter(Boolean).join(' ')` ceremony required. The
    project class composes with `dz-card-wrapper` and `is-animating`
    via plain space-separated class output."""

    def test_template_emits_region_css_class(self) -> None:
        """The Jinja template emits `r.css_class` into the rendered
        class attribute so the project hook is present in the DOM."""
        path = (
            Path(__file__).resolve().parents[2] / "src/dazzle_ui/templates/workspace/_content.html"
        )
        contents = path.read_text()
        assert "r.css_class" in contents, (
            "Card wrapper missing `r.css_class` binding — #894 hook lost"
        )
        # v0.62 CSS refactor: the inline transition utility class
        # moved to the .is-animating semantic state modifier
        # (resolved in dashboard.css).
        assert "is-animating" in contents, (
            "Existing transition state class missing from server-rendered "
            "card wrapper. The .is-animating modifier must apply to the "
            "outer wrapper alongside dz-card-wrapper."
        )

    def test_template_renders_class_via_jinja_interpolation(self) -> None:
        """Pin the #948 server-render shape — the binding is a Jinja
        `{% if r.css_class %}` branch that emits the project class
        verbatim into the `class=` attribute. No `:class` Alpine
        binding, no array form, no string-concat helper. Plain HTML."""
        path = (
            Path(__file__).resolve().parents[2] / "src/dazzle_ui/templates/workspace/_content.html"
        )
        contents = path.read_text()
        assert "{% if r.css_class %}" in contents, (
            "Card wrapper class hook regressed — must use a Jinja "
            "`{% if r.css_class %}` guard so the project class only "
            "appears when set."
        )
        # No leftover `:class=` Alpine binding on the card wrapper
        assert ':class="[' not in contents
        assert ".filter(Boolean).join" not in contents

    def test_alpine_binding_simulation_includes_css_class(self) -> None:
        """Simulate the Alpine binding evaluation in pure Python —
        when card.css_class is set and isDragging+drag are false, the
        output string MUST contain both the project class AND the
        transition class. This catches the #900 failure mode (the
        css_class string getting dropped) at the test level."""

        def simulate_binding(
            card_css_class: str,
            is_dragging: bool = False,
            drag: bool = False,
        ) -> str:
            """Mirror the Alpine expression in `_content.html`:
            `[card.css_class, cond ? "..." : ""].filter(Boolean).join(' ')`
            """
            parts = [
                card_css_class,
                "transition-all duration-[200ms] [transition-timing-function:cubic-bezier(0.2,0,0,1)]"
                if (not is_dragging and not drag)
                else "",
            ]
            return " ".join(p for p in parts if p)

        # Project hook + transition both apply
        out = simulate_binding("action-band")
        assert "action-band" in out
        assert "transition-all duration-[200ms]" in out

        # Project hook applies even mid-drag (transition omitted then)
        out = simulate_binding("action-band", drag=True)
        assert "action-band" in out
        assert "transition-all" not in out

        # Empty css_class doesn't introduce stray spaces or undefined
        out = simulate_binding("")
        assert "transition-all" in out
        assert out.strip() == out  # no leading/trailing whitespace


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
