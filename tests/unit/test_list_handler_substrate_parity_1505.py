"""Phase 2 parity: the http/ HTMX-refresh row branch, once routed through the
render/ substrate (`build_data_table` → `render_data_table_rows`), must be
byte-identical to the legacy ``"".join(_render_table_row(...))`` it replaces
(#1505 P2).

Boot-free: asserts equality at the `table_dict → rows` seam across the same
capability matrix the row-core characterization uses.
"""

import pytest

from dazzle.http.runtime.htmx_render import _render_table_row
from tests.unit.test_data_row_characterization_1505 import _IDS, CAP_MATRIX


@pytest.mark.parametrize(("label", "table", "item"), CAP_MATRIX, ids=_IDS)
def test_substrate_rows_match_legacy_join(label: str, table: dict, item: dict) -> None:
    from dazzle.http.runtime.handlers.list_handlers import build_data_table
    from dazzle.render.fragment.renderer._data_row import render_data_table_rows

    items = [item]
    legacy = "".join(_render_table_row(table, i) for i in items)
    new = render_data_table_rows(build_data_table(table, items))
    assert new == legacy


def test_substrate_rows_match_legacy_join_multi_row() -> None:
    """Two rows through the substrate equal the legacy per-row join."""
    from dazzle.http.runtime.handlers.list_handlers import build_data_table
    from dazzle.render.fragment.renderer._data_row import render_data_table_rows

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
    legacy = "".join(_render_table_row(table, i) for i in items)
    new = render_data_table_rows(build_data_table(table, items))
    assert new == legacy
