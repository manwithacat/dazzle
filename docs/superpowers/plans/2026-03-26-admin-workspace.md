# Universal Admin Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-generate admin workspaces with platform entities for every Dazzle app, replacing the standalone ops/founder console.

**Architecture:** The linker generates synthetic platform entities (SystemHealth, SystemMetric, DeployHistory, ProcessRun, SessionInfo) and assembles them into one or two admin workspaces gated by security profile and tenancy. A new `SystemEntityStore` adapter routes reads for virtual entities to existing Redis/in-memory stores. The standalone console is deprecated in Phase 3.

**Tech Stack:** Python 3.12+, Pydantic, FastAPI, Redis, PostgreSQL

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/dazzle/core/admin_builder.py` | Create | Synthetic entity + surface + workspace builders |
| `src/dazzle/core/linker.py` | Modify (lines 126-143) | Call `build_admin_infrastructure()` in build_appspec |
| `src/dazzle_back/runtime/system_entity_store.py` | Create | Read adapter for virtual entities (health, metrics, processes) |
| `tests/unit/test_admin_builder.py` | Create | Unit tests for entity/surface/workspace generation |
| `tests/unit/test_system_entity_store.py` | Create | Unit tests for virtual entity store routing |

---

## Phase 1: Synthetic Platform Entities + Linker Integration

### Task 1: Platform Entity Field Definitions

**Files:**
- Create: `src/dazzle/core/ir/admin_entities.py`
- Test: `tests/unit/test_admin_builder.py`

- [ ] **Step 1: Create the field definition module**

Create `src/dazzle/core/ir/admin_entities.py` with field tuples for all five synthetic entities. This follows the same pattern as `FEEDBACK_REPORT_FIELDS` in `ir/feedback_widget.py` and `AI_JOB_FIELDS` in `ir/llm.py`.

```python
"""
Field definitions for auto-generated admin platform entities.

Format: (name, type_str, modifiers_tuple, default_value_or_None)
Same convention as AI_JOB_FIELDS and FEEDBACK_REPORT_FIELDS.
"""

# Virtual entity — backed by health_aggregator (in-memory)
SYSTEM_HEALTH_FIELDS: tuple[tuple[str, str, tuple[str, ...], str | None], ...] = (
    ("id", "uuid", ("pk",), None),
    ("component", "str(100)", ("required",), None),
    ("status", "enum[healthy,degraded,unhealthy]", ("required",), None),
    ("message", "text", (), None),
    ("latency_ms", "float", (), None),
    ("checked_at", "datetime", (), "now"),
)

# Virtual entity — backed by metrics_store (Redis streams). Standard+ only.
SYSTEM_METRIC_FIELDS: tuple[tuple[str, str, tuple[str, ...], str | None], ...] = (
    ("id", "uuid", ("pk",), None),
    ("name", "str(200)", ("required",), None),
    ("value", "float", ("required",), None),
    ("unit", "str(50)", (), None),
    ("tags", "text", (), None),
    ("bucket_start", "datetime", (), None),
    ("resolution", "str(10)", (), None),
)

# PostgreSQL-backed — durable audit data. All profiles.
DEPLOY_HISTORY_FIELDS: tuple[tuple[str, str, tuple[str, ...], str | None], ...] = (
    ("id", "uuid", ("pk",), None),
    ("version", "str(50)", ("required",), None),
    ("previous_version", "str(50)", (), None),
    ("deployed_by", "str(200)", (), None),
    ("deployed_at", "datetime", (), "now"),
    ("status", "enum[pending,in_progress,completed,failed,rolled_back]", (), "pending"),
    ("rollback_of", "str(50)", (), None),
)

# Virtual entity — backed by process_monitor (Redis). Standard+ only.
PROCESS_RUN_FIELDS: tuple[tuple[str, str, tuple[str, ...], str | None], ...] = (
    ("id", "uuid", ("pk",), None),
    ("process_name", "str(200)", ("required",), None),
    ("status", "enum[pending,running,waiting,suspended,compensating,completed,failed,cancelled]", (), "pending"),
    ("started_at", "datetime", (), None),
    ("completed_at", "datetime", (), None),
    ("current_step", "str(200)", (), None),
    ("error", "text", (), None),
)

# PostgreSQL-backed via auth store. Standard+ only.
SESSION_INFO_FIELDS: tuple[tuple[str, str, tuple[str, ...], str | None], ...] = (
    ("id", "uuid", ("pk",), None),
    ("user_id", "str(200)", ("required",), None),
    ("email", "str(200)", (), None),
    ("created_at", "datetime", (), "now"),
    ("expires_at", "datetime", (), None),
    ("ip_address", "str(45)", (), None),
    ("user_agent", "str(500)", (), None),
    ("is_active", "bool", (), "true"),
)

# Which entities are virtual (non-PostgreSQL backing store)
VIRTUAL_ENTITY_NAMES: frozenset[str] = frozenset({
    "SystemHealth",
    "SystemMetric",
    "ProcessRun",
})

# All admin entity definitions: (name, title, intent, fields_tuple, patterns, profile_gate)
# profile_gate: None = all profiles, "standard" = standard+strict only
ADMIN_ENTITY_DEFS: tuple[tuple[str, str, str, tuple, list[str], str | None], ...] = (
    (
        "SystemHealth",
        "System Health",
        "Real-time health status of application components",
        SYSTEM_HEALTH_FIELDS,
        ["system"],
        None,
    ),
    (
        "SystemMetric",
        "System Metric",
        "Time-series metrics from application monitoring",
        SYSTEM_METRIC_FIELDS,
        ["system"],
        "standard",
    ),
    (
        "DeployHistory",
        "Deploy History",
        "Deployment audit trail — versions, rollbacks, and status",
        DEPLOY_HISTORY_FIELDS,
        ["system", "audit"],
        None,
    ),
    (
        "ProcessRun",
        "Process Run",
        "Workflow and process execution tracking",
        PROCESS_RUN_FIELDS,
        ["system"],
        "standard",
    ),
    (
        "SessionInfo",
        "Session Info",
        "Active user session tracking for admin oversight",
        SESSION_INFO_FIELDS,
        ["system"],
        "standard",
    ),
)
```

- [ ] **Step 2: Write the first test — field definitions are importable and well-formed**

Create `tests/unit/test_admin_builder.py`:

```python
"""Tests for admin workspace infrastructure generation."""

