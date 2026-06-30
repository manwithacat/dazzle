"""#1489 — two surfaces resolving to the same route are a hard validate error,
and the auto-injected tenant-admin surface is suppressed when the app already
declares a user list surface on the tenant entity (it would otherwise collide
and be silently dropped at boot).
"""

from dazzle.core import ir
from dazzle.core.archetype_expander import expand_archetypes, generate_archetype_surfaces
from dazzle.core.validation.surfaces import validate_surfaces


def _entity(name: str) -> ir.EntitySpec:
    return ir.EntitySpec(
        name=name,
        title=name,
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                modifiers=[ir.FieldModifier.PK],
            ),
            ir.FieldSpec(
                name="title",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
            ),
        ],
    )


def _surface(name: str, entity: str, mode: ir.SurfaceMode) -> ir.SurfaceSpec:
    return ir.SurfaceSpec(
        name=name,
        title=name,
        entity_ref=entity,
        mode=mode,
        sections=[
            ir.SurfaceSection(
                name="main",
                elements=[ir.SurfaceElement(field_name="title", label="Title")],
            )
        ],
    )


def _appspec(entities, surfaces, experiences=None) -> ir.AppSpec:
    return ir.AppSpec(
        name="Test",
        domain=ir.DomainSpec(entities=entities),
        surfaces=surfaces,
        experiences=experiences or [],
        apis=[],
        foreign_models=[],
        integrations=[],
    )


# ── validate-time collision error ────────────────────────────────────────


def test_two_list_surfaces_on_same_entity_is_an_error() -> None:
    appspec = _appspec(
        [_entity("Invoice")],
        [
            _surface("invoice_list", "Invoice", ir.SurfaceMode.LIST),
            _surface("audit_export", "Invoice", ir.SurfaceMode.LIST),
        ],
    )
    errors, _ = validate_surfaces(appspec)
    collision = [e for e in errors if "resolve to the same route" in e]
    assert len(collision) == 1
    assert "invoice_list" in collision[0] and "audit_export" in collision[0]


def test_view_and_edit_on_same_entity_do_not_collide() -> None:
    # Different modes route to different paths — must NOT be flagged.
    appspec = _appspec(
        [_entity("Invoice")],
        [
            _surface("invoice_detail", "Invoice", ir.SurfaceMode.VIEW),
            _surface("invoice_edit", "Invoice", ir.SurfaceMode.EDIT),
        ],
    )
    errors, _ = validate_surfaces(appspec)
    assert not [e for e in errors if "resolve to the same route" in e]


def test_custom_mode_surfaces_are_exempt() -> None:
    appspec = _appspec(
        [_entity("Invoice")],
        [
            _surface("custom_a", "Invoice", ir.SurfaceMode.CUSTOM),
            _surface("custom_b", "Invoice", ir.SurfaceMode.CUSTOM),
        ],
    )
    errors, _ = validate_surfaces(appspec)
    assert not [e for e in errors if "resolve to the same route" in e]


def test_experience_step_surfaces_are_exempt_1512() -> None:
    # #1512: a view surface that exists only to be rendered inline as an
    # experience surface-step renders by name, never claiming the entity's
    # auto-route — so it must NOT collide with the entity's route-mounted view.
    appspec = _appspec(
        [_entity("Employee")],
        [
            _surface("employee_detail", "Employee", ir.SurfaceMode.VIEW),
            _surface("employee_review_step", "Employee", ir.SurfaceMode.VIEW),
        ],
        experiences=[
            ir.ExperienceSpec(
                name="onboarding",
                title="Onboarding",
                start_step="review",
                steps=[
                    ir.ExperienceStep(
                        name="review",
                        kind=ir.StepKind.SURFACE,
                        surface="employee_review_step",
                    )
                ],
            )
        ],
    )
    errors, _ = validate_surfaces(appspec)
    assert not [e for e in errors if "resolve to the same route" in e]


def test_route_mounted_collision_still_errors_with_a_step_surface_present() -> None:
    # The exemption is narrow: two genuinely route-mounted list surfaces still
    # collide even when an unrelated experience-step surface exists.
    appspec = _appspec(
        [_entity("Invoice")],
        [
            _surface("invoice_list", "Invoice", ir.SurfaceMode.LIST),
            _surface("audit_export", "Invoice", ir.SurfaceMode.LIST),
            _surface("invoice_step", "Invoice", ir.SurfaceMode.VIEW),
        ],
        experiences=[
            ir.ExperienceSpec(
                name="flow",
                title="Flow",
                start_step="s",
                steps=[
                    ir.ExperienceStep(name="s", kind=ir.StepKind.SURFACE, surface="invoice_step")
                ],
            )
        ],
    )
    errors, _ = validate_surfaces(appspec)
    collision = [e for e in errors if "resolve to the same route" in e]
    assert len(collision) == 1
    assert "invoice_list" in collision[0] and "audit_export" in collision[0]


def test_single_list_surface_per_entity_is_clean() -> None:
    appspec = _appspec(
        [_entity("Invoice"), _entity("Supplier")],
        [
            _surface("invoice_list", "Invoice", ir.SurfaceMode.LIST),
            _surface("supplier_list", "Supplier", ir.SurfaceMode.LIST),
        ],
    )
    errors, _ = validate_surfaces(appspec)
    assert not [e for e in errors if "resolve to the same route" in e]


# ── tenant-admin auto-injection suppression ──────────────────────────────

_TENANT_DSL = """
module test
app Test "Test"

entity Org "Org":
    archetype: tenant
    id: uuid pk
    name: str(100)
    region: str(50)
"""


def _expand_tenant():
    from tests.unit.test_archetype_expander import _create_test_module

    module, symbols = _create_test_module(_TENANT_DSL)
    return expand_archetypes(list(module.fragment.entities), symbols)


def test_tenant_admin_injected_when_no_user_list() -> None:
    expanded = _expand_tenant()
    surfaces = generate_archetype_surfaces(expanded, [])
    # The auto-admin tenant list surface is injected.
    assert any(s.mode == ir.SurfaceMode.LIST and s.entity_ref == "Org" for s in surfaces)


def test_tenant_admin_suppressed_when_user_list_exists() -> None:
    expanded = _expand_tenant()
    user_list = _surface("org_list", "Org", ir.SurfaceMode.LIST)
    surfaces = generate_archetype_surfaces(expanded, [user_list])
    # No auto-admin list surface — the user's wins (no GET /orgs collision).
    assert not [s for s in surfaces if s.mode == ir.SurfaceMode.LIST and s.entity_ref == "Org"]
