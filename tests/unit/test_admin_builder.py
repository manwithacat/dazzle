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
from dazzle.core.ir.admin_entities import ADMIN_ENTITY_DEFS
from dazzle.core.ir.feedback_widget import FeedbackWidgetSpec
from dazzle.core.ir.module import AppConfigSpec
from dazzle.core.ir.security import SecurityConfig, SecurityProfile
from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.db.virtual import VIRTUAL_ENTITY_NAMES

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_security(profile: SecurityProfile, *, multi_tenant: bool = False) -> SecurityConfig:
    """Construct a SecurityConfig from a profile shortcut."""
    return SecurityConfig.from_profile(profile, multi_tenant=multi_tenant)


# ---------------------------------------------------------------------------
# Task 1 — Field tuple shape tests
# ---------------------------------------------------------------------------


def test_admin_entity_defs_combined() -> None:
    """Combined ADMIN_ENTITY_DEFS shape contract:
    - Exactly 7 entity definitions.
    - Every field tuple is (str, str, tuple, str|None).
    - Every entity has exactly one 'pk' field named 'id'.
    - VIRTUAL_ENTITY_NAMES is a subset of all entity names.
    """
    # Top-level count.
    assert len(ADMIN_ENTITY_DEFS) == 7

    all_names: set[str] = set()
    for ent_name, _title, _intent, fields_tuple, _patterns, _gate in ADMIN_ENTITY_DEFS:
        all_names.add(ent_name)

        # Field tuple shape.
        for entry in fields_tuple:
            assert len(entry) == 4, f"{ent_name}: expected 4-tuple, got {entry!r}"
            name, type_str, modifiers, default = entry
            assert isinstance(name, str)
            assert isinstance(type_str, str)
            assert isinstance(modifiers, tuple)
            assert default is None or isinstance(default, str)

        # Exactly one pk named 'id'.
        pk_fields = [f for f in fields_tuple if "pk" in f[2]]
        assert len(pk_fields) == 1, f"{ent_name}: expected one pk, got {pk_fields}"
        assert pk_fields[0][0] == "id", f"{ent_name}: pk not 'id', got {pk_fields[0][0]!r}"

    # VIRTUAL_ENTITY_NAMES subset of all defs.
    assert VIRTUAL_ENTITY_NAMES <= all_names, (
        f"Virtual names not subset: {VIRTUAL_ENTITY_NAMES - all_names}"
    )


# ---------------------------------------------------------------------------
# Task 2 — _build_admin_entities tests
# ---------------------------------------------------------------------------


def test_build_admin_entities_combined() -> None:
    """Combined: _build_admin_entities profile-gating + EntitySpec invariants.
    - BASIC profile: 3 entities (no profile_gate); STANDARD/STRICT: 7 entities.
    - STANDARD includes LogEntry + EventTrace.
    - All entities have domain='platform' and 'system' in patterns.
    - All entities are read-only (only READ + LIST permissions).
    - All permission rules require ['admin', 'super_admin'].
    """
    from dazzle.core.admin_builder import _build_admin_entities
    from dazzle.core.ir.domain import PermissionKind

    # BASIC profile: only entities with profile_gate=None.
    basic_entities = _build_admin_entities(_make_security(SecurityProfile.BASIC))
    basic_names = {e.name for e in basic_entities}
    assert "SystemHealth" in basic_names
    assert "DeployHistory" in basic_names
    for gated in ("ProcessRun", "SessionInfo", "LogEntry", "EventTrace"):
        assert gated not in basic_names

    # STANDARD profile: all 7, including log/event.
    standard_entities = _build_admin_entities(_make_security(SecurityProfile.STANDARD))
    assert len(standard_entities) == 7
    standard_names = {e.name for e in standard_entities}
    assert "LogEntry" in standard_names
    assert "EventTrace" in standard_names

    # STRICT profile: all 7.
    strict_entities = _build_admin_entities(_make_security(SecurityProfile.STRICT))
    assert len(strict_entities) == 7

    # Per-entity invariants on the STRICT set (which has them all).
    write_ops = {PermissionKind.CREATE, PermissionKind.UPDATE, PermissionKind.DELETE}
    expected_personas = ["admin", "super_admin"]
    for entity in strict_entities:
        # domain + patterns
        assert entity.domain == "platform", f"{entity.name}: bad domain"
        assert "system" in entity.patterns, f"{entity.name}: 'system' not in patterns"
        # read-only access
        assert entity.access is not None, f"{entity.name}: access is None"
        ops = {rule.operation for rule in entity.access.permissions}
        assert not (ops & write_ops), f"{entity.name}: write ops {ops & write_ops!r}"
        assert PermissionKind.READ in ops
        assert PermissionKind.LIST in ops
        # admin-only personas
        for rule in entity.access.permissions:
            assert rule.personas == expected_personas