from dazzle.core.ir.admin_entities import (
    ADMIN_ENTITY_DEFS,
    DEPLOY_HISTORY_FIELDS,
    PROCESS_RUN_FIELDS,
    SESSION_INFO_FIELDS,
    SYSTEM_HEALTH_FIELDS,
    SYSTEM_METRIC_FIELDS,
    VIRTUAL_ENTITY_NAMES,
)


def test_field_tuples_have_correct_shape():
    """Every field tuple has exactly 4 elements: (name, type_str, modifiers, default)."""
    all_fields = [
        SYSTEM_HEALTH_FIELDS,
        SYSTEM_METRIC_FIELDS,
        DEPLOY_HISTORY_FIELDS,
        PROCESS_RUN_FIELDS,
        SESSION_INFO_FIELDS,
    ]
    for fields in all_fields:
        assert len(fields) > 0, "Field tuple must not be empty"
        for field in fields:
            assert len(field) == 4, f"Field {field[0]} has {len(field)} elements, expected 4"


def test_all_entities_have_pk():
    """Every entity definition has a uuid pk as first field."""
    for name, _, _, fields, _, _ in ADMIN_ENTITY_DEFS:
        first_field = fields[0]
        assert first_field[0] == "id", f"{name} first field should be 'id'"
        assert first_field[1] == "uuid", f"{name} id should be uuid"
        assert "pk" in first_field[2], f"{name} id should be pk"


def test_admin_entity_defs_count():
    """Five admin entities defined."""
    assert len(ADMIN_ENTITY_DEFS) == 5


def test_virtual_entities_are_subset():
    """Virtual entity names are a subset of defined entity names."""
    defined_names = {name for name, *_ in ADMIN_ENTITY_DEFS}
    assert VIRTUAL_ENTITY_NAMES <= defined_names
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/unit/test_admin_builder.py -v`
Expected: 4 tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/core/ir/admin_entities.py tests/unit/test_admin_builder.py
git commit -m "feat: admin entity field definitions for platform workspace (#686)"
```

---

### Task 2: Admin Entity Builder Functions

**Files:**
- Create: `src/dazzle/core/admin_builder.py`
- Modify: `tests/unit/test_admin_builder.py`

- [ ] **Step 1: Write failing tests for entity generation**

Add to `tests/unit/test_admin_builder.py`:

```python
from dazzle.core.ir.security import SecurityConfig, SecurityProfile
from dazzle.core.ir.admin_entities import ADMIN_ENTITY_DEFS


def _make_security(profile: SecurityProfile, multi_tenant: bool = False) -> SecurityConfig:
    return SecurityConfig.from_profile(profile, multi_tenant=multi_tenant)


class TestBuildAdminEntities:
    """Tests for _build_admin_entities()."""

    def test_basic_profile_gets_all_profile_entities(self):
        """Basic profile generates SystemHealth and DeployHistory only."""
        from dazzle.core.admin_builder import _build_admin_entities

        security = _make_security(SecurityProfile.BASIC)
        entities = _build_admin_entities(security)
        names = {e.name for e in entities}
        assert names == {"SystemHealth", "DeployHistory"}

    def test_standard_profile_gets_all_entities(self):
        """Standard profile generates all five entities."""
        from dazzle.core.admin_builder import _build_admin_entities

        security = _make_security(SecurityProfile.STANDARD)
        entities = _build_admin_entities(security)
        names = {e.name for e in entities}
        assert names == {"SystemHealth", "SystemMetric", "DeployHistory", "ProcessRun", "SessionInfo"}

    def test_strict_profile_gets_all_entities(self):
        """Strict profile generates all five entities."""
        from dazzle.core.admin_builder import _build_admin_entities

        security = _make_security(SecurityProfile.STRICT, multi_tenant=True)
        entities = _build_admin_entities(security)
        names = {e.name for e in entities}
        assert names == {"SystemHealth", "SystemMetric", "DeployHistory", "ProcessRun", "SessionInfo"}

    def test_entities_have_platform_domain(self):
        """All generated entities have domain='platform'."""
        from dazzle.core.admin_builder import _build_admin_entities

        security = _make_security(SecurityProfile.STANDARD)
        for entity in _build_admin_entities(security):
            assert entity.domain == "platform", f"{entity.name} should have platform domain"

    def test_entities_have_system_pattern(self):
        """All generated entities include 'system' in patterns."""
        from dazzle.core.admin_builder import _build_admin_entities

        security = _make_security(SecurityProfile.STANDARD)
        for entity in _build_admin_entities(security):
            assert "system" in entity.patterns, f"{entity.name} should have system pattern"

    def test_entities_are_read_only(self):
        """All entities only permit READ and LIST, not CREATE/UPDATE/DELETE."""
        from dazzle.core.admin_builder import _build_admin_entities
        from dazzle.core.ir.domain import PermissionKind

        security = _make_security(SecurityProfile.STANDARD)
        for entity in _build_admin_entities(security):
            assert entity.access is not None, f"{entity.name} should have access spec"
            ops = {p.operation for p in entity.access.permissions}
            assert ops == {PermissionKind.READ, PermissionKind.LIST}, (
                f"{entity.name} should only permit READ and LIST, got {ops}"
            )

    def test_entities_require_admin_personas(self):
        """All permission rules require admin or super_admin personas."""
        from dazzle.core.admin_builder import _build_admin_entities

        security = _make_security(SecurityProfile.STANDARD)
        for entity in _build_admin_entities(security):
            for perm in entity.access.permissions:
                assert set(perm.personas) == {"admin", "super_admin"}, (
                    f"{entity.name} {perm.operation} should require admin personas"
                )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_admin_builder.py::TestBuildAdminEntities -v`
Expected: FAIL with `ImportError` or `ModuleNotFoundError`

- [ ] **Step 3: Implement `_build_admin_entities` in admin_builder.py**

Create `src/dazzle/core/admin_builder.py`:

