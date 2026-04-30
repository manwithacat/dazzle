"""Tests for #966 — list-mode inline edit JS-escapes title arguments via tojson.

Background: `fragments/table_rows.html` interpolates a row's cell value into
an Alpine `@dblclick="startEdit(..., '...')"` expression. Pre-#966 the value
was emitted with the Jinja `| e` (HTML-escape only) filter inside a
single-quoted JS literal — an apostrophe in the value closed the JS string
early and broke the Alpine expression parser.

Fix: pipe the value through `tojson` so it becomes a properly-escaped JSON
string literal (double-quoted, all special characters backslash-escaped).
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TABLE_ROWS = REPO_ROOT / "src" / "dazzle_ui" / "templates" / "fragments" / "table_rows.html"


def test_dblclick_uses_tojson_for_value() -> None:
    """The `@dblclick` startEdit() call must pass the cell value via tojson."""
    html = TABLE_ROWS.read_text()
    # Anchor on the startEdit() call — the value is the third argument.
    assert "@dblclick=" in html
    assert "startEdit(" in html
    # The fix: third argument piped through `| tojson`. The single-quote-
    # wrapped `| e` form is the regression pattern (#966).
    assert "| tojson" in html, (
        "Expected the @dblclick startEdit() third argument to be piped "
        "through `tojson` so titles with apostrophes don't break Alpine "
        "expression parsing (#966)."
    )


def test_dblclick_does_not_use_e_filter_in_js_literal() -> None:
    """The regressed pattern (`'{{ ... | e }}'`) must not return."""
    html = TABLE_ROWS.read_text()
    # Locate the startEdit() call site and check its third argument.
    idx = html.find("startEdit(")
    assert idx >= 0
    # Read enough following chars to cover the call.
    block = html[idx : idx + 400]
    assert "| e }}" not in block or "| tojson" in block, (
        "The startEdit() call still uses `| e` inside a quoted JS literal — "
        "this re-introduces #966. Use `| tojson` instead (no surrounding "
        "single quotes; tojson emits a complete JSON string literal)."
    )