# ---------------------------------------------------------------------------
# Task 3 — Collision detection tests
# ---------------------------------------------------------------------------


class TestCollisionDetection:
    """_check_collisions raises LinkError on name collisions."""

    def test_collision_branches(self) -> None:
        """Entity collision raises; workspace collision raises; no overlap is silent."""
        from dazzle.core.admin_builder import _check_collisions

        # Entity name collision
        with pytest.raises(LinkError, match="SystemHealth"):
            _check_collisions(
                existing_entity_names={"SystemHealth", "Task", "User"},
                existing_workspace_names=set(),
                synthetic_entity_names={"SystemHealth", "DeployHistory"},
                synthetic_workspace_names=set(),
            )

        # Workspace name collision
        with pytest.raises(LinkError, match="_platform_admin"):
            _check_collisions(
                existing_entity_names=set(),
                existing_workspace_names={"_platform_admin", "dashboard"},
                synthetic_entity_names=set(),
                synthetic_workspace_names={"_platform_admin"},
            )

        # No collision: silent pass
        _check_collisions(
            existing_entity_names={"Task", "User", "Project"},
            existing_workspace_names={"my_dashboard"},
            synthetic_entity_names={"SystemHealth", "DeployHistory"},
            synthetic_workspace_names={"_platform_admin"},
        )


# ---------------------------------------------------------------------------
# Task 4 — Admin surfaces builder tests
# ---------------------------------------------------------------------------


