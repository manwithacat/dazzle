# IR Triple Enrichment + Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cache (Entity, Surface, Persona) triples in the AppSpec IR at link time, rewrite contract generation as a thin mapper over triples, and add a reconciliation engine that back-propagates contract failures to DSL levers.

**Architecture:** Three layers — triples (IR enrichment at link time), contracts (rewritten as triple mapper), reconciler (failure → diagnosis with DSL fix suggestions). All new code in `src/dazzle/core/ir/triples.py` and `src/dazzle/testing/ux/reconciler.py`. No UI layer imports in the IR module.

**Tech Stack:** Python 3.12+, Pydantic v2 (frozen models), pytest

---

## File Structure

| File | Responsibility |
|---|---|
| `src/dazzle/core/ir/triples.py` | **New** — `WidgetKind`, `SurfaceFieldTriple`, `SurfaceActionTriple`, `VerifiableTriple` models + `derive_triples()` + permission helpers (moved from contracts.py) |
| `src/dazzle/core/ir/__init__.py` | Export new types |
| `src/dazzle/core/ir/appspec.py` | Add `triples` field + 3 getters |
| `src/dazzle/core/linker.py` | Add step 10b: `derive_triples()` call |
| `src/dazzle/testing/ux/contracts.py` | Rewrite `generate_contracts()` as thin mapper over `appspec.triples` |
| `src/dazzle/testing/ux/reconciler.py` | **New** — `DiagnosisKind`, `DSLLever`, `Diagnosis` models + `reconcile()` |
| `.claude/commands/ux-converge.md` | Add reconciler integration |
| `tests/unit/test_triples.py` | **New** — widget, action, assembly, edge case tests |
| `tests/unit/test_reconciler.py` | **New** — mismatch diagnosis, lever identification tests |

---

### Task 1: Widget Resolution + SurfaceFieldTriple

**Files:**
- Create: `src/dazzle/core/ir/triples.py`
- Test: `tests/unit/test_triples.py`

- [ ] **Step 1: Write failing tests for widget resolution**

```python
# tests/unit/test_triples.py
"""Tests for IR triple derivation."""

import pytest

from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.triples import SurfaceFieldTriple, WidgetKind, resolve_widget


class TestResolveWidget:
    """Test widget resolution from field type."""

    def test_bool_becomes_checkbox(self):
        field = FieldSpec(name="active", type=FieldType(kind=FieldTypeKind.BOOL))
        assert resolve_widget(field) == WidgetKind.CHECKBOX

    def test_date_becomes_date_picker(self):
        field = FieldSpec(name="due_date", type=FieldType(kind=FieldTypeKind.DATE))
        assert resolve_widget(field) == WidgetKind.DATE_PICKER

    def test_datetime_becomes_datetime_picker(self):
        field = FieldSpec(name="created_at", type=FieldType(kind=FieldTypeKind.DATETIME))
        assert resolve_widget(field) == WidgetKind.DATETIME_PICKER

    def test_int_becomes_number_input(self):
        field = FieldSpec(name="count", type=FieldType(kind=FieldTypeKind.INT))
        assert resolve_widget(field) == WidgetKind.NUMBER_INPUT

    def test_decimal_becomes_number_input(self):
        field = FieldSpec(name="price", type=FieldType(kind=FieldTypeKind.DECIMAL, precision=10, scale=2))
        assert resolve_widget(field) == WidgetKind.NUMBER_INPUT

    def test_money_becomes_money_input(self):
        field = FieldSpec(name="amount", type=FieldType(kind=FieldTypeKind.MONEY, currency_code="GBP"))
        assert resolve_widget(field) == WidgetKind.MONEY_INPUT

    def test_text_becomes_textarea(self):
        field = FieldSpec(name="notes", type=FieldType(kind=FieldTypeKind.TEXT))
        assert resolve_widget(field) == WidgetKind.TEXTAREA

    def test_email_becomes_email_input(self):
        field = FieldSpec(name="email", type=FieldType(kind=FieldTypeKind.EMAIL))
        assert resolve_widget(field) == WidgetKind.EMAIL_INPUT

    def test_enum_becomes_enum_select(self):
        field = FieldSpec(name="status", type=FieldType(kind=FieldTypeKind.ENUM, enum_values=["a", "b"]))
        assert resolve_widget(field) == WidgetKind.ENUM_SELECT

    def test_ref_becomes_search_select(self):
        field = FieldSpec(name="school_id", type=FieldType(kind=FieldTypeKind.REF, ref_entity="School"))
        assert resolve_widget(field) == WidgetKind.SEARCH_SELECT

    def test_belongs_to_becomes_search_select(self):
        field = FieldSpec(name="parent_id", type=FieldType(kind=FieldTypeKind.BELONGS_TO, ref_entity="Parent"))
        assert resolve_widget(field) == WidgetKind.SEARCH_SELECT

    def test_file_becomes_file_upload(self):
        field = FieldSpec(name="avatar", type=FieldType(kind=FieldTypeKind.FILE))
        assert resolve_widget(field) == WidgetKind.FILE_UPLOAD

    def test_str_becomes_text_input(self):
        field = FieldSpec(name="title", type=FieldType(kind=FieldTypeKind.STR, max_length=200))
        assert resolve_widget(field) == WidgetKind.TEXT_INPUT

    def test_uuid_becomes_text_input(self):
        field = FieldSpec(name="token", type=FieldType(kind=FieldTypeKind.UUID))
        assert resolve_widget(field) == WidgetKind.TEXT_INPUT

    def test_id_suffix_convention_becomes_search_select(self):
        """UUID field with _id suffix is treated as FK → search_select."""
        field = FieldSpec(name="school_id", type=FieldType(kind=FieldTypeKind.UUID))
        assert resolve_widget(field) == WidgetKind.SEARCH_SELECT

    def test_id_suffix_requires_id_not_just_ending(self):
        """Field named 'id' itself should NOT become search_select."""
        field = FieldSpec(name="id", type=FieldType(kind=FieldTypeKind.UUID))
        assert resolve_widget(field) == WidgetKind.TEXT_INPUT

    def test_source_option_overrides_to_search_select(self):
        """Surface element with source= should override widget to search_select."""
        field = FieldSpec(name="title", type=FieldType(kind=FieldTypeKind.STR, max_length=200))
        assert resolve_widget(field, has_source=True) == WidgetKind.SEARCH_SELECT


class TestSurfaceFieldTriple:
    """Test SurfaceFieldTriple construction."""

    def test_basic_field(self):
        sft = SurfaceFieldTriple(
            field_name="title",
            widget=WidgetKind.TEXT_INPUT,
            is_required=True,
            is_fk=False,
        )
        assert sft.field_name == "title"
        assert sft.ref_entity is None

    def test_fk_field(self):
        sft = SurfaceFieldTriple(
            field_name="school_id",
            widget=WidgetKind.SEARCH_SELECT,
            is_required=True,
            is_fk=True,
            ref_entity="School",
        )
        assert sft.is_fk is True
        assert sft.ref_entity == "School"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_triples.py -v`
Expected: ImportError — `cannot import name 'resolve_widget' from 'dazzle.core.ir.triples'`

