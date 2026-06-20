"""Typed current_bucket sentinel tests (#1154).

Pins the three layers of the migration from string-substitution to
typed IR:

1. ``ConditionValue.current_bucket`` flag on the IR.
2. Parser emits the typed flag when it sees the identifier
   ``current_bucket`` on the RHS of a comparison.
3. ``_substitute_current_bucket`` walks a frozen ConditionExpr and
   rebuilds it with the sentinel replaced by a literal bucket key —
   the slow-path bar_chart substitution that used to mutate text.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import Parser
from dazzle.core.ir import (
    Comparison,
    ComparisonOperator,
    ConditionExpr,
    ConditionValue,
)
from dazzle.core.lexer import tokenize
from dazzle.http.runtime.workspace_aggregation import (
    _condition_references_current_bucket,
    _substitute_current_bucket,
)


def _parse_aggregate(src: str):
    tokens = tokenize(src + "\n", Path("t.dsl"))
    return Parser(tokens, Path("t.dsl")).parse_aggregate_ref()


# ─────────────── IR — typed flag ───────────────


def test_condition_value_current_bucket_flag() -> None:
    v = ConditionValue(current_bucket=True)
    assert v.is_current_bucket is True
    assert v.literal is None


def test_condition_value_default_not_current_bucket() -> None:
    v = ConditionValue(literal="draft")
    assert v.is_current_bucket is False


# ─────────────── Parser — emits typed flag ───────────────


def test_parser_current_bucket_becomes_typed_sentinel() -> None:
    ref = _parse_aggregate("count(Manuscript where computed_grade = current_bucket)")
    assert ref.where is not None
    cmp = ref.where.comparison
    assert cmp is not None
    assert cmp.field == "computed_grade"
    assert cmp.value.is_current_bucket is True
    # The legacy literal-string path must not fire — clean migration.
    assert cmp.value.literal is None


def test_parser_other_identifiers_unchanged() -> None:
    """An ordinary identifier value remains a string literal."""
    ref = _parse_aggregate("count(Task where status = draft)")
    cmp = ref.where.comparison
    assert cmp.value.is_current_bucket is False
    assert cmp.value.literal == "draft"


def test_parser_current_bucket_inside_compound() -> None:
    ref = _parse_aggregate("count(Task where status = draft and category = current_bucket)")
    assert ref.where.is_compound
    # Walk to the right comparison.
    right = ref.where.right
    assert right is not None
    assert right.comparison is not None
    assert right.comparison.value.is_current_bucket is True


# ─────────────── _condition_references_current_bucket ───────────────


def test_detector_reads_typed_flag() -> None:
    expr = ConditionExpr(
        comparison=Comparison(
            field="x",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(current_bucket=True),
        )
    )
    assert _condition_references_current_bucket(expr) is True


def test_detector_legacy_literal_string_fallback() -> None:
    """Hand-built ConditionExpr with the literal-string sentinel still
    matches — preserves the pre-#1154 behaviour for fixtures that
    haven't migrated."""
    expr = ConditionExpr(
        comparison=Comparison(
            field="x",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal="current_bucket"),
        )
    )
    assert _condition_references_current_bucket(expr) is True


def test_detector_returns_false_on_other_values() -> None:
    expr = ConditionExpr(
        comparison=Comparison(
            field="x",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal="other"),
        )
    )
    assert _condition_references_current_bucket(expr) is False


# ─────────────── _substitute_current_bucket ───────────────


def test_substitute_replaces_sentinel_with_literal() -> None:
    expr = ConditionExpr(
        comparison=Comparison(
            field="status",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(current_bucket=True),
        )
    )
    out = _substitute_current_bucket(expr, "draft")
    assert out.comparison.value.literal == "draft"
    assert out.comparison.value.is_current_bucket is False
    # Input is frozen — must not be mutated in place.
    assert expr.comparison.value.is_current_bucket is True


def test_substitute_walks_compound() -> None:
    left = ConditionExpr(
        comparison=Comparison(
            field="status",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal="open"),
        )
    )
    right = ConditionExpr(
        comparison=Comparison(
            field="category",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(current_bucket=True),
        )
    )
    from dazzle.core.ir.conditions import LogicalOperator

    compound = ConditionExpr(left=left, operator=LogicalOperator.AND, right=right)
    out = _substitute_current_bucket(compound, "Refactor")
    assert out.is_compound
    assert out.left.comparison.value.literal == "open"
    assert out.right.comparison.value.literal == "Refactor"


def test_substitute_passthrough_when_no_sentinel() -> None:
    expr = ConditionExpr(
        comparison=Comparison(
            field="status",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal="open"),
        )
    )
    out = _substitute_current_bucket(expr, "Refactor")
    assert out is expr  # identity — nothing to substitute


def test_substitute_handles_list_value() -> None:
    expr = ConditionExpr(
        comparison=Comparison(
            field="status",
            operator=ComparisonOperator.IN,
            value=ConditionValue(values=["draft", "current_bucket"]),
        )
    )
    out = _substitute_current_bucket(expr, "review")
    assert out.comparison.value.values == ["draft", "review"]
