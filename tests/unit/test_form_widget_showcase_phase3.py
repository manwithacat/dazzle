"""ADR-0049 Phase 3a — substrate parity for the `widget=`-driven form widgets
(combobox / tags / color / slider / switch / rich_text), widgets 3-7/9.

These are exercised by the `component_showcase` gallery fixture and ~12-20 fleet
DSL files each. combobox/tags are HM-native progressive-enhancement controllers
(dz-combobox / dz-tags) since HMC-018 slices 1-2; the remaining `data-dz-widget`
+ `data-dz-options` mount contract is read by dzRichText / dzRangeTooltip — so
this pins the substrate primitives to the markup those controllers expect.

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
    SwitchField,
    TagsField,
    ToggleGroupField,
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
    # HMC-018 slice 1: HM-native progressive enhancement over a real native
    # <select data-dz-combobox> — no TomSelect data-dz-widget mount anymore.
    assert "data-dz-combobox" in html
    assert 'data-dz-widget="combobox"' not in html
    assert "data-dz-options=" not in html
    assert 'id="field-status"' in html
    assert 'data-dazzle-field="status"' in html
    assert '<option value="open"' in html
    # A leading placeholder option is always rendered.
    assert '<option value="">' in html


def test_combobox_controller_required_validity() -> None:
    """dz-combobox.js must gate required on the overlay after enhance (2120)."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "hatchi-maxchi"
        / "controllers"
        / "dz-combobox.js"
    ).read_text(encoding="utf-8")
    assert "function syncRequiredValidity" in src
    assert "Select a value from the list" in src


def test_combobox_controller_leftover_does_not_invent() -> None:
    """dz-combobox.js must refuse leftover typed filter (2135)."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "hatchi-maxchi"
        / "controllers"
        / "dz-combobox.js"
    ).read_text(encoding="utf-8")
    assert "function leftoverKind" in src
    assert "must not invent" in src
    assert "leftover junk stays visible" in src


def test_grid_controller_rejects_whitespace_query() -> None:
    """dz-grid.js must not send q= for whitespace (cycle 2125)."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "hatchi-maxchi"
        / "controllers"
        / "dz-grid.js"
    ).read_text(encoding="utf-8")
    assert "function searchTerm" in src
    assert "do not invent a spaces filter" in src
    assert "encodeURIComponent(term)" in src


def test_search_select_controller_rejects_empty_query() -> None:
    """dz-search-select.js must not hx-get empty q (cycle 2126)."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "hatchi-maxchi"
        / "controllers"
        / "dz-search-select.js"
    ).read_text(encoding="utf-8")
    assert "function onEmptyQuery" in src
    assert "Type to search" in src
    assert "stopImmediatePropagation" in src
    assert "leftover typed text" in src
    assert "innerHTML" not in src


def test_search_box_controller_rejects_empty_query() -> None:
    """dz-search-box.js must not hx-get empty q (cycle 2123)."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "hatchi-maxchi"
        / "controllers"
        / "dz-search-box.js"
    ).read_text(encoding="utf-8")
    assert "function onQuery" in src
    assert "Type a title or keyword" in src
    assert "stopImmediatePropagation" in src


def test_search_box_mock_leftover_query_does_not_invent() -> None:
    """Gallery /mock/search must filter leftover q= (cycle 2148)."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "hatchi-maxchi"
        / "site"
        / "build_site.py"
    ).read_text(encoding="utf-8")
    assert "function renderSearchResults" in src
    assert "SEARCH_BOX_ITEMS" in src
    assert "must not invent Aurora" in src
    assert 'path === "/mock/search"' in src


def test_search_box_controller_does_not_reparse_dom_text() -> None:
    """Coaching restore must clone a node, not innerHTML a data attr (2124 / #223)."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "hatchi-maxchi"
        / "controllers"
        / "dz-search-box.js"
    ).read_text(encoding="utf-8")
    assert "WeakMap" in src
    assert "cloneNode" in src
    assert "textContent" in src
    assert "innerHTML" not in src
    assert "COACHING_ATTR" not in src
    assert "data-dz-search-coaching" not in src
    assert "outerHTML" not in src


def test_date_range_controller_rejects_inverted() -> None:
    """dz-date-range.js must not hx-get From>To (cycle 2122)."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "hatchi-maxchi"
        / "controllers"
        / "dz-date-range.js"
    ).read_text(encoding="utf-8")
    assert "function inverted" in src
    assert "From must be on or before To" in src
    assert "stopImmediatePropagation" in src


def test_date_range_controller_leftover_iso_does_not_invent() -> None:
    """dz-date-range.js must refuse leftover ISO junk (2139)."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "hatchi-maxchi"
        / "controllers"
        / "dz-date-range.js"
    ).read_text(encoding="utf-8")
    assert "function parseISO" in src
    assert "must not invent" in src
    assert "leftover junk stays visible" in src