```python
"""
Admin workspace infrastructure builder.

Generates synthetic platform entities, surfaces, and workspaces for
the admin dashboard. Called by the linker after feedback/AIJob entity
generation and before FK graph building.

See: docs/superpowers/specs/2026-03-26-admin-workspace-design.md
"""

from __future__ import annotations

from . import ir
from .ir.admin_entities import ADMIN_ENTITY_DEFS
from .ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
from .ir.security import SecurityConfig, SecurityProfile


def _parse_field_type(type_str: str) -> FieldType:
    """Parse a compact field type string into a FieldType.

    Duplicates linker._parse_field_type — extracted here to avoid
    circular imports. A shared helper can be extracted in a follow-up.
    """
    if type_str == "uuid":
        return FieldType(kind=FieldTypeKind.UUID)
    if type_str == "int":
        return FieldType(kind=FieldTypeKind.INT)
    if type_str == "text":
        return FieldType(kind=FieldTypeKind.TEXT)
    if type_str == "bool":
        return FieldType(kind=FieldTypeKind.BOOL)
    if type_str == "float":
        return FieldType(kind=FieldTypeKind.FLOAT)
    if type_str == "datetime":
        return FieldType(kind=FieldTypeKind.DATETIME)
    if type_str.startswith("str(") and type_str.endswith(")"):
        max_len = int(type_str[4:-1])
        return FieldType(kind=FieldTypeKind.STR, max_length=max_len)
    if type_str.startswith("enum[") and type_str.endswith("]"):
        values = [v.strip() for v in type_str[5:-1].split(",")]
        return FieldType(kind=FieldTypeKind.ENUM, enum_values=values)
    raise ValueError(f"Unknown field type: {type_str}")


_MODIFIER_MAP = {
    "pk": FieldModifier.PK,
    "required": FieldModifier.REQUIRED,
    "unique": FieldModifier.UNIQUE,
}


def _is_profile_included(profile_gate: str | None, active_profile: SecurityProfile) -> bool:
    """Check if an entity should be included for the given security profile."""
    if profile_gate is None:
        return True
    if profile_gate == "standard":
        return active_profile in (SecurityProfile.STANDARD, SecurityProfile.STRICT)
    return False


def _build_admin_entities(security: SecurityConfig) -> list[ir.EntitySpec]:
    """Build synthetic platform entities gated by security profile.

    Args:
        security: The app's security configuration.

    Returns:
        List of EntitySpec for admin platform entities.
    """
    result: list[ir.EntitySpec] = []

    for name, title, intent, fields_tuple, patterns, profile_gate in ADMIN_ENTITY_DEFS:
        if not _is_profile_included(profile_gate, security.profile):
            continue

        fields: list[FieldSpec] = []
        for fname, type_str, modifiers, default in fields_tuple:
            field_type = _parse_field_type(type_str)
            mods = [_MODIFIER_MAP[m] for m in modifiers]
            fields.append(FieldSpec(name=fname, type=field_type, modifiers=mods, default=default))

        access = ir.AccessSpec(
            permissions=[
                ir.PermissionRule(
                    operation=ir.PermissionKind.READ,
                    require_auth=True,
                    effect=ir.PolicyEffect.PERMIT,
                    personas=["admin", "super_admin"],
                ),
                ir.PermissionRule(
                    operation=ir.PermissionKind.LIST,
                    require_auth=True,
                    effect=ir.PolicyEffect.PERMIT,
                    personas=["admin", "super_admin"],
                ),
            ]
        )

        result.append(
            ir.EntitySpec(
                name=name,
                title=title,
                intent=intent,
                domain="platform",
                patterns=patterns,
                fields=fields,
                access=access,
            )
        )

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_admin_builder.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/admin_builder.py tests/unit/test_admin_builder.py
git commit -m "feat: admin entity builder — profile-gated synthetic entities (#686)"
```

---

### Task 3: Collision Detection

**Files:**
- Modify: `src/dazzle/core/admin_builder.py`
- Modify: `tests/unit/test_admin_builder.py`

- [ ] **Step 1: Write failing test for collision detection**

Add to `tests/unit/test_admin_builder.py`:

```python
import pytest
from dazzle.core.errors import LinkError


class TestCollisionDetection:
    """Tests for name collision between user-declared and synthetic entities."""

    def test_entity_collision_raises(self):
        """User-declared entity with same name as synthetic raises LinkError."""
        from dazzle.core.admin_builder import _check_collisions

        existing_entity_names = {"SystemHealth", "Task", "User"}
        synthetic_entity_names = {"SystemHealth", "DeployHistory"}

        with pytest.raises(LinkError, match="SystemHealth"):
            _check_collisions(
                existing_entity_names=existing_entity_names,
                existing_workspace_names=set(),
                synthetic_entity_names=synthetic_entity_names,
                synthetic_workspace_names=set(),
            )

    def test_workspace_collision_raises(self):
        """User-declared workspace with same name as synthetic raises LinkError."""
        from dazzle.core.admin_builder import _check_collisions

        with pytest.raises(LinkError, match="_platform_admin"):
            _check_collisions(
                existing_entity_names=set(),
                existing_workspace_names={"_platform_admin", "dashboard"},
                synthetic_entity_names=set(),
                synthetic_workspace_names={"_platform_admin"},
            )

    def test_no_collision_passes(self):
        """No collision raises nothing."""
        from dazzle.core.admin_builder import _check_collisions

        _check_collisions(
            existing_entity_names={"Task", "User"},
            existing_workspace_names={"dashboard"},
            synthetic_entity_names={"SystemHealth", "DeployHistory"},
            synthetic_workspace_names={"_platform_admin"},
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_admin_builder.py::TestCollisionDetection -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement `_check_collisions`**

Add to `src/dazzle/core/admin_builder.py`:

```python
from .errors import LinkError


