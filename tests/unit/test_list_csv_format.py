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


def test_entity_list_csv_badge_does_not_invent_snake_case() -> None:
    """Clerk CSV must title-case badge tokens the way the grid does (oral #130)."""
    columns = [
        {
            "key": "status",
            "label": "Status",
            "type": "badge",
            "filter_options": ["open", "in_progress"],
        },
        {
            "key": "sla_state",
            "label": "Sla State",
            "type": "badge",
            "filter_options": ["on_track", "at_risk", "breached"],
        },
    ]
    resp = render_entity_list_csv(
        [{"status": "in_progress", "sla_state": "on_track"}],
        columns,
        "Ticket",
    )
    rows = _parse_csv(_get_body(resp))
    assert rows[1] == ["In Progress", "On Track"]


def test_entity_list_csv_format_currency_does_not_invent_bare_amount() -> None:
    """DSL ``format: currency:GBP`` on decimal must match the grid £ (oral #131)."""
    columns = [
        {
            "key": "amount",
            "label": "Amount",
            "type": "text",
            "format_kind": "currency",
            "format_arg": "GBP",
        }
    ]
    resp = render_entity_list_csv([{"amount": "1250.00"}], columns, "Invoice")
    rows = _parse_csv(_get_body(resp))
    assert rows[1] == ["£1,250.00"]
    assert rows[1][0] != "1250.00"


_CONTACT_LABEL_DSL = """
module m
app a "A"

entity Contact "Contact":
  id: uuid pk
  photo_url: url
  is_favorite: bool=false
  company: str(80)

surface contacts "Contacts":
  uses entity Contact
  mode: list
  section main:
    field photo_url "Photo"
    field is_favorite "Favorite"
    field company
"""


def _contact_label_surface():
    from pathlib import Path

    from dazzle.core.dsl_parser_impl import parse_dsl

    *_, fragment = parse_dsl(_CONTACT_LABEL_DSL, Path("test.dsl"))
    entity = next(e for e in fragment.entities if e.name == "Contact")
    surface = next(s for s in fragment.surfaces if s.name == "contacts")
    return entity, surface


def test_surface_columns_use_author_label_not_schema_title() -> None:
    """Grid labels must ride CSV headers — not Photo Url / Is Favorite (oral #132)."""
    from dazzle.http.runtime.workspace_columns import build_surface_columns

    entity, surface = _contact_label_surface()
    cols = {c["key"]: c for c in build_surface_columns(entity, surface)}
    assert cols["photo_url"]["label"] == "Photo"
    assert cols["photo_url"]["label"] != "Photo Url"
    assert cols["is_favorite"]["label"] == "Favorite"
    assert cols["is_favorite"]["label"] != "Is Favorite"


def test_surface_columns_empty_label_stays_put_as_schema_title() -> None:
    """Leftover empty author labels must not invent a guessed clerk title (oral #132)."""
    from dazzle.http.runtime.workspace_columns import build_surface_columns

    entity, surface = _contact_label_surface()
    cols = {c["key"]: c for c in build_surface_columns(entity, surface)}
    assert cols["company"]["label"] == "Company"


def test_entity_list_csv_headers_use_surface_labels() -> None:
    """``GET /contacts?format=csv`` must match the grid THEAD, not schema titles."""
    from dazzle.http.runtime.workspace_columns import build_surface_columns

    entity, surface = _contact_label_surface()
    columns = build_surface_columns(entity, surface)
    resp = render_entity_list_csv(
        [{"photo_url": "https://example.test/a.png", "is_favorite": True, "company": "Acme"}],
        columns,
        "Contact",
    )
    rows = _parse_csv(_get_body(resp))
    assert rows[0] == ["Photo", "Favorite", "Company"]
    assert "Photo Url" not in rows[0]
    assert "Is Favorite" not in rows[0]
    assert rows[1][1] == "Yes"