def test_build_admin_surfaces_combined() -> None:
    """Combined _build_admin_surfaces contract:
    - STANDARD includes _admin_sessions; BASIC does not.
    - _admin_deploys + _admin_health present on every profile.
    - All surfaces are LIST mode, require_auth, admin/super_admin personas.
    """
    from dazzle.core.admin_builder import _build_admin_surfaces

    # Profile-gated session surface.
    standard_names = {
        s.name for s in _build_admin_surfaces(_make_security(SecurityProfile.STANDARD))
    }
    assert "_admin_sessions" in standard_names
    basic_names = {s.name for s in _build_admin_surfaces(_make_security(SecurityProfile.BASIC))}
    assert "_admin_sessions" not in basic_names

    # Universal surfaces — present on every profile.
    for profile in SecurityProfile:
        names = {s.name for s in _build_admin_surfaces(_make_security(profile))}
        assert "_admin_deploys" in names, f"_admin_deploys missing for {profile}"
        assert "_admin_health" in names, f"_admin_health missing for {profile}"

    # Per-surface invariants (use STANDARD which has the most surfaces).
    for surface in _build_admin_surfaces(_make_security(SecurityProfile.STANDARD)):
        assert surface.mode == SurfaceMode.LIST, f"{surface.name}: not LIST mode"
        assert surface.access is not None, f"{surface.name}: access is None"
        assert surface.access.require_auth is True, f"{surface.name}: !require_auth"
        assert set(surface.access.allow_personas) == {"admin", "super_admin"}, (
            f"{surface.name}: bad personas {surface.access.allow_personas!r}"
        )


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

    def test_multi_tenant_workspaces_combined(self) -> None:
        """Combined multi-tenant workspace contract:
        - Multi-tenant produces both _platform_admin and _tenant_admin.
        - _platform_admin allows only super_admin (in MT mode).
        - _tenant_admin allows only admin.
        - _tenant_admin regions are a strict subset of platform's, and never
          include 'tenants'.
        """
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD, multi_tenant=True)
        workspaces = _build_admin_workspaces(security, multi_tenant=True, feedback_enabled=True)
        names = {w.name for w in workspaces}
        assert names == {"_platform_admin", "_tenant_admin"}

        platform = next(w for w in workspaces if w.name == "_platform_admin")
        tenant = next(w for w in workspaces if w.name == "_tenant_admin")

        # Personas
        assert platform.access is not None
        assert platform.access.allow_personas == ["super_admin"]
        assert tenant.access is not None
        assert tenant.access.allow_personas == ["admin"]

        # Region subset, no 'tenants' in tenant.
        platform_names = {r.name for r in platform.regions}
        tenant_names = {r.name for r in tenant.regions}
        assert tenant_names < platform_names
        assert "tenants" not in tenant_names

    def test_platform_admin_single_tenant_personas(self) -> None:
        """Single-tenant _platform_admin allows admin AND super_admin."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD)
        workspaces = _build_admin_workspaces(security, multi_tenant=False, feedback_enabled=False)
        platform = next(w for w in workspaces if w.name == "_platform_admin")
        assert platform.access is not None
        assert set(platform.access.allow_personas) == {"admin", "super_admin"}

    def test_feedback_region_toggle_combined(self) -> None:
        """Combined: 'feedback' region appears iff feedback_enabled=True;
        all three nav groups (Management, Observability, Operations) present."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD)

        # Enabled — region present, all three nav groups present.
        ws_on = _build_admin_workspaces(security, multi_tenant=False, feedback_enabled=True)
        plat_on = next(w for w in ws_on if w.name == "_platform_admin")
        assert "feedback" in {r.name for r in plat_on.regions}
        assert {g.label for g in plat_on.nav_groups} == {
            "Management",
            "Observability",
            "Operations",
        }

        # Disabled — feedback region absent.
        ws_off = _build_admin_workspaces(security, multi_tenant=False, feedback_enabled=False)
        plat_off = next(w for w in ws_off if w.name == "_platform_admin")
        assert "feedback" not in {r.name for r in plat_off.regions}

    def test_nav_items_use_entity_name_not_region_name(self) -> None:
        """#993 — nav URLs must resolve to real entity routes.

        Pre-fix the items used short region names (\"feedback\", \"deploys\")
        which page_routes.py converted to /app/feedback (404). Post-fix
        each NavItemIR.entity is the actual entity name so the URL becomes
        /app/feedbackreport (real route).
        """
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD)
        workspaces = _build_admin_workspaces(security, multi_tenant=False, feedback_enabled=True)
        platform = next(w for w in workspaces if w.name == "_platform_admin")
        all_entities = {item.entity for g in platform.nav_groups for item in g.items}

        # Real entity names — these slugify to real /app/<entity> routes.
        assert "FeedbackReport" in all_entities
        assert "DeployHistory" in all_entities
        assert "SystemHealth" in all_entities
        assert "User" in all_entities

        # Short region names must not appear — those would 404.
        assert "feedback" not in all_entities
        assert "deploys" not in all_entities
        assert "health" not in all_entities

    def test_sourceless_regions_excluded_from_nav(self) -> None:
        """#993 — DIAGRAM-only regions (no entity_ref) drop out of the nav.

        app_map is a DIAGRAM region with entity_ref=None. There's no list
        route for it, so linking would 404. The nav builder must skip it.
        """
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD)
        workspaces = _build_admin_workspaces(security, multi_tenant=False, feedback_enabled=True)
        platform = next(w for w in workspaces if w.name == "_platform_admin")
        all_entities = {item.entity for g in platform.nav_groups for item in g.items}

        # app_map is in _NAV_GROUPS["Operations"] but has no source entity.
        assert "app_map" not in all_entities
        # The Operations group itself stays — has feedback + events members.
        labels = {g.label for g in platform.nav_groups}
        assert "Operations" in labels

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