def _check_collisions(
    *,
    existing_entity_names: set[str],
    existing_workspace_names: set[str],
    synthetic_entity_names: set[str],
    synthetic_workspace_names: set[str],
) -> None:
    """Raise LinkError if user-declared names collide with synthetic names."""
    entity_collisions = existing_entity_names & synthetic_entity_names
    workspace_collisions = existing_workspace_names & synthetic_workspace_names
    collisions = entity_collisions | workspace_collisions

    if collisions:
        names = ", ".join(sorted(collisions))
        raise LinkError(
            f"Name collision with framework-generated admin infrastructure: {names}. "
            "Rename your entity/workspace to avoid the conflict."
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_admin_builder.py::TestCollisionDetection -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/admin_builder.py tests/unit/test_admin_builder.py
git commit -m "feat: collision detection for synthetic admin names (#686)"
```

---

### Task 4: Admin Surfaces Builder

**Files:**
- Modify: `src/dazzle/core/admin_builder.py`
- Modify: `tests/unit/test_admin_builder.py`

- [ ] **Step 1: Write failing tests for admin surface generation**

Add to `tests/unit/test_admin_builder.py`:

```python
class TestBuildAdminSurfaces:
    """Tests for admin surface generation."""

    def test_standard_generates_session_surface(self):
        """Standard profile generates a session management list surface."""
        from dazzle.core.admin_builder import _build_admin_surfaces

        security = _make_security(SecurityProfile.STANDARD)
        surfaces = _build_admin_surfaces(security)
        names = {s.name for s in surfaces}
        assert "_admin_sessions" in names

    def test_basic_no_session_surface(self):
        """Basic profile does not generate session surface."""
        from dazzle.core.admin_builder import _build_admin_surfaces

        security = _make_security(SecurityProfile.BASIC)
        surfaces = _build_admin_surfaces(security)
        names = {s.name for s in surfaces}
        assert "_admin_sessions" not in names

    def test_surfaces_require_admin_personas(self):
        """All admin surfaces restrict access to admin personas."""
        from dazzle.core.admin_builder import _build_admin_surfaces

        security = _make_security(SecurityProfile.STANDARD)
        for surface in _build_admin_surfaces(security):
            assert surface.access is not None
            assert surface.access.require_auth is True
            assert set(surface.access.allow_personas) == {"admin", "super_admin"}

    def test_surfaces_are_list_mode(self):
        """Admin surfaces use LIST mode."""
        from dazzle.core.admin_builder import _build_admin_surfaces
        from dazzle.core.ir.surfaces import SurfaceMode

        security = _make_security(SecurityProfile.STANDARD)
        for surface in _build_admin_surfaces(security):
            assert surface.mode == SurfaceMode.LIST

    def test_deploy_surface_always_present(self):
        """DeployHistory surface present for all profiles."""
        from dazzle.core.admin_builder import _build_admin_surfaces

        for profile in SecurityProfile:
            security = _make_security(profile)
            surfaces = _build_admin_surfaces(security)
            names = {s.name for s in surfaces}
            assert "_admin_deploys" in names

    def test_health_surface_always_present(self):
        """SystemHealth surface present for all profiles."""
        from dazzle.core.admin_builder import _build_admin_surfaces

        for profile in SecurityProfile:
            security = _make_security(profile)
            surfaces = _build_admin_surfaces(security)
            names = {s.name for s in surfaces}
            assert "_admin_health" in names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_admin_builder.py::TestBuildAdminSurfaces -v`
Expected: FAIL

- [ ] **Step 3: Implement `_build_admin_surfaces`**

Add to `src/dazzle/core/admin_builder.py`:

```python
# Surface definitions: (surface_name, entity_name, title, display_fields, profile_gate)
# display_fields: list of (field_name, label) tuples for the LIST section
_ADMIN_SURFACE_DEFS: list[tuple[str, str, str, list[tuple[str, str]], str | None]] = [
    (
        "_admin_health",
        "SystemHealth",
        "System Health",
        [("component", "Component"), ("status", "Status"), ("message", "Message"), ("checked_at", "Checked")],
        None,
    ),
    (
        "_admin_deploys",
        "DeployHistory",
        "Deploy History",
        [("version", "Version"), ("status", "Status"), ("deployed_by", "Deployed By"), ("deployed_at", "Deployed At")],
        None,
    ),
    (
        "_admin_metrics",
        "SystemMetric",
        "System Metrics",
        [("name", "Metric"), ("value", "Value"), ("unit", "Unit"), ("bucket_start", "Time")],
        "standard",
    ),
    (
        "_admin_processes",
        "ProcessRun",
        "Process Runs",
        [("process_name", "Process"), ("status", "Status"), ("started_at", "Started"), ("current_step", "Step")],
        "standard",
    ),
    (
        "_admin_sessions",
        "SessionInfo",
        "Active Sessions",
        [("email", "User"), ("ip_address", "IP"), ("created_at", "Started"), ("expires_at", "Expires")],
        "standard",
    ),
]


def _build_admin_surfaces(security: SecurityConfig) -> list[ir.SurfaceSpec]:
    """Build admin LIST surfaces for platform entities.

    Args:
        security: The app's security configuration.

    Returns:
        List of SurfaceSpec for admin dashboard surfaces.
    """
    result: list[ir.SurfaceSpec] = []

    for surf_name, entity_name, title, display_fields, profile_gate in _ADMIN_SURFACE_DEFS:
        if not _is_profile_included(profile_gate, security.profile):
            continue

        elements = [
            ir.SurfaceElement(field_name=fname, label=label)
            for fname, label in display_fields
        ]

        result.append(
            ir.SurfaceSpec(
                name=surf_name,
                title=title,
                entity_ref=entity_name,
                mode=ir.SurfaceMode.LIST,
                sections=[ir.SurfaceSection(name="main", title=title, elements=elements)],
                access=ir.SurfaceAccessSpec(
                    require_auth=True,
                    allow_personas=["admin", "super_admin"],
                ),
            )
        )

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_admin_builder.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/admin_builder.py tests/unit/test_admin_builder.py
git commit -m "feat: admin surface builder — LIST surfaces for platform entities (#686)"
```

---

## Phase 2: Admin Workspaces

### Task 5: Workspace Builder

**Files:**
- Modify: `src/dazzle/core/admin_builder.py`
- Modify: `tests/unit/test_admin_builder.py`

- [ ] **Step 1: Write failing tests for workspace generation**

Add to `tests/unit/test_admin_builder.py`:

```python
from dazzle.core.ir.workspaces import WorkspaceAccessLevel
from dazzle.core.ir.feedback_widget import FeedbackWidgetSpec


class TestBuildAdminWorkspaces:
    """Tests for admin workspace generation."""

    def test_single_tenant_one_workspace(self):
        """Single-tenant app generates only _platform_admin."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD, multi_tenant=False)
        workspaces = _build_admin_workspaces(security, multi_tenant=False, feedback_enabled=False)
        names = {w.name for w in workspaces}
        assert names == {"_platform_admin"}

    def test_multi_tenant_two_workspaces(self):
        """Multi-tenant app generates both _platform_admin and _tenant_admin."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD, multi_tenant=True)
        workspaces = _build_admin_workspaces(security, multi_tenant=True, feedback_enabled=False)
        names = {w.name for w in workspaces}
        assert names == {"_platform_admin", "_tenant_admin"}

    def test_platform_admin_super_admin_only_multi_tenant(self):
        """In multi-tenant, _platform_admin allows only super_admin."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD, multi_tenant=True)
        workspaces = _build_admin_workspaces(security, multi_tenant=True, feedback_enabled=False)
        platform = next(w for w in workspaces if w.name == "_platform_admin")
        assert platform.access is not None
        assert platform.access.level == WorkspaceAccessLevel.PERSONA
        assert platform.access.allow_personas == ["super_admin"]

    def test_platform_admin_both_personas_single_tenant(self):
        """In single-tenant, _platform_admin allows admin and super_admin."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD, multi_tenant=False)
        workspaces = _build_admin_workspaces(security, multi_tenant=False, feedback_enabled=False)
        platform = next(w for w in workspaces if w.name == "_platform_admin")
        assert set(platform.access.allow_personas) == {"admin", "super_admin"}

    def test_tenant_admin_persona(self):
        """_tenant_admin allows only admin persona."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD, multi_tenant=True)
        workspaces = _build_admin_workspaces(security, multi_tenant=True, feedback_enabled=False)
        tenant = next(w for w in workspaces if w.name == "_tenant_admin")
        assert tenant.access.allow_personas == ["admin"]

    def test_tenant_admin_has_subset_of_regions(self):
        """_tenant_admin has fewer regions than _platform_admin."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD, multi_tenant=True)
        workspaces = _build_admin_workspaces(security, multi_tenant=True, feedback_enabled=False)
        platform = next(w for w in workspaces if w.name == "_platform_admin")
        tenant = next(w for w in workspaces if w.name == "_tenant_admin")
        platform_regions = {r.name for r in platform.regions}
        tenant_regions = {r.name for r in tenant.regions}
        assert tenant_regions < platform_regions, "Tenant regions should be strict subset of platform"

    def test_tenant_admin_no_tenants_region(self):
        """_tenant_admin does not include a tenants region."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD, multi_tenant=True)
        workspaces = _build_admin_workspaces(security, multi_tenant=True, feedback_enabled=False)
        tenant = next(w for w in workspaces if w.name == "_tenant_admin")
        region_names = {r.name for r in tenant.regions}
        assert "tenants" not in region_names

    def test_feedback_region_when_enabled(self):
        """Feedback region included when feedback_widget is enabled."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD)
        workspaces = _build_admin_workspaces(security, multi_tenant=False, feedback_enabled=True)
        platform = next(w for w in workspaces if w.name == "_platform_admin")
        region_names = {r.name for r in platform.regions}
        assert "feedback" in region_names

    def test_no_feedback_region_when_disabled(self):
        """Feedback region excluded when feedback_widget is disabled."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD)
        workspaces = _build_admin_workspaces(security, multi_tenant=False, feedback_enabled=False)
        platform = next(w for w in workspaces if w.name == "_platform_admin")
        region_names = {r.name for r in platform.regions}
        assert "feedback" not in region_names

    def test_nav_groups_present(self):
        """Workspaces have nav groups for Management, Observability, Operations."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        security = _make_security(SecurityProfile.STANDARD)
        workspaces = _build_admin_workspaces(security, multi_tenant=False, feedback_enabled=True)
        platform = next(w for w in workspaces if w.name == "_platform_admin")
        group_labels = {g.label for g in platform.nav_groups}
        assert group_labels == {"Management", "Observability", "Operations"}

    def test_basic_profile_fewer_regions(self):
        """Basic profile has fewer regions than standard (no metrics, processes, sessions)."""
        from dazzle.core.admin_builder import _build_admin_workspaces

        basic = _make_security(SecurityProfile.BASIC)
        standard = _make_security(SecurityProfile.STANDARD)
        basic_ws = _build_admin_workspaces(basic, multi_tenant=False, feedback_enabled=False)
        standard_ws = _build_admin_workspaces(standard, multi_tenant=False, feedback_enabled=False)
        basic_regions = {r.name for r in basic_ws[0].regions}
        standard_regions = {r.name for r in standard_ws[0].regions}
        assert basic_regions < standard_regions
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_admin_builder.py::TestBuildAdminWorkspaces -v`
Expected: FAIL

- [ ] **Step 3: Implement `_build_admin_workspaces`**

Add to `src/dazzle/core/admin_builder.py`:

```python
from .ir.workspaces import (
    DisplayMode,
    NavGroupSpec,
    NavItemIR,
    WorkspaceAccessLevel,
    WorkspaceAccessSpec,
    WorkspaceRegion,
    WorkspaceSpec,
)


# Canonical region definitions: (name, source, display, profile_gate, tenant_admin_visible, feedback_only, multi_tenant_only)
_REGION_DEFS: list[tuple[str, str, DisplayMode, str | None, bool, bool, bool]] = [
    # Management
    ("users", "User", DisplayMode.LIST, None, True, False, False),
    ("tenants", "Tenant", DisplayMode.LIST, "standard", False, False, True),
    ("sessions", "_admin_sessions", DisplayMode.LIST, "standard", True, False, False),
    # Observability
    ("health", "_admin_health", DisplayMode.GRID, None, True, False, False),
    ("metrics", "_admin_metrics", DisplayMode.BAR_CHART, "standard", False, False, False),
    ("processes", "_admin_processes", DisplayMode.LIST, "standard", False, False, False),
    # Operations
    ("deploys", "_admin_deploys", DisplayMode.LIST, None, True, False, False),
    ("feedback", "feedback_admin", DisplayMode.LIST, None, True, True, False),
]

# Nav group assignments: (group_label, region_names)
_NAV_GROUPS: list[tuple[str, list[str]]] = [
    ("Management", ["users", "tenants", "sessions"]),
    ("Observability", ["health", "metrics", "processes"]),
    ("Operations", ["deploys", "feedback"]),
]


def _build_regions(
    security: SecurityConfig,
    *,
    multi_tenant: bool,
    feedback_enabled: bool,
    tenant_admin: bool = False,
) -> list[WorkspaceRegion]:
    """Build workspace regions filtered by profile, tenancy, and role."""
    regions: list[WorkspaceRegion] = []

    for name, source, display, profile_gate, tenant_visible, feedback_only, mt_only in _REGION_DEFS:
        if not _is_profile_included(profile_gate, security.profile):
            continue
        if feedback_only and not feedback_enabled:
            continue
        if mt_only and not multi_tenant:
            continue
        if tenant_admin and not tenant_visible:
            continue

        regions.append(
            WorkspaceRegion(name=name, source=source, display=display)
        )

    return regions


def _build_nav_groups(region_names: set[str]) -> list[NavGroupSpec]:
    """Build nav groups containing only regions that exist."""
    groups: list[NavGroupSpec] = []
    for label, member_names in _NAV_GROUPS:
        items = [NavItemIR(entity=name) for name in member_names if name in region_names]
        if items:
            groups.append(NavGroupSpec(label=label, items=items))
    return groups


def _build_admin_workspaces(
    security: SecurityConfig,
    *,
    multi_tenant: bool,
    feedback_enabled: bool,
) -> list[WorkspaceSpec]:
    """Build admin workspaces gated by profile and tenancy.

    Single-tenant: one _platform_admin workspace for admin + super_admin.
    Multi-tenant: _platform_admin (super_admin) + _tenant_admin (admin).
    """
    workspaces: list[WorkspaceSpec] = []

    # Platform admin workspace — always generated
    platform_regions = _build_regions(
        security, multi_tenant=multi_tenant, feedback_enabled=feedback_enabled, tenant_admin=False,
    )
    platform_region_names = {r.name for r in platform_regions}

    if multi_tenant:
        platform_personas = ["super_admin"]
    else:
        platform_personas = ["admin", "super_admin"]

    workspaces.append(
        WorkspaceSpec(
            name="_platform_admin",
            title="Platform Admin",
            purpose="Framework-generated admin dashboard for platform management",
            regions=platform_regions,
            nav_groups=_build_nav_groups(platform_region_names),
            access=WorkspaceAccessSpec(
                level=WorkspaceAccessLevel.PERSONA,
                allow_personas=platform_personas,
            ),
        )
    )

    # Tenant admin workspace — multi-tenant only
    if multi_tenant:
        tenant_regions = _build_regions(
            security, multi_tenant=multi_tenant, feedback_enabled=feedback_enabled, tenant_admin=True,
        )
        tenant_region_names = {r.name for r in tenant_regions}

        workspaces.append(
            WorkspaceSpec(
                name="_tenant_admin",
                title="Admin",
                purpose="Tenant-scoped admin dashboard",
                regions=tenant_regions,
                nav_groups=_build_nav_groups(tenant_region_names),
                access=WorkspaceAccessSpec(
                    level=WorkspaceAccessLevel.PERSONA,
                    allow_personas=["admin"],
                ),
            )
        )

    return workspaces
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_admin_builder.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/admin_builder.py tests/unit/test_admin_builder.py
git commit -m "feat: admin workspace builder — profile-gated regions + nav groups (#686)"
```

---

### Task 6: Top-Level Entry Point + Linker Integration

**Files:**
- Modify: `src/dazzle/core/admin_builder.py`
- Modify: `src/dazzle/core/linker.py` (lines 126-143)
- Modify: `tests/unit/test_admin_builder.py`

- [ ] **Step 1: Write failing test for `build_admin_infrastructure`**

Add to `tests/unit/test_admin_builder.py`:

```python
from dazzle.core.ir.module import AppConfigSpec


class TestBuildAdminInfrastructure:
    """Tests for the top-level entry point."""

    def test_returns_entities_surfaces_workspaces(self):
        """Returns a 3-tuple of (entities, surfaces, workspaces)."""
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
        assert len(entities) == 5
        assert len(surfaces) > 0
        assert len(workspaces) == 1

    def test_collision_with_existing_entity(self):
        """Raises LinkError when existing entity collides with synthetic."""
        from dazzle.core.admin_builder import build_admin_infrastructure

        security = _make_security(SecurityProfile.BASIC)
        app_config = AppConfigSpec(security_profile="basic")

        colliding_entity = ir.EntitySpec(
            name="SystemHealth",
            title="My Health",
            fields=[ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID), modifiers=[ir.FieldModifier.PK])],
        )

        with pytest.raises(LinkError, match="SystemHealth"):
            build_admin_infrastructure(
                entities=[colliding_entity],
                surfaces=[],
                security_config=security,
                app_config=app_config,
                feedback_widget=None,
                existing_workspaces=[],
            )

    def test_multi_tenant_generates_two_workspaces(self):
        """Multi-tenant config produces two workspaces."""
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
        names = {w.name for w in workspaces}
        assert names == {"_platform_admin", "_tenant_admin"}

    def test_feedback_enabled_includes_feedback_region(self):
        """Feedback widget enabled adds feedback region to workspaces."""
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
        region_names = {r.name for r in platform.regions}
        assert "feedback" in region_names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_admin_builder.py::TestBuildAdminInfrastructure -v`
Expected: FAIL

- [ ] **Step 3: Implement `build_admin_infrastructure`**

Add to `src/dazzle/core/admin_builder.py`:

```python
from .ir.feedback_widget import FeedbackWidgetSpec


