"""DataTable + RowCapabilities primitive (#1505 Phase 1).

The substrate home for the rich `dz-tr-row` data-table, previously rendered by
`http/runtime/htmx_render.py::_render_table_row`. `RowCapabilities` is the
orthogonal capability vector (§3.2 of the convergence design); Phase 1 carries
only the flags that gate the data-table archetype's output.
"""

import pytest

from dazzle.render.fragment.primitives import DataTable, RowCapabilities


def test_row_capabilities_defaults() -> None:
    caps = RowCapabilities()
    assert caps.bulk_select is False
    assert caps.inline_editable == ()
    assert caps.drill is False
    assert caps.peek == "off"


def test_row_capabilities_set() -> None:
    caps = RowCapabilities(bulk_select=True, inline_editable=("name",), drill=True)
    assert caps.bulk_select is True
    assert caps.inline_editable == ("name",)
    assert caps.drill is True


def test_data_table_construction_and_defaults() -> None:
    dt = DataTable(
        columns=({"key": "name", "type": "str"},),
        rows=({"id": "a", "name": "Ada"},),
        entity_name="Task",
        api_endpoint="/api/tasks",
        capabilities=RowCapabilities(bulk_select=True),
    )
    assert dt.entity_name == "Task"
    assert dt.capabilities.bulk_select is True
    # Defaults
    assert dt.detail_url_template == ""
    assert dt.table_id == "dt-table"
    # A DataTable with no explicit capabilities gets the empty vector.
    bare = DataTable(columns=({"key": "name", "type": "str"},))
    assert bare.capabilities == RowCapabilities()
    assert bare.rows == ()


def test_data_table_requires_columns() -> None:
    with pytest.raises(ValueError, match="at least one column"):
        DataTable(columns=())
