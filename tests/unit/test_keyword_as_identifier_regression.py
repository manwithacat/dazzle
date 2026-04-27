"""Regression tests for the v0.61.55 keyword-shadowing bug (#899).

The display-mode batch (v0.61.52–v0.61.56) added several new lexer
tokens that, until v0.61.57, made common identifier names like
`primary`, `secondary`, `caption`, etc. unusable in enum literals
and field names.

Each token here MUST appear in `KEYWORD_AS_IDENTIFIER_TYPES` in
`src/dazzle/core/dsl_parser_impl/base.py`, so the parser still
treats it as an identifier in expression / enum contexts. Regression:
without this list, downstream projects with enums like
``school_phase: enum[primary, secondary, all_through, special]``
fail to parse — exactly the AegisMark scenario reported in #899.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl


def _parse_entity(src: str):  # type: ignore[no-untyped-def]
    fragment = parse_dsl(src, Path("test.dsl"))[5]
    return fragment.entities[0]


_BASE = """module t
app t "Test"

entity X:
  id: uuid pk
"""


# ─────────────────── #899 canonical repro ───────────────────


class TestSchoolPhaseEnumLiteral:
    """The exact repro from #899 — `enum[primary, secondary, ...]`
    parses on v0.61.57+ but failed on v0.61.55–v0.61.56."""

    def test_school_phase_enum_with_primary_secondary(self) -> None:
        src = """module t
app t "Test"

entity School:
  id: uuid pk
  school_phase: enum[primary,secondary,all_through,special]=secondary
"""
        entity = _parse_entity(src)
        phase = next(f for f in entity.fields if f.name == "school_phase")
        assert phase is not None


# ─────────────────── per-token round-trip ───────────────────


@pytest.mark.parametrize(
    "ident",
    [
        # v0.61.55 (#892) profile_card keys
        "primary",
        "secondary",
        "avatar_field",
        "stats",
        "facts",
        # v0.61.56 (#890) pipeline_steps key
        "caption",
        # v0.61.54 (#891) action_grid keys
        "actions",
        "tone",
        "count_aggregate",
        # v0.61.53 (#893) bar_track keys
        "track_max",
        "track_format",
        # v0.61.52 (#894) region class hook (Python keyword anyway, but
        # the lexer token CSS_CLASS = "class" — still pinning the
        # round-trip in case a downstream uses `enum[class_a, class_b]`)
    ],
)
def test_keyword_usable_as_enum_value(ident: str) -> None:
    """Each new region-block keyword must remain usable as an enum
    literal value — the canonical #899 failure mode."""
    src = f"""module t
app t "Test"

entity Item:
  id: uuid pk
  category: enum[alpha,{ident},gamma]
"""
    entity = _parse_entity(src)
    cat_field = next(f for f in entity.fields if f.name == "category")
    assert cat_field is not None


@pytest.mark.parametrize(
    "ident",
    [
        # Same set as enum-value test, focused on field-name usage
        "primary",
        "secondary",
        "stats",
        "facts",
        "caption",
        "actions",
        "tone",
        "track_max",
        "track_format",
    ],
)
def test_keyword_usable_as_field_name(ident: str) -> None:
    """Each new region-block keyword must remain usable as a plain
    entity field name. Some downstream projects might have a
    `primary: bool` flag or a `caption: str` description."""
    src = f"""module t
app t "Test"

entity Item:
  id: uuid pk
  {ident}: str(100)
"""
    entity = _parse_entity(src)
    field_names = [f.name for f in entity.fields]
    assert ident in field_names


# ─────────────────── invariant guard ───────────────────


class TestKeywordIdentifierListContainsNewTokens:
    """Static check on `KEYWORD_AS_IDENTIFIER_TYPES` itself — if a
    future edit removes any of these tokens from the list, the
    regression returns. Catches it at the source, not via a downstream
    project failing to upgrade."""

    def test_all_v0_61_5x_tokens_in_list(self) -> None:
        from dazzle.core.dsl_parser_impl.base import KEYWORD_AS_IDENTIFIER_TYPES
        from dazzle.core.lexer import TokenType

        required = [
            TokenType.AVATAR_FIELD,
            TokenType.PRIMARY,
            TokenType.SECONDARY,
            TokenType.STATS,
            TokenType.FACTS,
            TokenType.CAPTION,
            TokenType.ACTIONS,
            TokenType.TONE,
            TokenType.COUNT_AGGREGATE,
            TokenType.TRACK_MAX,
            TokenType.TRACK_FORMAT,
            TokenType.CSS_CLASS,
        ]
        missing = [t.name for t in required if t not in KEYWORD_AS_IDENTIFIER_TYPES]
        assert not missing, (
            f"Tokens missing from KEYWORD_AS_IDENTIFIER_TYPES: {missing} — "
            f"this regresses #899. Add them back."
        )
