"""
Tests for admin entity field definitions and the admin entity builder.

Covers:
  - Task 1: ADMIN_ENTITY_DEFS and individual FIELDS constants
  - Task 2: _build_admin_entities profile-gating and EntitySpec shape
  - Task 3: Collision detection for synthetic admin names
  - Task 4: Admin surface builder — LIST surfaces for platform entities
  - Task 5: Admin workspace builder — profile-gated regions + nav groups
"""

import pytest

from dazzle.core import ir
from dazzle.core.errors import LinkError
from dazzle.core.ir.admin_entities import (
    ADMIN_ENTITY_DEFS,
    VIRTUAL_ENTITY_NAMES,
)
from dazzle.core.ir.feedback_widget import FeedbackWidgetSpec
from dazzle.core.ir.module import AppConfigSpec
from dazzle.core.ir.security import SecurityConfig, SecurityProfile
from dazzle.core.ir.surfaces import SurfaceMode

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_security(profile: SecurityProfile, *, multi_tenant: bool = False) -> SecurityConfig:
    """Construct a SecurityConfig from a profile shortcut."""
    return SecurityConfig.from_profile(profile, multi_tenant=multi_tenant)


# ---------------------------------------------------------------------------
# Task 1 — Field tuple shape tests
# ---------------------------------------------------------------------------


class TestFieldTuples:
    """Shape and content tests for the individual FIELDS constants."""

    def _all_field_tuples(
        self,
    ) -> list[tuple[str, str, tuple[str, ...], str | None]]:
        """Collect every field tuple across all entity defs."""
        result = []
        for _name, _title, _intent, fields_tuple, _patterns, _gate in ADMIN_ENTITY_DEFS:
            result.extend(fields_tuple)
        return result

    def test_field_tuples_have_correct_shape(self) -> None:
        """Every field tuple is (str, str, tuple, str|None)."""
        for entry in self._all_field_tuples():
            assert len(entry) == 4, f"Expected 4-tuple, got {entry!r}"
            name, type_str, modifiers, default = entry
            assert isinstance(name, str)
            assert isinstance(type_str, str)
            assert isinstance(modifiers, tuple)
            assert default is None or isinstance(default, str)

    def test_all_entities_have_pk(self) -> None:
        """Every entity definition has exactly one 'pk' field named 'id'."""
        for ent_name, _title, _intent, fields_tuple, _patterns, _gate in ADMIN_ENTITY_DEFS:
            pk_fields = [f for f in fields_tuple if "pk" in f[2]]
            assert len(pk_fields) == 1, (
                f"{ent_name}: expected exactly one pk field, got {pk_fields}"
            )
            assert pk_fields[0][0] == "id", (
                f"{ent_name}: pk field should be named 'id', got {pk_fields[0][0]!r}"
            )

    def test_admin_entity_defs_count(self) -> None:
        """ADMIN_ENTITY_DEFS contains exactly 7 entity definitions."""
        assert len(ADMIN_ENTITY_DEFS) == 7

    def test_virtual_entities_are_subset(self) -> None:
        """VIRTUAL_ENTITY_NAMES is a subset of all entity names in ADMIN_ENTITY_DEFS."""
        all_names = {entry[0] for entry in ADMIN_ENTITY_DEFS}
        assert VIRTUAL_ENTITY_NAMES <= all_names, (
            f"Virtual names not subset: {VIRTUAL_ENTITY_NAMES - all_names}"
        )


# ---------------------------------------------------------------------------
# Task 2 — _build_admin_entities tests
# ---------------------------------------------------------------------------


