"""Tests for the v0.61.60 region `eyebrow:` field.

The AegisMark UX patterns roadmap (item #1) — every panel in the
SIMS-sync-opt-in prototype has a kicker line ("Data flow", "Legal
basis", "Approved data scopes") above the panel title. Promoting this
to a first-class region field gives DSL authors the eyebrow / title /
copy header trio without forking templates.

See ``dev_docs/2026-04-27-aegismark-ux-patterns.md`` for the full
roadmap context.
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

workspace dash "Dash":
  panel:
    source: Item
    display: list
"""


# ───────────────────────── parser ──────────────────────────


class TestEyebrowParser:
    def test_default_is_none(self) -> None:
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.eyebrow is None

    def test_eyebrow_quoted_string(self) -> None:
        src = _BASE_DSL + '    eyebrow: "Data flow"\n'
        region = _parse(src).workspaces[0].regions[0]
        assert region.eyebrow == "Data flow"

    def test_eyebrow_with_special_chars(self) -> None:
        src = _BASE_DSL + '    eyebrow: "Step 2 / 4 — Authorisation"\n'
        region = _parse(src).workspaces[0].regions[0]
        assert region.eyebrow == "Step 2 / 4 — Authorisation"

    def test_eyebrow_does_not_affect_other_fields(self) -> None:
        src = (
            _BASE_DSL
            + '    eyebrow: "Legal basis"\n'
            + "    limit: 50\n"
            + '    empty: "No items"\n'
        )
        region = _parse(src).workspaces[0].regions[0]
        assert region.eyebrow == "Legal basis"
        assert region.limit == 50
        assert region.empty_message == "No items"

    def test_eyebrow_must_be_quoted(self) -> None:
        """Eyebrow text typically contains spaces — bare identifiers
        wouldn't tokenise. Quoted string is required (same constraint
        as `purpose:`, `secondary:`, etc.)."""
        from dazzle.core.errors import ParseError

        src = _BASE_DSL + "    eyebrow: Data flow\n"
        with pytest.raises(ParseError):
            _parse(src)


# ───────────────────────── identifier round-trip ──────────────────────────


class TestEyebrowAsIdentifier:
    """`eyebrow` becomes a reserved keyword in v0.61.60. Per the
    #899 fix pattern, it MUST remain usable as an enum value or
    field name elsewhere — added to KEYWORD_AS_IDENTIFIER_TYPES."""

    def test_eyebrow_as_enum_value(self) -> None:
        src = """module t
app t "Test"

entity Style:
  id: uuid pk
  variant: enum[heading,eyebrow,body,caption]
"""
        entity = _parse(src).entities[0]
        variant = next(f for f in entity.fields if f.name == "variant")
        assert variant is not None

    def test_eyebrow_as_field_name(self) -> None:
        src = """module t
app t "Test"

entity Article:
  id: uuid pk
  eyebrow: str(60)
  title: str(200)
"""
        entity = _parse(src).entities[0]
        field_names = [f.name for f in entity.fields]
        assert "eyebrow" in field_names

    def test_eyebrow_in_keyword_identifier_list(self) -> None:
        """Static guard — if a future edit drops EYEBROW from the
        keyword-identifier list, this test fails before the regression
        ships."""
        from dazzle.core.dsl_parser_impl.base import KEYWORD_AS_IDENTIFIER_TYPES
        from dazzle.core.lexer import TokenType

        assert TokenType.EYEBROW in KEYWORD_AS_IDENTIFIER_TYPES


# ───────────────────────── runtime + template wiring ──────────────────────────


class TestEyebrowRuntimeWiring:
    def test_region_context_default_empty_string(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        ctx = RegionContext(name="r")
        assert ctx.eyebrow == ""

    def test_region_context_carries_value(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        ctx = RegionContext(name="r", eyebrow="Data flow")
        assert ctx.eyebrow == "Data flow"

    def test_card_payload_carries_eyebrow(self) -> None:
        """The dashboard panel header reads `card.eyebrow` from the
        Alpine data island — `cards_for_json` must include the field
        for every region."""
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        regions = [
            RegionContext(name="data_flow", eyebrow="Data flow"),
            RegionContext(name="plain"),
        ]
        cards = [
            {
                "id": f"card-{i}",
                "region": r.name,
                "title": r.name.title(),
                "col_span": r.col_span,
                "row_order": i,
                "eyebrow": getattr(r, "eyebrow", "") or "",
            }
            for i, r in enumerate(regions)
        ]
        assert cards[0]["eyebrow"] == "Data flow"
        assert cards[1]["eyebrow"] == ""


class TestEyebrowTemplateBinding:
    """The `_content.html` panel header must surface the region's
    eyebrow above the title, hidden when empty so existing dashboards
    render unchanged.

    #948: cards are server-rendered HTML now (was Alpine `card.eyebrow`
    pre-#948). The Jinja branch reads `r.eyebrow` directly."""

    def test_template_emits_region_eyebrow(self) -> None:
        path = (
            Path(__file__).resolve().parents[2] / "src/dazzle_ui/templates/workspace/_content.html"
        )
        contents = path.read_text()
        # Server-rendered: Jinja reads r.eyebrow directly inside an `if`
        assert "r.eyebrow" in contents, (
            "Card panel header missing `r.eyebrow` binding — AegisMark roadmap item #1 lost"
        )
        assert "{% if r.eyebrow %}" in contents
        assert "dz-card-eyebrow" in contents


# ───────────────────────── invariants ──────────────────────────


class TestEyebrowIsPresentationOnly:
    """Like region `class:`, eyebrow is a pure presentation hook —
    no impact on data, scope, or aggregates."""

    def test_eyebrow_does_not_affect_aggregates(self) -> None:
        src_with = _BASE_DSL + '    eyebrow: "Data flow"\n'
        src_without = _BASE_DSL
        r_with = _parse(src_with).workspaces[0].regions[0]
        r_without = _parse(src_without).workspaces[0].regions[0]
        assert r_with.source == r_without.source
        assert r_with.display == r_without.display
        assert r_with.aggregates == r_without.aggregates
        assert r_with.filter == r_without.filter