def build_admin_infrastructure(
    *,
    entities: list[ir.EntitySpec],
    surfaces: list[ir.SurfaceSpec],
    security_config: SecurityConfig,
    app_config: ir.AppConfigSpec | None,
    feedback_widget: FeedbackWidgetSpec | None,
    existing_workspaces: list[WorkspaceSpec],
) -> tuple[list[ir.EntitySpec], list[ir.SurfaceSpec], list[WorkspaceSpec]]:
    """Build all admin infrastructure: entities, surfaces, workspaces.

    This is the single entry point called from the linker.

    Args:
        entities: Existing entities (for collision check).
        surfaces: Existing surfaces (for collision check).
        security_config: App security configuration.
        app_config: App configuration (for multi_tenant flag).
        feedback_widget: Feedback widget spec (for feedback region).
        existing_workspaces: Existing workspaces (for collision check).

    Returns:
        Tuple of (new_entities, new_surfaces, new_workspaces) to add to the AppSpec.

    Raises:
        LinkError: If name collisions are detected.
    """
    multi_tenant = app_config.multi_tenant if app_config else False
    feedback_enabled = feedback_widget is not None and feedback_widget.enabled

    # Build synthetic entities and surfaces
    admin_entities = _build_admin_entities(security_config)
    admin_surfaces = _build_admin_surfaces(security_config)

    # Build workspaces
    admin_workspaces = _build_admin_workspaces(
        security_config, multi_tenant=multi_tenant, feedback_enabled=feedback_enabled,
    )

    # Check for collisions
    existing_entity_names = {e.name for e in entities}
    existing_workspace_names = {w.name for w in existing_workspaces}
    _check_collisions(
        existing_entity_names=existing_entity_names,
        existing_workspace_names=existing_workspace_names,
        synthetic_entity_names={e.name for e in admin_entities},
        synthetic_workspace_names={w.name for w in admin_workspaces},
    )

    return admin_entities, admin_surfaces, admin_workspaces
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_admin_builder.py -v`
Expected: All PASS

- [ ] **Step 5: Integrate into linker.py**

Modify `src/dazzle/core/linker.py`. After line 126 (end of feedback widget block), before line 128 (FK graph building), add:

```python
    # 9c. Auto-generate admin platform entities, surfaces, and workspaces (#686)
    from .admin_builder import build_admin_infrastructure

    admin_entities, admin_surfaces, admin_workspaces = build_admin_infrastructure(
        entities=entities,
        surfaces=surfaces,
        security_config=security_config,
        app_config=root_module.app_config,
        feedback_widget=merged_fragment.feedback_widget,
        existing_workspaces=merged_fragment.workspaces,
    )
    entities = [*entities, *admin_entities]
    surfaces = [*surfaces, *admin_surfaces]
