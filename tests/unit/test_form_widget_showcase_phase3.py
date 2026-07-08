"""ADR-0049 Phase 3a — substrate parity for the `widget=`-driven form widgets
(combobox / tags / color / slider / rich_text), widgets 3-7/9.

These are exercised by the `component_showcase` gallery fixture and ~12-20 fleet
DSL files each. Each emits the `data-dz-widget` + `data-dz-options` mount
contract the client controllers (TomSelect, dzRichText, dzRangeTooltip) read —
so this pins the substrate primitives to the legacy `form_renderer` markup that
keeps those controllers working after the 3b flip.

`multi_select`, `range`/date_range, and the flatpickr `picker` datepicker are
NOT ported (zero fleet usage); date/datetime fields render as native
`<input type=date>`.
"""

from __future__ import annotations

from dazzle.http.runtime.renderers.fragment_adapter import _field_to_primitive
from dazzle.render.fragment import (
    ColorField,
    FragmentRenderer,
    RichTextField,
    SliderField,
    TagsField,
    WidgetCombobox,
)

_R = FragmentRenderer()


def _render(field_dict: dict) -> str:
    return _R.render(_field_to_primitive(field_dict))


def test_combobox_widget_maps_and_renders() -> None:
    fd = {
        "name": "status",
        "label": "Status",
        "widget": "combobox",
        "options": [("open", "Open"), ("closed", "Closed")],
    }
    assert isinstance(_field_to_primitive(fd), WidgetCombobox)
    html = _render(fd)
    assert 'data-dz-widget="combobox"' in html
    assert "data-dz-options='{}'" in html
    assert 'id="field-status"' in html
    assert '<option value="open"' in html
    # Distinct from the plain Combobox (vanilla select, no TomSelect mount).
    assert "dz-combobox__select" not in html


def test_tags_widget() -> None:
    fd = {"name": "labels", "label": "Labels", "widget": "tags"}
    assert isinstance(_field_to_primitive(fd), TagsField)
    html = _render(fd)
    assert 'data-dz-widget="tags"' in html
    assert '"create":true' in html
    assert '"plugins":["remove_button"]' in html
    assert 'id="field-labels"' in html


def test_color_widget_state_in_dom() -> None:
    """F4e: the hex readout mirrors the input via the delegated HM
    dz-color.js (input event → sibling .dz-form-color-hex textContent).
    The straggler `x-data value` island retired with the Alpine runtime."""
    fd = {"name": "accent", "label": "Accent", "widget": "color", "default": "#ff0000"}
    assert isinstance(_field_to_primitive(fd), ColorField)
    html = _render(fd)
    assert 'type="color"' in html
    assert 'id="field-accent"' in html
    assert "x-model" not in html and "x-data" not in html and "x-text" not in html
    assert 'value="#ff0000"' in html  # SSR'd input value
    assert ">#ff0000</span>" in html  # SSR'd hex readout


def test_color_default_fallback() -> None:
    html = _render({"name": "c", "label": "C", "widget": "color"})
    assert "#3b82f6" in html  # framework default colour


def test_slider_widget_min_max_step() -> None:
    fd = {
        "name": "priority",
        "label": "Priority",
        "widget": "slider",
        "extra": {"min": 1, "max": 5, "step": 1},
        "default": "3",
    }
    assert isinstance(_field_to_primitive(fd), SliderField)
    html = _render(fd)
    assert 'data-dz-widget="range-tooltip"' in html
    assert 'type="range"' in html
    assert "data-dz-slider" in html
    assert 'min="1"' in html
    assert 'max="5"' in html
    assert 'step="1"' in html
    assert 'value="3"' in html
    assert "data-dz-range-value" in html


def test_rich_text_widget_options() -> None:
    fd = {
        "name": "description",
        "label": "Description",
        "widget": "rich_text",
        "extra": {"rich_text_toolbar": "bold,italic,link", "rich_text_max_length": 5000},
    }
    assert isinstance(_field_to_primitive(fd), RichTextField)
    html = _render(fd)
    assert 'data-dz-widget="richtext"' in html
    assert "data-dz-editor" in html
    assert 'type="hidden"' in html  # holds the HTML payload
    # data-dz-options JSON is HTML-escaped inside the attribute (&quot;) — assert
    # on the un-ambiguous bare substrings present in the escaped form.
    assert "toolbar" in html
    assert "bold,italic,link" in html
    assert "maxLength" in html
    assert "5000" in html


def test_rich_text_empty_options() -> None:
    html = _render({"name": "notes", "label": "Notes", "widget": "rich_text"})
    assert 'data-dz-widget="richtext"' in html
    assert "data-dz-options='{}'" in html


# NOTE: the `def test_parity_with_legacy_widgets` legacy-vs-substrate parity test was removed in ADR-0049
# Phase 3b — `form_renderer` is deleted, so there is no legacy renderer left to
# compare against; the substrate is now the source of truth (parity is recorded
# in git history + the CHANGELOG). The substrate-only assertions above stand.