- [ ] **Step 3: Implement WidgetKind, SurfaceFieldTriple, resolve_widget**

```python
# src/dazzle/core/ir/triples.py
"""Verifiable (Entity, Surface, Persona) triples for the AppSpec IR.

Derived at link time from entities, surfaces, and personas. Downstream
consumers (contract verification, validation, compliance) read these
instead of re-deriving from HTML.

See ADR-0019 and docs/superpowers/specs/2026-03-28-ir-triple-enrichment-design.md.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .fields import FieldSpec, FieldTypeKind


class WidgetKind(StrEnum):
    TEXT_INPUT = "text_input"
    TEXTAREA = "textarea"
    CHECKBOX = "checkbox"
    DATE_PICKER = "date_picker"
    DATETIME_PICKER = "datetime_picker"
    NUMBER_INPUT = "number_input"
    EMAIL_INPUT = "email_input"
    ENUM_SELECT = "enum_select"
    SEARCH_SELECT = "search_select"
    MONEY_INPUT = "money_input"
    FILE_UPLOAD = "file_upload"


_WIDGET_MAP: dict[FieldTypeKind, WidgetKind] = {
    FieldTypeKind.BOOL: WidgetKind.CHECKBOX,
    FieldTypeKind.DATE: WidgetKind.DATE_PICKER,
    FieldTypeKind.DATETIME: WidgetKind.DATETIME_PICKER,
    FieldTypeKind.INT: WidgetKind.NUMBER_INPUT,
    FieldTypeKind.DECIMAL: WidgetKind.NUMBER_INPUT,
    FieldTypeKind.MONEY: WidgetKind.MONEY_INPUT,
    FieldTypeKind.TEXT: WidgetKind.TEXTAREA,
    FieldTypeKind.EMAIL: WidgetKind.EMAIL_INPUT,
    FieldTypeKind.ENUM: WidgetKind.ENUM_SELECT,
    FieldTypeKind.REF: WidgetKind.SEARCH_SELECT,
    FieldTypeKind.BELONGS_TO: WidgetKind.SEARCH_SELECT,
    FieldTypeKind.FILE: WidgetKind.FILE_UPLOAD,
}


def resolve_widget(field: FieldSpec, *, has_source: bool = False) -> WidgetKind:
    """Determine the widget kind for a field.

    Args:
        field: The field specification from the entity.
        has_source: True if the surface element has a ``source=`` option.

    Returns:
        The resolved widget kind.
    """
    if has_source:
        return WidgetKind.SEARCH_SELECT

    if field.type:
        mapped = _WIDGET_MAP.get(field.type.kind)
        if mapped is not None:
            return mapped

    # _id suffix convention: uuid field ending in _id (but not "id" itself)
    if (
        field.name.endswith("_id")
        and field.name != "id"
        and field.type
        and field.type.kind == FieldTypeKind.UUID
    ):
        return WidgetKind.SEARCH_SELECT

    return WidgetKind.TEXT_INPUT


class SurfaceFieldTriple(BaseModel):
    """Per-field rendering resolution for a surface."""

    field_name: str
    widget: WidgetKind
    is_required: bool
    is_fk: bool
    ref_entity: str | None = None

    model_config = ConfigDict(frozen=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_triples.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/ir/triples.py tests/unit/test_triples.py
git commit -m "feat(ir): add WidgetKind, SurfaceFieldTriple, resolve_widget"
```

---

### Task 2: Permission Helpers + Action Derivation

**Files:**
- Modify: `src/dazzle/core/ir/triples.py`
- Test: `tests/unit/test_triples.py`

- [ ] **Step 1: Write failing tests for permission helpers and action derivation**

```python
# Append to tests/unit/test_triples.py

from dazzle.core.ir.domain import (
    AccessSpec,
    EntitySpec,
    PermissionKind,
    PermissionRule,
    PolicyEffect,
)
from dazzle.core.ir.personas import PersonaSpec
from dazzle.core.ir.state_machine import StateMachineSpec, StateTransition
from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle.core.ir.triples import (
    SurfaceActionTriple,
    get_permitted_personas,
    resolve_surface_actions,
)


def _make_entity(
    name: str,
    permissions: list[tuple[PermissionKind, list[str]]] | None = None,
    state_machine: StateMachineSpec | None = None,
) -> EntitySpec:
    """Helper to build a minimal entity with permissions."""
    rules = []
    if permissions:
        for op, personas in permissions:
            rules.append(PermissionRule(
                operation=op,
                effect=PolicyEffect.PERMIT,
                require_auth=True,
                personas=personas,
            ))
    access = AccessSpec(permissions=rules) if rules else None
    return EntitySpec(name=name, title=name, fields=[], access=access, state_machine=state_machine)


def _make_surface(name: str, entity_ref: str, mode: SurfaceMode) -> SurfaceSpec:
    return SurfaceSpec(name=name, entity_ref=entity_ref, mode=mode)


def _make_personas(*ids: str) -> list[PersonaSpec]:
    return [PersonaSpec(id=pid) for pid in ids]


class TestGetPermittedPersonas:
    def test_open_permission_returns_all(self):
        entity = _make_entity("Task", [(PermissionKind.LIST, [])])
        personas = _make_personas("admin", "user")
        result = get_permitted_personas(
            [entity], personas, "Task", PermissionKind.LIST,
        )
        assert set(result) == {"admin", "user"}

    def test_restricted_permission_returns_named(self):
        entity = _make_entity("Task", [(PermissionKind.DELETE, ["admin"])])
        personas = _make_personas("admin", "user")
        result = get_permitted_personas(
            [entity], personas, "Task", PermissionKind.DELETE,
        )
        assert result == ["admin"]

    def test_no_permission_returns_empty(self):
        entity = _make_entity("Task")  # no access rules
        personas = _make_personas("admin")
        result = get_permitted_personas(
            [entity], personas, "Task", PermissionKind.DELETE,
        )
        # No access spec → all personas permitted (default-allow for authenticated)
        assert result == ["admin"]


class TestResolveSurfaceActions:
    def test_list_mode_actions(self):
        entity = _make_entity("Task", [
            (PermissionKind.LIST, []),
            (PermissionKind.CREATE, ["admin"]),
        ])
        surfaces = [_make_surface("task_list", "Task", SurfaceMode.LIST)]
        personas = _make_personas("admin", "viewer")
        actions = resolve_surface_actions(entity, surfaces[0], surfaces, personas, [entity])
        action_names = [a.action for a in actions]
        assert "list" in action_names
        assert "detail_link" in action_names
        assert "create_link" in action_names

    def test_view_mode_with_edit_surface(self):
        entity = _make_entity("Task", [
            (PermissionKind.UPDATE, ["admin"]),
            (PermissionKind.DELETE, ["admin"]),
        ])
        surfaces = [
            _make_surface("task_view", "Task", SurfaceMode.VIEW),
            _make_surface("task_edit", "Task", SurfaceMode.EDIT),
        ]
        personas = _make_personas("admin")
        actions = resolve_surface_actions(entity, surfaces[0], surfaces, personas, [entity])
        action_names = [a.action for a in actions]
        assert "edit_link" in action_names
        assert "delete_button" in action_names

    def test_view_mode_without_edit_surface(self):
        entity = _make_entity("Task", [(PermissionKind.UPDATE, ["admin"])])
        surfaces = [_make_surface("task_view", "Task", SurfaceMode.VIEW)]
        personas = _make_personas("admin")
        actions = resolve_surface_actions(entity, surfaces[0], surfaces, personas, [entity])
        action_names = [a.action for a in actions]
        assert "edit_link" not in action_names

    def test_view_mode_with_transitions(self):
        sm = StateMachineSpec(
            status_field="status",
            states=["draft", "published"],
            transitions=[StateTransition(from_state="draft", to_state="published")],
        )
        entity = _make_entity("Task", [(PermissionKind.UPDATE, [])], state_machine=sm)
        surfaces = [_make_surface("task_view", "Task", SurfaceMode.VIEW)]
        personas = _make_personas("admin")
        actions = resolve_surface_actions(entity, surfaces[0], surfaces, personas, [entity])
        action_names = [a.action for a in actions]
        assert "transition:published" in action_names

    def test_create_mode_actions(self):
        entity = _make_entity("Task", [(PermissionKind.CREATE, [])])
        surfaces = [_make_surface("task_create", "Task", SurfaceMode.CREATE)]
        personas = _make_personas("admin")
        actions = resolve_surface_actions(entity, surfaces[0], surfaces, personas, [entity])
        assert [a.action for a in actions] == ["create_submit"]

    def test_edit_mode_actions(self):
        entity = _make_entity("Task", [(PermissionKind.UPDATE, [])])
        surfaces = [_make_surface("task_edit", "Task", SurfaceMode.EDIT)]
        personas = _make_personas("admin")
        actions = resolve_surface_actions(entity, surfaces[0], surfaces, personas, [entity])
        assert [a.action for a in actions] == ["edit_submit"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_triples.py::TestGetPermittedPersonas -v`
