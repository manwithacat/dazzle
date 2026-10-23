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

The `def test_parity_with_legacy_widgets` legacy-vs-substrate parity test was
removed in ADR-0049 Phase 3b — `form_renderer` is deleted, so the substrate is
the source of truth (parity is recorded in git history + the CHANGELOG).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.http.runtime.renderers.fragment_adapter import _field_to_primitive
from dazzle.render.fragment import (
    ColorField,
    FragmentRenderer,
    RichTextField,
    SliderField,
    SwitchField,
    TagsField,
    ToggleField,
    ToggleGroupField,
    WidgetCombobox,
)

_R = FragmentRenderer()
_ROOT = Path(__file__).resolve().parents[2]
_HM_CONTROLLERS = "packages/hatchi-maxchi/controllers"


def _render(field_dict: dict) -> str:
    return _R.render(_field_to_primitive(field_dict))


# ── widget= → substrate primitive → markup ──────────────────────────


@pytest.mark.parametrize(
    ("field", "primitive", "present", "absent"),
    [
        # HMC-018 slice 1: HM-native progressive enhancement over a real native
        # <select data-dz-combobox> — no TomSelect data-dz-widget mount; a
        # leading placeholder option is always rendered.
        pytest.param(
            {
                "name": "status",
                "label": "Status",
                "widget": "combobox",
                "options": [("open", "Open"), ("closed", "Closed")],
            },
            WidgetCombobox,
            (
                "data-dz-combobox",
                'id="field-status"',
                'data-dazzle-field="status"',
                '<option value="open"',
                '<option value="">',
            ),
            ('data-dz-widget="combobox"', "data-dz-options="),
            id="combobox-native-select",
        ),
        # HMC-018 slice 2: native <input data-dz-tags> with a comma-joined value.
        pytest.param(
            {"name": "labels", "label": "Labels", "widget": "tags"},
            TagsField,
            ("data-dz-tags", 'id="field-labels"', 'data-dazzle-field="labels"', 'type="text"'),
            ('data-dz-widget="tags"', "data-dz-options="),
            id="tags-native-input",
        ),
        # F4e: the hex companion mirrors the swatch via delegated HM dz-color.js;
        # the straggler Alpine `x-data value` island is gone, and junk must not
        # invent a colour (cycle 2133) so the hex is an input, not a span.
        pytest.param(
            {"name": "accent", "label": "Accent", "widget": "color", "default": "#ff0000"},
            ColorField,
            (
                'type="color"',
                'id="field-accent"',
                'value="#ff0000"',
                'class="dz-form-color-hex"',
                'aria-label="Accent hex colour"',
            ),
            ("x-model", "x-data", "x-text", ">#ff0000</span>"),
            id="color-state-in-dom-2133",
        ),
        pytest.param(
            {"name": "c", "label": "C", "widget": "color"},
            ColorField,
            ("#3b82f6",),
            (),
            id="color-framework-default",
        ),
        # Cycle 2134 — HM owns the slider companion; no range-tooltip widget.
        pytest.param(
            {
                "name": "priority",
                "label": "Priority",
                "widget": "slider",
                "extra": {"min": 1, "max": 5, "step": 1},
                "default": "3",
            },
            SliderField,
            (
                'type="range"',
                "data-dz-slider",
                'min="1"',
                'max="5"',
                'step="1"',
                'value="3"',
                "data-dz-range-value",
                'aria-label="Priority value"',
            ),
            ('data-dz-widget="range-tooltip"', ">3</span>"),
            id="slider-min-max-step-2134",
        ),
        # widget=switch mounts the HM Switch spine, refusing the controls-pill
        # almost-DOM (input.dz-switch) and the plain checkbox class.
        pytest.param(
            {"name": "is_active", "label": "Active", "widget": "switch", "value": "true"},
            SwitchField,
            (
                'data-dz-widget="switch"',
                'class="dz-switch"',
                "data-dz-switch",
                'class="dz-switch__track"',
                'type="checkbox"',
                'value="true"',
                " checked",
                "Active",
            ),
            ('input class="dz-switch"', 'class="dz-form-checkbox"'),
            id="switch-hm-anatomy-checked",
        ),
        pytest.param(
            {"name": "muted", "label": "Muted", "widget": "switch", "value": "false"},
            SwitchField,
            ("data-dz-switch",),
            (" checked",),
            id="switch-unchecked",
        ),
        # widget=toggle mounts the HM Toggle spine (aria-pressed button, not switch).
        pytest.param(
            {"name": "is_starred", "label": "Starred", "widget": "toggle", "value": "true"},
            ToggleField,
            (
                'data-dz-field-widget="toggle"',
                'class="dz-toggle"',
                "data-dz-toggle",
                'aria-pressed="true"',
                "Starred",
            ),
            ('data-dz-widget="toggle"', "dz-switch"),
            id="toggle-hm-anatomy",
        ),
        # The label sits outside the fieldset — no legend.
        pytest.param(
            {
                "name": "priority",
                "label": "Priority",
                "widget": "toggle_group",
                "options": [("low", "Low"), ("medium", "Medium"), ("high", "High")],
                "value": "medium",
            },
            ToggleGroupField,
            (
                'data-dz-widget="toggle_group"',
                'class="dz-toggle-group"',
                'role="radiogroup"',
                'type="radio"',
                'value="medium"',
                " checked",
                "Priority",
            ),
            ("<legend",),
            id="toggle-group-hm-anatomy",
        ),
        # data-dz-options JSON is HTML-escaped inside the attribute (&quot;), so
        # the bare substrings are asserted; the <textarea> is the payload carrier.
        pytest.param(
            {
                "name": "description",
                "label": "Description",
                "widget": "rich_text",
                "extra": {"rich_text_toolbar": "bold,italic,link", "rich_text_max_length": 5000},
            },
            RichTextField,
            (
                'data-dz-widget="richtext"',
                "data-dz-editor",
                "<textarea",
                "toolbar",
                "bold,italic,link",
                "maxLength",
                "5000",
            ),
            (),
            id="rich-text-options",
        ),
        pytest.param(
            {"name": "notes", "label": "Notes", "widget": "rich_text"},
            RichTextField,
            ('data-dz-widget="richtext"', "data-dz-options='{}'"),
            (),
            id="rich-text-empty-options",
        ),
    ],
)
def test_widget_renders(
    field: dict, primitive: type, present: tuple[str, ...], absent: tuple[str, ...]
) -> None:
    assert isinstance(_field_to_primitive(field), primitive)
    html = _render(field)
    for text in present:
        assert text in html, text
    for text in absent:
        assert text not in html, text


