"""PersonaVariant ``defaults:`` wiring for create/edit forms."""

from __future__ import annotations

from dazzle.core import ir
from dazzle.core.ir.surfaces import SurfaceSection
from dazzle.http.runtime.page_routes import _apply_persona_form_overrides
from dazzle.page.converters.template_compiler import _compile_form_surface
from dazzle.render.context import FieldContext, FormContext


def _entity() -> ir.EntitySpec:
    return ir.EntitySpec(
        name="Device",
        label="Device",
        fields=[
            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID), pk=True),
            ir.FieldSpec(name="status", type=ir.FieldType(kind=ir.FieldTypeKind.STR)),
            ir.FieldSpec(name="reported_by_id", type=ir.FieldType(kind=ir.FieldTypeKind.STR)),
        ],
    )


def test_compile_form_collects_persona_defaults() -> None:
    surface = ir.SurfaceSpec(
        name="device_create",
        title="Create Device",
        mode=ir.SurfaceMode.CREATE,
        entity_ref="Device",
        sections=[SurfaceSection(name="main", elements=[])],
        ux=ir.UXSpec(
            persona_variants=[
                ir.PersonaVariant(
                    persona="engineer",
                    defaults={"status": "prototype", "reported_by_id": "current_user"},
                ),
            ]
        ),
    )
    ctx = _compile_form_surface(surface, _entity(), "Device", "/devices", "device", "/app")
    assert ctx.form is not None
    assert ctx.form.persona_defaults["engineer"] == {
        "status": "prototype",
        "reported_by_id": "current_user",
    }


def test_apply_defaults_on_create() -> None:
    form = FormContext(
        entity_name="Device",
        title="Create",
        fields=[FieldContext(name="status", label="Status", type="text")],
        action_url="/devices",
        mode="create",
        persona_defaults={"engineer": {"status": "prototype"}},
    )
    assert _apply_persona_form_overrides(form, ["role_engineer"]) is False
    assert form.initial_values["status"] == "prototype"


def test_current_user_token_resolves() -> None:
    form = FormContext(
        entity_name="Issue",
        title="Create",
        fields=[FieldContext(name="reported_by_id", label="By", type="text")],
        action_url="/issues",
        mode="create",
        persona_defaults={"tester": {"reported_by_id": "current_user"}},
    )
    assert _apply_persona_form_overrides(form, ["tester"], user_id="user-42") is False
    assert form.initial_values["reported_by_id"] == "user-42"


def test_defaults_do_not_overwrite_existing_values() -> None:
    form = FormContext(
        entity_name="Device",
        title="Edit",
        fields=[FieldContext(name="status", label="Status", type="text")],
        action_url="/devices/1",
        mode="edit",
        initial_values={"status": "live"},
        persona_defaults={"engineer": {"status": "prototype"}},
    )
    _apply_persona_form_overrides(form, ["engineer"])
    assert form.initial_values["status"] == "live"