class TestBuildAdminEntities:
    """_build_admin_entities profile-gating and EntitySpec correctness."""

    def test_basic_profile_gets_all_profile_entities(self) -> None:
        """BASIC profile receives only entities with no profile gate (3 of 7)."""
        from dazzle.core.admin_builder import _build_admin_entities

        security = _make_security(SecurityProfile.BASIC)
        entities = _build_admin_entities(security)
        names = {e.name for e in entities}
        # profile_gate=None entities (available on all profiles)
        assert "SystemHealth" in names
        assert "DeployHistory" in names
        # profile_gate="standard" entities should NOT be present for basic
        assert "ProcessRun" not in names
        assert "SessionInfo" not in names
        assert "LogEntry" not in names
        assert "EventTrace" not in names

    def test_standard_profile_gets_all_entities(self) -> None:
        """STANDARD profile receives all 7 admin entities."""
        from dazzle.core.admin_builder import _build_admin_entities

        security = _make_security(SecurityProfile.STANDARD)
        entities = _build_admin_entities(security)
        assert len(entities) == 7

    def test_strict_profile_gets_all_entities(self) -> None:
        """STRICT profile receives all 7 admin entities."""
        from dazzle.core.admin_builder import _build_admin_entities

        security = _make_security(SecurityProfile.STRICT)
        entities = _build_admin_entities(security)
        assert len(entities) == 7

    def test_standard_profile_includes_log_and_event_entities(self) -> None:
        """STANDARD profile includes LogEntry and EventTrace."""
        from dazzle.core.admin_builder import _build_admin_entities

        security = _make_security(SecurityProfile.STANDARD)
        entities = _build_admin_entities(security)
        names = {e.name for e in entities}
        assert "LogEntry" in names
        assert "EventTrace" in names

    def test_entities_have_platform_domain(self) -> None:
        """All generated entities carry domain='platform'."""
        from dazzle.core.admin_builder import _build_admin_entities

        security = _make_security(SecurityProfile.STRICT)
        for entity in _build_admin_entities(security):
            assert entity.domain == "platform", (
                f"{entity.name}: expected domain='platform', got {entity.domain!r}"
            )

    def test_entities_have_system_pattern(self) -> None:
        """All generated entities include 'system' in their patterns list."""
        from dazzle.core.admin_builder import _build_admin_entities

        security = _make_security(SecurityProfile.STRICT)
        for entity in _build_admin_entities(security):
            assert "system" in entity.patterns, (
                f"{entity.name}: 'system' not in patterns {entity.patterns!r}"
            )

    def test_entities_are_read_only(self) -> None:
        """Generated entities only have READ and LIST permissions (no CREATE/UPDATE/DELETE)."""
        from dazzle.core.admin_builder import _build_admin_entities
        from dazzle.core.ir.domain import PermissionKind

        security = _make_security(SecurityProfile.STRICT)
        write_ops = {PermissionKind.CREATE, PermissionKind.UPDATE, PermissionKind.DELETE}

        for entity in _build_admin_entities(security):
            assert entity.access is not None, f"{entity.name}: access is None"
            ops = {rule.operation for rule in entity.access.permissions}
            illegal = ops & write_ops
            assert not illegal, (
                f"{entity.name}: found write operations {illegal!r} — should be read-only"
            )
            assert PermissionKind.READ in ops, f"{entity.name}: missing READ permission"
            assert PermissionKind.LIST in ops, f"{entity.name}: missing LIST permission"

    def test_entities_require_admin_personas(self) -> None:
        """All permission rules are scoped to ['admin', 'super_admin']."""
        from dazzle.core.admin_builder import _build_admin_entities

        security = _make_security(SecurityProfile.STRICT)
        expected_personas = ["admin", "super_admin"]

        for entity in _build_admin_entities(security):
            assert entity.access is not None, f"{entity.name}: access is None"
            for rule in entity.access.permissions:
                assert rule.personas == expected_personas, (
                    f"{entity.name} op={rule.operation}: "
                    f"expected personas {expected_personas!r}, got {rule.personas!r}"
                )


# ---------------------------------------------------------------------------
# Task 3 — Collision detection tests
# ---------------------------------------------------------------------------