```

And in the AppSpec constructor (line 143), change `workspaces=merged_fragment.workspaces` to:

```python
        workspaces=[*merged_fragment.workspaces, *admin_workspaces],
```

- [ ] **Step 6: Run full linker test suite**

Run: `pytest tests/unit/test_linker.py tests/unit/test_admin_builder.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/core/admin_builder.py src/dazzle/core/linker.py tests/unit/test_admin_builder.py
git commit -m "feat: wire admin workspace builder into linker (#686)"
```

---

### Task 7: SystemEntityStore

**Files:**
- Create: `src/dazzle_back/runtime/system_entity_store.py`
- Create: `tests/unit/test_system_entity_store.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_system_entity_store.py`:

```python
"""Tests for SystemEntityStore — virtual entity routing."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone

from dazzle_back.runtime.system_entity_store import SystemEntityStore


class TestSystemEntityStoreHealth:
    """Tests for SystemHealth entity reads."""

    @pytest.mark.asyncio
    async def test_list_returns_component_statuses(self):
        """list() delegates to health aggregator and returns dicts."""
        mock_aggregator = MagicMock()
        mock_aggregator.get_latest.return_value = MagicMock(
            components=[
                MagicMock(
                    name="database",
                    status=MagicMock(value="healthy"),
                    message="OK",
                    latency_ms=5.2,
                    last_checked=datetime(2026, 3, 26, tzinfo=timezone.utc),
                ),
                MagicMock(
                    name="redis",
                    status=MagicMock(value="degraded"),
                    message="High latency",
                    latency_ms=150.0,
                    last_checked=datetime(2026, 3, 26, tzinfo=timezone.utc),
                ),
            ]
        )

        store = SystemEntityStore(
            entity_name="SystemHealth",
            health_aggregator=mock_aggregator,
        )
        results = await store.list()
        assert len(results) == 2
        assert results[0]["component"] == "database"
        assert results[0]["status"] == "healthy"
        assert results[1]["component"] == "redis"
        assert results[1]["status"] == "degraded"


class TestSystemEntityStoreProcessRun:
    """Tests for ProcessRun entity reads."""

    @pytest.mark.asyncio
    async def test_list_returns_recent_runs(self):
        """list() delegates to process monitor."""
        mock_monitor = MagicMock()
        mock_monitor.get_recent_runs.return_value = [
            MagicMock(
                id="run-1",
                process_name="order_fulfillment",
                status="completed",
                started_at=1711411200.0,
                completed_at=1711411260.0,
                current_step=None,
                error=None,
            ),
        ]

        store = SystemEntityStore(
            entity_name="ProcessRun",
            process_monitor=mock_monitor,
        )
        results = await store.list()
        assert len(results) == 1
        assert results[0]["process_name"] == "order_fulfillment"
        assert results[0]["status"] == "completed"


class TestSystemEntityStoreMetric:
    """Tests for SystemMetric entity reads."""

    @pytest.mark.asyncio
    async def test_list_returns_metric_points(self):
        """list() delegates to metrics store."""
        mock_store = MagicMock()
        mock_store.get_metric_names.return_value = ["api.latency", "api.errors"]
        mock_store.get_latest.side_effect = [42.5, 3.0]

        store = SystemEntityStore(
            entity_name="SystemMetric",
            metrics_store=mock_store,
        )
        results = await store.list()
        assert len(results) == 2
        assert results[0]["name"] == "api.latency"
        assert results[0]["value"] == 42.5


class TestSystemEntityStoreWriteBlocked:
    """Virtual entities reject writes."""

    @pytest.mark.asyncio
    async def test_create_raises(self):
        store = SystemEntityStore(entity_name="SystemHealth", health_aggregator=MagicMock())
        with pytest.raises(NotImplementedError, match="read-only"):
            await store.create({})

    @pytest.mark.asyncio
    async def test_update_raises(self):
        store = SystemEntityStore(entity_name="SystemHealth", health_aggregator=MagicMock())
        with pytest.raises(NotImplementedError, match="read-only"):
            await store.update("id", {})

    @pytest.mark.asyncio
    async def test_delete_raises(self):
        store = SystemEntityStore(entity_name="SystemHealth", health_aggregator=MagicMock())
        with pytest.raises(NotImplementedError, match="read-only"):
            await store.delete("id")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_system_entity_store.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement SystemEntityStore**

Create `src/dazzle_back/runtime/system_entity_store.py`:

```python
"""
Virtual entity store for platform system entities.

