"""Tests for #965 — list-surface table-scroll height reservation.

Background: #962 fixed CLS on workspace cards via per-display-mode
min-height. List surfaces (`/{entity}` URLs) rendered via
`components/filterable_table.html` were a separate code path with no
equivalent reservation, producing CLS in the 0.19–0.48 range.

Fix:
  1. `.dz-table-scroll` in `table.css` carries a min-height that
     reserves vertical space before the htmx fetch arrives. Uses a
     CSS custom property `--dz-list-rows` (set from `table.page_size`),
     clamped to 10 internally so very large page sizes don't reserve
     absurd vertical space when actual results are small.
  2. `filterable_table.html` emits `style="--dz-list-rows: ..."` on
     the `.dz-table-scroll` div, feeding (1).

These tests pin the contract.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TABLE_CSS = (
    REPO_ROOT / "src" / "dazzle_ui" / "runtime" / "static" / "css" / "components" / "table.css"
)
TEMPLATE = REPO_ROOT / "src" / "dazzle_ui" / "templates" / "components" / "filterable_table.html"


def test_table_scroll_reserves_min_height() -> None:
    """The `.dz-table-scroll` rule must declare a `min-height`."""
    css = TABLE_CSS.read_text()
    # Find the .dz-table-scroll selector block.
    start = css.find(".dz-table-scroll {")
    assert start >= 0, "missing .dz-table-scroll selector block"
    end = css.find("}", start)
    block = css[start:end]
    assert "min-height:" in block, (
        "Expected `min-height:` inside `.dz-table-scroll { ... }` "
        "(reservation prevents CLS on list surfaces — #965)"
    )


def test_table_scroll_uses_dz_list_rows_variable() -> None:
    """Reservation must scale via `--dz-list-rows` (set per-template from page_size)."""
    css = TABLE_CSS.read_text()
    start = css.find(".dz-table-scroll {")
    end = css.find("}", start)
    block = css[start:end]
    assert "var(--dz-list-rows" in block, (
        "Expected `var(--dz-list-rows, ...)` in the min-height calc — "
        "lets the template scale the reservation by `table.page_size` (#965)."
    )


def test_table_scroll_clamps_reservation() -> None:
    """The CSS calc must clamp via `min(...)` so huge page_sizes don't reserve absurd height."""
    css = TABLE_CSS.read_text()
    start = css.find(".dz-table-scroll {")
    end = css.find("}", start)
    block = css[start:end]
    assert "min(" in block, (
        "Expected a `min(...)` clamp inside the .dz-table-scroll min-height calc — "
        "prevents over-reservation when page_size >> typical actual rows (#965)."
    )


def test_template_emits_dz_list_rows() -> None:
    """`filterable_table.html` must emit `--dz-list-rows` on the scroll container."""
    html = TEMPLATE.read_text()
    assert "--dz-list-rows:" in html, (
        'Expected `style="--dz-list-rows: ..."` on the .dz-table-scroll div — '
        "this is what feeds the CSS min-height calc (#965)."
    )
    assert "table.page_size" in html, (
        "Expected `table.page_size` interpolation in the --dz-list-rows binding "
        "so the reservation scales with the configured page (#965)."
    )