class TestCollisionDetection:
    """_check_collisions raises LinkError on name collisions."""

    def test_entity_collision_raises(self) -> None:
        """Entity name collision with synthetic names raises LinkError."""
        from dazzle.core.admin_builder import _check_collisions

        with pytest.raises(LinkError, match="SystemHealth"):
            _check_collisions(
                existing_entity_names={"SystemHealth", "Task", "User"},
                existing_workspace_names=set(),
                synthetic_entity_names={"SystemHealth", "DeployHistory"},
                synthetic_workspace_names=set(),
            )

    def test_workspace_collision_raises(self) -> None:
        """Workspace name collision with synthetic names raises LinkError."""
        from dazzle.core.admin_builder import _check_collisions

        with pytest.raises(LinkError, match="_platform_admin"):
            _check_collisions(
                existing_entity_names=set(),
                existing_workspace_names={"_platform_admin", "dashboard"},
                synthetic_entity_names=set(),
                synthetic_workspace_names={"_platform_admin"},
            )

    def test_no_collision_passes(self) -> None:
        """No overlap between existing and synthetic names raises no error."""
        from dazzle.core.admin_builder import _check_collisions

        # Should not raise
        _check_collisions(
            existing_entity_names={"Task", "User", "Project"},
            existing_workspace_names={"my_dashboard"},
            synthetic_entity_names={"SystemHealth", "DeployHistory"},
            synthetic_workspace_names={"_platform_admin"},
        )


# ---------------------------------------------------------------------------
# Task 4 — Admin surfaces builder tests
# ---------------------------------------------------------------------------


class TestBuildAdminSurfaces:
    """_build_admin_surfaces profile-gating and SurfaceSpec shape."""

    def test_standard_generates_session_surface(self) -> None:
        """STANDARD profile includes the _admin_sessions surface."""
        from dazzle.core.admin_builder import _build_admin_surfaces

        security = _make_security(SecurityProfile.STANDARD)
        surfaces = _build_admin_surfaces(security)
        names = {s.name for s in surfaces}
        assert "_admin_sessions" in names

    def test_basic_no_session_surface(self) -> None:
        """BASIC profile does NOT include the _admin_sessions surface."""
        from dazzle.core.admin_builder import _build_admin_surfaces

        security = _make_security(SecurityProfile.BASIC)
        surfaces = _build_admin_surfaces(security)
        names = {s.name for s in surfaces}
        assert "_admin_sessions" not in names

    def test_surfaces_require_admin_personas(self) -> None:
        """All surfaces require auth and allow only admin/super_admin personas."""
        from dazzle.core.admin_builder import _build_admin_surfaces

        security = _make_security(SecurityProfile.STANDARD)
        for surface in _build_admin_surfaces(security):
            assert surface.access is not None, f"{surface.name}: access is None"
            assert surface.access.require_auth is True, f"{surface.name}: require_auth is False"
            assert set(surface.access.allow_personas) == {"admin", "super_admin"}, (
                f"{surface.name}: unexpected personas {surface.access.allow_personas!r}"
            )

    def test_surfaces_are_list_mode(self) -> None:
        """All generated surfaces have mode=LIST."""
        from dazzle.core.admin_builder import _build_admin_surfaces

        security = _make_security(SecurityProfile.STANDARD)
        for surface in _build_admin_surfaces(security):
            assert surface.mode == SurfaceMode.LIST, (
                f"{surface.name}: expected LIST mode, got {surface.mode!r}"
            )

    def test_deploy_surface_always_present(self) -> None:
        """_admin_deploys is present for all security profiles."""
        from dazzle.core.admin_builder import _build_admin_surfaces

        for profile in SecurityProfile:
            security = _make_security(profile)
            names = {s.name for s in _build_admin_surfaces(security)}
            assert "_admin_deploys" in names, f"_admin_deploys missing for profile={profile}"

    def test_health_surface_always_present(self) -> None:
        """_admin_health is present for all security profiles."""
        from dazzle.core.admin_builder import _build_admin_surfaces

        for profile in SecurityProfile:
            security = _make_security(profile)
            names = {s.name for s in _build_admin_surfaces(security)}
            assert "_admin_health" in names, f"_admin_health missing for profile={profile}"


# ---------------------------------------------------------------------------
# Task 5 — Admin workspace builder tests
# ---------------------------------------------------------------------------


