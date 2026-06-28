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


class TestRenderDataTableRows:
    """`render_data_table_rows` — the <tbody>-children entry the Phase-2 http/
    HTMX-refresh transport path calls down into (#1505 P1)."""

    def test_concatenates_one_tr_per_row(self) -> None:
        from dazzle.render.fragment.renderer._data_row import (
            render_data_row,
            render_data_table_rows,
        )

        cols = ({"key": "name", "type": "str"},)
        items = ({"id": "a", "name": "Ada"}, {"id": "b", "name": "Babbage"})
        dt = DataTable(columns=cols, rows=items, entity_name="Task", api_endpoint="/api/tasks")
        expected = "".join(
            render_data_row(
                cols,
                dict(i),
                dt.capabilities,
                entity_name="Task",
                api_endpoint="/api/tasks",
                detail_url_template="",
                table_id="dt-table",
            )
            for i in items
        )
        assert render_data_table_rows(dt) == expected
        assert render_data_table_rows(dt).count('class="dz-tr-row group"') == 2

    def test_empty_rows_render_nothing(self) -> None:
        from dazzle.render.fragment.renderer._data_row import render_data_table_rows

        dt = DataTable(columns=({"key": "name", "type": "str"},), rows=())
        assert render_data_table_rows(dt) == ""

    def test_threads_capabilities(self) -> None:
        from dazzle.render.fragment.renderer._data_row import render_data_table_rows

        dt = DataTable(
            columns=({"key": "name", "type": "str"},),
            rows=({"id": "a", "name": "Ada"},),
            capabilities=RowCapabilities(bulk_select=True, drill=True),
            detail_url_template="/tasks/{id}",
        )
        out = render_data_table_rows(dt)
        assert "dz-tr-checkbox" in out  # bulk_select threaded
        assert 'hx-get="/tasks/a"' in out  # drill threaded
