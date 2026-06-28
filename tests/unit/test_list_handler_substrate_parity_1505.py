"""Phase 2 parity: the http/ HTMX-refresh row branch renders via the render/
substrate (`build_data_table` → `render_data_table_rows`) and must produce the
canonical rich-row bytes (#1505 P2).

Boot-free: asserts equality at the `table_dict → rows` seam against the
committed row-core fixtures (the durable byte anchor) — proving the
`build_data_table` capability mapping yields exactly the rich `dz-tr-row` bytes.
"""

import pytest

from dazzle.http.runtime.handlers.list_handlers import build_data_table
from dazzle.render.fragment.renderer._data_row import render_data_table_rows
from tests.unit.test_data_row_characterization_1505 import _IDS, CAP_MATRIX, _fixture_path


@pytest.mark.parametrize(("label", "table", "item"), CAP_MATRIX, ids=_IDS)
def test_build_data_table_rows_match_fixture(label: str, table: dict, item: dict) -> None:
    rendered = render_data_table_rows(build_data_table(table, [item]))
    assert rendered == _fixture_path(label).read_text(encoding="utf-8")


def test_build_data_table_threads_peek_mode() -> None:
    """#1494 P4: a `peek: expand` surface (table_dict["peek_mode"]) flows through
    build_data_table → caps.peek → the inline-detail chevron."""
    table = {
        "entity_name": "Task",
        "api_endpoint": "/api/tasks",
        "detail_url_template": "/tasks/{id}",
        "peek_mode": "expand",
        "columns": [{"key": "name", "type": "str"}],
    }
    dt = build_data_table(table, [{"id": "a", "name": "Ada"}])
    assert dt.capabilities.peek == "expand"
    out = render_data_table_rows(dt)
    assert "dz-tr-peek-toggle" in out
    assert 'hx-get="/tasks/a?peek=1"' in out
    # Absent peek_mode → off → no chevron (byte-stable default).
    table_no_peek = {**table}
    del table_no_peek["peek_mode"]
    assert "dz-tr-peek-toggle" not in render_data_table_rows(
        build_data_table(table_no_peek, [{"id": "a", "name": "Ada"}])
    )


def test_multi_row_is_per_row_concatenation() -> None:
    """Two rows through one DataTable equal the two single-row renders joined."""
    table = {
        "entity_name": "Task",
        "api_endpoint": "/api/tasks",
        "detail_url_template": "/tasks/{id}",
        "bulk_actions": True,
        "inline_editable": ["name"],
        "columns": [{"key": "name", "type": "str"}, {"key": "status", "type": "badge"}],
    }
    items = [
        {"id": "a", "name": "Ada", "status": "open"},
        {"id": "b", "name": "Babbage", "status": "done"},
    ]
    joined = "".join(render_data_table_rows(build_data_table(table, [i])) for i in items)
    assert render_data_table_rows(build_data_table(table, items)) == joined
