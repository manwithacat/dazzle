"""Tests for the transitional ConditionExpr → legacy where-clause stringifier.

Pins the round-trip shape so the per-site migrations (Slices 1b–1e) can
keep using ``_fetch_count_metric`` / ``_fetch_scalar_metric``'s string
interface until Slice 1f retires it.

When Slice 1f retires the stringifier, these tests retire with it.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import Parser
from dazzle.core.ir.aggregate_legacy import condition_expr_to_legacy_where
from dazzle.core.lexer import tokenize


def _where_from_dsl(src: str) -> str | None:
    """Parse a one-line aggregate DSL and stringify its where-clause."""
    tokens = tokenize(src + "\n", Path("t.dsl"))
    parser = Parser(tokens, Path("t.dsl"))
    ref = parser.parse_aggregate_ref()
    return condition_expr_to_legacy_where(ref.where)


def test_none_returns_none() -> None:
    assert condition_expr_to_legacy_where(None) is None


def test_no_where_clause() -> None:
    assert _where_from_dsl("count(Task)") is None


def test_simple_eq() -> None:
    assert _where_from_dsl("count(Task where status = open)") == "status = open"


def test_boolean_literal_renders_lowercase() -> None:
    """Booleans render as ``true`` / ``false`` to match the legacy regex
    grammar's expectations (the regex never quoted RHS values)."""
    assert _where_from_dsl("count(Task where flagged = true)") == "flagged = true"
    assert _where_from_dsl("count(Task where flagged = false)") == "flagged = false"


def test_not_equals() -> None:
    assert _where_from_dsl("count(Task where status != done)") == "status != done"


def test_compound_and() -> None:
    out = _where_from_dsl("count(Task where status = open and priority = high)")
    assert out == "status = open and priority = high"


def test_compound_or() -> None:
    out = _where_from_dsl("count(Task where status = open or status = doing)")
    assert out == "status = open or status = doing"


def test_round_trip_via_parse_aggregate_where() -> None:
    """The legacy stringifier's output must parse cleanly through
    ``parse_aggregate_where`` — that's the whole point of the bridge."""
    from dazzle.http.runtime.aggregate_where_parser import parse_aggregate_where

    out = _where_from_dsl("count(Task where status = open and priority = high)")
    assert out is not None
    pred = parse_aggregate_where(out, known_columns={"status", "priority"})
    assert pred is not None