Routes read operations to existing backing stores (health aggregator,
metrics store, process monitor) instead of PostgreSQL. Write operations
are blocked — these entities are read-only projections.

See: docs/superpowers/specs/2026-03-26-admin-workspace-design.md
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


class SystemEntityStore:
    """Read-only store adapter for virtual platform entities.

    Each instance is bound to a single entity name and delegates
    reads to the appropriate backing store.
    """

    def __init__(
        self,
        entity_name: str,
        *,
        health_aggregator: Any | None = None,
        metrics_store: Any | None = None,
        process_monitor: Any | None = None,
    ) -> None:
        self.entity_name = entity_name
        self._health_aggregator = health_aggregator
        self._metrics_store = metrics_store
        self._process_monitor = process_monitor

    async def list(
        self,
        filters: dict[str, Any] | None = None,
        sort: list[str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """List entity records from the backing store."""
        if self.entity_name == "SystemHealth":
            return self._list_health()
        elif self.entity_name == "SystemMetric":
            return self._list_metrics()
        elif self.entity_name == "ProcessRun":
            return self._list_process_runs(limit=limit)
        raise ValueError(f"Unknown virtual entity: {self.entity_name}")

    async def get(self, record_id: str) -> dict[str, Any] | None:
        """Get a single record by ID. Limited support for virtual entities."""
        return None

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(f"{self.entity_name} is read-only")

    async def update(self, record_id: str, data: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(f"{self.entity_name} is read-only")

    async def delete(self, record_id: str) -> None:
        raise NotImplementedError(f"{self.entity_name} is read-only")

    # -- Private adapters --

    def _list_health(self) -> list[dict[str, Any]]:
        system_health = self._health_aggregator.get_latest()
        results: list[dict[str, Any]] = []
        for comp in system_health.components:
            status_val = comp.status.value if hasattr(comp.status, "value") else str(comp.status)
            results.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, comp.name)),
                "component": comp.name,
                "status": status_val,
                "message": comp.message,
                "latency_ms": comp.latency_ms,
                "checked_at": comp.last_checked or datetime.now(timezone.utc),
            })
        return results

    def _list_metrics(self) -> list[dict[str, Any]]:
        metric_names = self._metrics_store.get_metric_names()
        results: list[dict[str, Any]] = []
        for name in metric_names:
            latest = self._metrics_store.get_latest(name)
            if latest is not None:
                results.append({
                    "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, name)),
                    "name": name,
                    "value": latest,
                    "unit": None,
                    "tags": None,
                    "bucket_start": None,
                    "resolution": None,
                })
        return results

    def _list_process_runs(self, limit: int | None = None) -> list[dict[str, Any]]:
        runs = self._process_monitor.get_recent_runs(count=limit or 20)
        results: list[dict[str, Any]] = []
        for run in runs:
            started = None
            if run.started_at:
                started = datetime.fromtimestamp(run.started_at, tz=timezone.utc)
            completed = None
            if run.completed_at:
                completed = datetime.fromtimestamp(run.completed_at, tz=timezone.utc)
            results.append({
                "id": run.id,
                "process_name": run.process_name,
                "status": run.status,
                "started_at": started,
                "completed_at": completed,
                "current_step": run.current_step,
                "error": run.error,
            })
        return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_system_entity_store.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/system_entity_store.py tests/unit/test_system_entity_store.py