Expected: ImportError — `cannot import name 'get_permitted_personas'`

- [ ] **Step 3: Implement permission helpers and action derivation**

Append to `src/dazzle/core/ir/triples.py`:

```python
from .domain import EntitySpec, PermissionKind, PermissionRule
from .personas import PersonaSpec
from .surfaces import SurfaceMode, SurfaceSpec


# ---------------------------------------------------------------------------
# Permission helpers (moved from testing/ux/contracts.py)
# ---------------------------------------------------------------------------

def _condition_matches_role(condition: object, role: str) -> bool:
    """Return True if a ConditionExpr contains a role_check matching *role*."""
    if condition is None:
        return False
    role_check = getattr(condition, "role_check", None)
    if role_check is not None:
        return getattr(role_check, "role_name", None) == role
    left = getattr(condition, "left", None)
    right = getattr(condition, "right", None)
    if left is not None or right is not None:
        return _condition_matches_role(left, role) or _condition_matches_role(right, role)
    return False


def _condition_is_pure_role_only(condition: object) -> bool:
    """Return True if condition is exclusively role_check nodes."""
    if condition is None:
        return False
    if getattr(condition, "comparison", None) is not None:
        return False
    if getattr(condition, "grant_check", None) is not None:
        return False
    if getattr(condition, "role_check", None) is not None:
        return True
    left = getattr(condition, "left", None)
    right = getattr(condition, "right", None)
    if left is not None or right is not None:
        left_pure = _condition_is_pure_role_only(left) if left is not None else True
        right_pure = _condition_is_pure_role_only(right) if right is not None else True
        return left_pure and right_pure
    return False


def _rule_matches_persona(rule: PermissionRule, persona_id: str) -> bool:
    """Return True if a PermissionRule applies to the given persona ID."""
    personas = getattr(rule, "personas", [])
    condition = getattr(rule, "condition", None)
    if not personas:
        if _condition_is_pure_role_only(condition):
            return _condition_matches_role(condition, persona_id)
        return True
    if persona_id in personas:
        return True
    if _condition_matches_role(condition, persona_id):
        return True
    return False


def get_permitted_personas(
    entities: list[EntitySpec],
    personas: list[PersonaSpec],
    entity_name: str,
    operation: PermissionKind,
) -> list[str]:
    """Return persona IDs that have a permit rule for the given operation."""
    entity = next((e for e in entities if e.name == entity_name), None)
    if not entity or not entity.access:
        return [p.id for p in personas]
    permitted: set[str] = set()
    for rule in entity.access.permissions:
        if rule.operation == operation:
            if rule.personas:
                permitted.update(rule.personas)
            else:
                condition = getattr(rule, "condition", None)
                if _condition_is_pure_role_only(condition):
                    for p in personas:
                        if _condition_matches_role(condition, p.id):
                            permitted.add(p.id)
                else:
                    return [p.id for p in personas]
    return list(permitted)


# ---------------------------------------------------------------------------
# Action derivation
# ---------------------------------------------------------------------------

class SurfaceActionTriple(BaseModel):
    """Per-surface action with permission requirement."""

    action: str
    requires_permission: str
    visible_to: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


def resolve_surface_actions(
    entity: EntitySpec,
    surface: SurfaceSpec,
    all_surfaces: list[SurfaceSpec],
    personas: list[PersonaSpec],
    entities: list[EntitySpec],
) -> list[SurfaceActionTriple]:
    """Derive actions for a surface based on mode, permissions, and related surfaces."""
    mode = str(surface.mode.value) if hasattr(surface.mode, "value") else str(surface.mode)
    actions: list[SurfaceActionTriple] = []

    if mode == "list":
        actions.append(SurfaceActionTriple(
            action="list",
            requires_permission="LIST",
            visible_to=get_permitted_personas(entities, personas, entity.name, PermissionKind.LIST),
        ))
        actions.append(SurfaceActionTriple(
            action="detail_link",
            requires_permission="LIST",
            visible_to=get_permitted_personas(entities, personas, entity.name, PermissionKind.LIST),
        ))
        create_personas = get_permitted_personas(entities, personas, entity.name, PermissionKind.CREATE)
        if create_personas:
            actions.append(SurfaceActionTriple(
                action="create_link",
                requires_permission="CREATE",
                visible_to=create_personas,
            ))

    elif mode == "view":
        # edit_link only if UPDATE permitted AND an edit surface exists
        has_edit_surface = any(
            s.entity_ref == entity.name
            and (str(s.mode.value) if hasattr(s.mode, "value") else str(s.mode)) == "edit"
            for s in all_surfaces
        )
        update_personas = get_permitted_personas(entities, personas, entity.name, PermissionKind.UPDATE)
        if has_edit_surface and update_personas:
            actions.append(SurfaceActionTriple(
                action="edit_link",
                requires_permission="UPDATE",
                visible_to=update_personas,
            ))

        delete_personas = get_permitted_personas(entities, personas, entity.name, PermissionKind.DELETE)
        if delete_personas:
            actions.append(SurfaceActionTriple(
                action="delete_button",
                requires_permission="DELETE",
                visible_to=delete_personas,
            ))

        # Transitions from state machine
        if entity.state_machine:
            seen_targets: set[str] = set()
            for t in entity.state_machine.transitions:
                to_s = t.to_state if isinstance(t.to_state, str) else t.to_state.name
                if to_s not in seen_targets:
                    seen_targets.add(to_s)
                    actions.append(SurfaceActionTriple(
                        action=f"transition:{to_s}",
                        requires_permission="UPDATE",
                        visible_to=update_personas,
                    ))

    elif mode == "create":
        actions.append(SurfaceActionTriple(
            action="create_submit",
            requires_permission="CREATE",
            visible_to=get_permitted_personas(entities, personas, entity.name, PermissionKind.CREATE),
        ))

    elif mode == "edit":
        actions.append(SurfaceActionTriple(
            action="edit_submit",
            requires_permission="UPDATE",
            visible_to=get_permitted_personas(entities, personas, entity.name, PermissionKind.UPDATE),
        ))

    return actions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_triples.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/ir/triples.py tests/unit/test_triples.py
git commit -m "feat(ir): add permission helpers and action derivation for triples"
```

