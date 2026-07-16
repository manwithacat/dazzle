"""#1603 — list row open via FK hop (task → parent/context entity)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.appspec_loader import load_project_appspec
from dazzle.page.open_via import resolve_list_detail_url_template
from dazzle.render.fragment.region._row_links import _resolve_row_links

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
SIMPLE = REPO / "examples" / "simple_task"


def test_resolve_default_same_entity() -> None:
    surface = ir.SurfaceSpec(
        name="task_list",
        title="Tasks",
        entity_ref="Task",
        mode=ir.SurfaceMode.LIST,
    )
    entity = ir.EntitySpec(name="Task", title="Task", fields=[])
    tmpl = resolve_list_detail_url_template(surface, entity)
    assert tmpl == "/app/task/{id}"


def test_resolve_open_via_fk_hop() -> None:
    surface = ir.SurfaceSpec(
        name="task_list",
        title="Tasks",
        entity_ref="Task",
        mode=ir.SurfaceMode.LIST,
        open_via="assigned_to",
        open_entity="User",
    )
    entity = ir.EntitySpec(
        name="Task",
        title="Task",
        fields=[
            ir.FieldSpec(
                name="assigned_to",
                type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="User"),
            ),
        ],
    )
    tmpl = resolve_list_detail_url_template(surface, entity)
    assert tmpl == "/app/user/{assigned_to}"


def test_row_links_format_fk_placeholder() -> None:
    tmpl = "/app/user/{assigned_to}"
    rows = [
        {"id": "t1", "assigned_to": "u-aaa", "title": "A"},
        {"id": "t2", "assigned_to": None, "title": "B"},
        {"id": "t3", "title": "C"},  # missing key
    ]
    links = _resolve_row_links(rows, tmpl)
    assert links[0] == "/app/user/u-aaa"
    assert links[1] is None  # null FK — no dead link
    assert links[2] is None  # missing key


def test_row_links_null_fk_falls_back_to_same_entity() -> None:
    """#1614: open-via null → same-entity ``.../{id}`` so row stays drillable."""
    tmpl = "/app/user/{assigned_to}"
    fallback = "/app/task/{id}"
    rows = [
        {"id": "t1", "assigned_to": "u-aaa"},
        {"id": "t2", "assigned_to": None},
        {"id": "t3"},  # missing key
    ]
    links = _resolve_row_links(rows, tmpl, fallback_template=fallback)
    assert links[0] == "/app/user/u-aaa"
    assert links[1] == "/app/task/t2"
    assert links[2] == "/app/task/t3"


def test_row_links_unwraps_hydrated_ref_dict_and_uuid() -> None:
    """#1603 dogfood v0.104.9: list JSON embeds full contact dict under FK key.

    CyFuture saw::

        hx-get="/app/contact/{'id': UUID('7048…'), 'first_name': 'Demo', …}"

    format_map must extract the scalar id, not str(dict).
    """
    from uuid import UUID

    uid = UUID("704816af-f88a-42eb-9ecf-e28308774039")
    tmpl = "/app/contact/{contact}"
    rows = [
        {
            "id": "task-1",
            "contact": {
                "id": uid,
                "first_name": "Demo",
                "last_name": "User",
            },
        },
        {"id": "task-2", "contact": {"name": "no-id-field"}},  # unwrappable
        {"id": "task-3", "contact": uid},  # bare UUID
        {"id": "task-4", "contact": str(uid)},  # already scalar
    ]
    links = _resolve_row_links(rows, tmpl)
    assert links[0] == f"/app/contact/{uid}"
    assert links[1] is None
    assert links[2] == f"/app/contact/{uid}"
    assert links[3] == f"/app/contact/{uid}"


def test_data_row_htmx_unwraps_nested_contact_dict() -> None:
    from uuid import UUID

    from dazzle.render.fragment.primitives import RowCapabilities
    from dazzle.render.fragment.renderer._data_row import render_data_row

    uid = UUID("704816af-f88a-42eb-9ecf-e28308774039")
    columns = [{"key": "title", "type": "str"}]
    item = {
        "id": "task-1",
        "title": "Call",
        "contact": {"id": uid, "first_name": "Demo"},
    }
    html = render_data_row(
        columns,
        item,
        RowCapabilities(drill=True),
        detail_url_template="/app/contact/{contact}",
        entity_name="Task",
        api_endpoint="/api/tasks",
    )
    assert f'hx-get="/app/contact/{uid}"' in html
    assert "first_name" not in html
    assert "UUID(" not in html
    assert "{contact}" not in html


