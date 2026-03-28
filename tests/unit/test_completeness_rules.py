"""Tests for CRUD completeness relevance rules."""

from dazzle.core.discovery.completeness_rules import check_completeness_relevance
from dazzle.core.ir.domain import AccessSpec, EntitySpec, PermissionKind, PermissionRule
from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _str_field(name: str = "title") -> FieldSpec:
    return FieldSpec(name=name, type=FieldType(kind=FieldTypeKind.STR, max_length=200))


def _permit(op: PermissionKind) -> PermissionRule:
    return PermissionRule(operation=op)


def _make_entity(name: str, ops: list[PermissionKind]) -> EntitySpec:
    access = AccessSpec(permissions=[_permit(op) for op in ops])
    return EntitySpec(name=name, fields=[_str_field()], access=access)


def _make_entity_no_access(name: str) -> EntitySpec:
    return EntitySpec(name=name, fields=[_str_field()])


def _make_surface(name: str, entity_ref: str, mode: SurfaceMode) -> SurfaceSpec:
    return SurfaceSpec(name=name, entity_ref=entity_ref, mode=mode)


# ---------------------------------------------------------------------------
# Rule: missing edit surface
# ---------------------------------------------------------------------------


def test_update_permit_no_edit_surface_produces_edit_relevance() -> None:
    """Entity with update permit but no edit surface → edit surface relevance."""
    entity = _make_entity("Task", [PermissionKind.UPDATE])
    # Provide a list surface for the entity (not an edit surface)
    surface = _make_surface("task_list", "Task", SurfaceMode.LIST)
    results = check_completeness_relevance(entities=[entity], surfaces=[surface])
    kg_entities = [r.kg_entity for r in results]
    assert "capability:completeness_missing_edit" in kg_entities
    match = next(r for r in results if r.kg_entity == "capability:completeness_missing_edit")
    assert match.category == "completeness"
    assert match.examples == []
    assert "edit" in match.capability.lower()
    assert "Task" in match.context
    assert "update" in match.context


def test_update_permit_with_edit_surface_no_relevance() -> None:
    """Entity with update permit AND an edit surface → no edit relevance."""
    entity = _make_entity("Task", [PermissionKind.UPDATE])
    surface = _make_surface("task_edit", "Task", SurfaceMode.EDIT)
    results = check_completeness_relevance(entities=[entity], surfaces=[surface])
    kg_entities = [r.kg_entity for r in results]
    assert "capability:completeness_missing_edit" not in kg_entities


# ---------------------------------------------------------------------------
# Rule: missing list surface
# ---------------------------------------------------------------------------


def test_list_permit_no_list_surface_produces_list_relevance() -> None:
    """Entity with list permit but no list surface → list surface relevance."""
    entity = _make_entity("Task", [PermissionKind.LIST])
    # Provide a view surface for the entity (not a list surface)
    surface = _make_surface("task_view", "Task", SurfaceMode.VIEW)
    results = check_completeness_relevance(entities=[entity], surfaces=[surface])
    kg_entities = [r.kg_entity for r in results]
    assert "capability:completeness_missing_list" in kg_entities
    match = next(r for r in results if r.kg_entity == "capability:completeness_missing_list")
    assert match.category == "completeness"
    assert match.examples == []
    assert "list" in match.capability.lower()
    assert "Task" in match.context


def test_list_permit_with_list_surface_no_relevance() -> None:
    """Entity with list permit AND a list surface → no list relevance."""
    entity = _make_entity("Task", [PermissionKind.LIST])
    surface = _make_surface("task_list", "Task", SurfaceMode.LIST)
    results = check_completeness_relevance(entities=[entity], surfaces=[surface])
    kg_entities = [r.kg_entity for r in results]
    assert "capability:completeness_missing_list" not in kg_entities


# ---------------------------------------------------------------------------
# Rule: missing create surface
# ---------------------------------------------------------------------------


def test_create_permit_no_create_surface_produces_create_relevance() -> None:
    """Entity with create permit but no create surface → create surface relevance."""
    entity = _make_entity("Task", [PermissionKind.CREATE])
    surface = _make_surface("task_list", "Task", SurfaceMode.LIST)
    results = check_completeness_relevance(entities=[entity], surfaces=[surface])
    kg_entities = [r.kg_entity for r in results]
    assert "capability:completeness_missing_create" in kg_entities
    match = next(r for r in results if r.kg_entity == "capability:completeness_missing_create")
    assert match.category == "completeness"
    assert match.examples == []
    assert "create" in match.capability.lower()


def test_create_permit_with_create_surface_no_relevance() -> None:
    """Entity with create permit AND a create surface → no create relevance."""
    entity = _make_entity("Task", [PermissionKind.CREATE])
    surface = _make_surface("task_create", "Task", SurfaceMode.CREATE)
    results = check_completeness_relevance(entities=[entity], surfaces=[surface])
    kg_entities = [r.kg_entity for r in results]
    assert "capability:completeness_missing_create" not in kg_entities


