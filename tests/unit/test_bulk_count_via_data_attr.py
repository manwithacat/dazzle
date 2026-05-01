"""Tests for #978 — bulkCount via data-attribute, not Alpine x-show/x-text on children.

Background: bulk_actions.html and table_pagination.html previously bound
`x-show="bulkCount > 0"` and `x-text="bulkCount"` on children of the
dzTable x-data scope. On htmx morph, idiomorph re-evaluated those
bindings before Alpine re-established the parent scope, throwing
"bulkCount is not defined" — same family as #970/#972.

Fix per ADR-0022's preferred pattern:
  - dzTable.init() installs `$watch("bulkCount", ...)` that mirrors
    the value to `data-dz-bulk-count` on the root and `textContent`
    on `[data-dz-bulk-count-target]` descendants.
  - Templates use plain HTML with the `data-dz-bulk-count-target` and
    `dz-bulk-plural` / `dz-bulk-summary-*` class hooks; CSS handles
    visibility via `.dz-table[data-dz-bulk-count="0"]` selectors.

No Alpine bindings on morphable children → no scope-rebind race.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BULK_ACTIONS = REPO_ROOT / "src" / "dazzle_ui" / "templates" / "fragments" / "bulk_actions.html"
PAGINATION = REPO_ROOT / "src" / "dazzle_ui" / "templates" / "fragments" / "table_pagination.html"
DZ_ALPINE = REPO_ROOT / "src" / "dazzle_ui" / "runtime" / "static" / "js" / "dz-alpine.js"
TABLE_HTML = REPO_ROOT / "src" / "dazzle_ui" / "templates" / "components" / "filterable_table.html"
FRAGMENTS_CSS = (
    REPO_ROOT / "src" / "dazzle_ui" / "runtime" / "static" / "css" / "components" / "fragments.css"
)


def test_bulk_actions_no_x_show_or_x_text() -> None:
    """bulk_actions.html must not bind `bulkCount` via Alpine on children."""
    html = BULK_ACTIONS.read_text()
    forbidden = ('x-show="bulkCount', 'x-text="bulkCount', "x-cloak")
    for token in forbidden:
        assert token not in html, (
            f"bulk_actions.html contains `{token}` — re-introduces the "
            f"#978 morph race. Use data-dz-bulk-count-target / .dz-bulk-plural "
            f"hooks instead."
        )


def test_pagination_no_x_show_or_x_text() -> None:
    """table_pagination.html must not bind `bulkCount` via Alpine on children."""
    html = PAGINATION.read_text()
    forbidden = ('x-show="bulkCount', 'x-text="bulkCount', 'x-show="!bulkCount')
    for token in forbidden:
        assert token not in html, (
            f"table_pagination.html contains `{token}` — re-introduces the "
            f"#978 morph race. Use .dz-bulk-summary-selected / "
            f".dz-bulk-summary-rows + data-dz-bulk-count-target instead."
        )


def test_dz_alpine_watches_bulk_count() -> None:
    """dzTable.init() must install $watch on bulkCount that mirrors to DOM."""
    js = DZ_ALPINE.read_text()
    assert '$watch("bulkCount"' in js, (
        "dzTable.init() must $watch bulkCount and mirror to data attribute "
        "+ count-target descendants (#978)."
    )
    assert "data-dz-bulk-count" in js, (
        "dzTable's bulkCount watcher must write a `data-dz-bulk-count` "
        "attribute that CSS keys off (#978)."
    )
    assert "data-dz-bulk-count-target" in js, (
        "dzTable's bulkCount watcher must update textContent on "
        "`[data-dz-bulk-count-target]` descendants (#978)."
    )


def test_filterable_table_initialises_data_attr() -> None:
    """The .dz-table wrapper must default `data-dz-bulk-count="0"`."""
    html = TABLE_HTML.read_text()
    assert 'data-dz-bulk-count="0"' in html, (
        'filterable_table.html must initialise `data-dz-bulk-count="0"` '
        "on the .dz-table wrapper so CSS selectors fire correctly before "
        "dzTable's first watch callback (#978)."
    )


def test_css_keys_off_data_attr() -> None:
    """CSS must show/hide via `.dz-table[data-dz-bulk-count]` selectors."""
    css = FRAGMENTS_CSS.read_text()
    # Pin both directions of the visibility flip.
    assert '.dz-table:not([data-dz-bulk-count="0"]) .dz-bulk-actions' in css, (
        'Missing `.dz-table:not([data-dz-bulk-count="0"]) .dz-bulk-actions` '
        "rule — bulk-actions toolbar must reveal when bulkCount > 0 (#978)."
    )
    assert ".dz-bulk-actions {" in css and "display: none" in css, (
        ".dz-bulk-actions must default to `display: none` so the toolbar "
        "doesn't flash on initial paint (#978)."
    )
