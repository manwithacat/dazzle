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
