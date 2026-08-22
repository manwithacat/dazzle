"""List/queue IBAN cells must not dump an ungrouped blob (oral #176)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_columns import (
    build_entity_columns,
    field_kind_to_col_type,
)
from dazzle.http.runtime.workspace_csv import _csv_cell
from dazzle.page.converters.template_compiler import _field_type_to_column_type
from dazzle.render.fragment.format_cell import format_cell
from dazzle.render.fragment.region._shared import _render_typed_value
from dazzle.render.fragment.renderer._data_row import _render_cell_display
from dazzle.render.iban_cell import (
    clerk_iban_cell_html,
    clerk_iban_compact,
    clerk_iban_display,
    iban_field_name,
)

_EXAMPLE = "GB82WEST12345698765432"
_GROUPED = "GB82 WEST 1234 5698 7654 32"


def _supplier_bank_iban():
    spec = load_project(Path("examples/invoice_ops"))
    account = spec.get_entity("SupplierBankAccount")
    assert account is not None
    iban = next(f for f in account.fields if f.name == "iban")
    return spec, account, iban


def test_invoice_ops_bank_ref_iban_is_iban_cell() -> None:
    spec, account, iban = _supplier_bank_iban()
    assert iban_field_name("iban")
    assert field_kind_to_col_type(iban, account) == "iban"
    assert _field_type_to_column_type(iban, "iban") == "iban"
    col = next(c for c in build_entity_columns(account, spec.enums) if c["key"] == "iban")
    assert col["type"] == "iban"


def test_generic_account_numbers_are_not_iban_cells() -> None:
    assert not iban_field_name("bank_account_ref")
    assert not iban_field_name("account_name")
    assert not iban_field_name("account_number")
    assert not iban_field_name("sort_code")
    assert not iban_field_name("iban_count")
    assert not iban_field_name("liban")
    assert iban_field_name("beneficiary_iban")
    assert iban_field_name("iban_number")


def test_clerk_iban_split_leftover_and_empty() -> None:
    assert clerk_iban_compact(_EXAMPLE) == _EXAMPLE
    assert clerk_iban_display(_EXAMPLE) == _GROUPED
    assert clerk_iban_display("GB82 WEST 1234 5698 7654 32") == _GROUPED
    assert clerk_iban_display("zzz") == "zzz"
    assert clerk_iban_display("1e2") == "1e2"
    assert clerk_iban_display("ghost") == "ghost"
    assert clerk_iban_display("") == ""
    assert clerk_iban_display(None) == ""
    assert clerk_iban_compact("not-an-iban") is None
    assert clerk_iban_display("not-an-iban") == "not-an-iban"
    assert format_cell(_EXAMPLE, "iban") == _GROUPED
    assert format_cell("zzz", "iban") == "zzz"


def test_list_html_renders_grouped_iban_not_blob() -> None:
    html = _render_cell_display(
        {"key": "iban", "label": "IBAN", "type": "iban"},
        _EXAMPLE,
    )
    assert "dz-iban" in html
    assert _GROUPED in html
    leftover = _render_cell_display({"key": "iban", "type": "iban"}, "zzz")
    assert "zzz" in leftover
    assert "dz-iban" not in leftover
    assert clerk_iban_cell_html("") == ""
    assert _render_cell_display({"key": "iban", "type": "iban"}, "") == "—"


def test_workspace_typed_value_renders_grouped_iban() -> None:
    frag = _render_typed_value(
        {"iban": _EXAMPLE},
        {"key": "iban", "label": "IBAN", "type": "iban"},
    )
    html = getattr(frag, "html", str(frag))
    assert "dz-iban" in html
    assert _GROUPED in html
    leftover = _render_typed_value(
        {"iban": "zzz"},
        {"key": "iban", "type": "iban"},
    )
    leftover_html = getattr(leftover, "html", str(leftover))
    assert "zzz" in leftover_html
    assert "dz-iban" not in leftover_html


def test_csv_iban_is_grouped_not_blob() -> None:
    col = {"key": "iban", "label": "IBAN", "type": "iban"}
    assert _csv_cell({"iban": _EXAMPLE}, col) == _GROUPED
    assert _csv_cell({"iban": "zzz"}, col) == "zzz"
    assert _csv_cell({"iban": ""}, col) == ""
