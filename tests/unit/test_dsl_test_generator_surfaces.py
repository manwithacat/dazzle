"""Tests for surface-aware test generation (#248, #249, #250)."""

from __future__ import annotations

from dazzle.core.ir import AppSpec
from dazzle.core.ir.domain import DomainSpec, EntitySpec
from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.invariant import (
    ComparisonExpr,
    ComparisonOperator,
    InvariantFieldRef,
    InvariantLiteral,
    InvariantSpec,
    LogicalExpr,
    LogicalOperator,
)
from dazzle.core.ir.personas import PersonaSpec
from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle.core.ir.workspaces import WorkspaceAccessLevel, WorkspaceAccessSpec, WorkspaceSpec
from dazzle.testing.dsl_test_generator import DSLTestGenerator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pk_field() -> FieldSpec:
    return FieldSpec(
        name="id",
        type=FieldType(kind=FieldTypeKind.UUID),
        modifiers=[FieldModifier.PK],
    )


def _str_field(name: str, required: bool = True) -> FieldSpec:
    mods = [FieldModifier.REQUIRED] if required else []
    return FieldSpec(
        name=name,
        type=FieldType(kind=FieldTypeKind.STR, max_length=200),
        modifiers=mods,
    )


def _ref_field(name: str, target: str, required: bool = True) -> FieldSpec:
    mods = [FieldModifier.REQUIRED] if required else []
    return FieldSpec(
        name=name,
        type=FieldType(kind=FieldTypeKind.REF, ref_entity=target),
        modifiers=mods,
    )


def _enum_field(name: str, values: list[str], required: bool = True) -> FieldSpec:
    mods = [FieldModifier.REQUIRED] if required else []
    return FieldSpec(
        name=name,
        type=FieldType(kind=FieldTypeKind.ENUM, enum_values=values),
        modifiers=mods,
    )


def _make_appspec(
    entities: list[EntitySpec],
    surfaces: list[SurfaceSpec] | None = None,
    workspaces: list[WorkspaceSpec] | None = None,
    personas: list[PersonaSpec] | None = None,
) -> AppSpec:
    return AppSpec(
        name="test",
        title="Test",
        domain=DomainSpec(entities=entities),
        surfaces=surfaces or [],
        views=[],
        enums=[],
        processes=[],
        ledgers=[],
        transactions=[],
        workspaces=workspaces or [],
        experiences=[],
        personas=personas or [],
        stories=[],
        webhooks=[],
        approvals=[],
        slas=[],
        islands=[],
    )