def test_data_row_htmx_path_substitutes_open_via_fk() -> None:
    """#1603 dogfood: rich CRUD data-table path must format {contact} etc.

    CyFuture pilot saw literal ``hx-get="/app/contact/{contact}"`` because
    ``_data_row`` only did ``.replace("{id}", …)``. Row HTML must carry the
    substituted UUID when the via field is present.
    """
    from dazzle.render.fragment.primitives import RowCapabilities
    from dazzle.render.fragment.renderer._data_row import render_data_row

    columns = [{"key": "title", "type": "str"}]
    item = {"id": "task-1", "title": "Call", "contact": "c-uuid-99"}
    html = render_data_row(
        columns,
        item,
        RowCapabilities(drill=True),
        detail_url_template="/app/contact/{contact}",
        entity_name="Task",
        api_endpoint="/api/tasks",
    )
    assert 'hx-get="/app/contact/c-uuid-99"' in html or 'href="/app/contact/c-uuid-99"' in html
    assert "{contact}" not in html


def test_data_row_null_fk_falls_back_to_same_entity_detail() -> None:
    """#1614: null open-via FK → same-entity detail + click drill (not bare row)."""
    from dazzle.render.fragment.primitives import RowCapabilities
    from dazzle.render.fragment.renderer._data_row import render_data_row

    columns = [{"key": "title", "type": "str"}]
    item = {"id": "task-2", "title": "Orphan", "contact": None}
    html = render_data_row(
        columns,
        item,
        RowCapabilities(drill=True),
        detail_url_template="/app/contact/{contact}",
        detail_url_fallback_template="/app/task/{id}",
        entity_name="Task",
        api_endpoint="/api/tasks",
    )
    assert "{contact}" not in html
    assert 'hx-get="/app/task/task-2"' in html
    assert 'hx-trigger="click"' in html


def test_delete_button_pins_hx_trigger_click() -> None:
    """#1613: delete must not inherit tbody load via implicitInheritance."""
    from dazzle.render.fragment.primitives import RowCapabilities
    from dazzle.render.fragment.renderer._data_row import render_data_row

    columns = [{"key": "title", "type": "str"}]
    item = {"id": "task-3", "title": "X"}
    html = render_data_row(
        columns,
        item,
        RowCapabilities(drill=True),
        detail_url_template="/app/task/{id}",
        entity_name="Task",
        api_endpoint="/api/tasks",
    )
    assert 'hx-delete="/api/tasks/task-3"' in html
    assert 'hx-trigger="click"' in html
    assert "hx-disinherit" in html


def test_simple_task_parses_open_via() -> None:
    appspec = load_project_appspec(SIMPLE)
    task_list = next(s for s in appspec.surfaces if s.name == "task_list")
    assert task_list.open_via == "assigned_to"
    assert task_list.open_entity == "User"
    entity = appspec.get_entity("Task")
    tmpl = resolve_list_detail_url_template(task_list, entity)
    assert tmpl == "/app/user/{assigned_to}"


def test_resolve_first_non_null_candidates() -> None:
    """#1600 P2: multi-hop open produces ordered candidate templates."""
    surface = ir.SurfaceSpec(
        name="sub_list",
        title="Subs",
        entity_ref="ClientSubscription",
        mode=ir.SurfaceMode.LIST,
        open_via="company",
        open_entity="Company",
        open_via_targets=[
            ir.OpenViaTarget(via="company", entity="Company"),
            ir.OpenViaTarget(via="sole_trader", entity="SoleTrader"),
            ir.OpenViaTarget(via="partnership", entity="Partnership"),
        ],
    )
    entity = ir.EntitySpec(
        name="ClientSubscription",
        title="Sub",
        fields=[
            ir.FieldSpec(
                name="company",
                type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Company"),
            ),
            ir.FieldSpec(
                name="sole_trader",
                type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="SoleTrader"),
            ),
            ir.FieldSpec(
                name="partnership",
                type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Partnership"),
            ),
        ],
    )
    from dazzle.page.open_via import resolve_list_detail_url_candidates

    cands = resolve_list_detail_url_candidates(surface, entity)
    assert cands == [
        "/app/company/{company}",
        "/app/soletrader/{sole_trader}",
        "/app/partnership/{partnership}",
    ]
    assert resolve_list_detail_url_template(surface, entity) == cands[0]


