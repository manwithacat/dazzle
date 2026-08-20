"""Entity-list ``?format=csv`` must not be treated as a graph dialect.

Cycle 2260 / oral #129: ``dz.downloadCsv`` appends ``format=csv`` to the
grid hx-get (``/tasks``). Graph serialization (#619) used to 400 that as
``Supported: cytoscape, d3, raw``, so Task (no ``graph_edge``) invented
a graph endpoint and the clerk toast-failed. CSV rides; leftover junk
stays 400; cytoscape/d3 stay graph.
"""

from __future__ import annotations

from datetime import datetime

from dazzle.http.runtime.workspace_csv import (
    list_export_kind,
    render_entity_list_csv,
)
from dazzle.render.fragment.format_cell import format_cell
from tests.unit.test_csv_export import _get_body, _parse_csv


def test_list_export_kind_csv_is_not_graph() -> None:
    assert list_export_kind("csv") == "csv"
    assert list_export_kind("cytoscape") == "graph"
    assert list_export_kind("d3") == "graph"
    assert list_export_kind("raw") == "json"
    assert list_export_kind(None) == "json"
    assert list_export_kind("") == "json"


def test_list_export_kind_leftover_stays_put() -> None:
    """Leftover format junk must not invent CSV or a graph (oral #129)."""
    assert list_export_kind("zzz") == "leftover"
    assert list_export_kind("json") == "leftover"
    assert list_export_kind("CSV") == "leftover"


def test_entity_list_csv_datetime_does_not_invent_wall_iso() -> None:
    stored = datetime(2026, 8, 18, 14, 30, 0)
    columns = [
        {"key": "title", "label": "Title", "type": "text"},
        {"key": "created_at", "label": "Created", "type": "datetime"},
    ]
    resp = render_entity_list_csv(
        [{"title": "Review Q3 brand guidelines draft", "created_at": stored}],
        columns,
        "Task",
    )
    assert resp.media_type == "text/csv"
    assert 'filename="Task.csv"' in resp.headers["content-disposition"]
    rows = _parse_csv(_get_body(resp))
    assert rows[0] == ["Title", "Created"]
    assert rows[1][0] == "Review Q3 brand guidelines draft"
    assert rows[1][1] == format_cell(stored, "datetime")
    assert rows[1][1] != "2026-08-18 14:30:00"


def test_entity_list_csv_fk_dict_does_not_invent_repr() -> None:
    columns = [{"key": "assigned_to", "label": "Assigned To", "type": "ref"}]
    resp = render_entity_list_csv(
        [{"assigned_to": {"id": "u1", "name": "Carol Member"}}],
        columns,
        "Task",
    )
    rows = _parse_csv(_get_body(resp))
    assert rows[1] == ["Carol Member"]
    assert "{" not in rows[1][0]