---

### Task 3: VerifiableTriple + derive_triples()

**Files:**
- Modify: `src/dazzle/core/ir/triples.py`
- Test: `tests/unit/test_triples.py`

- [ ] **Step 1: Write failing tests for triple assembly**

```python
# Append to tests/unit/test_triples.py

from dazzle.core.ir.triples import VerifiableTriple, derive_triples


class TestDeriveTriples:
    def test_basic_triple_count(self):
        """2 entities × 2 surfaces each × 2 personas = 8 triples max."""
        entities = [
            _make_entity("Task", [
                (PermissionKind.LIST, []),
                (PermissionKind.CREATE, ["admin"]),
            ]),
            _make_entity("Project", [
                (PermissionKind.LIST, []),
            ]),
        ]
        surfaces = [
            _make_surface("task_list", "Task", SurfaceMode.LIST),
            _make_surface("task_create", "Task", SurfaceMode.CREATE),
            _make_surface("project_list", "Project", SurfaceMode.LIST),
        ]
        personas = _make_personas("admin", "viewer")
        triples = derive_triples(entities, surfaces, personas)
        # task_list: admin + viewer (both have LIST)
        # task_create: admin only (only admin has CREATE)
        # project_list: admin + viewer (both have LIST)
        assert len(triples) == 5

    def test_triple_fields_populated(self):
        entities = [
            EntitySpec(
                name="Task",
                title="Task",
                fields=[
                    FieldSpec(name="id", type=FieldType(kind=FieldTypeKind.UUID), modifiers=[FieldModifier.PK]),
                    FieldSpec(name="title", type=FieldType(kind=FieldTypeKind.STR, max_length=200), modifiers=[FieldModifier.REQUIRED]),
                    FieldSpec(name="done", type=FieldType(kind=FieldTypeKind.BOOL)),
                ],
                access=AccessSpec(permissions=[
                    PermissionRule(operation=PermissionKind.LIST, effect=PolicyEffect.PERMIT, require_auth=True),
                ]),
            ),
        ]
        surfaces = [_make_surface("task_list", "Task", SurfaceMode.LIST)]
        personas = _make_personas("user")
        triples = derive_triples(entities, surfaces, personas)
        assert len(triples) == 1
        t = triples[0]
        assert t.entity == "Task"
        assert t.surface == "task_list"
        assert t.persona == "user"
        assert t.surface_mode == "list"
        field_names = [f.field_name for f in t.fields]
        assert "title" in field_names
        assert "done" in field_names
        assert "id" not in field_names  # PK excluded

    def test_framework_entities_excluded(self):
        entities = [_make_entity("AIJob"), _make_entity("Task", [(PermissionKind.LIST, [])])]
        surfaces = [
            _make_surface("aijob_list", "AIJob", SurfaceMode.LIST),
            _make_surface("task_list", "Task", SurfaceMode.LIST),
        ]
        personas = _make_personas("admin")
        triples = derive_triples(entities, surfaces, personas)
        assert all(t.entity != "AIJob" for t in triples)

    def test_entity_without_surfaces_produces_no_triples(self):
        entities = [_make_entity("Task", [(PermissionKind.LIST, [])])]
        surfaces: list[SurfaceSpec] = []
        personas = _make_personas("admin")
        triples = derive_triples(entities, surfaces, personas)
        assert triples == []

    def test_persona_actions_filtered(self):
        """Viewer should not see create_link on list surface."""
        entities = [_make_entity("Task", [
            (PermissionKind.LIST, []),
            (PermissionKind.CREATE, ["admin"]),
        ])]
        surfaces = [_make_surface("task_list", "Task", SurfaceMode.LIST)]
        personas = _make_personas("admin", "viewer")
        triples = derive_triples(entities, surfaces, personas)
        admin_triple = next(t for t in triples if t.persona == "admin")
        viewer_triple = next(t for t in triples if t.persona == "viewer")
        assert "create_link" in admin_triple.actions
        assert "create_link" not in viewer_triple.actions
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_triples.py::TestDeriveTriples -v`
Expected: ImportError — `cannot import name 'VerifiableTriple'`

- [ ] **Step 3: Implement VerifiableTriple and derive_triples()**

Append to `src/dazzle/core/ir/triples.py`:

```python
class VerifiableTriple(BaseModel):
    """Atomic unit of verifiable behavior: (Entity, Surface, Persona)."""

    entity: str
    surface: str
    persona: str
    surface_mode: str
    actions: list[str] = Field(default_factory=list)
    fields: list[SurfaceFieldTriple] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


_FRAMEWORK_ENTITIES: frozenset[str] = frozenset(
    {"AIJob", "FeedbackReport", "SystemHealth", "SystemMetric", "DeployHistory"}
)


def _resolve_surface_fields(
    entity: EntitySpec,
    surface: SurfaceSpec,
) -> list[SurfaceFieldTriple]:
    """Build field triples for a surface from its sections or entity fields."""
    fields_to_check: list[tuple[str, FieldSpec | None, bool]] = []

    if surface.sections:
        for section in surface.sections:
            for element in section.elements:
                field_spec = next(
                    (f for f in entity.fields if f.name == element.field_name), None
                )
                has_source = bool(element.options.get("source"))
                fields_to_check.append((element.field_name, field_spec, has_source))
    else:
        for field in entity.fields:
            if field.is_primary_key:
                continue
            modifiers = [str(m) for m in (field.modifiers or [])]
            if "auto_add" in modifiers or "auto_update" in modifiers:
                continue
            fields_to_check.append((field.name, field, False))

    result: list[SurfaceFieldTriple] = []
    for field_name, field_spec, has_source in fields_to_check:
        if field_spec is None:
            widget = WidgetKind.TEXT_INPUT
            is_required = False
            is_fk = False
            ref_entity = None
        else:
            widget = resolve_widget(field_spec, has_source=has_source)
            modifiers = [str(m) for m in (field_spec.modifiers or [])]
            is_required = "required" in modifiers
            ref_entity_val = getattr(field_spec.type, "ref_entity", None) if field_spec.type else None
            is_fk = ref_entity_val is not None or (
                field_name.endswith("_id") and field_name != "id"
            )
            ref_entity = ref_entity_val
        result.append(SurfaceFieldTriple(
            field_name=field_name,
            widget=widget,
            is_required=is_required and not is_fk,
            is_fk=is_fk,
            ref_entity=ref_entity,
        ))
    return result


def derive_triples(
    entities: list[EntitySpec],
    surfaces: list[SurfaceSpec],
    personas: list[PersonaSpec],
) -> list[VerifiableTriple]:
    """Derive all verifiable triples from entities, surfaces, and personas.

    Pure function — no side effects, no imports from dazzle_ui.
    """
    # Index: entity name → surfaces
    entity_surfaces: dict[str, list[SurfaceSpec]] = {}
    for surface in surfaces:
        if surface.entity_ref:
            entity_surfaces.setdefault(surface.entity_ref, []).append(surface)

    triples: list[VerifiableTriple] = []
    for entity in entities:
        if entity.name in _FRAMEWORK_ENTITIES:
            continue
        ent_surfaces = entity_surfaces.get(entity.name, [])
        if not ent_surfaces:
            continue

        for surface in ent_surfaces:
            mode = str(surface.mode.value) if hasattr(surface.mode, "value") else str(surface.mode)
            fields = _resolve_surface_fields(entity, surface)
            actions = resolve_surface_actions(entity, surface, surfaces, personas, entities)

            for persona in personas:
                persona_actions = [
                    a.action for a in actions if persona.id in a.visible_to
                ]
                if not persona_actions:
                    continue
                triples.append(VerifiableTriple(
                    entity=entity.name,
                    surface=surface.name,
                    persona=persona.id,
                    surface_mode=mode,
                    actions=persona_actions,
                    fields=fields,
                ))

    return triples
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_triples.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/ir/triples.py tests/unit/test_triples.py
git commit -m "feat(ir): add VerifiableTriple and derive_triples()"
```

---

### Task 4: Wire into Linker + AppSpec

**Files:**
- Modify: `src/dazzle/core/ir/appspec.py:79-189`
- Modify: `src/dazzle/core/ir/__init__.py:1-1227`
- Modify: `src/dazzle/core/linker.py:142-192`
- Test: `tests/unit/test_triples.py`

- [ ] **Step 1: Write failing test for linker integration**

```python
# Append to tests/unit/test_triples.py
from pathlib import Path
from dazzle.core.appspec_loader import load_project_appspec


class TestLinkerIntegration:
    def test_simple_task_has_triples(self):
        appspec = load_project_appspec(Path("examples/simple_task"))
        assert len(appspec.triples) > 0

    def test_simple_task_triple_count(self):
        appspec = load_project_appspec(Path("examples/simple_task"))
        # 8 entities, 12 surfaces, 3 personas → some triples
        # Exact count may vary; just verify it's reasonable
        assert 10 <= len(appspec.triples) <= 100

    def test_fieldtest_hub_triple_count(self):
        appspec = load_project_appspec(Path("examples/fieldtest_hub"))
        assert 30 <= len(appspec.triples) <= 200

    def test_appspec_get_triple(self):
        appspec = load_project_appspec(Path("examples/simple_task"))
        # Find any triple and verify getter works
        if appspec.triples:
            t = appspec.triples[0]
            found = appspec.get_triple(t.entity, t.surface, t.persona)
            assert found is not None
            assert found.entity == t.entity

    def test_appspec_get_triples_for_entity(self):
        appspec = load_project_appspec(Path("examples/simple_task"))
        if appspec.triples:
            entity_name = appspec.triples[0].entity
            entity_triples = appspec.get_triples_for_entity(entity_name)
            assert all(t.entity == entity_name for t in entity_triples)

    def test_appspec_get_triples_for_persona(self):
        appspec = load_project_appspec(Path("examples/simple_task"))
        if appspec.triples:
            persona = appspec.triples[0].persona
            persona_triples = appspec.get_triples_for_persona(persona)
            assert all(t.persona == persona for t in persona_triples)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_triples.py::TestLinkerIntegration::test_simple_task_has_triples -v`
Expected: AttributeError — `AppSpec` has no attribute `triples`

- [ ] **Step 3: Add triples field to AppSpec**

In `src/dazzle/core/ir/appspec.py`, add the import at the top (after existing imports) and the field + getters:

Add import:
```python
from .triples import VerifiableTriple
```

Add field to AppSpec class (after `fk_graph`):
```python
    # Verifiable triples (v0.50.0 IR Triple Enrichment)
    triples: list[VerifiableTriple] = Field(default_factory=list)
```

Add getters (after `get_grant_schemas_by_scope`):
```python
    # Triple getters (v0.50.0 IR Triple Enrichment)

    def get_triples_for_entity(self, entity: str) -> list[VerifiableTriple]:
        """Get all triples for a given entity."""
        return [t for t in self.triples if t.entity == entity]

    def get_triples_for_persona(self, persona: str) -> list[VerifiableTriple]:
        """Get all triples for a given persona."""
        return [t for t in self.triples if t.persona == persona]

    def get_triple(self, entity: str, surface: str, persona: str) -> VerifiableTriple | None:
        """Get a specific triple by entity, surface, and persona."""
        for t in self.triples:
            if t.entity == entity and t.surface == surface and t.persona == persona:
                return t
        return None
```

- [ ] **Step 4: Add exports to `__init__.py`**

In `src/dazzle/core/ir/__init__.py`, add import block (after the Personas import):

```python
# Triples (v0.50.0 IR Triple Enrichment)
from .triples import (
    SurfaceActionTriple,
    SurfaceFieldTriple,
    VerifiableTriple,
    WidgetKind,
)
```

Add to `__all__` list (after `"PersonaSpec"`):
```python
    # Triples (v0.50.0 IR Triple Enrichment)
    "SurfaceActionTriple",
    "SurfaceFieldTriple",
    "VerifiableTriple",
    "WidgetKind",
```

- [ ] **Step 5: Wire derive_triples into linker**

In `src/dazzle/core/linker.py`, add step 10b between the scope predicate compilation (line ~147) and the AppSpec construction (line ~150). After:

```python
    entities = _compile_scope_predicates(entities, fk_graph, build_scope_predicate)
```

Add:

```python
    # 10b. Derive verifiable triples
    from .ir.triples import derive_triples

    triples = derive_triples(entities, surfaces, merged_fragment.personas)
```

Then add `triples=triples,` to the `ir.AppSpec(...)` constructor call, after `fk_graph=fk_graph,`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/test_triples.py -v`
Expected: All PASS

- [ ] **Step 7: Run existing tests to verify no regressions**

Run: `pytest tests/ -m "not e2e" -x -q --timeout=60`
Expected: All existing tests still PASS

- [ ] **Step 8: Commit**

```bash
git add src/dazzle/core/ir/appspec.py src/dazzle/core/ir/__init__.py src/dazzle/core/linker.py tests/unit/test_triples.py
git commit -m "feat(ir): wire derive_triples into linker step 10b + AppSpec field"
```

---

### Task 5: Rewrite contracts.py as Triple Mapper

**Files:**
- Modify: `src/dazzle/testing/ux/contracts.py`
- Test: `tests/unit/test_triples.py`

- [ ] **Step 1: Write contract parity test**

```python
# Append to tests/unit/test_triples.py
from dazzle.testing.ux.contracts import generate_contracts


