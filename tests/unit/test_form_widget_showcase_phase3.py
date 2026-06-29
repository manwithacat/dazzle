"""ADR-0049 Phase 3a — substrate parity for the `widget=`-driven form widgets
(combobox / tags / picker / color / slider / rich_text), widgets 3-8/9.

These are exercised by the `component_showcase` gallery fixture and ~12-20 fleet
DSL files each. Each emits the `data-dz-widget` + `data-dz-options` mount
contract the client controllers (TomSelect, Flatpickr, dzRichText,
dzRangeTooltip) read — so this pins the substrate primitives to the legacy
`form_renderer` markup that keeps those controllers working after the 3b flip.

`multi_select` and `range`/date_range are intentionally NOT ported (zero fleet
usage) — they are dropped from the legacy renderer at the 3b delete.
"""

from __future__ import annotations

from dazzle.http.runtime.renderers.fragment_adapter import _field_to_primitive
from dazzle.render.fragment import (
    ColorField,
    DatePickerField,
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


def test_picker_date_vs_datetime() -> None:
    date_fd = {"name": "start", "label": "Start", "widget": "picker", "kind": "date"}
    dt_fd = {"name": "due", "label": "Due", "widget": "picker", "kind": "datetime"}
    assert isinstance(_field_to_primitive(date_fd), DatePickerField)
    date_html = _render(date_fd)
    dt_html = _render(dt_fd)
    assert 'data-dz-widget="datepicker"' in date_html
    assert '"dateFormat":"Y-m-d"' in date_html
    assert '"enableTime":true' not in date_html
    # datetime variant enables time + the H:i format.
    assert '"dateFormat":"Y-m-d H:i"' in dt_html
    assert '"enableTime":true' in dt_html


def test_color_widget_self_contained_alpine() -> None:
    fd = {"name": "accent", "label": "Accent", "widget": "color", "default": "#ff0000"}
    assert isinstance(_field_to_primitive(fd), ColorField)
    html = _render(fd)
    assert 'type="color"' in html
    assert 'id="field-accent"' in html
    assert 'x-model="value"' in html
    assert "value: '#ff0000'" in html
    assert "#ff0000" in html  # hex readout


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


def test_parity_with_legacy_widgets() -> None:
    """Direct mount-attribute parity vs the legacy renderers for the contract
    attrs the client controllers depend on."""
    from types import SimpleNamespace

    from dazzle.page.runtime.form_renderer import (
        _render_color,
        _render_combobox,
        _render_date_picker,
        _render_rich_text,
        _render_slider,
        _render_tags,
    )

    # combobox
    lf = SimpleNamespace(
        name="status", label="Status", placeholder="", options=[{"value": "open", "label": "Open"}]
    )
    legacy = _render_combobox(lf, None, "", "")
    sub = _render(
        {"name": "status", "label": "Status", "widget": "combobox", "options": [("open", "Open")]}
    )
    for tok in ('data-dz-widget="combobox"', "data-dz-options='{}'", 'id="field-status"'):
        assert tok in legacy and tok in sub, f"combobox parity: {tok}"

    # tags
    lf = SimpleNamespace(name="t", label="T", placeholder="")
    legacy = _render_tags(lf, None, "", "")
    sub = _render({"name": "t", "label": "T", "widget": "tags"})
    for tok in ('data-dz-widget="tags"', '"create":true'):
        assert tok in legacy and tok in sub, f"tags parity: {tok}"

    # date picker (datetime)
    lf = SimpleNamespace(name="d", label="D", type="datetime", placeholder="", default="")
    legacy = _render_date_picker(lf, None, "", "")
    sub = _render({"name": "d", "label": "D", "widget": "picker", "kind": "datetime"})
    for tok in ('data-dz-widget="datepicker"', '"enableTime":true'):
        assert tok in legacy and tok in sub, f"picker parity: {tok}"

    # color
    lf = SimpleNamespace(name="c", label="C", default="#3b82f6")
    legacy = _render_color(lf, None, "", "")
    sub = _render({"name": "c", "label": "C", "widget": "color"})
    for tok in ('type="color"', 'x-model="value"'):
        assert tok in legacy and tok in sub, f"color parity: {tok}"

    # slider
    lf = SimpleNamespace(name="s", label="S", extra={"min": 0, "max": 100, "step": 1}, default="50")
    legacy = _render_slider(lf, None, "", "")
    sub = _render({"name": "s", "label": "S", "widget": "slider", "default": "50"})
    for tok in ('data-dz-widget="range-tooltip"', 'type="range"', "data-dz-slider"):
        assert tok in legacy and tok in sub, f"slider parity: {tok}"

    # rich text
    lf = SimpleNamespace(name="r", label="R", extra={"rich_text_toolbar": "bold"})
    legacy = _render_rich_text(lf, None, "", "")
    sub = _render(
        {"name": "r", "label": "R", "widget": "rich_text", "extra": {"rich_text_toolbar": "bold"}}
    )
    for tok in ('data-dz-widget="richtext"', "data-dz-editor", "toolbar", "bold"):
        assert tok in legacy and tok in sub, f"rich_text parity: {tok}"
    # The escaped data-dz-options JSON must be byte-identical between paths.
    import re

    leg_opts = re.search(r"data-dz-options='([^']*)'", legacy).group(1)
    sub_opts = re.search(r"data-dz-options='([^']*)'", sub).group(1)
    assert leg_opts == sub_opts, f"rich_text options drift: {leg_opts!r} vs {sub_opts!r}"