def test_row_links_first_non_null_picks_second_hop() -> None:
    """#1600 P2: null company → sole_trader hop; all null → fallback."""
    cands = (
        "/app/company/{company}",
        "/app/soletrader/{sole_trader}",
        "/app/partnership/{partnership}",
    )
    fallback = "/app/clientsubscription/{id}"
    rows = [
        {"id": "s1", "company": "co-1", "sole_trader": None, "partnership": None},
        {"id": "s2", "company": None, "sole_trader": "st-9", "partnership": None},
        {"id": "s3", "company": None, "sole_trader": None, "partnership": "p-2"},
        {"id": "s4", "company": None, "sole_trader": None, "partnership": None},
    ]
    links = _resolve_row_links(
        rows,
        cands[0],
        fallback_template=fallback,
        candidate_templates=cands,
    )
    assert links[0] == "/app/company/co-1"
    assert links[1] == "/app/soletrader/st-9"
    assert links[2] == "/app/partnership/p-2"
    assert links[3] == "/app/clientsubscription/s4"


def test_parse_open_first_non_null_bare_fields() -> None:
    """Parse ``open: first_non_null(company, sole_trader)``."""
    from dazzle.core.dsl_parser_impl import parse_dsl

    dsl = """
module test.core
app test_app "T"

entity Company "Company":
  id: uuid pk
  name: str(100)

entity SoleTrader "Sole Trader":
  id: uuid pk
  name: str(100)

entity Sub "Sub":
  id: uuid pk
  company: ref Company
  sole_trader: ref SoleTrader

surface sub_list "Subs":
  uses entity Sub
  mode: list
  open: first_non_null(company, sole_trader)
"""
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    surface = fragment.surfaces[0]
    assert surface.open_via == "company"
    assert surface.open_entity is None  # bare fields — entity inferred later
    assert len(surface.open_via_targets) == 2
    assert surface.open_via_targets[0].via == "company"
    assert surface.open_via_targets[0].entity is None
    assert surface.open_via_targets[1].via == "sole_trader"


def test_parse_open_pipe_chain() -> None:
    """Parse ``open: Company via company | SoleTrader via sole_trader``."""
    from dazzle.core.dsl_parser_impl import parse_dsl

    dsl = """
module test.core
app test_app "T"

entity Company "Company":
  id: uuid pk

entity SoleTrader "Sole Trader":
  id: uuid pk

entity Sub "Sub":
  id: uuid pk
  company: ref Company
  sole_trader: ref SoleTrader

surface sub_list "Subs":
  uses entity Sub
  mode: list
  open: Company via company | SoleTrader via sole_trader
"""
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    surface = fragment.surfaces[0]
    assert surface.open_via == "company"
    assert surface.open_entity == "Company"
    assert [(t.entity, t.via) for t in surface.open_via_targets] == [
        ("Company", "company"),
        ("SoleTrader", "sole_trader"),
    ]


def test_data_row_first_non_null_htmx() -> None:
    """Rich data-table path uses multi-hop candidates."""
    from dazzle.render.fragment.primitives import RowCapabilities
    from dazzle.render.fragment.renderer._data_row import render_data_row

    columns = [{"key": "title", "type": "str"}]
    item = {
        "id": "s2",
        "title": "ST client",
        "company": None,
        "sole_trader": "st-uuid",
        "partnership": None,
    }
    html = render_data_row(
        columns,
        item,
        RowCapabilities(drill=True),
        detail_url_template="/app/company/{company}",
        detail_url_candidates=(
            "/app/company/{company}",
            "/app/soletrader/{sole_trader}",
            "/app/partnership/{partnership}",
        ),
        detail_url_fallback_template="/app/sub/{id}",
        entity_name="Sub",
        api_endpoint="/api/subs",
    )
    assert 'hx-get="/app/soletrader/st-uuid"' in html
    assert "{company}" not in html


def test_validate_open_via_wrong_mode_errors() -> None:
    from dazzle.core.validation.surfaces import validate_surfaces

    appspec = ir.AppSpec(
        name="t",
        domain=ir.DomainSpec(
            entities=[
                ir.EntitySpec(
                    name="Task",
                    title="Task",
                    fields=[
                        ir.FieldSpec(
                            name="assigned_to",
                            type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="User"),
                        ),
                    ],
                )
            ]
        ),
        surfaces=[
            ir.SurfaceSpec(
                name="task_detail",
                title="Detail",
                entity_ref="Task",
                mode=ir.SurfaceMode.VIEW,
                open_via="assigned_to",
                open_entity="User",
            )
        ],
    )
    errors, _ = validate_surfaces(appspec)
    assert any("open" in e.lower() and "list" in e.lower() for e in errors)