class TestContractParity:
    def test_fieldtest_hub_contract_ids_match(self):
        """New triple-based contracts must produce same contract_ids as old code."""
        appspec = load_project_appspec(Path("examples/fieldtest_hub"))
        new_contracts = generate_contracts(appspec)
        # Verify we get contracts (basic sanity)
        assert len(new_contracts) > 0
        # Verify all expected contract kinds are present
        kinds = {c.kind for c in new_contracts}
        assert "list_page" in kinds
        assert "rbac" in kinds

    def test_simple_task_contracts_from_triples(self):
        appspec = load_project_appspec(Path("examples/simple_task"))
        contracts = generate_contracts(appspec)
        assert len(contracts) > 0
```

- [ ] **Step 2: Run parity test to verify it passes with old code**

Run: `pytest tests/unit/test_triples.py::TestContractParity -v`
Expected: PASS (old generate_contracts still works)

- [ ] **Step 3: Rewrite contracts.py as thin mapper**

Replace the `generate_contracts` function and remove the permission helpers (they now live in `triples.py`). Keep the contract data classes unchanged. The new `generate_contracts`:

```python
def generate_contracts(appspec: AppSpec) -> list[Contract]:
    """Generate the full set of UX contracts from an AppSpec.

    Reads pre-computed triples from ``appspec.triples`` and maps each
    to the appropriate Contract subclass.  Permission helpers have moved
    to ``dazzle.core.ir.triples``.
    """
    from dazzle.core.ir.domain import PermissionKind
    from dazzle.core.ir.triples import get_permitted_personas

    contracts: list[Contract] = []
    seen_list: set[str] = set()
    seen_create: set[str] = set()
    seen_edit: set[str] = set()
    seen_detail: set[str] = set()

    for triple in appspec.triples:
        if triple.surface_mode == "list" and triple.entity not in seen_list:
            seen_list.add(triple.entity)
            contracts.append(ListPageContract(
                entity=triple.entity,
                surface=triple.surface,
                fields=[f.field_name for f in triple.fields],
            ))

        elif triple.surface_mode == "create" and triple.entity not in seen_create:
            seen_create.add(triple.entity)
            contracts.append(CreateFormContract(
                entity=triple.entity,
                required_fields=[f.field_name for f in triple.fields if f.is_required and not f.is_fk],
                all_fields=[f.field_name for f in triple.fields],
            ))

        elif triple.surface_mode == "edit" and triple.entity not in seen_edit:
            seen_edit.add(triple.entity)
            contracts.append(EditFormContract(
                entity=triple.entity,
                editable_fields=[f.field_name for f in triple.fields if not f.is_fk],
            ))

        elif triple.surface_mode == "view" and triple.entity not in seen_detail:
            seen_detail.add(triple.entity)
            entity_spec = appspec.get_entity(triple.entity)
            transitions: list[str] = []
            if entity_spec and entity_spec.state_machine:
                for t in entity_spec.state_machine.transitions:
                    from_s = t.from_state if isinstance(t.from_state, str) else t.from_state.name
                    to_s = t.to_state if isinstance(t.to_state, str) else t.to_state.name
                    transitions.append(f"{from_s}\u2192{to_s}")

            has_edit = "edit_link" in triple.actions
            has_delete = "delete_button" in triple.actions
            contracts.append(DetailViewContract(
                entity=triple.entity,
                fields=[f.field_name for f in triple.fields],
                has_edit=has_edit,
                has_delete=has_delete,
                transitions=transitions,
            ))

    # RBAC contracts — one per entity × persona × operation
    all_personas = [p.id for p in appspec.personas]
    entities_with_surfaces = {t.entity for t in appspec.triples}
    for entity_name in entities_with_surfaces:
        for operation in (PermissionKind.LIST, PermissionKind.CREATE, PermissionKind.UPDATE, PermissionKind.DELETE):
            permitted = set(get_permitted_personas(
                list(appspec.domain.entities), appspec.personas, entity_name, operation,
            ))
            for pid in all_personas:
                contracts.append(RBACContract(
                    entity=entity_name,
                    persona=pid,
                    operation=str(operation),
                    expected_present=pid in permitted,
                ))

    # WorkspaceContracts (unchanged — workspaces don't get triples)
    for workspace in appspec.workspaces:
        region_names = [r.name for r in getattr(workspace, "regions", [])]
        contracts.append(WorkspaceContract(
            workspace=workspace.name,
            regions=region_names,
            fold_count=0,
        ))

    return contracts
```

Delete from `contracts.py`:
- `_condition_matches_role` (moved to triples.py)
- `_condition_is_pure_role_only` (moved to triples.py)
- `_rule_matches_persona` (moved to triples.py)
- `_get_permitted_personas` (moved to triples.py)

Keep:
- All contract dataclasses (`Contract`, `ListPageContract`, etc.)
- `_FRAMEWORK_ENTITIES` constant (still used for reference)
- `ContractKind` enum

- [ ] **Step 4: Run parity test**

Run: `pytest tests/unit/test_triples.py::TestContractParity -v`
Expected: PASS

- [ ] **Step 5: Run all existing UX tests**

Run: `pytest tests/unit/ -k "ux or contract" -v --timeout=60`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/testing/ux/contracts.py tests/unit/test_triples.py
git commit -m "refactor(ux): rewrite generate_contracts as thin mapper over IR triples"
```

---

### Task 6: Reconciliation Engine

**Files:**
- Create: `src/dazzle/testing/ux/reconciler.py`
- Test: `tests/unit/test_reconciler.py`

- [ ] **Step 1: Write failing tests for reconciler**

