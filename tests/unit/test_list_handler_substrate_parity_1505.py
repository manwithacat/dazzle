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
