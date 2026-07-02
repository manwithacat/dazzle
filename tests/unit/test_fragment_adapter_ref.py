"""Adapter: widget-kind to primitive mapping (Plan 14 + Plan 16).

The adapter receives WIDGET kinds (matching `FieldContext.type` from the
template runtime), NOT DSL FieldType.kind values. Issue #1026 exposed
that earlier versions assumed DSL kinds — silently swapping str↔text and
mis-rendering enum/bool. v0.66.45 fixed the mapping.
"""

import pytest

from dazzle.http.runtime.renderers.fragment_adapter import _field_to_primitive
from dazzle.render.fragment.primitives.forms import Combobox, Field, RefPicker

# ─────────────────────────── REF ──────────────────────────────────────


def test_ref_api_in_field_dict_produces_refpicker() -> None:
    """A field_dict with a non-empty ref_api produces RefPicker —
    discriminated by data, not by `kind`. The widget kind passed
    through (typically "select") is irrelevant once ref_api is set."""
    primitive = _field_to_primitive(
        {
            "name": "assigned_to",
            "label": "Assigned",
            "kind": "select",  # widget kind from FieldContext
            "ref_api": "/user",
            "required": True,
            "value": "abc-123",
            "initial_label": "Alice",
        }
    )
    assert isinstance(primitive, RefPicker)
    assert primitive.name == "assigned_to"
    assert primitive.ref_api.value == "/user"
    assert primitive.required is True
    assert primitive.initial_value == "abc-123"
    assert primitive.initial_label == "Alice"


def test_no_ref_api_no_options_falls_through_to_widget_field() -> None:
    """Without ref_api or options, the dispatch falls through to the
    widget→Field mapping. A `kind: "ref"` value (legacy DSL kind) just
    isn't in the widget map and falls back to plain text Field."""
    primitive = _field_to_primitive(
        {"name": "x", "label": "X", "kind": "ref"}  # DSL kind, not widget
    )
    assert isinstance(primitive, Field)
    assert primitive.kind == "text"  # safe fallback


# ─────────────────────────── Enum / Combobox ──────────────────────────


def test_select_widget_with_options_produces_combobox() -> None:
    """The `select` widget kind with options populates a Combobox.
    This is the production path: FieldContext.type="select" + the page
    route's `_build_dispatch_ctx` converting FieldContext.options
    (list of {value,label} dicts) into a list of (value,label) tuples."""
    primitive = _field_to_primitive(
        {
            "name": "priority",
            "label": "Priority",
            "kind": "select",
            "options": [("low", "Low"), ("high", "High")],
            "value": "low",
        }
    )
    assert isinstance(primitive, Combobox)
    assert primitive.name == "priority"
    assert primitive.options == (("low", "Low"), ("high", "High"))
    assert primitive.initial_value == "low"


def test_combobox_widget_kind_also_produces_combobox() -> None:
    """Either `select` or `combobox` widget kinds route to Combobox."""
    primitive = _field_to_primitive(
        {
            "name": "x",
            "label": "X",
            "kind": "combobox",
            "options": [("a", "A")],
        }
    )
    assert isinstance(primitive, Combobox)


def test_options_alone_imply_combobox_even_without_select_kind() -> None:
    """If options are supplied but the widget kind is something else
    (defensive: a renderer-side decision), still produce a Combobox —
    the options data is the authoritative signal."""
    primitive = _field_to_primitive(
        {
            "name": "x",
            "label": "X",
            "kind": "text",  # widget says text, but options say enum
            "options": [("a", "A")],
        }
    )
    assert isinstance(primitive, Combobox)


# ─────────────────────────── Widget kind → Field.kind ─────────────────


@pytest.mark.parametrize(
    ("widget_kind", "expected_field_kind"),
    [
        # str(N) DSL fields arrive as widget kind 'text'.
        pytest.param("text", "text", id="text"),
        # text DSL fields arrive as widget kind 'textarea'.
        pytest.param("textarea", "textarea", id="textarea"),
        # bool DSL fields arrive as widget kind 'checkbox'.
        pytest.param("checkbox", "checkbox", id="checkbox"),
        # int/decimal/float DSL fields arrive as widget kind 'number'.
        pytest.param("number", "number", id="number"),
        pytest.param("email", "email", id="email"),
        pytest.param("date", "date", id="date"),
        # datetime field type maps to widget 'datetime', renders as
        # HTML input type='datetime-local'.
        pytest.param("datetime", "datetime-local", id="datetime-to-datetime-local"),
        pytest.param("url", "url", id="url"),
        # Any widget kind the adapter doesn't explicitly recognise renders
        # as plain text — graceful, not an exception.
        pytest.param("definitely-not-a-widget", "text", id="unknown-falls-back-to-text"),
    ],
)
def test_widget_kind_produces_field_kind(widget_kind: str, expected_field_kind: str) -> None:
    primitive = _field_to_primitive({"name": "x", "label": "X", "kind": widget_kind})
    assert isinstance(primitive, Field)
    assert primitive.kind == expected_field_kind


def test_money_widget_kind_produces_money_field() -> None:
    """money DSL fields arrive as widget 'money' and route to MoneyField —
    the dzMoney controller widget (major/minor split + currency), NOT a plain
    number input. ADR-0049 Phase 3a fixed the prior degrade-to-number (the
    regression Phase 2's review flagged); see test_form_widget_money_phase3."""
    from dazzle.render.fragment import MoneyField

    primitive = _field_to_primitive({"name": "m", "label": "M", "kind": "money"})
    assert isinstance(primitive, MoneyField)
    assert not isinstance(primitive, Field)
