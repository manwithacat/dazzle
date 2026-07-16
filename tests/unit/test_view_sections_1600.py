"""#1600 Wedge B — multi-section VIEW overview chrome.

Client/context hubs declare multiple ``section`` blocks on ``mode: view``;
render must stack titled sections (not a single flat field grid) above
related groups. Paired with #1603 ``open: Entity via field`` for queue→hub.
"""

from __future__ import annotations

import pytest

from dazzle.core import ir
from dazzle.http.runtime.dispatch_ctx import _dispatch_ctx_from_detail
from dazzle.http.runtime.renderers.fragment_adapter import render_generic_detail
from dazzle.page.converters.template_compiler import compile_surface_to_context

pytestmark = pytest.mark.gate


def _user_entity() -> ir.EntitySpec:
    return ir.EntitySpec(
        name="User",
        title="User",
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                modifiers=[ir.FieldModifier.PK],
            ),
            ir.FieldSpec(name="name", type=ir.FieldType(kind=ir.FieldTypeKind.STR)),
            ir.FieldSpec(name="email", type=ir.FieldType(kind=ir.FieldTypeKind.STR)),
            ir.FieldSpec(name="role", type=ir.FieldType(kind=ir.FieldTypeKind.STR)),
        ],
    )


def _overview_surface() -> ir.SurfaceSpec:
    return ir.SurfaceSpec(
        name="user_detail",
        title="Team Member Overview",
        entity_ref="User",
        mode=ir.SurfaceMode.VIEW,
        sections=[
            ir.SurfaceSection(
                name="identity",
                title="Identity",
                elements=[
                    ir.SurfaceElement(field_name="name", label="Name"),
                    ir.SurfaceElement(field_name="email", label="Email"),
                ],
            ),
            ir.SurfaceSection(
                name="role",
                title="Role & access",
                elements=[
                    ir.SurfaceElement(field_name="role", label="Role"),
                ],
            ),
        ],
    )


def test_compile_view_preserves_section_titles() -> None:
    ctx = compile_surface_to_context(_overview_surface(), _user_entity())
    assert ctx.detail is not None
    assert len(ctx.detail.sections) == 2
    assert ctx.detail.sections[0].title == "Identity"
    assert [f.name for f in ctx.detail.sections[0].fields] == ["name", "email"]
    assert ctx.detail.sections[1].title == "Role & access"
    # Flat fields still populated for back-compat consumers.
    assert {f.name for f in ctx.detail.fields} >= {"name", "email", "role"}


def test_section_layout_strip_parses_and_renders_row() -> None:
    """layout: strip → horizontal status/RAG strip on VIEW (#1600)."""
    surface = ir.SurfaceSpec(
        name="user_detail",
        title="Overview",
        entity_ref="User",
        mode=ir.SurfaceMode.VIEW,
        sections=[
            ir.SurfaceSection(
                name="role",
                title="Role strip",
                layout="strip",
                elements=[
                    ir.SurfaceElement(field_name="role", label="Role"),
                    ir.SurfaceElement(field_name="name", label="Name"),
                ],
            ),
        ],
    )
    page = compile_surface_to_context(surface, _user_entity())
    assert page.detail is not None
    assert page.detail.sections[0].layout == "strip"
    page.detail.item = {"id": "u1", "name": "Ada", "role": "admin"}
    dctx = _dispatch_ctx_from_detail(page.detail, surface)
    assert dctx["sections"][0]["layout"] == "strip"
    html = render_generic_detail(surface, dctx)
    assert "Role strip" in html
    assert "admin" in html


def test_view_html_emits_section_headings() -> None:
    surface = _overview_surface()
    entity = _user_entity()
    page = compile_surface_to_context(surface, entity)
    assert page.detail is not None
    page.detail.item = {
        "id": "u1",
        "name": "Ada",
        "email": "ada@example.com",
        "role": "admin",
    }
    dctx = _dispatch_ctx_from_detail(page.detail, surface)
    assert len(dctx["sections"]) == 2
    html = render_generic_detail(surface, dctx)
    assert "Identity" in html
    assert "Role &amp; access" in html or "Role & access" in html
    assert "Ada" in html
    assert "ada@example.com" in html
