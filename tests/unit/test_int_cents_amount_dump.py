"""INT cents amount cells must not dump raw pence (oral #175)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.ir.fields import FieldTypeKind
from dazzle.core.ir.money import is_money_field_name
from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_columns import (
    build_surface_columns,
    field_kind_to_col_type,
)
from dazzle.http.runtime.workspace_csv import _csv_cell
from dazzle.page.converters.template_compiler import _field_type_to_column_type
from dazzle.render.filters import _currency_filter
from dazzle.render.fragment.format_cell import format_cell
from dazzle.render.fragment.region._shared import _render_typed_value
from dazzle.render.fragment.renderer._data_row import _render_cell_display


def _acme_invoice_amount():
    spec = load_project(Path("examples/acme_billing"))
    invoice = spec.get_entity("Invoice")
    assert invoice is not None
    amount = next(f for f in invoice.fields if f.name == "amount")
    surface = next(s for s in spec.surfaces if s.name == "invoice_list")
    return spec, invoice, amount, surface


def test_acme_invoice_list_amount_is_currency_cell() -> None:
    spec, invoice, amount, surface = _acme_invoice_amount()
    assert amount.type.kind == FieldTypeKind.INT
    assert is_money_field_name("amount")
    assert is_money_field_name("unit_amount")
    assert field_kind_to_col_type(amount, invoice) == "currency"
    assert _field_type_to_column_type(amount, "amount") == "currency"
    col = next(
        c for c in build_surface_columns(invoice, surface, spec.enums) if c["key"] == "amount"
    )
    assert col["type"] == "currency"
    assert col.get("currency_code") == "GBP"


def test_generic_ints_are_not_cents_cells() -> None:
    assert not is_money_field_name("duration_minutes")
    assert not is_money_field_name("quantity")
    assert not is_money_field_name("days_open")
    assert not is_money_field_name("rating")
    assert not is_money_field_name("temperature")


def test_decimal_major_amount_is_not_int_cents() -> None:
    spec = load_project(Path("examples/invoice_ops"))
    invoice = spec.get_entity("Invoice")
    assert invoice is not None
    amount = next(f for f in invoice.fields if f.name == "amount")
    assert amount.type.kind == FieldTypeKind.DECIMAL
    assert field_kind_to_col_type(amount, invoice) != "currency"


def test_clerk_cents_split_leftover_and_empty() -> None:
    assert _currency_filter(125000, "GBP") == "£1,250.00"
    assert _currency_filter(87500, "GBP") == "£875.00"
    assert _currency_filter("zzz", "GBP") == "zzz"
    assert _currency_filter("1e2", "GBP") == "1e2"
    assert _currency_filter("", "GBP") == ""
    assert _currency_filter(None, "GBP") == ""
    assert format_cell(125000, "currency") == "£1,250.00"
    assert format_cell("zzz", "currency") == "zzz"


def test_list_html_renders_pounds_not_raw_pence() -> None:
    html = _render_cell_display(
        {"key": "amount", "label": "Amount", "type": "currency", "currency_code": "GBP"},
        125000,
    )
    assert "£1,250.00" in html
    leftover = _render_cell_display(
        {"key": "amount", "type": "currency", "currency_code": "GBP"},
        "zzz",
    )
    assert "zzz" in leftover
    assert "£" not in leftover
    empty = _render_cell_display(
        {"key": "amount", "type": "currency", "currency_code": "GBP"},
        "",
    )
    assert empty == ""


def test_workspace_typed_value_renders_pounds() -> None:
    frag = _render_typed_value(
        {"amount": 125000},
        {"key": "amount", "label": "Amount", "type": "currency", "currency_code": "GBP"},
    )
    html = getattr(frag, "html", str(frag))
    assert "£1,250.00" in html
    leftover = _render_typed_value(
        {"amount": "zzz"},
        {"key": "amount", "type": "currency", "currency_code": "GBP"},
    )
    leftover_html = getattr(leftover, "html", str(leftover))
    assert "zzz" in leftover_html
    assert "£" not in leftover_html


def test_csv_int_cents_has_pounds_not_raw_pence() -> None:
    col = {"key": "amount", "label": "Amount", "type": "currency", "currency_code": "GBP"}
    assert _csv_cell({"amount": 125000}, col) == "£1,250.00"
    assert _csv_cell({"amount": 87500}, col) == "£875.00"
    assert _csv_cell({"amount": "zzz"}, col) == "zzz"
    assert _csv_cell({"amount": ""}, col) == ""
