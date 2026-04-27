"""Tests for the v0.61.63 region `title:` override field (#903).

Workspace region cards auto-derive their title from the snake_case
region key (e.g. `hero_marked_overnight` → "Hero Marked Overnight").
For prototype-fidelity dashboards this produces ugly PascalCase
titles. The Alpine template already binds `card.title`; this adds the
DSL/IR/parser plumbing to override the auto-derivation with an
explicit string.

Pairs with the `eyebrow:` field shipped in v0.61.60 — together they
complete the "eyebrow / title / copy" panel header trio.
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
  hero_marked_overnight:
    source: Item
    display: list
"""


# ───────────────────────── parser ──────────────────────────


class TestTitleParser:
    def test_default_is_none(self) -> None:
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.title is None

    def test_title_override_parses(self) -> None:
        src = _BASE_DSL + '    title: "Marked overnight"\n'
        region = _parse(src).workspaces[0].regions[0]
        assert region.title == "Marked overnight"

    def test_title_with_eyebrow_both_parse(self) -> None:
        """The #903 repro DSL — both `title:` and `eyebrow:` on the
        same region. The original v0.61.61 parser failed on `title:`
        before reaching `eyebrow:`."""
        src = _BASE_DSL + '    title: "Marked overnight"\n' + '    eyebrow: "Today"\n'
        region = _parse(src).workspaces[0].regions[0]
        assert region.title == "Marked overnight"
        assert region.eyebrow == "Today"

    def test_empty_string_treated_as_none(self) -> None:
        """Per #903 edge-case spec: empty title falls back to
        auto-derived. The IR records None so the renderer's `or`
        fallback fires."""
        src = _BASE_DSL + '    title: ""\n'
        region = _parse(src).workspaces[0].regions[0]
        assert region.title is None

    def test_title_must_be_quoted(self) -> None:
        """Titles typically contain spaces — bare identifier wouldn't
        tokenise. Same constraint as `eyebrow:` and `purpose:`."""
        from dazzle.core.errors import ParseError

        src = _BASE_DSL + "    title: Marked overnight\n"
        with pytest.raises(ParseError):
            _parse(src)


# ───────────────────────── identifier round-trip ──────────────────────────


class TestTitleAsIdentifier:
    """`title` is the single most common field name in the world —
    every entity-shaped concept has one. MUST remain usable as a
    field name and enum value (per the #899 fix pattern)."""

    def test_title_as_entity_field_name(self) -> None:
        """Most common case — entity has a `title` field."""
        src = """module t
app t "Test"

entity Article:
  id: uuid pk
  title: str(200)
  body: text
"""
        entity = _parse(src).entities[0]
        field_names = [f.name for f in entity.fields]
        assert "title" in field_names

    def test_title_as_enum_value(self) -> None:
        src = """module t
app t "Test"

entity Section:
  id: uuid pk
  variant: enum[heading,title,subtitle,body]
"""
        entity = _parse(src).entities[0]
        variant = next(f for f in entity.fields if f.name == "variant")
        assert variant is not None

    def test_title_is_not_a_lexer_keyword(self) -> None:
        """`title` is NOT a lexer keyword — it's string-matched against
        the IDENTIFIER value in the workspace region parser. This is
        deliberate: making it a keyword would break every parser that
        does `expect(IDENTIFIER)` and expected `title` as a literal
        identifier (flow assertions, demo blocks, etc.). The
        keyword-identifier escape hatch from #899 is the wrong
        approach here — keep `title` as an IDENTIFIER everywhere."""
        from dazzle.core.lexer import TokenType

        # Sanity check — TITLE token must NOT exist
        assert not hasattr(TokenType, "TITLE"), (
            "`title` was promoted to a lexer keyword — this breaks every "
            "`expect(IDENTIFIER)` site. Use string-match in the workspace "
            "region parser instead."
        )


# ───────────────────────── runtime renderer ──────────────────────────


class TestTitleRenderingFallback:
    """The renderer's `card.title = region.title or auto_derived`
    contract: explicit title wins; missing/empty falls back."""

    def test_explicit_title_used_when_set(self) -> None:
        """Simulate the `cards_for_json` / RegionContext title resolution
        as it lands in the Alpine data payload."""
        src = _BASE_DSL + '    title: "Marked overnight"\n'
        region = _parse(src).workspaces[0].regions[0]
        # Mirror the renderer's fallback expression
        rendered_title = (region.title or "") or region.name.replace("_", " ").title()
        assert rendered_title == "Marked overnight"

    def test_auto_derived_when_title_missing(self) -> None:
        """Without explicit `title:`, fall back to the snake_case ->
        TitleCase derivation."""
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        rendered_title = (region.title or "") or region.name.replace("_", " ").title()
        assert rendered_title == "Hero Marked Overnight"

    def test_empty_string_title_falls_back(self) -> None:
        """`title: ""` → IR title is None → renderer uses auto-derived."""
        src = _BASE_DSL + '    title: ""\n'
        region = _parse(src).workspaces[0].regions[0]
        rendered_title = (region.title or "") or region.name.replace("_", " ").title()
        assert rendered_title == "Hero Marked Overnight"


# ───────────────────────── invariants ──────────────────────────


class TestTitleIsPresentationOnly:
    """Pure presentation hook — no impact on data, scope, or
    aggregates."""

    def test_title_does_not_affect_other_fields(self) -> None:
        src_with = _BASE_DSL + '    title: "Marked overnight"\n'
        src_without = _BASE_DSL
        r_with = _parse(src_with).workspaces[0].regions[0]
        r_without = _parse(src_without).workspaces[0].regions[0]
        assert r_with.source == r_without.source
        assert r_with.display == r_without.display
        assert r_with.aggregates == r_without.aggregates
        assert r_with.filter == r_without.filter