def test_rich_text_required_on_textarea_not_hidden() -> None:
    html = _render({"name": "notes", "label": "Notes", "widget": "rich_text", "required": True})
    assert 'type="hidden"' not in html
    ta = html.split("<textarea", 1)[1].split(">", 1)[0]
    assert "required" in ta
    assert 'aria-required="true"' in ta


# ── controller source pins (leftover-honest + required validity) ────
#
# The client controllers must refuse leftover/junk input rather than invent a
# value, and gate `required` after enhancement. Behaviour runs in the HM
# Playwright suite; these pins catch a controller losing the guard. The id
# carries the improve-loop cycle that introduced it.

_LEFTOVER = ("must not invent", "leftover junk stays visible")


@pytest.mark.parametrize(
    ("path", "present", "absent"),
    [
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-combobox.js",
            ("function syncRequiredValidity", "Select a value from the list"),
            (),
            id="dz-combobox-required-2120",
        ),
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-combobox.js",
            ("function leftoverKind", *_LEFTOVER),
            (),
            id="dz-combobox-leftover-2135",
        ),
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-tags.js",
            ("function syncRequiredValidity", "Add at least one tag"),
            (),
            id="dz-tags-required-2120",
        ),
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-tags.js",
            ("function commitLeftover", "must not vanish"),
            (),
            id="dz-tags-commit-leftover-on-blur-2131",
        ),
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-money.js",
            ("function parseMajor", "Enter a valid amount", "never 0"),
            (),
            id="dz-money-rejects-garbage-2121",
        ),
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-date-range.js",
            ("function inverted", "From must be on or before To", "stopImmediatePropagation"),
            (),
            id="dz-date-range-rejects-inverted-2122",
        ),
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-date-range.js",
            ("function parseISO", *_LEFTOVER),
            (),
            id="dz-date-range-leftover-iso-2139",
        ),
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-search-box.js",
            ("function onQuery", "Type a title or keyword", "stopImmediatePropagation"),
            (),
            id="dz-search-box-rejects-empty-query-2123",
        ),
        # Coaching restore must clone a node, not innerHTML a data attr (#223).
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-search-box.js",
            ("WeakMap", "cloneNode", "textContent"),
            ("innerHTML", "COACHING_ATTR", "data-dz-search-coaching", "outerHTML"),
            id="dz-search-box-no-dom-reparse-2124-223",
        ),
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-grid.js",
            ("function searchTerm", "do not invent a spaces filter", "encodeURIComponent(term)"),
            (),
            id="dz-grid-rejects-whitespace-query-2125",
        ),
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-grid.js",
            ("function parseGridPage", "must not invent", "?page=2abc"),
            (),
            id="dz-grid-leftover-page-2157",
        ),
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-search-select.js",
            (
                "function onEmptyQuery",
                "Type to search",
                "stopImmediatePropagation",
                "leftover typed text",
            ),
            ("innerHTML",),
            id="dz-search-select-rejects-empty-query-2126",
        ),
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-color.js",
            ("function parseHex", *_LEFTOVER),
            (),
            id="dz-color-leftover-hex-2133",
        ),
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-slider.js",
            ("function parseNumber", *_LEFTOVER),
            (),
            id="dz-slider-leftover-readout-2134",
        ),
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-time.js",
            ("function parseClock", "function parseISO", *_LEFTOVER),
            (),
            id="dz-time-leftover-iso-2144",
        ),
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-date.js",
            ("function parseISO", *_LEFTOVER),
            (),
            id="dz-date-leftover-iso-2145",
        ),
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-number.js",
            ("function parseNumber", *_LEFTOVER),
            (),
            id="dz-number-leftover-2149",
        ),
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-grid-edit.js",
            ("function dateLeftoverBlocksCommit", "must not invent", "data-dz-date-iso"),
            (),
            id="dz-grid-edit-leftover-date-2150",
        ),
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-grid-edit.js",
            (
                "function timeLeftoverBlocksCommit",
                "function leftoverBlocksCommit",
                "data-dz-time-iso",
                "must not invent a clock commit",
            ),
            (),
            id="dz-grid-edit-leftover-time-2153",
        ),
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-grid-edit.js",
            (
                "function numberLeftoverBlocksCommit",
                "function leftoverBlocksCommit",
                "data-dz-number-value",
                "must not invent a number commit",
            ),
            (),
            id="dz-grid-edit-leftover-number-2155",
        ),
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-pdf.js",
            ("function parsePage", *_LEFTOVER),
            (),
            id="dz-pdf-leftover-page-2151",
        ),
        pytest.param(
            f"{_HM_CONTROLLERS}/dz-pdf.js",
            ("function parseZoom", "leftoverZoomMessage", "?dzpdf-zoom leftover", *_LEFTOVER),
            (),
            id="dz-pdf-leftover-zoom-2152",
        ),
        # Cycle 2156: the leftover-zoom behaviour prove must not use 1.25 — CI
        # Chromium fit-width rendered 876px = 1.25x the sample page, so "valid
        # zoom must render" failed 876px != 876px and re-redded the badge.
        pytest.param(
            "packages/hatchi-maxchi/tests/test_behaviour.py",
            (
                "def test_pdf_leftover_zoom_does_not_invent_zoom",
                'page.fill(inp, "2")',
                "valid zoom must render",
                "2× cannot collide with fit",
            ),
            ('page.fill(inp, "1.25")',),
            id="hm-behaviour-pdf-zoom-avoids-fit-collision-2156",
        ),
        pytest.param(
            "packages/hatchi-maxchi/site/build_site.py",
            (
                "function renderSearchResults",
                "SEARCH_BOX_ITEMS",
                "must not invent Aurora",
                'path === "/mock/search"',
            ),
            (),
            id="gallery-mock-search-filters-leftover-q-2148",
        ),
        pytest.param(
            "packages/hatchi-maxchi/site/build_site.py",
            ("function parseGridPage", 'parsedSize.kind === "ok"'),
            (),
            id="gallery-mock-grid-leftover-page-2157",
        ),
        # dz-richtext must not count a visually-empty <p><br></p> as filled.
        pytest.param(
            "src/dazzle/page/runtime/static/js/dz-richtext.js",
            (
                "function isVisuallyEmpty",
                'isVisuallyEmpty(html) ? ""',
                "new DOMParser()",
                "function syncRequiredValidity",
                "Enter some text",
            ),
            ('.replace(/<[^>]+>/g, "")',),
            id="dz-richtext-collapses-visual-empty-2128",
        ),
    ],
)
def test_controller_source_pin(
    path: str, present: tuple[str, ...], absent: tuple[str, ...]
) -> None:
    src = (_ROOT / path).read_text(encoding="utf-8")
    for text in present:
        assert text in src, text
    for text in absent:
        assert text not in src, text