class TestAdminDefaultUX:
    """Default-UX helper for admin surfaces (#824).

    Ensures that framework-generated admin surfaces (`_admin_metrics`,
    `_admin_sessions`, `_admin_events`, `_admin_logs`) get sensible
    sort/filter defaults so their tables are usable AND the
    `_lint_list_surface_ux` rule stops flagging them on every adopter.
    """

    def test_default_admin_ux_per_surface(self) -> None:
        """Combined #824 sort/filter defaults across _admin_metrics, _admin_events, _admin_logs."""
        from dazzle.core.admin_builder import _default_admin_ux

        # SystemMetric: bucket_start → desc sort
        ux_metrics = _default_admin_ux(
            [
                ("name", "Metric"),
                ("value", "Value"),
                ("unit", "Unit"),
                ("bucket_start", "Time"),
            ]
        )
        assert ux_metrics.sort, "expected bucket_start to produce a sort default"
        assert ux_metrics.sort[0].field == "bucket_start"
        assert ux_metrics.sort[0].direction == "desc"

        # EventTrace: event_type filter + timestamp sort
        ux_events = _default_admin_ux(
            [
                ("topic", "Topic"),
                ("event_type", "Type"),
                ("key", "Key"),
                ("timestamp", "Time"),
            ]
        )
        assert "event_type" in ux_events.filter
        assert ux_events.sort[0].field == "timestamp"

        # LogEntry: level + component filters, timestamp sort
        ux_logs = _default_admin_ux(
            [
                ("timestamp", "Time"),
                ("level", "Level"),
                ("component", "Component"),
                ("message", "Message"),
            ]
        )
        assert "level" in ux_logs.filter
        assert "component" in ux_logs.filter
        assert ux_logs.sort[0].field == "timestamp"


def test_synthetic_lint_skips_combined() -> None:
    """Combined #824 lint-skip contract for `_`-prefixed framework names:
    - _platform_admin workspace skipped by persona + access-declaration lints.
    - _admin_* synthetic surfaces skipped by UX lint.
    - Real adopter workspaces (no `_` prefix) STILL trigger persona lint
      (guard that the skip rule doesn't over-correct).
    """
    from dazzle.core import ir as _ir
    from dazzle.core.validator import (
        _lint_list_surface_ux,
        _lint_workspace_access_declarations,
        _lint_workspace_personas,
    )

    # 1) _platform_admin skipped by persona lint (alongside a normal user_ws).
    synthetic_ws = _ir.WorkspaceSpec(name="_platform_admin", title="Admin")
    user_ws = _ir.WorkspaceSpec(
        name="user_ws",
        title="User",
        access=_ir.WorkspaceAccessSpec(allow_personas=["admin"]),
    )
    spec_a = _ir.AppSpec(
        name="t",
        app_name="t",
        app_title="T",
        domain=_ir.DomainSpec(entities=[]),
        workspaces=[synthetic_ws, user_ws],
        personas=[_ir.PersonaSpec(id="admin", label="A")],
    )
    assert not any("_platform_admin" in w for w in _lint_workspace_personas(spec_a))

    # 2) _platform_admin skipped by access-declaration lint.
    spec_b = _ir.AppSpec(
        name="t",
        app_name="t",
        app_title="T",
        domain=_ir.DomainSpec(entities=[]),
        workspaces=[_ir.WorkspaceSpec(name="_platform_admin", title="Admin")],
        personas=[_ir.PersonaSpec(id="admin", label="A")],
    )
    assert not any("_platform_admin" in w for w in _lint_workspace_access_declarations(spec_b))

    # 3) Synthetic _admin_* surfaces skipped by UX lint.
    for name in ("_admin_metrics", "_admin_sessions", "_admin_events"):
        synthetic = _ir.SurfaceSpec(
            name=name,
            title=name,
            mode=_ir.SurfaceMode.LIST,
            target="Entity",
            entity_ref="Entity",
        )
        spec_c = _ir.AppSpec(
            name="t",
            app_name="t",
            app_title="T",
            domain=_ir.DomainSpec(entities=[]),
            surfaces=[synthetic],
        )
        assert not any(name in w for w in _lint_list_surface_ux(spec_c)), (
            f"synthetic surface {name} should not produce lint warnings"
        )

    # 4) Adopter workspace (no `_` prefix) STILL triggers lint.
    unclaimed_ws = _ir.WorkspaceSpec(name="orphan_workspace", title="Orphan")
    spec_d = _ir.AppSpec(
        name="t",
        app_name="t",
        app_title="T",
        domain=_ir.DomainSpec(entities=[]),
        workspaces=[unclaimed_ws],
        personas=[_ir.PersonaSpec(id="admin", label="A")],
    )
    assert any("orphan_workspace" in w for w in _lint_workspace_personas(spec_d))