# ---------------------------------------------------------------------------
# Rule: unreachable entity (permissions but no surfaces at all)
# ---------------------------------------------------------------------------


def test_entity_with_permissions_and_no_surfaces_is_unreachable() -> None:
    """Entity with permissions but no surfaces at all → unreachable relevance."""
    entity = _make_entity("Task", [PermissionKind.READ, PermissionKind.UPDATE])
    results = check_completeness_relevance(entities=[entity], surfaces=[])
    kg_entities = [r.kg_entity for r in results]
    assert "capability:completeness_unreachable" in kg_entities
    match = next(r for r in results if r.kg_entity == "capability:completeness_unreachable")
    assert match.category == "completeness"
    assert match.examples == []
    assert "Task" in match.context


def test_entity_with_permissions_and_surfaces_for_other_entity_is_unreachable() -> None:
    """Surfaces for a different entity don't count — own entity is still unreachable."""
    entity = _make_entity("Task", [PermissionKind.LIST])
    surface = _make_surface("other_list", "Project", SurfaceMode.LIST)
    results = check_completeness_relevance(entities=[entity], surfaces=[surface])
    kg_entities = [r.kg_entity for r in results]
    assert "capability:completeness_unreachable" in kg_entities


def test_entity_with_surfaces_but_no_entity_ref_is_unreachable() -> None:
    """Surface with entity_ref=None doesn't satisfy the entity's surface requirement."""
    entity = _make_entity("Task", [PermissionKind.LIST])
    surface = SurfaceSpec(name="orphan_list", entity_ref=None, mode=SurfaceMode.LIST)
    results = check_completeness_relevance(entities=[entity], surfaces=[surface])
    kg_entities = [r.kg_entity for r in results]
    assert "capability:completeness_unreachable" in kg_entities


# ---------------------------------------------------------------------------
# Rule: entity with all matching surfaces — no relevance
# ---------------------------------------------------------------------------


def test_entity_with_all_surfaces_matching_produces_no_relevance() -> None:
    """Entity with create/update/list permits and all three matching surfaces → no relevance."""
    entity = _make_entity(
        "Task",
        [PermissionKind.CREATE, PermissionKind.UPDATE, PermissionKind.LIST],
    )
    surfaces = [
        _make_surface("task_create", "Task", SurfaceMode.CREATE),
        _make_surface("task_edit", "Task", SurfaceMode.EDIT),
        _make_surface("task_list", "Task", SurfaceMode.LIST),
    ]
    results = check_completeness_relevance(entities=[entity], surfaces=surfaces)
    assert results == []


def test_entity_without_access_spec_produces_no_relevance() -> None:
    """Entity with no access spec → no relevance (no declared permissions)."""
    entity = _make_entity_no_access("Task")
    results = check_completeness_relevance(entities=[entity], surfaces=[])
    assert results == []


def test_entity_with_empty_permissions_produces_no_relevance() -> None:
    """Entity with an AccessSpec but empty permissions list → no relevance."""
    access = AccessSpec(permissions=[])
    entity = EntitySpec(name="Task", fields=[_str_field()], access=access)
    results = check_completeness_relevance(entities=[entity], surfaces=[])
    assert results == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_inputs_return_empty_list() -> None:
    """No entities or surfaces → empty results."""
    results = check_completeness_relevance(entities=[], surfaces=[])
    assert results == []


def test_read_and_delete_permits_alone_produce_no_mode_gaps() -> None:
    """READ and DELETE permissions have no mapped surface mode → no mode-gap relevance."""
    entity = _make_entity("Task", [PermissionKind.READ, PermissionKind.DELETE])
    # Provide a surface so it's not flagged as unreachable
    surface = _make_surface("task_view", "Task", SurfaceMode.VIEW)
    results = check_completeness_relevance(entities=[entity], surfaces=[surface])
    kg_entities = [r.kg_entity for r in results]
    assert "capability:completeness_missing_edit" not in kg_entities
    assert "capability:completeness_missing_list" not in kg_entities
    assert "capability:completeness_missing_create" not in kg_entities


def test_multiple_entities_with_gaps() -> None:
    """Two entities each with a different missing surface mode → two relevance items."""
    entity_a = _make_entity("Task", [PermissionKind.UPDATE])
    entity_b = _make_entity("Project", [PermissionKind.LIST])
    surface_a = _make_surface("task_list", "Task", SurfaceMode.LIST)
    surface_b = _make_surface("project_view", "Project", SurfaceMode.VIEW)
    results = check_completeness_relevance(
        entities=[entity_a, entity_b], surfaces=[surface_a, surface_b]
    )
    kg_entities = [r.kg_entity for r in results]
    assert "capability:completeness_missing_edit" in kg_entities
    assert "capability:completeness_missing_list" in kg_entities
