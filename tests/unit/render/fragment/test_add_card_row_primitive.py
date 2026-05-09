"""Phase 4B.5.b.2.iii (v0.66.123): byte-equivalence + structural tests
for the typed `AddCardRow` primitive.

Composes the `+ Add Card` button with the embedded `CardPicker` —
the legacy `_content.html` add-card section."""

from __future__ import annotations

import json

from dazzle.render.fragment import (
    AddCardRow,
    CardPicker,
    CardPickerEntry,
    FragmentRenderer,
)
from dazzle_back.runtime.renderers.dual_path import diff_summary
from dazzle_ui.runtime.template_renderer import create_jinja_env

# Legacy add-card row block (lines 213-222 of `_content.html`) which
# also embeds `_card_picker.html`. The Jinja `{% include %}`
# resolves at render time so the comparison covers the whole row +
# picker composition.
_LEGACY_ROW_TEMPLATE = """<div class="dz-add-card-row">
    <button @click="showPicker = !showPicker"
            data-test-id="dz-add-card-trigger"
            class="dz-add-card-button">
      <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
      Add Card
    </button>
    {% include 'workspace/_card_picker.html' %}
  </div>"""


def _legacy_render(catalog: list[dict[str, str]]) -> str:
    env = create_jinja_env()
    tmpl = env.from_string(_LEGACY_ROW_TEMPLATE)
    return tmpl.render(catalog=catalog)


def _typed_render(catalog: list[dict[str, str]]) -> str:
    entries = tuple(
        CardPickerEntry(
            name=c["name"],
            title=c["title"],
            entity=c["entity"],
            display=c.get("display", ""),
        )
        for c in catalog
    )
    picker = CardPicker(entries=entries, catalog_json=json.dumps(catalog, sort_keys=True))
    return FragmentRenderer().render(AddCardRow(picker=picker))


def test_add_card_row_with_populated_picker_byte_equivalence() -> None:
    """Two-entry catalog renders byte-for-byte through both paths."""
    catalog = [
        {"name": "tasks", "title": "Tasks", "entity": "Task", "display": "LIST"},
        {"name": "kanban_board", "title": "Board", "entity": "Task", "display": "KANBAN"},
    ]
    assert diff_summary(_legacy_render(catalog), _typed_render(catalog)) is None


def test_add_card_row_with_empty_picker_byte_equivalence() -> None:
    """Empty catalog → picker emits the `dz-card-picker-empty` fallback,
    AddCardRow still emits the trigger button."""
    assert diff_summary(_legacy_render([]), _typed_render([])) is None


def test_add_card_row_emits_trigger_test_id() -> None:
    """`data-test-id="dz-add-card-trigger"` anchors the harness for
    the click that opens the picker."""
    html = _typed_render([])
    assert 'data-test-id="dz-add-card-trigger"' in html


def test_add_card_row_button_toggles_alpine_show_picker_state() -> None:
    """The trigger button binds `@click="showPicker = !showPicker"` —
    parent `dzDashboardBuilder()` x-data owns the toggle state, this
    primitive only emits the binding."""
    html = _typed_render([])
    assert '@click="showPicker = !showPicker"' in html
    assert 'class="dz-add-card-button"' in html


def test_add_card_row_carries_plus_icon_svg() -> None:
    """The `+` SVG path matches the legacy template — same glyph used
    in WorkspacePrimaryAction (consistent visual vocabulary for "add"
    affordances across the chrome)."""
    html = _typed_render([])
    assert 'd="M12 4v16m8-8H4"' in html
    assert 'viewBox="0 0 24 24"' in html


def test_add_card_row_embeds_picker_inside_outer_div() -> None:
    """Visibility is CSS-driven via `[data-show-picker="1"]` on the
    workspace ancestor (#982); the picker itself emits no x-show /
    x-cloak. AddCardRow simply embeds the rendered picker inside its
    `dz-add-card-row` wrapper."""
    html = _typed_render([{"name": "x", "title": "X", "entity": "Item", "display": "LIST"}])
    assert '<div class="dz-add-card-row">' in html
    assert "</div>" in html
    assert 'class="dz-card-picker"' in html  # picker shell embedded
    assert html.find("dz-card-picker") > html.find("dz-add-card-button")
