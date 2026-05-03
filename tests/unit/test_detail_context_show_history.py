"""Tests for #956 cycle 10 — `show_history` flows DetailContext.

Cycle 8 added `SurfaceSpec.show_history`; cycle 10 propagates the
flag from the compiled IR into the runtime `DetailContext` so the
template renderer (cycle 11) can decide whether to include the
HTMX-loaded audit history fragment.

Pure compile-time wiring — no runtime fetch / RBAC behaviour
changes. Tests verify the field exists with the right default and
the `_compile_view_surface` path threads the value through.
"""

from __future__ import annotations

import pytest

from dazzle.core import ir
from dazzle.core.ir import SurfaceMode, SurfaceSpec
from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind

# ---------------------------------------------------------------------------
# DetailContext field
# ---------------------------------------------------------------------------


class TestDetailContextField:
    def test_default_false(self):
        from dazzle_ui.runtime.template_context import DetailContext

        ctx = DetailContext(entity_name="Manuscript", title="M", fields=[])
        assert ctx.show_history is False

    def test_explicit_true(self):
        from dazzle_ui.runtime.template_context import DetailContext

        ctx = DetailContext(entity_name="Manuscript", title="M", fields=[], show_history=True)
        assert ctx.show_history is True


# ---------------------------------------------------------------------------
# _compile_view_surface propagation
# ---------------------------------------------------------------------------


def _make_entity() -> ir.EntitySpec:
    return ir.EntitySpec(
        name="Manuscript",
        title="Manuscript",
        intent="Test entity",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            FieldSpec(
                name="status",
                type=FieldType(kind=FieldTypeKind.STR, max_length=50),
                modifiers=[FieldModifier.REQUIRED],
            ),
        ],
    )


def _make_surface(*, show_history: bool) -> SurfaceSpec:
    return SurfaceSpec(
        name="manuscript_detail",
        title="Detail",
        entity_ref="Manuscript",
        mode=SurfaceMode.VIEW,
        show_history=show_history,
    )


@pytest.fixture()
def compile_view():
    from dazzle_ui.converters.template_compiler import _compile_view_surface

    def _compile(*, show_history: bool):
        return _compile_view_surface(
            surface=_make_surface(show_history=show_history),
            entity=_make_entity(),
            entity_name="Manuscript",
            api_endpoint="/api/manuscripts",
            entity_slug="manuscripts",
            app_prefix="/app",
        )

    return _compile


class TestCompileViewSurfacePropagation:
    def test_show_history_true_propagates(self, compile_view):
        page = compile_view(show_history=True)
        assert page.detail is not None
        assert page.detail.show_history is True

    def test_show_history_false_propagates(self, compile_view):
        page = compile_view(show_history=False)
        assert page.detail is not None
        assert page.detail.show_history is False