class TestBuildAdminWorkspaces:
    """_build_admin_workspaces workspace count, regions, and access."""

    def test_single_tenant_one_workspace(self) -> None:
        """Single-tenant app produces only _platform_admin."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD)
        workspaces = _build_admin_workspaces(security, multi_tenant=False, feedback_enabled=False)
        names = {w.name for w in workspaces}
        assert names == {"_platform_admin"}

    def test_multi_tenant_two_workspaces(self) -> None:
        """Multi-tenant app produces _platform_admin and _tenant_admin."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD, multi_tenant=True)
        workspaces = _build_admin_workspaces(security, multi_tenant=True, feedback_enabled=False)
        names = {w.name for w in workspaces}
        assert names == {"_platform_admin", "_tenant_admin"}

    def test_platform_admin_super_admin_only_multi_tenant(self) -> None:
        """In multi-tenant mode, _platform_admin allows only super_admin."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD, multi_tenant=True)
        workspaces = _build_admin_workspaces(security, multi_tenant=True, feedback_enabled=False)
        platform = next(w for w in workspaces if w.name == "_platform_admin")
        assert platform.access is not None
        assert platform.access.allow_personas == ["super_admin"]

    def test_platform_admin_both_personas_single_tenant(self) -> None:
        """In single-tenant mode, _platform_admin allows admin and super_admin."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD)
        workspaces = _build_admin_workspaces(security, multi_tenant=False, feedback_enabled=False)
        platform = next(w for w in workspaces if w.name == "_platform_admin")
        assert platform.access is not None
        assert set(platform.access.allow_personas) == {"admin", "super_admin"}

    def test_tenant_admin_persona(self) -> None:
        """_tenant_admin allows only admin persona."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD, multi_tenant=True)
        workspaces = _build_admin_workspaces(security, multi_tenant=True, feedback_enabled=False)
        tenant = next(w for w in workspaces if w.name == "_tenant_admin")
        assert tenant.access is not None
        assert tenant.access.allow_personas == ["admin"]

    def test_tenant_admin_has_subset_of_regions(self) -> None:
        """_tenant_admin regions are a strict subset of _platform_admin regions."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD, multi_tenant=True)
        workspaces = _build_admin_workspaces(security, multi_tenant=True, feedback_enabled=True)
        platform = next(w for w in workspaces if w.name == "_platform_admin")
        tenant = next(w for w in workspaces if w.name == "_tenant_admin")
        platform_names = {r.name for r in platform.regions}
        tenant_names = {r.name for r in tenant.regions}
        assert tenant_names < platform_names, (
            f"Tenant regions {tenant_names!r} are not a strict subset of "
            f"platform regions {platform_names!r}"
        )

    def test_tenant_admin_no_tenants_region(self) -> None:
        """_tenant_admin does not include the 'tenants' region."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD, multi_tenant=True)
        workspaces = _build_admin_workspaces(security, multi_tenant=True, feedback_enabled=False)
        tenant = next(w for w in workspaces if w.name == "_tenant_admin")
        tenant_region_names = {r.name for r in tenant.regions}
        assert "tenants" not in tenant_region_names

    def test_feedback_region_when_enabled(self) -> None:
        """'feedback' region appears in _platform_admin when feedback is enabled."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD)
        workspaces = _build_admin_workspaces(security, multi_tenant=False, feedback_enabled=True)
        platform = next(w for w in workspaces if w.name == "_platform_admin")
        region_names = {r.name for r in platform.regions}
        assert "feedback" in region_names

    def test_no_feedback_region_when_disabled(self) -> None:
        """'feedback' region is absent when feedback is disabled."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD)
        workspaces = _build_admin_workspaces(security, multi_tenant=False, feedback_enabled=False)
        platform = next(w for w in workspaces if w.name == "_platform_admin")
        region_names = {r.name for r in platform.regions}
        assert "feedback" not in region_names

    def test_nav_groups_present(self) -> None:
        """All three nav groups (Management, Observability, Operations) are present."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD)
        workspaces = _build_admin_workspaces(security, multi_tenant=False, feedback_enabled=True)
        platform = next(w for w in workspaces if w.name == "_platform_admin")
        labels = {g.label for g in platform.nav_groups}
        assert labels == {"Management", "Observability", "Operations"}

    def test_basic_profile_fewer_regions(self) -> None:
        """BASIC profile produces fewer regions than STANDARD in _platform_admin."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        basic_security = _make_security(SecurityProfile.BASIC)
        standard_security = _make_security(SecurityProfile.STANDARD)

        basic_ws = _build_admin_workspaces(
            basic_security, multi_tenant=False, feedback_enabled=True
        )
        standard_ws = _build_admin_workspaces(
            standard_security, multi_tenant=False, feedback_enabled=True
        )

        basic_platform = next(w for w in basic_ws if w.name == "_platform_admin")
        standard_platform = next(w for w in standard_ws if w.name == "_platform_admin")

        assert len(basic_platform.regions) < len(standard_platform.regions), (
            f"Expected BASIC ({len(basic_platform.regions)}) < STANDARD "
            f"({len(standard_platform.regions)}) region count"
        )


# ---------------------------------------------------------------------------
# Task 6 — build_admin_infrastructure entry point tests
# ---------------------------------------------------------------------------


class TestBuildAdminInfrastructure:
    """build_admin_infrastructure top-level entry point."""

    def test_returns_entities_surfaces_workspaces(self) -> None:
        """Standard profile returns 5 entities, >0 surfaces, and 1 workspace."""
        from dazzle.core.admin_builder import build_admin_infrastructure

        security = _make_security(SecurityProfile.STANDARD)
        app_config = AppConfigSpec(security_profile="standard", multi_tenant=False)
        entities, surfaces, workspaces = build_admin_infrastructure(
            entities=[],
            surfaces=[],
            security_config=security,
            app_config=app_config,
            feedback_widget=None,
            existing_workspaces=[],
        )
        assert len(entities) == 7
        assert len(surfaces) > 0
        assert len(workspaces) == 1

    def test_collision_with_existing_entity(self) -> None:
        """User entity named SystemHealth raises LinkError."""
        from dazzle.core.admin_builder import build_admin_infrastructure

        security = _make_security(SecurityProfile.BASIC)
        app_config = AppConfigSpec(security_profile="basic")
        colliding = ir.EntitySpec(
            name="SystemHealth",
            title="My Health",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                )
            ],
        )
        with pytest.raises(LinkError, match="SystemHealth"):
            build_admin_infrastructure(
                entities=[colliding],
                surfaces=[],
                security_config=security,
                app_config=app_config,
                feedback_widget=None,
                existing_workspaces=[],
            )

    def test_multi_tenant_generates_two_workspaces(self) -> None:
        """Multi-tenant app generates _platform_admin and _tenant_admin."""
        from dazzle.core.admin_builder import build_admin_infrastructure

        security = _make_security(SecurityProfile.STANDARD, multi_tenant=True)
        app_config = AppConfigSpec(security_profile="standard", multi_tenant=True)
        _, _, workspaces = build_admin_infrastructure(
            entities=[],
            surfaces=[],
            security_config=security,
            app_config=app_config,
            feedback_widget=None,
            existing_workspaces=[],
        )
        assert {w.name for w in workspaces} == {"_platform_admin", "_tenant_admin"}

    def test_feedback_enabled_includes_feedback_region(self) -> None:
        """Enabled feedback widget causes 'feedback' region to appear in _platform_admin."""
        from dazzle.core.admin_builder import build_admin_infrastructure

        security = _make_security(SecurityProfile.STANDARD)
        app_config = AppConfigSpec(security_profile="standard")
        fw = FeedbackWidgetSpec(enabled=True)
        _, _, workspaces = build_admin_infrastructure(
            entities=[],
            surfaces=[],
            security_config=security,
            app_config=app_config,
            feedback_widget=fw,
            existing_workspaces=[],
        )
        platform = next(w for w in workspaces if w.name == "_platform_admin")
        assert "feedback" in {r.name for r in platform.regions}
