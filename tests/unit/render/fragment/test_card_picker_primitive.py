"""Phase 4B.5.a (v0.66.119): byte-equivalence tests for the typed
`CardPicker` primitive vs legacy `workspace/_card_picker.html`.

The card picker is the first chrome piece ported off Jinja. Validates
the chrome-port pattern before we tackle the heavier `_content.html`
pieces (workspace shell, drawer, edit chrome) in 4B.5.b.
"""

from __future__ import annotations

import json

from dazzle.render.fragment import CardPicker, CardPickerEntry, FragmentRenderer
from dazzle_back.runtime.renderers.dual_path import diff_summary


def _render_legacy(catalog: list[dict[str, str]]) -> str:
    from dazzle_ui.runtime.template_renderer import render_fragment

    return render_fragment("workspace/_card_picker.html", catalog=catalog)


def _render_typed(catalog: list[dict[str, str]]) -> str:
    entries = tuple(
        CardPickerEntry(
            name=c["name"],
            title=c["title"],
            entity=c["entity"],
            display=c.get("display", ""),
        )
        for c in catalog
    )
    catalog_json = json.dumps(catalog, sort_keys=True)
    return FragmentRenderer().render(CardPicker(entries=entries, catalog_json=catalog_json))


def test_card_picker_populated_byte_equivalence() -> None:
    """Two-entry catalog with mixed display tags renders byte-for-byte
    identically through both paths."""
    catalog = [
        {"name": "tasks", "title": "Tasks", "entity": "Task", "display": "LIST"},
        {"name": "kanban_board", "title": "Board", "entity": "Task", "display": "KANBAN"},
    ]
    assert diff_summary(_render_legacy(catalog), _render_typed(catalog)) is None


def test_card_picker_empty_byte_equivalence() -> None:
    """Empty catalog → both paths emit `<div class="dz-card-picker-empty">
    No widgets available.</div>`."""
    assert diff_summary(_render_legacy([]), _render_typed([])) is None


def test_card_picker_single_entry_special_chars_byte_equivalence() -> None:
    """Region names with underscores, titles with spaces, and entity
    names with PascalCase round-trip cleanly through `tojson` →
    `addCard("...")`."""
    catalog = [
        {
            "name": "ingestion_journey",
            "title": "Ingestion Journey",
            "entity": "Manuscript",
            "display": "LIST",
        },
    ]
    assert diff_summary(_render_legacy(catalog), _render_typed(catalog)) is None


def test_card_picker_at_click_uses_single_quotes() -> None:
    """The `@click` attribute must be single-quoted (matches legacy
    #949 fix). Inner `"` from the JSON-encoded name would terminate
    a double-quoted attribute mid-value."""
    catalog = [{"name": "x", "title": "X", "entity": "Item", "display": "LIST"}]
    html = _render_typed(catalog)
    assert "@click='addCard(" in html
    assert '@click="addCard(' not in html


def test_card_picker_emits_test_harness_attributes() -> None:
    """`data-test-id` and `data-test-region` must round-trip exactly —
    Playwright + the contract checker key off these attributes."""
    catalog = [{"name": "tasks", "title": "Tasks", "entity": "Task", "display": "LIST"}]
    html = _render_typed(catalog)
    assert 'data-test-id="dz-card-picker-entry"' in html
    assert 'data-test-region="tasks"' in html


def test_card_picker_lowercases_display_tag() -> None:
    """Legacy template applies Jinja's `lower` filter to the display
    tag; the typed renderer matches."""
    catalog = [{"name": "x", "title": "X", "entity": "Item", "display": "KANBAN"}]
    html = _render_typed(catalog)
    assert ">kanban<" in html
    assert ">KANBAN<" not in html