git commit -m "feat: SystemEntityStore — virtual entity read adapter (#686)"
```

---

### Task 8: Lint + Type Check + Full Test Suite

**Files:** None (validation only)

- [ ] **Step 1: Run ruff**

Run: `ruff check src/dazzle/core/admin_builder.py src/dazzle/core/ir/admin_entities.py src/dazzle_back/runtime/system_entity_store.py --fix && ruff format src/dazzle/core/admin_builder.py src/dazzle/core/ir/admin_entities.py src/dazzle_back/runtime/system_entity_store.py`
Expected: Clean or auto-fixed

- [ ] **Step 2: Run mypy**

Run: `mypy src/dazzle/core/admin_builder.py src/dazzle/core/ir/admin_entities.py`
Expected: No errors

- [ ] **Step 3: Run full unit test suite**

Run: `pytest tests/ -m "not e2e" --timeout=120 -q`
Expected: All existing tests still pass, new tests pass

- [ ] **Step 4: Commit any lint/type fixes**

```bash
git add -u
git commit -m "chore: lint + type fixes for admin workspace (#686)"
```

---

## Phase 3: Console Deprecation

### Task 9: Deprecation Headers on Console Routes

**Files:**
- Modify: `src/dazzle_back/runtime/ops_routes.py`
- Modify: `src/dazzle_back/runtime/console_routes.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_console_deprecation.py`:

```python
"""Tests for console route deprecation headers."""

import pytest


def test_ops_routes_have_deprecation_header():
    """Ops routes should include X-Dazzle-Deprecated header."""
    from dazzle_back.runtime.ops_routes import DEPRECATION_HEADER_KEY, DEPRECATION_HEADER_VALUE

    assert DEPRECATION_HEADER_KEY == "X-Dazzle-Deprecated"
    assert "admin workspace" in DEPRECATION_HEADER_VALUE.lower()


def test_console_routes_have_deprecation_header():
    """Console routes should include X-Dazzle-Deprecated header."""
    from dazzle_back.runtime.console_routes import DEPRECATION_HEADER_KEY, DEPRECATION_HEADER_VALUE

    assert DEPRECATION_HEADER_KEY == "X-Dazzle-Deprecated"
    assert "admin workspace" in DEPRECATION_HEADER_VALUE.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_console_deprecation.py -v`
Expected: FAIL

- [ ] **Step 3: Add deprecation constants and middleware to ops_routes.py and console_routes.py**

Add to the top of each file:

```python
DEPRECATION_HEADER_KEY = "X-Dazzle-Deprecated"
DEPRECATION_HEADER_VALUE = "Use admin workspace (_platform_admin). Console will be removed in a future release."
```

Add the header to all responses. These files use FastAPI `APIRouter`. Add a router-level middleware:

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

@router.middleware("http")
async def add_deprecation_header(request: Request, call_next):
    response = await call_next(request)
    response.headers[DEPRECATION_HEADER_KEY] = DEPRECATION_HEADER_VALUE
    return response
```

If the router doesn't support `.middleware()`, wrap each endpoint's `Response` with `response.headers[DEPRECATION_HEADER_KEY] = DEPRECATION_HEADER_VALUE`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_console_deprecation.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/ops_routes.py src/dazzle_back/runtime/console_routes.py tests/unit/test_console_deprecation.py
git commit -m "feat: deprecation headers on console routes (#686)"
```

---

### Task 10: File Follow-Up Issues

**Files:** None (GitHub issues only)

- [ ] **Step 1: File follow-up issues**

Create GitHub issues for deferred work:

1. **Log viewer region** — complex filtering UI for admin workspace
2. **App map / entity graph visualization** — migrate `/_console/app-map`
3. **Deploy trigger actions** — write operations from admin workspace
4. **Event explorer migration** — migrate to admin workspace region
5. **Review remaining control plane code** — deprecation/repurposing sweep
6. **Update examples for auth-universal** — basic profile gets admin persona
7. **Clarify basic/standard/strict taxonomy** — document what each profile means

- [ ] **Step 2: Commit**

No code changes — issue tracking only.

---

### Task 11: Final Verification

**Files:** None (validation only)

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -m "not e2e" --timeout=120 -q`
Expected: All pass

- [ ] **Step 2: Run lint**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/`
Expected: Clean

- [ ] **Step 3: Run mypy**

Run: `mypy src/dazzle`
Expected: No new errors

- [ ] **Step 4: Verify admin workspace in a real app**

Run: `cd examples/simple_task && dazzle validate`
Expected: Validation passes with the new synthetic entities and workspaces visible in the output.
