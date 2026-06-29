"""Characterization fixtures for the legacy list *chrome* (ADR-0049 Phase 1).

The substrate-universal render-path migration (ADR-0049) makes the typed
Fragment substrate the sole list render path and deletes the legacy
`page/runtime/table_renderer.py::render_filterable_table`. Before the flip
(Task 5) and delete (Task 6), these committed fixtures freeze the legacy
chrome across a representative matrix — the **visual-parity reference** the
substrate `_build_list` must reproduce.

Per ADR-0049 D1 these are NOT a byte gate after the flip (the substrate DOM
becomes canonical). They document what the legacy renderer emits so the Task 4
gap-closing + the Task 5 adversarial review can diff substrate-vs-legacy chrome
element by element. The file is deleted alongside `render_filterable_table` in
Task 6.

Regenerate intentionally with `UPDATE_LEGACY_LIST_CHAR=1 uv run pytest
tests/unit/test_legacy_list_chrome_char_phase1.py` and inspect the diff.
"""

import os
import pathlib

import pytest

from dazzle.page.runtime.table_renderer import render_filterable_table
from dazzle.render.context import ColumnContext, TableContext

_FIXTURE_DIR = pathlib.Path(__file__).parent / "__snapshots__" / "legacy_list_chrome"
_UPDATE = os.environ.get("UPDATE_LEGACY_LIST_CHAR") == "1"


def _tc(**over: object) -> TableContext:
    base: dict = {
        "entity_name": "Task",
        "title": "Tasks",
        "columns": [],
        "api_endpoint": "/api/task",
        "table_id": "dt-task",
        "search_enabled": False,
    }
    base.update(over)
    return TableContext(**base)


# Columns: a plain sortable name, a filterable select, a filterable text, a
# filterable ref-select, plus extras to trip the >3-column visibility menu.
_COL_NAME = ColumnContext(key="name", label="Name", sortable=True)
_COL_STATUS_SELECT = ColumnContext(
    key="status",
    label="Status",
    filterable=True,
    filter_type="select",
    filter_options=[{"value": "open", "label": "Open"}, {"value": "done", "label": "Done"}],
)
_COL_OWNER_TEXT = ColumnContext(key="owner", label="Owner", filterable=True, filter_type="text")
_COL_CLIENT_REF = ColumnContext(
    key="client",
    label="Client",
    filterable=True,
    filter_type="select",
    filter_ref_entity="Client",
    filter_ref_api="/client",
)
_COL_PRIORITY = ColumnContext(key="priority", label="Priority", sortable=True)
_COL_DUE = ColumnContext(key="due", label="Due", type="date")
_COL_HIDDEN = ColumnContext(key="secret", label="Secret", hidden=True)


# (label, TableContext, page_title) — the chrome matrix.
CHROME_MATRIX: list[tuple[str, TableContext, str]] = [
    ("minimal", _tc(), ""),
    ("page_title", _tc(), "All Tasks"),
    ("search", _tc(search_enabled=True, columns=[_COL_NAME]), ""),
    ("search_first", _tc(search_enabled=True, search_first=True, columns=[_COL_NAME]), ""),
    ("filter_select", _tc(columns=[_COL_STATUS_SELECT]), ""),
    ("filter_text", _tc(columns=[_COL_OWNER_TEXT]), ""),
    ("filter_ref", _tc(columns=[_COL_CLIENT_REF]), ""),
    ("sortable", _tc(columns=[_COL_NAME, _COL_PRIORITY]), ""),
    ("bulk", _tc(columns=[_COL_NAME], bulk_actions=True), ""),
    (
        "col_menu",  # >3 visible columns → column-visibility menu
        _tc(columns=[_COL_NAME, _COL_STATUS_SELECT, _COL_OWNER_TEXT, _COL_PRIORITY, _COL_DUE]),
        "",
    ),
    ("hidden_col", _tc(columns=[_COL_NAME, _COL_HIDDEN]), ""),
    ("create", _tc(columns=[_COL_NAME], create_url="/app/task/create"), ""),
    (
        "create_titled",
        _tc(columns=[_COL_NAME], create_url="/app/task/create", entity_title="To-Do"),
        "",
    ),
    ("refresh", _tc(columns=[_COL_NAME], refresh_interval=30), ""),
    ("infinite", _tc(columns=[_COL_NAME], pagination_mode="infinite"), ""),
    (
        "sort_default",
        _tc(columns=[_COL_NAME], default_sort_field="name", default_sort_dir="desc"),
        "",
    ),
    (
        "full",  # everything at once — the dense chrome reference
        _tc(
            search_enabled=True,
            columns=[_COL_NAME, _COL_STATUS_SELECT, _COL_OWNER_TEXT, _COL_CLIENT_REF, _COL_DUE],
            bulk_actions=True,
            create_url="/app/task/create",
            entity_title="To-Do",
            default_sort_field="name",
            default_sort_dir="asc",
            refresh_interval=15,
        ),
        "All Tasks",
    ),
]

_IDS = [c[0] for c in CHROME_MATRIX]


def _fixture_path(label: str) -> pathlib.Path:
    return _FIXTURE_DIR / f"{label}.html"


@pytest.mark.parametrize(("label", "table", "page_title"), CHROME_MATRIX, ids=_IDS)
def test_legacy_list_chrome_matches_fixture(
    label: str, table: TableContext, page_title: str
) -> None:
    rendered = render_filterable_table(table, page_title=page_title)
    path = _fixture_path(label)
    if _UPDATE:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
    assert path.exists(), f"missing fixture {path} — regenerate with UPDATE_LEGACY_LIST_CHAR=1"
    assert rendered == path.read_text(encoding="utf-8")
