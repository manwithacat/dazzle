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