def test_money_controller_rejects_invalid_text() -> None:
    """dz-money.js must not invent 0 from garbage (cycle 2121)."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "hatchi-maxchi"
        / "controllers"
        / "dz-money.js"
    ).read_text(encoding="utf-8")
    assert "function parseMajor" in src
    assert "Enter a valid amount" in src
    assert "never 0" in src


def test_tags_controller_required_validity() -> None:
    """dz-tags.js must gate required on the entry after enhance (2120)."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "hatchi-maxchi"
        / "controllers"
        / "dz-tags.js"
    ).read_text(encoding="utf-8")
    assert "function syncRequiredValidity" in src
    assert "Add at least one tag" in src


def test_tags_controller_commits_leftover_on_blur() -> None:
    """dz-tags.js must commit leftover typed token on blur (2131)."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "hatchi-maxchi"
        / "controllers"
        / "dz-tags.js"
    ).read_text(encoding="utf-8")
    assert "function commitLeftover" in src
    assert "must not vanish" in src


def test_tags_widget() -> None:
    fd = {"name": "labels", "label": "Labels", "widget": "tags"}
    assert isinstance(_field_to_primitive(fd), TagsField)
    html = _render(fd)
    # HMC-018 slice 2: HM-native progressive enhancement over a real native
    # <input data-dz-tags> carrying a comma-joined value — no TomSelect
    # data-dz-widget mount anymore.
    assert "data-dz-tags" in html
    assert 'data-dz-widget="tags"' not in html
    assert "data-dz-options=" not in html
    assert 'id="field-labels"' in html
    assert 'data-dazzle-field="labels"' in html
    assert 'type="text"' in html


def test_color_widget_state_in_dom() -> None:
    """F4e: hex companion mirrors the swatch via delegated HM dz-color.js.
    Leftover junk must not invent a colour (cycle 2133). The straggler
    `x-data value` island retired with the Alpine runtime."""
    fd = {"name": "accent", "label": "Accent", "widget": "color", "default": "#ff0000"}
    assert isinstance(_field_to_primitive(fd), ColorField)
    html = _render(fd)
    assert 'type="color"' in html
    assert 'id="field-accent"' in html
    assert "x-model" not in html and "x-data" not in html and "x-text" not in html
    assert 'value="#ff0000"' in html  # SSR'd swatch + hex
    assert 'class="dz-form-color-hex"' in html
    assert 'aria-label="Hex colour"' in html
    assert ">#ff0000</span>" not in html


def test_color_controller_leftover_hex_does_not_invent() -> None:
    """dz-color.js must refuse leftover hex junk (2133)."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "hatchi-maxchi"
        / "controllers"
        / "dz-color.js"
    ).read_text(encoding="utf-8")
    assert "function parseHex" in src
    assert "must not invent" in src
    assert "leftover junk stays visible" in src


def test_number_controller_leftover_does_not_invent() -> None:
    """dz-number.js must refuse leftover number junk (2149)."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "hatchi-maxchi"
        / "controllers"
        / "dz-number.js"
    ).read_text(encoding="utf-8")
    assert "function parseNumber" in src
    assert "must not invent" in src
    assert "leftover junk stays visible" in src


def test_date_controller_leftover_iso_does_not_invent() -> None:
    """dz-date.js must refuse leftover ISO junk (2145)."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "hatchi-maxchi"
        / "controllers"
        / "dz-date.js"
    ).read_text(encoding="utf-8")
    assert "function parseISO" in src
    assert "must not invent" in src
    assert "leftover junk stays visible" in src


def test_time_controller_leftover_iso_does_not_invent() -> None:
    """dz-time.js must refuse leftover ISO junk (2144)."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "hatchi-maxchi"
        / "controllers"
        / "dz-time.js"
    ).read_text(encoding="utf-8")
    assert "function parseClock" in src
    assert "function parseISO" in src
    assert "must not invent" in src
    assert "leftover junk stays visible" in src


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
    # Cycle 2134 — HM owns the companion; no range-tooltip widget.
    assert 'data-dz-widget="range-tooltip"' not in html
    assert 'type="range"' in html
    assert "data-dz-slider" in html
    assert 'min="1"' in html
    assert 'max="5"' in html
    assert 'step="1"' in html
    assert 'value="3"' in html
    assert "data-dz-range-value" in html
    assert 'aria-label="Slider value"' in html
    assert ">3</span>" not in html


def test_slider_controller_leftover_does_not_invent() -> None:
    """dz-slider.js must refuse leftover readout junk (2134)."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "hatchi-maxchi"
        / "controllers"
        / "dz-slider.js"
    ).read_text(encoding="utf-8")
    assert "function parseNumber" in src
    assert "must not invent" in src
    assert "leftover junk stays visible" in src


