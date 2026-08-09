"""popover hyperpart emitter — unit pins (cycle 1776).

Host-local free content under trigger: list Columns panel dual-locks
``.dz-popover``. Fragment: ``Popover`` dual-lock spine.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.qa.hyperpart_dsl_shapes import shapes_snapshot
from dazzle.render.fragment import ColumnVisibilityMenu, FragmentRenderer, Popover

ROOT = Path(__file__).resolve().parents[2]
SIMPLE = ROOT / "examples" / "simple_task"


def test_popover_emit_mounts_dz_spine() -> None:
    html = FragmentRenderer().render(
        Popover(
            trigger="Details",
            title="Dimensions",
            body="Filters, previews, quick forms.",
        )
    )
    assert 'class="dz-popover"' in html
    assert "data-dz-popover" in html
    assert "<details" in html
    assert 'class="dz-button"' in html
    assert 'data-dz-variant="outline"' in html
    assert "Details" in html
    assert 'class="dz-popover__panel"' in html
    assert 'class="dz-popover__title"' in html
    assert "Dimensions" in html
    assert 'class="dz-popover__body"' in html
    assert "Filters, previews" in html


def test_popover_open_and_align() -> None:
    html = FragmentRenderer().render(
        Popover(trigger="More", body="Extra facts", open=True, align="end")
    )
    assert " open" in html or html.startswith("<details") and " open>" in html or " open " in html
    assert 'data-dz-align="end"' in html
    assert "open" in html


def test_popover_dismiss_attr() -> None:
    html = FragmentRenderer().render(Popover(trigger="Help", title="Tip", dismiss="esc outside"))
    assert 'data-dz-dismiss="esc outside"' in html


def test_popover_requires_content() -> None:
    try:
        Popover(trigger="X")
    except ValueError as e:
        assert "title and/or body" in str(e)
    else:
        raise AssertionError("expected ValueError for empty content")


def test_column_visibility_dual_locks_as_popover() -> None:
    html = FragmentRenderer().render(
        ColumnVisibilityMenu(columns=(("name", "Name"), ("status", "Status")))
    )
    assert 'class="dz-popover dz-table-col-menu"' in html
    assert "data-dz-popover" in html
    assert 'data-dz-align="end"' in html
    assert "dz-popover__panel" in html
    assert "dz-table-col-menu-panel" in html
    assert 'data-dz-grid-col-toggle="name"' in html
    assert 'data-dz-grid-col-toggle="status"' in html
    assert "Show all columns" in html
    assert "data-dz-grid-cols-reset" in html


def test_simple_task_list_has_multi_column_dogfood() -> None:
    """simple_task task lists declare enough fields for Columns free panel."""
    text = (SIMPLE / "dsl" / "app.dsl").read_text(encoding="utf-8")
    assert "entity Task" in text or "entity: Task" in text or "Task:" in text
    # List surfaces with filters imply multi-column grids in the fleet
    assert "filter:" in text


def test_popover_shape_live() -> None:
    snap = shapes_snapshot()
    assert "popover" not in snap["planned_ids"]
    assert snap["next_planned"] != "popover"