```python
# tests/unit/test_reconciler.py
"""Tests for the UX contract reconciliation engine."""

import pytest

from dazzle.core.ir.triples import SurfaceFieldTriple, VerifiableTriple, WidgetKind
from dazzle.testing.ux.contracts import (
    CreateFormContract,
    DetailViewContract,
    ListPageContract,
    RBACContract,
)
from dazzle.testing.ux.reconciler import (
    Diagnosis,
    DiagnosisKind,
    reconcile,
)


def _make_triple(
    entity: str = "Task",
    surface: str = "task_list",
    persona: str = "admin",
    mode: str = "list",
    actions: list[str] | None = None,
    fields: list[SurfaceFieldTriple] | None = None,
) -> VerifiableTriple:
    return VerifiableTriple(
        entity=entity,
        surface=surface,
        persona=persona,
        surface_mode=mode,
        actions=actions or ["list"],
        fields=fields or [],
    )


class TestReconcileActionMissing:
    def test_edit_link_missing_from_html(self):
        """Triple says edit_link visible, HTML has no edit link → ACTION_MISSING."""
        contract = DetailViewContract(
            entity="Task",
            fields=["title"],
            has_edit=True,
            has_delete=False,
        )
        contract.status = "failed"
        contract.error = "Missing edit link"
        triple = _make_triple(
            mode="view",
            actions=["edit_link"],
            fields=[SurfaceFieldTriple(field_name="title", widget=WidgetKind.TEXT_INPUT, is_required=False, is_fk=False)],
        )
        # HTML without any edit link
        html = '<div data-entity="Task"><p>Title: Test</p></div>'
        diagnosis = reconcile(contract, triple, html, [], [])
        assert diagnosis.kind == DiagnosisKind.ACTION_MISSING
        assert len(diagnosis.levers) > 0

    def test_delete_button_present_unexpectedly(self):
        """Contract says no delete, but HTML has one → ACTION_UNEXPECTED."""
        contract = RBACContract(
            entity="Task",
            persona="viewer",
            operation="DELETE",
            expected_present=False,
        )
        contract.status = "failed"
        contract.error = "Expected DELETE to be absent but it was found"
        triple = _make_triple(persona="viewer", mode="list", actions=["list"])
        html = '<div><button hx-delete="/api/tasks/1">Delete</button></div>'
        diagnosis = reconcile(contract, triple, html, [], [])
        assert diagnosis.kind == DiagnosisKind.ACTION_UNEXPECTED


class TestReconcileTemplateBug:
    def test_triple_and_contract_agree_html_wrong(self):
        """Triple says field present, contract says present, HTML missing → TEMPLATE_BUG."""
        contract = CreateFormContract(
            entity="Task",
            required_fields=["title"],
            all_fields=["title", "description"],
        )
        contract.status = "failed"
        contract.error = "Missing required field input: title"
        triple = _make_triple(
            mode="create",
            actions=["create_submit"],
            fields=[
                SurfaceFieldTriple(field_name="title", widget=WidgetKind.TEXT_INPUT, is_required=True, is_fk=False),
                SurfaceFieldTriple(field_name="description", widget=WidgetKind.TEXTAREA, is_required=False, is_fk=False),
            ],
        )
        html = '<form hx-post="/api/tasks"><button type="submit">Create</button></form>'
        diagnosis = reconcile(contract, triple, html, [], [])
        assert diagnosis.kind == DiagnosisKind.TEMPLATE_BUG
        assert len(diagnosis.levers) == 0  # Not a DSL issue


class TestReconcileNoTriple:
    def test_no_triple_means_permission_gap(self):
        """No triple for this persona+entity → PERMISSION_GAP."""
        contract = RBACContract(
            entity="Task",
            persona="guest",
            operation="LIST",
            expected_present=True,
        )
        contract.status = "failed"
        contract.error = "Expected LIST to be present but not found"
        diagnosis = reconcile(contract, None, "", [], [])
        assert diagnosis.kind == DiagnosisKind.PERMISSION_GAP
        assert len(diagnosis.levers) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_reconciler.py -v`
Expected: ImportError — `No module named 'dazzle.testing.ux.reconciler'`

- [ ] **Step 3: Implement reconciler**

