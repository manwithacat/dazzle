"""The product's `currency_default` must reach every currency display path (#1715).

Why this exists
---------------
`DisplayLocaleProfile.currency_default` is the product's currency setting. Only
`format_cell` consulted it; several display paths passed an explicit `"GBP"`
instead, which short-circuits ``currency_code or prof.currency_default``. A
tenant that set ``locale.currency_default = "USD"`` therefore saw **USD in the
app and GBP in the CSV export** — the same silent per-surface disagreement as
#1632's `metric_current_user_lie`.

What this catches
-----------------
A currency cell rendering with a hardcoded code where the profile default was
configured. Each case is asserted through the real render path, not by reading
the source.

How to satisfy it
-----------------
Pass the column's own code when it has one, and otherwise let the profile
resolve the default. A non-empty fallback defeats the profile.

What this does NOT catch
------------------------
A column that legitimately *declares* its own ``currency_code`` — that is a
per-field override and must keep winning over the product default. Only the
fallback path is under test.
"""

from __future__ import annotations

import pytest

from dazzle.i18n.display_locale import (
    DisplayLocaleProfile,
    reset_display_locale,
    set_display_locale,
)

pytestmark = pytest.mark.gate

_NON_GBP = "USD"


@pytest.fixture
def product_currency_usd():
    """Configure the product default to USD for the duration of one test."""
    token = set_display_locale(DisplayLocaleProfile(currency_default=_NON_GBP))
    try:
        yield
    finally:
        reset_display_locale(token)


def _assert_no_gbp(text: str, *, where: str) -> None:
    assert "£" not in text, f"{where} rendered GBP despite currency_default={_NON_GBP}: {text!r}"
    assert "$" in text or "USD" in text, f"{where} did not render the configured currency: {text!r}"


def test_format_cell_uses_the_product_default(product_currency_usd) -> None:
    """The reference path: `format_cell` already consulted the profile."""
    from dazzle.render.fragment.format_cell import format_cell

    _assert_no_gbp(format_cell(1999, "currency", currency_code=""), where="format_cell")


def test_csv_export_uses_the_product_default(product_currency_usd) -> None:
    """The reported symptom: GBP in CSV while the app showed the tenant's own."""
    from dazzle.http.runtime.workspace_csv import _csv_typed_cell

    out = _csv_typed_cell(1999, {"type": "currency", "key": "amount"})
    _assert_no_gbp(out, where="workspace_csv")


def test_csv_export_still_honours_an_explicit_column_code(product_currency_usd) -> None:
    """A column that declares its own code must keep winning over the default."""
    from dazzle.http.runtime.workspace_csv import _csv_typed_cell

    out = _csv_typed_cell(1999, {"type": "currency", "key": "amount", "currency_code": "GBP"})
    assert "£" in out, f"an explicit column currency_code must win: {out!r}"


def test_minor_currency_code_defaults_to_the_product_currency(product_currency_usd) -> None:
    """The region helper that feeds the same value into `_currency_filter`."""
    from dazzle.render.fragment.region._shared import _minor_currency_code

    assert _minor_currency_code({"key": "amount_minor"}) == _NON_GBP


def test_minor_currency_code_prefers_the_column_then_the_record(product_currency_usd) -> None:
    """Precedence is unchanged: column, then the record's companion, then default."""
    from dazzle.render.fragment.region._shared import _minor_currency_code

    assert _minor_currency_code({"key": "amount_minor", "currency_code": "EUR"}) == "EUR"
    assert _minor_currency_code({"key": "amount_minor"}, {"amount_currency": "JPY"}) == "JPY"


def test_data_row_currency_cell_uses_the_product_default(product_currency_usd) -> None:
    """The entity table cell — the surface a tenant notices first."""
    from dazzle.render.fragment.renderer._data_row import _render_cell_display

    out = _render_cell_display({"type": "currency", "key": "amount"}, 1999)
    _assert_no_gbp(str(out), where="_data_row entity table cell")


def test_data_row_currency_cell_honours_an_explicit_column_code(product_currency_usd) -> None:
    """Per-column currency still overrides the product default."""
    from dazzle.render.fragment.renderer._data_row import _render_cell_display

    out = _render_cell_display({"type": "currency", "key": "amount", "currency_code": "GBP"}, 1999)
    assert "£" in str(out), f"an explicit column currency_code must win: {out!r}"


def test_region_typed_currency_cell_uses_the_product_default(product_currency_usd) -> None:
    """The `type: currency` region cell — the path #1704 added.

    Its fallback chain is per-record -> column -> **product default**. It ended
    at a literal "GBP", so it would have kept disagreeing with the entity table
    and the CSV for a tenant with its own currency. Exercises the real helper
    with a row dict, which is where the per-record companion is read from.
    """
    from dazzle.render.fragment.region._shared import _render_typed_value

    out = _render_typed_value({"amount": 1999}, {"type": "currency", "key": "amount"})
    _assert_no_gbp(str(out), where="region typed currency cell")


def test_region_typed_currency_cell_prefers_the_record(product_currency_usd) -> None:
    """A record-level companion currency still wins over the product default."""
    from dazzle.render.fragment.region._shared import _render_typed_value

    out = _render_typed_value(
        {"amount": 1500, "amount_currency": "JPY"}, {"type": "currency", "key": "amount"}
    )
    text = str(out)
    assert "¥" in text or "JPY" in text, f"record currency must win: {text!r}"
    assert "USD" not in text and "$" not in text, (
        f"product default leaked over the record: {text!r}"
    )
