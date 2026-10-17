"""Workspace ``today`` must resolve to tenant calendar — not drop or invent."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from dazzle.core.date_expr_eval import date_expr_filter_value, evaluate_date_expr
from dazzle.core.ir.dates import (
    DateArithmeticExpr,
    DateArithmeticOp,
    DateLiteral,
    DateLiteralKind,
    DurationLiteral,
)
from dazzle.core.ir.invariant import DurationUnit
from dazzle.i18n.display_locale import calendar_today


def test_today_is_tenant_calendar() -> None:
    lit = DateLiteral(kind=DateLiteralKind.TODAY)
    assert evaluate_date_expr(lit) == calendar_today()
    assert date_expr_filter_value(lit) == calendar_today().isoformat()


def test_today_dump_dict() -> None:
    assert evaluate_date_expr({"kind": "today"}) == calendar_today()


def test_today_plus_seven_days() -> None:
    expr = DateArithmeticExpr(
        left=DateLiteral(kind=DateLiteralKind.TODAY),
        operator=DateArithmeticOp.ADD,
        right=DurationLiteral(value=7, unit=DurationUnit.DAYS),
    )
    assert evaluate_date_expr(expr) == calendar_today() + timedelta(days=7)


def test_leftover_kind_stays_unresolved() -> None:
    assert evaluate_date_expr({"kind": "zzz"}) is None
    assert evaluate_date_expr("ghost") is None
    assert date_expr_filter_value(None) is None


def test_field_ref_base_stays_unresolved() -> None:
    expr = DateArithmeticExpr(
        left="start_date",
        operator=DateArithmeticOp.ADD,
        right=DurationLiteral(value=30, unit=DurationUnit.DAYS),
    )
    assert evaluate_date_expr(expr) is None


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (DateLiteralKind.START_OF_WEEK, date(2026, 11, 16)),  # ISO Monday
        (DateLiteralKind.START_OF_MONTH, date(2026, 11, 1)),
        (DateLiteralKind.START_OF_QUARTER, date(2026, 10, 1)),
        (DateLiteralKind.START_OF_YEAR, date(2026, 1, 1)),
    ],
)
def test_start_of_anchors_on_tenant_today(
    monkeypatch: pytest.MonkeyPatch, kind: DateLiteralKind, expected: date
) -> None:
    """#1800: start_of(period) is the first day of the period containing the
    tenant's today (a Wednesday here); the attention dump-dict form agrees."""
    monkeypatch.setattr("dazzle.core.date_expr_eval.calendar_today", lambda: date(2026, 11, 18))
    lit = DateLiteral(kind=kind)
    assert evaluate_date_expr(lit) == expected
    assert evaluate_date_expr(lit.model_dump()) == expected
    assert date_expr_filter_value(lit) == expected.isoformat()
