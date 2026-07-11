"""#1577: form primitive → HM ingest adapters and sole-emitter attr helpers."""

from __future__ import annotations

import pytest

from dazzle.render.fragment.ingest import (
    SearchResultRow,
    combobox_from_form,
    combobox_marker_attrs,
    combobox_options_html,
    money_from_form,
    money_root_attrs,
    render_search_result_row,
    search_select_root_attrs,
    search_select_shell_from_form,
    tags_from_form,
    tags_marker_attrs,
)

pytestmark = pytest.mark.gate


def test_tags_from_form_splits_comma_seed() -> None:
    field = tags_from_form(
        name="labels",
        label="Labels",
        placeholder="Add…",
        initial_value="urgent, backend",
    )
    assert field.name == "labels"
    assert field.field_id == "field-labels"
    assert field.tags == ["urgent", "backend"]
    assert field.placeholder == "Add…"
    assert "data-dz-tags" in tags_marker_attrs(field)
    assert 'name="labels"' in tags_marker_attrs(field)


def test_tags_from_form_empty_seed() -> None:
    field = tags_from_form(name="skills", label="Skills")
    assert field.tags == []


def test_combobox_from_form_normalises_options() -> None:
    field = combobox_from_form(
        name="priority",
        label="Priority",
        options=(("low", "Low"), ("high", "High")),
        placeholder="Select…",
        initial_value="high",
    )
    assert field.selected == "high"
    assert [o.value for o in field.options] == ["low", "high"]
    assert "data-dz-combobox" in combobox_marker_attrs(field)
    html = combobox_options_html(field, placeholder_html="Select…")
    assert 'value="high" selected' in html
    assert '<option value="">Select…</option>' in html


def test_money_from_form_computes_major_from_minor() -> None:
    field = money_from_form(
        name="amount",
        currency_code="GBP",
        scale="2",
        minor_initial="1250",
    )
    assert field.currency == "GBP"
    assert field.scale == 2
    assert field.minor_value == 1250
    assert field.major_display == "12.50"
    assert field.field_id == "field-amount"
    attrs = money_root_attrs(field)
    assert "data-dz-money" in attrs
    assert 'data-dz-currency="GBP"' in attrs
    assert 'data-dz-scale="2"' in attrs


def test_money_from_form_empty_minor_blank_display() -> None:
    field = money_from_form(name="fee", currency_code="USD", scale="2")
    assert field.minor_value == 0
    assert field.major_display == ""
    assert field.currency == "USD"


def test_money_from_form_jpy_scale_zero() -> None:
    field = money_from_form(
        name="yen",
        currency_code="JPY",
        scale="0",
        minor_initial="1500",
    )
    assert field.scale == 0
    assert field.major_display == "1500"


def test_search_select_shell_from_form_ids_and_timing() -> None:
    shell = search_select_shell_from_form(
        name="owner",
        search_url="/_dazzle/fragments/search?source=users&field_name=owner",
        label="Owner",
        min_chars=2,
        debounce_ms=250,
    )
    assert shell.field_id == "field-owner"
    assert shell.input_id == "search-input-owner"
    assert shell.results_id == "search-results-owner"
    assert shell.debounce_ms == 250
    assert "at least 2" in shell.prompt
    attrs = search_select_root_attrs(shell)
    assert 'data-dz-widget="search_select"' in attrs
    assert "data-dz-blur-grace-ms=" in attrs
    assert "data-dz-confirm-hold-ms=" in attrs


def test_render_search_result_row_slots() -> None:
    row = SearchResultRow(
        id="u-1",
        name="Ada",
        secondary="ada@example.com",
        media_html='<span aria-hidden="true">A</span>',
        select_url="/select?id=u-1",
        results_target="#search-results-owner",
    )
    html = render_search_result_row(row)
    assert 'data-dz-result-id="u-1"' in html
    assert "dz-search-result-media" in html
    assert "dz-search-result-secondary" in html
    assert "Ada" in html