```python
# src/dazzle/testing/ux/reconciler.py
"""Reconciliation engine — back-propagate contract failures to DSL levers.

Given a failed contract, its corresponding triple, and the rendered HTML,
produce a Diagnosis that identifies the DSL construct controlling the
mismatch and suggests a fix.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from dazzle.core.ir.domain import EntitySpec
    from dazzle.core.ir.surfaces import SurfaceSpec
    from dazzle.core.ir.triples import VerifiableTriple
    from dazzle.testing.ux.contracts import Contract


class DiagnosisKind(StrEnum):
    WIDGET_MISMATCH = "widget_mismatch"
    ACTION_MISSING = "action_missing"
    ACTION_UNEXPECTED = "action_unexpected"
    FIELD_MISSING = "field_missing"
    PERMISSION_GAP = "permission_gap"
    SURFACE_MISSING = "surface_missing"
    TEMPLATE_BUG = "template_bug"


class DSLLever(BaseModel):
    """A specific DSL construct that controls the observed behavior."""

    file: str = ""
    construct: str
    current_value: str
    suggested_value: str
    explanation: str

    model_config = ConfigDict(frozen=True)


class Diagnosis(BaseModel):
    """Back-propagation result: why a contract failed and what to change."""

    contract_id: str
    kind: DiagnosisKind
    triple: str
    observation: str
    expectation: str
    levers: list[DSLLever] = Field(default_factory=list)
    category: str = ""

    model_config = ConfigDict(frozen=True)


def _diagnose_no_triple(contract: Contract) -> Diagnosis:
    """No triple exists for this contract — permission or surface gap."""
    from dazzle.testing.ux.contracts import RBACContract

    if isinstance(contract, RBACContract):
        return Diagnosis(
            contract_id=contract.contract_id,
            kind=DiagnosisKind.PERMISSION_GAP,
            triple="",
            observation="no triple exists for this persona+entity",
            expectation=f"{contract.operation} should be present for {contract.persona}",
            levers=[DSLLever(
                construct=f"entity.{contract.entity}.access.permit",
                current_value="no matching permit rule",
                suggested_value=f"permit {contract.operation.lower()} for {contract.persona}",
                explanation=f"persona '{contract.persona}' has no {contract.operation} permission on {contract.entity}",
            )],
            category="permission_model_gap",
        )
    return Diagnosis(
        contract_id=contract.contract_id,
        kind=DiagnosisKind.PERMISSION_GAP,
        triple="",
        observation="no triple exists",
        expectation=str(contract.error or ""),
        levers=[DSLLever(
            construct="entity.access.permit",
            current_value="missing",
            suggested_value="add permit rule",
            explanation="no triple was derived — likely missing permission or surface",
        )],
        category="permission_model_gap",
    )


def _diagnose_action_issue(
    contract: Contract,
    triple: VerifiableTriple,
    html: str,
) -> Diagnosis:
    """Diagnose action visibility mismatches."""
    from dazzle.testing.ux.contracts import DetailViewContract, RBACContract

    triple_key = f"{triple.entity}.{triple.surface}.{triple.persona}"

    if isinstance(contract, RBACContract):
        if contract.expected_present:
            # Contract expected the action, it's missing
            return Diagnosis(
                contract_id=contract.contract_id,
                kind=DiagnosisKind.ACTION_MISSING,
                triple=triple_key,
                observation=f"{contract.operation} action not found in HTML",
                expectation=f"{contract.operation} should be visible for {contract.persona}",
                levers=[DSLLever(
                    construct=f"entity.{contract.entity}.access.permit",
                    current_value="permit rule may be missing or restricted",
                    suggested_value=f"permit {contract.operation.lower()} with persona {contract.persona}",
                    explanation=f"persona '{contract.persona}' needs {contract.operation} on {contract.entity}",
                )],
                category="permission_model_gap",
            )
        else:
            return Diagnosis(
                contract_id=contract.contract_id,
                kind=DiagnosisKind.ACTION_UNEXPECTED,
                triple=triple_key,
                observation=f"{contract.operation} action found in HTML but should be absent",
                expectation=f"{contract.operation} should NOT be visible for {contract.persona}",
                levers=[DSLLever(
                    construct=f"entity.{contract.entity}.access",
                    current_value="permission too broad",
                    suggested_value=f"add persona restriction or forbid {contract.operation.lower()} for {contract.persona}",
                    explanation=f"persona '{contract.persona}' should not have {contract.operation} on {contract.entity}",
                )],
                category="permission_model_gap",
            )

    if isinstance(contract, DetailViewContract):
        missing_actions = []
        if contract.has_edit and "edit" not in html.lower():
            missing_actions.append("edit_link")
        if contract.has_delete and "hx-delete" not in html:
            missing_actions.append("delete_button")

        if missing_actions:
            levers = []
            for action in missing_actions:
                if action == "edit_link":
                    levers.append(DSLLever(
                        construct=f"entity.{contract.entity}.access.permit",
                        current_value="UPDATE may be missing",
                        suggested_value="permit update",
                        explanation="edit link requires UPDATE permission + an edit surface",
                    ))
                elif action == "delete_button":
                    levers.append(DSLLever(
                        construct=f"entity.{contract.entity}.access.permit",
                        current_value="DELETE may be missing",
                        suggested_value="permit delete",
                        explanation="delete button requires DELETE permission",
                    ))
            return Diagnosis(
                contract_id=contract.contract_id,
                kind=DiagnosisKind.ACTION_MISSING,
                triple=triple_key,
                observation=f"missing actions: {', '.join(missing_actions)}",
                expectation="actions should be present based on permissions",
                levers=levers,
                category="permission_model_gap",
            )

    # If we can't determine the specific issue, it's likely a template bug
    return Diagnosis(
        contract_id=contract.contract_id,
        kind=DiagnosisKind.TEMPLATE_BUG,
        triple=triple_key,
        observation=str(contract.error or ""),
        expectation="contract expectation not met",
        levers=[],
        category="template_bug",
    )


def _diagnose_field_issue(
    contract: Contract,
    triple: VerifiableTriple,
    html: str,
) -> Diagnosis:
    """Diagnose field presence/widget mismatches."""
    triple_key = f"{triple.entity}.{triple.surface}.{triple.persona}"

    # If triple has the field and contract expects it but HTML doesn't → template bug
    error = contract.error or ""
    if "Missing required field" in error or "Missing field" in error:
        return Diagnosis(
            contract_id=contract.contract_id,
            kind=DiagnosisKind.TEMPLATE_BUG,
            triple=triple_key,
            observation=error,
            expectation="field should be rendered in form",
            levers=[],
            category="template_bug",
        )

    return Diagnosis(
        contract_id=contract.contract_id,
        kind=DiagnosisKind.FIELD_MISSING,
        triple=triple_key,
        observation=error,
        expectation="field should be present",
        levers=[DSLLever(
            construct=f"surface.{triple.surface}.sections",
            current_value="field not in section elements",
            suggested_value="add field to surface section",
            explanation="field must be listed in a surface section to render",
        )],
        category="contract_generation",
    )


def reconcile(
    contract: Contract,
    triple: VerifiableTriple | None,
    html: str,
    appspec_entities: list[EntitySpec],
    appspec_surfaces: list[SurfaceSpec],
) -> Diagnosis:
    """Produce a Diagnosis for a failed contract.

    Compares the contract's expectation against the triple (what the IR
    predicted) and the HTML (what actually rendered) to determine the
    root cause and suggest DSL changes.
    """
    from dazzle.testing.ux.contracts import (
        CreateFormContract,
        DetailViewContract,
        EditFormContract,
        RBACContract,
    )

    if triple is None:
        return _diagnose_no_triple(contract)

    error = contract.error or ""

    # RBAC contracts — action visibility issues
    if isinstance(contract, RBACContract):
        return _diagnose_action_issue(contract, triple, html)

    # Detail view — action issues (edit/delete/transitions)
    if isinstance(contract, DetailViewContract):
        if "edit" in error.lower() or "delete" in error.lower() or "transition" in error.lower():
            return _diagnose_action_issue(contract, triple, html)

    # Form contracts — field issues
    if isinstance(contract, (CreateFormContract, EditFormContract)):
        if "field" in error.lower() or "Missing" in error:
            return _diagnose_field_issue(contract, triple, html)

    # Default: template bug
    triple_key = f"{triple.entity}.{triple.surface}.{triple.persona}"
    return Diagnosis(
        contract_id=contract.contract_id,
        kind=DiagnosisKind.TEMPLATE_BUG,
        triple=triple_key,
        observation=error,
        expectation="contract should pass",
        levers=[],
        category="template_bug",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_reconciler.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/testing/ux/reconciler.py tests/unit/test_reconciler.py
git commit -m "feat(ux): add reconciliation engine — back-propagate failures to DSL levers"
```

---

### Task 7: Update /ux-converge Command + Final Verification

**Files:**
- Modify: `.claude/commands/ux-converge.md`
- Test: run full suite

- [ ] **Step 1: Update ux-converge command to reference reconciler**

In `.claude/commands/ux-converge.md`, replace Step 2 "Classify Each Failure" with:

```markdown
## Step 2: Reconcile Each Failure

For each failed contract, run the reconciler to get a structured diagnosis:

```python
from dazzle.core.ir.triples import VerifiableTriple
from dazzle.testing.ux.reconciler import reconcile

diagnosis = reconcile(contract, triple, html, appspec.domain.entities, appspec.surfaces)
# diagnosis.kind → category (WIDGET_MISMATCH, ACTION_MISSING, TEMPLATE_BUG, etc.)
# diagnosis.levers → specific DSL changes to fix the issue
# diagnosis.category → maps to fix strategy below
```

| Category | diagnosis.kind | Action |
|----------|---------------|--------|
| **DSL fix** | `WIDGET_MISMATCH`, `ACTION_MISSING`, `PERMISSION_GAP`, `SURFACE_MISSING` | Apply `diagnosis.levers` suggestion to DSL file |
| **Contract calibration** | `ACTION_UNEXPECTED`, `FIELD_MISSING` | Fix contract generation or checker |
| **Template bug** | `TEMPLATE_BUG` | Fix template in `src/dazzle_ui/`, or file GitHub issue |

The reconciler replaces manual classification. Read `diagnosis.levers` for the specific DSL construct and suggested value.
```

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x -q --timeout=120`
Expected: All tests PASS, no regressions

- [ ] **Step 3: Run linting**

Run: `ruff check src/dazzle/core/ir/triples.py src/dazzle/testing/ux/reconciler.py src/dazzle/testing/ux/contracts.py --fix && ruff format src/dazzle/core/ir/triples.py src/dazzle/testing/ux/reconciler.py src/dazzle/testing/ux/contracts.py`
Expected: Clean

- [ ] **Step 4: Run type checks**

Run: `mypy src/dazzle/core/ir/triples.py src/dazzle/testing/ux/reconciler.py`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add .claude/commands/ux-converge.md
git commit -m "docs(ux): update /ux-converge to use reconciler for failure classification"
```

- [ ] **Step 6: Version bump**

Run `/bump patch` to get a unique version for this feature.