def test_switch_widget_hm_anatomy() -> None:
    """widget=switch mounts HM Switch spine (not controls pill input.dz-switch)."""
    fd = {
        "name": "is_active",
        "label": "Active",
        "widget": "switch",
        "value": "true",
    }
    assert isinstance(_field_to_primitive(fd), SwitchField)
    html = _render(fd)
    assert 'data-dz-widget="switch"' in html
    assert 'class="dz-switch"' in html
    assert "data-dz-switch" in html
    assert 'class="dz-switch__track"' in html
    assert 'type="checkbox"' in html
    assert 'value="true"' in html
    assert " checked" in html
    assert "Active" in html
    # Refuse controls-pill almost-DOM (input.dz-switch)
    assert 'class="dz-switch"' in html and "input" in html
    assert 'input class="dz-switch"' not in html.replace("dz-switch__", "")
    assert 'class="dz-form-checkbox"' not in html


def test_switch_widget_unchecked() -> None:
    html = _render({"name": "muted", "label": "Muted", "widget": "switch", "value": "false"})
    assert "data-dz-switch" in html
    assert " checked" not in html


def test_toggle_widget_hm_anatomy() -> None:
    """widget=toggle mounts HM Toggle spine (aria-pressed button, not switch)."""
    from dazzle.render.fragment import ToggleField

    fd = {
        "name": "is_starred",
        "label": "Starred",
        "widget": "toggle",
        "value": "true",
    }
    assert isinstance(_field_to_primitive(fd), ToggleField)
    html = _render(fd)
    assert 'data-dz-field-widget="toggle"' in html
    assert 'class="dz-toggle"' in html
    assert "data-dz-toggle" in html
    assert 'aria-pressed="true"' in html
    assert 'data-dz-widget="toggle"' not in html
    assert "dz-switch" not in html
    assert "Starred" in html


def test_toggle_group_widget_hm_anatomy() -> None:
    fd = {
        "name": "priority",
        "label": "Priority",
        "widget": "toggle_group",
        "options": [("low", "Low"), ("medium", "Medium"), ("high", "High")],
        "value": "medium",
    }
    assert isinstance(_field_to_primitive(fd), ToggleGroupField)
    html = _render(fd)
    assert 'data-dz-widget="toggle_group"' in html
    assert 'class="dz-toggle-group"' in html
    assert 'role="radiogroup"' in html
    assert 'type="radio"' in html
    assert 'value="medium"' in html and " checked" in html
    assert "Priority" in html
    # label outside fieldset — no legend
    assert "<legend" not in html


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
    assert "<textarea" in html  # payload carrier (required-valid, not hidden input)
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


def test_rich_text_required_on_textarea_not_hidden() -> None:
    html = _render({"name": "notes", "label": "Notes", "widget": "rich_text", "required": True})
    assert 'type="hidden"' not in html
    ta = html.split("<textarea", 1)[1].split(">", 1)[0]
    assert "required" in ta
    assert 'aria-required="true"' in ta


def test_richtext_controller_collapses_visual_empty() -> None:
    """dz-richtext emit must not invent <p><br></p> as filled (cycle 2128)."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "dazzle"
        / "page"
        / "runtime"
        / "static"
        / "js"
        / "dz-richtext.js"
    ).read_text(encoding="utf-8")
    assert "function isVisuallyEmpty" in src
    assert 'isVisuallyEmpty(html) ? ""' in src or 'isVisuallyEmpty(html) ? ""' in src
    assert "new DOMParser()" in src
    assert '.replace(/<[^>]+>/g, "")' not in src
    assert "function syncRequiredValidity" in src
    assert "Enter some text" in src


# NOTE: the `def test_parity_with_legacy_widgets` legacy-vs-substrate parity test was removed in ADR-0049
# Phase 3b — `form_renderer` is deleted, so there is no legacy renderer left to
# compare against; the substrate is now the source of truth (parity is recorded
# in git history + the CHANGELOG). The substrate-only assertions above stand.
