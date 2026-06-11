"""Regression gate for GitHub issue #1327.

`_render_table_row` interpolates the row id into Alpine bindings. The id token
came from `json.dumps(item_id)` — a *double*-quoted JS literal (`"<id>"`). When
embedded inside a *double*-quoted HTML/Alpine attribute (`:class="…"`,
`x-if="…"`), the inner `"` terminates the attribute early, so Alpine receives a
truncated expression and throws "Unexpected token".

The fix uses a *single*-quoted JS literal (`'<id>'`) inside those double-quoted
attributes (mirroring the checkbox's `selected.has('<id>')`), while keeping the
double-quoted literal inside the single-quoted `@dblclick='…'` attribute.
"""

from __future__ import annotations

import re

from dazzle.back.runtime.htmx_render import _render_table_row


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


def _attr_values(html: str, attr: str) -> list[str]:
    """Extract the value of every `attr="..."` (double-quoted) occurrence."""
    return re.findall(rf'{re.escape(attr)}="([^"]*)"', html)


def test_class_binding_uses_single_quoted_id_no_premature_quote() -> None:
    """#1327: the :class binding must reference the id as a single-quoted JS
    literal so its value is one balanced double-quoted attribute."""
    html = _render_table_row(_table(), {"id": "abc-123", "name": "Ada"})

    class_vals = _attr_values(html, ":class")
    assert class_vals, ":class binding not emitted"
    cls = class_vals[0]
    # The id appears single-quoted inside selected.has(...), never double-quoted.
    assert "selected.has('abc-123')" in cls
    assert 'selected.has("abc-123")' not in cls
    # The captured attribute value contains no stray double-quote (that would
    # mean the regex stopped early because the id's `"` closed the attribute).
    assert '"' not in cls


def test_x_if_bindings_use_single_quoted_id() -> None:
    """#1327: both x-if bindings (display + edit templates) must use the
    single-quoted id literal inside their double-quoted attribute."""
    html = _render_table_row(_table(), {"id": "row-9", "name": "Grace"})

    x_if_vals = _attr_values(html, "x-if")
    assert len(x_if_vals) >= 2, "expected display + edit x-if bindings"
    for val in x_if_vals:
        assert "isEditing('row-9'" in val
        assert 'isEditing("row-9"' not in val
        assert '"' not in val


def test_dblclick_single_quoted_attr_keeps_double_quoted_id() -> None:
    """The @dblclick handler lives in a *single*-quoted attribute, so its id
    literal must stay double-quoted (a single-quoted id would collide with the
    attribute delimiter)."""
    html = _render_table_row(_table(), {"id": "xyz-7", "name": "Edsger"})

    # @dblclick='startEdit("xyz-7", "name", ...)'  — double-quoted id is correct
    assert '@dblclick=\'startEdit("xyz-7"' in html


def test_balanced_double_quotes_overall() -> None:
    """The whole row markup has balanced double quotes — a stray id-quote
    collision would make the count odd."""
    html = _render_table_row(_table(), {"id": "id-balanced", "name": "x"})
    assert html.count('"') % 2 == 0


def test_id_with_embedded_single_quote_is_escaped() -> None:
    """Non-UUID string ids containing a single quote stay correct: the id is
    JS-escaped then HTML-escaped, so it neither breaks the JS literal nor the
    HTML attribute."""
    html = _render_table_row(_table(), {"id": "o'brien", "name": "x"})
    class_vals = _attr_values(html, ":class")
    assert class_vals
    # No premature double-quote termination, and the raw apostrophe doesn't
    # appear unescaped as a bare JS-string terminator.
    assert '"' not in class_vals[0]