def _or_not_null_invariant(field_a: str, field_b: str) -> InvariantSpec:
    """Build ``field_a != null or field_b != null`` invariant."""
    return InvariantSpec(
        description=f"{field_a} or {field_b} must be set",
        expression=LogicalExpr(
            operator=LogicalOperator.OR,
            left=ComparisonExpr(
                operator=ComparisonOperator.NE,
                left=InvariantFieldRef(path=[field_a]),
                right=InvariantLiteral(value=None),
            ),
            right=ComparisonExpr(
                operator=ComparisonOperator.NE,
                left=InvariantFieldRef(path=[field_b]),
                right=InvariantLiteral(value=None),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# #248: Skip CRUD CREATE for entities without create surface
# ---------------------------------------------------------------------------

TASK_ENTITY = EntitySpec(
    name="Task",
    title="Task",
    fields=[_pk_field(), _str_field("title")],
)

AUDIT_LOG_ENTITY = EntitySpec(
    name="AuditLog",
    title="Audit Log",
    fields=[_pk_field(), _str_field("message")],
)


class TestNoCreateSurface:
    """Entities without a create surface should not get CRUD CREATE tests."""

    def test_entity_with_create_surface_gets_create_test(self):
        surfaces = [SurfaceSpec(name="task_create", entity_ref="Task", mode=SurfaceMode.CREATE)]
        appspec = _make_appspec([TASK_ENTITY], surfaces=surfaces)
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        ids = {d["test_id"] for d in suite.designs}
        assert "CRUD_TASK_CREATE" in ids
        assert "CRUD_TASK_READ" in ids

    def test_entity_without_create_surface_no_create_test(self):
        # Only a list surface, no create surface
        surfaces = [SurfaceSpec(name="audit_list", entity_ref="AuditLog", mode=SurfaceMode.LIST)]
        appspec = _make_appspec([AUDIT_LOG_ENTITY], surfaces=surfaces)
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        ids = {d["test_id"] for d in suite.designs}
        assert "CRUD_AUDITLOG_CREATE" not in ids

    def test_read_only_entity_gets_read_test(self):
        surfaces = [SurfaceSpec(name="audit_list", entity_ref="AuditLog", mode=SurfaceMode.LIST)]
        appspec = _make_appspec([AUDIT_LOG_ENTITY], surfaces=surfaces)
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        ids = {d["test_id"] for d in suite.designs}
        assert "CRUD_AUDITLOG_READ" in ids

    def test_read_only_entity_tagged(self):
        surfaces = [SurfaceSpec(name="audit_list", entity_ref="AuditLog", mode=SurfaceMode.LIST)]
        appspec = _make_appspec([AUDIT_LOG_ENTITY], surfaces=surfaces)
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        read_test = next(d for d in suite.designs if d["test_id"] == "CRUD_AUDITLOG_READ")
        assert "read_only" in read_test["tags"]

    def test_read_only_entity_no_validation_tests(self):
        surfaces = [SurfaceSpec(name="audit_list", entity_ref="AuditLog", mode=SurfaceMode.LIST)]
        appspec = _make_appspec([AUDIT_LOG_ENTITY], surfaces=surfaces)
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        ids = {d["test_id"] for d in suite.designs}
        assert "VAL_AUDITLOG_REQUIRED" not in ids

    def test_no_surfaces_at_all_still_generates_read(self):
        """Entities with no surfaces at all get read-only tests (no POST exists)."""
        appspec = _make_appspec([TASK_ENTITY], surfaces=[])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        ids = {d["test_id"] for d in suite.designs}
        assert "CRUD_TASK_CREATE" not in ids
        assert "CRUD_TASK_READ" in ids

    def test_mixed_entities_correct_tests(self):
        """One entity with create, one without — correct tests for each."""
        surfaces = [SurfaceSpec(name="task_create", entity_ref="Task", mode=SurfaceMode.CREATE)]
        appspec = _make_appspec([TASK_ENTITY, AUDIT_LOG_ENTITY], surfaces=surfaces)
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        ids = {d["test_id"] for d in suite.designs}
        assert "CRUD_TASK_CREATE" in ids
        assert "CRUD_AUDITLOG_CREATE" not in ids
        assert "CRUD_AUDITLOG_READ" in ids


# ---------------------------------------------------------------------------
# #249: Invariant-aware ref fields in payloads
# ---------------------------------------------------------------------------

CONTACT_ENTITY = EntitySpec(
    name="Contact",
    title="Contact",
    fields=[_pk_field(), _str_field("name")],
)

COMPANY_ENTITY = EntitySpec(
    name="Company",
    title="Company",
    fields=[_pk_field(), _str_field("name")],
)

DOCUMENT_ENTITY = EntitySpec(
    name="Document",
    title="Document",
    fields=[
        _pk_field(),
        _ref_field("contact", "Contact", required=False),
        _ref_field("company", "Company", required=False),
        _enum_field("document_type", ["incorporation_cert", "tax_return"]),
    ],
    invariants=[_or_not_null_invariant("contact", "company")],
)


class TestInvariantRefFields:
    """Invariant OR-clause FK fields should be included in test payloads."""

    def test_invariant_ref_included_in_required_refs(self):
        surfaces = [
            SurfaceSpec(name="doc_create", entity_ref="Document", mode=SurfaceMode.CREATE),
            SurfaceSpec(name="contact_create", entity_ref="Contact", mode=SurfaceMode.CREATE),
            SurfaceSpec(name="company_create", entity_ref="Company", mode=SurfaceMode.CREATE),
        ]
        appspec = _make_appspec(
            [CONTACT_ENTITY, COMPANY_ENTITY, DOCUMENT_ENTITY], surfaces=surfaces
        )
        gen = DSLTestGenerator(appspec)
        refs = gen._get_required_refs(DOCUMENT_ENTITY)
        ref_fields = {r[0] for r in refs}
        # At least one of contact/company should be in refs (first from invariant)
        assert "contact" in ref_fields

    def test_create_test_has_parent_setup_for_invariant_ref(self):
        surfaces = [
            SurfaceSpec(name="doc_create", entity_ref="Document", mode=SurfaceMode.CREATE),
            SurfaceSpec(name="contact_create", entity_ref="Contact", mode=SurfaceMode.CREATE),
            SurfaceSpec(name="company_create", entity_ref="Company", mode=SurfaceMode.CREATE),
        ]
        appspec = _make_appspec(
            [CONTACT_ENTITY, COMPANY_ENTITY, DOCUMENT_ENTITY], surfaces=surfaces
        )
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        create_test = next(d for d in suite.designs if d["test_id"] == "CRUD_DOCUMENT_CREATE")
        # Setup steps should create a Contact (for the invariant)
        setup_targets = [s["target"] for s in create_test["steps"] if s["action"] == "create"]
        assert "entity:Contact" in setup_targets

    def test_entity_data_includes_invariant_ref_placeholder(self):
        surfaces = [
            SurfaceSpec(name="doc_create", entity_ref="Document", mode=SurfaceMode.CREATE),
            SurfaceSpec(name="contact_create", entity_ref="Contact", mode=SurfaceMode.CREATE),
            SurfaceSpec(name="company_create", entity_ref="Company", mode=SurfaceMode.CREATE),
        ]
        appspec = _make_appspec(
            [CONTACT_ENTITY, COMPANY_ENTITY, DOCUMENT_ENTITY], surfaces=surfaces
        )
        gen = DSLTestGenerator(appspec)
        refs = gen._get_required_refs(DOCUMENT_ENTITY)
        data = gen._generate_entity_data_with_refs(DOCUMENT_ENTITY, refs)
        # contact should have a $ref: placeholder
        assert "contact" in data
        assert str(data["contact"]).startswith("$ref:")


# ---------------------------------------------------------------------------
# #250: Workspace tests specify persona from access rules
# ---------------------------------------------------------------------------


class TestWorkspacePersona:
    """Workspace tests should set persona from access rules."""

    def test_workspace_with_persona_access(self):
        ws = WorkspaceSpec(
            name="agent_dashboard",
            title="Agent Dashboard",
            access=WorkspaceAccessSpec(
                level=WorkspaceAccessLevel.PERSONA,
                allow_personas=["agent", "admin"],
            ),
        )
        appspec = _make_appspec([], workspaces=[ws])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        nav_test = next(d for d in suite.designs if d["test_id"] == "WS_AGENT_DASHBOARD_NAV")
        assert nav_test["persona"] == "agent"

    def test_workspace_route_test_has_persona(self):
        ws = WorkspaceSpec(
            name="agent_dashboard",
            title="Agent Dashboard",
            access=WorkspaceAccessSpec(
                level=WorkspaceAccessLevel.PERSONA,
                allow_personas=["agent"],
            ),
        )
        appspec = _make_appspec([], workspaces=[ws])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        route_test = next(d for d in suite.designs if d["test_id"] == "WS_AGENT_DASHBOARD_ROUTE")
        assert route_test["persona"] == "agent"

    def test_workspace_without_access_no_persona(self):
        ws = WorkspaceSpec(name="public_dash", title="Public Dashboard")
        appspec = _make_appspec([], workspaces=[ws])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        nav_test = next(d for d in suite.designs if d["test_id"] == "WS_PUBLIC_DASH_NAV")
        assert nav_test["persona"] is None

    def test_workspace_nav_includes_login_step(self):
        ws = WorkspaceSpec(
            name="agent_dashboard",
            title="Agent Dashboard",
            access=WorkspaceAccessSpec(
                level=WorkspaceAccessLevel.PERSONA,
                allow_personas=["agent"],
            ),
        )
        appspec = _make_appspec([], workspaces=[ws])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        nav_test = next(d for d in suite.designs if d["test_id"] == "WS_AGENT_DASHBOARD_NAV")
        first_step = nav_test["steps"][0]
        assert first_step["action"] == "login_as"
        assert first_step["target"] == "agent"

    def test_workspace_without_access_no_login_step(self):
        ws = WorkspaceSpec(name="public_dash", title="Public Dashboard")
        appspec = _make_appspec([], workspaces=[ws])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        nav_test = next(d for d in suite.designs if d["test_id"] == "WS_PUBLIC_DASH_NAV")
        actions = [s["action"] for s in nav_test["steps"]]
        assert "login_as" not in actions

    def test_multiple_workspaces_correct_personas(self):
        ws_agent = WorkspaceSpec(
            name="agent_dash",
            title="Agent",
            access=WorkspaceAccessSpec(
                level=WorkspaceAccessLevel.PERSONA,
                allow_personas=["agent"],
            ),
        )
        ws_admin = WorkspaceSpec(
            name="admin_dash",
            title="Admin",
            access=WorkspaceAccessSpec(
                level=WorkspaceAccessLevel.PERSONA,
                allow_personas=["admin"],
            ),
        )
        appspec = _make_appspec([], workspaces=[ws_agent, ws_admin])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        agent_nav = next(d for d in suite.designs if d["test_id"] == "WS_AGENT_DASH_NAV")
        admin_nav = next(d for d in suite.designs if d["test_id"] == "WS_ADMIN_DASH_NAV")
        assert agent_nav["persona"] == "agent"
        assert admin_nav["persona"] == "admin"
