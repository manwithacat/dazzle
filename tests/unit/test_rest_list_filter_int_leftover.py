"""Leftover REST ?filter[amount]=zzz must not invent empty (cycle 2198).

leftover-honest bool VALUES already exist (oral #78). REST
``list_handlers`` still landed leftover INT VALUES on known
``amount`` keys in ``gated_list`` / ``repo.list`` and invented
empty / the zero-amount slice. Valid integer / decimal tokens
ride; leftover restores unfiltered (omit). Oral #79 — not
another GET list bool VALUE (oral #78).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.page_routes import (
    entity_int_filter_fields,
    leftover_honest_filter_decimal,
    leftover_honest_filter_int,
    leftover_honest_list_filters,
)

_PAGE_ROUTES = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "page_routes.py"
)
_LIST = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "handlers"
    / "list_handlers.py"
)
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "acme_billing" / "dsl" / "entities.dsl"

_ALLOWED = frozenset({"id", "title", "status", "amount", "unit_price"})
_SPEC = SimpleNamespace(
    fields=[
        SimpleNamespace(name="id"),
        SimpleNamespace(name="title"),
        SimpleNamespace(name="status"),
        SimpleNamespace(name="amount", type=SimpleNamespace(kind="int")),
        SimpleNamespace(name="unit_price", type=SimpleNamespace(kind="decimal")),
    ]
)


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"filter[amount]": "zzz"}, {}),
        ({"filter[amount]": "ghost"}, {}),
        ({"filter[amount]": "1e3"}, {}),
        ({"filter[amount]": "1.5"}, {}),
        ({"filter[amount]": "42"}, {"amount": "42"}),
        ({"filter[amount]": "0"}, {"amount": "0"}),
        ({"filter[amount]": "-3"}, {"amount": "-3"}),
        ({"filter[unit_price]": "zzz"}, {}),
        ({"filter[unit_price]": "1e3"}, {}),
        ({"filter[unit_price]": "12.50"}, {"unit_price": "12.50"}),
        ({"filter[unit_price]": "42"}, {"unit_price": "42"}),
        (
            {"filter[amount]": "zzz", "filter[title]": "Invoice"},
            {"title": "Invoice"},
        ),
        (
            {"filter[amount]": "42", "filter[title]": "Invoice"},
            {"amount": "42", "title": "Invoice"},
        ),
        ({"amount": "zzz"}, {}),
        ({"amount": "42"}, {"amount": "42"}),
        ({}, {}),
        (None, {}),
    ],
    ids=[
        "bracket-leftover-amount",
        "bracket-leftover-ghost",
        "bracket-leftover-sci",
        "bracket-decimal-on-int",
        "bracket-valid-amount",
        "bracket-valid-zero",
        "bracket-valid-neg",
        "bracket-leftover-price",
        "bracket-leftover-price-sci",
        "bracket-valid-price",
        "bracket-int-on-decimal",
        "bracket-leftover-plus-title",
        "bracket-valid-plus-title",
        "bare-leftover-amount",
        "bare-valid-amount",
        "empty-params",
        "none-params",
    ],
)
def test_leftover_honest_list_filter_int_values_do_not_invent(
    params: dict[str, str] | None,
    expected: dict[str, str],
) -> None:
    query = params if params is not None else SimpleNamespace()
    assert (
        leftover_honest_list_filters(
            query,
            allowed=_ALLOWED,
            filter_fields=["amount", "unit_price", "title"],
            entity_spec=_SPEC,
        )
        == expected
    )


def test_entity_int_filter_fields_reads_spec() -> None:
    assert entity_int_filter_fields(_SPEC) == {
        "amount": "int",
        "unit_price": "decimal",
    }
    assert entity_int_filter_fields(None) == {}
    assert entity_int_filter_fields(SimpleNamespace()) == {}
    assert entity_int_filter_fields(SimpleNamespace(fields=[SimpleNamespace(name="title")])) == {}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("zzz", ""),
        ("ghost", ""),
        ("1e3", ""),
        ("1.5", ""),
        ("", ""),
        (None, ""),
        ("42", "42"),
        ("0", "0"),
        ("-3", "-3"),
        (42, "42"),
        (True, ""),
        (False, ""),
    ],
    ids=[
        "junk",
        "ghost",
        "sci",
        "decimal",
        "empty",
        "none",
        "int",
        "zero",
        "neg",
        "py-int",
        "py-true",
        "py-false",
    ],
)
def test_leftover_honest_filter_int_does_not_invent(raw: object, expected: str) -> None:
    assert leftover_honest_filter_int(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("zzz", ""),
        ("ghost", ""),
        ("1e3", ""),
        ("", ""),
        (None, ""),
        ("12.50", "12.50"),
        ("42", "42"),
        ("-0.5", "-0.5"),
        (12.5, "12.5"),
        (float("nan"), ""),
        (float("inf"), ""),
        (True, ""),
    ],
    ids=[
        "junk",
        "ghost",
        "sci",
        "empty",
        "none",
        "decimal",
        "int",
        "neg",
        "py-float",
        "nan",
        "inf",
        "py-true",
    ],
)
def test_leftover_honest_filter_decimal_does_not_invent(raw: object, expected: str) -> None:
    assert leftover_honest_filter_decimal(raw) == expected


def test_helper_source_pins_list_filter_int_leftover() -> None:
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert "def leftover_honest_list_filters" in src
    assert "def entity_int_filter_fields" in src
    assert "_parse_list_filter_int_values" in src
    assert "filter[amount]=zzz" in src
    assert "leftover_honest_filter_int" in src


def test_list_handler_source_pins_filter_int_leftover() -> None:
    src = _LIST.read_text(encoding="utf-8")
    assert "leftover_honest_list_filters(" in src
    assert "filter[amount]=zzz" in src


def test_live_acme_billing_invoice_amount() -> None:
    src = _LIVE.read_text(encoding="utf-8")
    assert 'entity Invoice "Invoice":' in src
    assert "amount: int required" in src
