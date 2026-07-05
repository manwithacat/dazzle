"""Regression gate for GitHub issue #1327 (and its C2.3 resolution).

#1327's bug class: `_render_table_row` interpolated the row id into Alpine
binding attributes (`:class="…"`, `x-if="…"`, `@dblclick='…'`) as a JS string
literal, and a wrong quote flavour terminated the HTML attribute early —
Alpine "Unexpected token".

Convergence C2.3 eliminated the bug class structurally: rows emit NO Alpine
bindings at all. Selection (`is-selected`) and edit state (`is-saving` /
`is-error`) are applied by the delegated controllers (dz-grid.js /
dz-grid-edit.js) as plain classes; the inline-edit affordance is a display
span whose contract rides html-escaped data attributes; the row id appears
once, on `data-dz-row-id`. This gate pins that absence — a reintroduced
Alpine row bind would resurrect the #1327 quoting hazard.
"""

from __future__ import annotations

import re

from dazzle.http.runtime.handlers.list_handlers import build_data_table
from dazzle.render.fragment.renderer._data_row import render_data_table_rows


def _render_table_row(table: dict, item: dict) -> str:
    """Render one rich row via the converged render/ substrate (#1505 P2) — the
    `dz-tr-row` source of truth, formerly `http/htmx_render._render_table_row`."""
    return render_data_table_rows(build_data_table(table, [item]))


def _table(*, bulk_actions: bool = True, inline: bool = True) -> dict:
    return {
        "entity_name": "Contact",
        "api_endpoint": "/api/contacts",
        "detail_url_template": "/contacts/{id}",
        "bulk_actions": bulk_actions,
        "inline_editable": ["name"] if inline else [],
        "columns": [
            {"key": "name", "type": "str"},
        ],
    }


def test_no_alpine_row_bindings_emitted() -> None:
    """C2.3: the row carries no Alpine bindings — the #1327 id-in-JS-literal
    quoting hazard has no surface left to bite."""
    html = _render_table_row(_table(), {"id": "abc-123", "name": "Ada"})

    assert ":class=" not in html
    assert "x-if=" not in html
    assert "@dblclick=" not in html
    assert "isEditing(" not in html
    assert "startEdit(" not in html


def test_row_id_rides_data_attribute() -> None:
    """The row id appears on `data-dz-row-id` (the controllers' anchor) and as
    the morph key — plain html-escaped attributes, no JS-literal context."""
    html = _render_table_row(_table(), {"id": "row-9", "name": "Grace"})

    assert 'data-dz-row-id="row-9"' in html
    # Drill rows carry an explicit dom_id (`row-<id>`), which doubles as the
    # morph key; `dz-grid-row-<id>` is the fallback when no dom_id exists.
    assert 'id="row-row-9"' in html


def test_inline_edit_seam_span_contract() -> None:
    """The editable cell emits the C2.3 display-span seam (id-free — the
    controller reads the row id from the enclosing `data-dz-row-id`)."""
    html = _render_table_row(_table(), {"id": "abc", "name": "Ada"})

    assert 'data-dz-grid-edit="name"' in html
    assert 'data-dz-edit-kind="text"' in html
    assert 'data-dz-edit-value="Ada"' in html


def test_balanced_double_quotes_overall() -> None:
    """The whole row markup has balanced double quotes — a stray id-quote
    collision would make the count odd."""
    html = _render_table_row(_table(), {"id": "id-balanced", "name": "x"})
    assert html.count('"') % 2 == 0


def test_id_with_embedded_quotes_stays_escaped() -> None:
    """Ids (and values) containing quote characters stay html-escaped in the
    data attributes — neither flavour can terminate an attribute early."""
    html = _render_table_row(_table(), {"id": "o'brien", "name": 'say "hi"'})

    assert 'data-dz-row-id="o&#x27;brien"' in html
    # The double quote inside the value must arrive entity-escaped.
    assert 'data-dz-edit-value="say &quot;hi&quot;"' in html
    # Every double-quoted attribute value parses without a premature close.
    for val in re.findall(r'data-dz-edit-value="([^"]*)"', html):
        assert '"' not in val
    assert html.count('"') % 2 == 0
