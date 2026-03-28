"""Tests for component relevance rules."""

from dazzle.core.discovery.component_rules import check_component_relevance
from dazzle.core.ir.domain import EntitySpec
from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle.core.ir.workspaces import DisplayMode, WorkspaceRegion, WorkspaceSpec

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_surface(name: str) -> SurfaceSpec:
    return SurfaceSpec(name=name, mode=SurfaceMode.LIST)


def _make_entity_with_enum_status(name: str) -> EntitySpec:
    status_field = FieldSpec(
        name="status",
        type=FieldType(
            kind=FieldTypeKind.ENUM,
            enum_values=["active", "inactive", "pending"],
        ),
    )
    return EntitySpec(name=name, fields=[status_field])


def _make_entity_no_status(name: str) -> EntitySpec:
    title_field = FieldSpec(
        name="title",
        type=FieldType(kind=FieldTypeKind.STR, max_length=200),
    )
    return EntitySpec(name=name, fields=[title_field])


def _make_grid_workspace(name: str, source: str) -> WorkspaceSpec:
    region = WorkspaceRegion(name="main", source=source, display=DisplayMode.GRID)
    return WorkspaceSpec(name=name, regions=[region])


# ---------------------------------------------------------------------------
# Rule 1: dzCommandPalette — app with 5+ surfaces, no command_palette fragment
# ---------------------------------------------------------------------------


def test_command_palette_triggered_with_six_surfaces() -> None:
    """6 surfaces with no command_palette fragment → dzCommandPalette relevance."""
    surfaces = [_make_surface(f"s{i}") for i in range(6)]
    results = check_component_relevance(entities=[], surfaces=surfaces, workspaces=[])
    kg_entities = [r.kg_entity for r in results]
    assert "capability:component_command_palette" in kg_entities
    match = next(r for r in results if r.kg_entity == "capability:component_command_palette")
    assert match.category == "component"
    assert match.examples == []
    assert "dzCommandPalette" in match.capability


def test_command_palette_not_triggered_with_three_surfaces() -> None:
    """3 surfaces → no command palette relevance (below threshold of 5)."""
    surfaces = [_make_surface(f"s{i}") for i in range(3)]
    results = check_component_relevance(entities=[], surfaces=surfaces, workspaces=[])
    kg_entities = [r.kg_entity for r in results]
    assert "capability:component_command_palette" not in kg_entities


def test_command_palette_not_triggered_when_fragment_present() -> None:
    """6 surfaces WITH command_palette fragment → no relevance."""
    surfaces = [_make_surface(f"s{i}") for i in range(6)]
    results = check_component_relevance(
        entities=[],
        surfaces=surfaces,
        workspaces=[],
        fragments=["command_palette"],
    )
    kg_entities = [r.kg_entity for r in results]
    assert "capability:component_command_palette" not in kg_entities


def test_command_palette_exactly_five_surfaces() -> None:
    """Exactly 5 surfaces (boundary) → command palette relevance triggered."""
    surfaces = [_make_surface(f"s{i}") for i in range(5)]
    results = check_component_relevance(entities=[], surfaces=surfaces, workspaces=[])
    kg_entities = [r.kg_entity for r in results]
    assert "capability:component_command_palette" in kg_entities


# ---------------------------------------------------------------------------
# Rule 2: Toggle group — entity with enum status field + grid workspace display
# ---------------------------------------------------------------------------


def test_toggle_group_triggered_for_enum_status_with_grid() -> None:
    """Entity with enum status field + grid workspace region → toggle group relevance."""
    entity = _make_entity_with_enum_status("Task")
    workspace = _make_grid_workspace("task_ws", source="Task")
    results = check_component_relevance(
        entities=[entity],
        surfaces=[],
        workspaces=[workspace],
    )
    kg_entities = [r.kg_entity for r in results]
    assert "capability:component_toggle_group" in kg_entities
    match = next(r for r in results if r.kg_entity == "capability:component_toggle_group")
    assert match.category == "component"
    assert match.examples == []
    assert "toggle group" in match.capability.lower()


def test_toggle_group_not_triggered_for_non_status_enum() -> None:
    """Entity with an enum field that does NOT have 'status' in the name → no toggle group."""
    priority_field = FieldSpec(
        name="priority",
        type=FieldType(
            kind=FieldTypeKind.ENUM,
            enum_values=["low", "medium", "high"],
        ),
    )
    entity = EntitySpec(name="Task", fields=[priority_field])
    workspace = _make_grid_workspace("task_ws", source="Task")
    results = check_component_relevance(
        entities=[entity],
        surfaces=[],
        workspaces=[workspace],
    )
    kg_entities = [r.kg_entity for r in results]
    assert "capability:component_toggle_group" not in kg_entities


def test_toggle_group_not_triggered_for_list_display() -> None:
    """Entity with enum status but workspace region uses LIST (not GRID) → no toggle group."""
    entity = _make_entity_with_enum_status("Task")
    region = WorkspaceRegion(name="main", source="Task", display=DisplayMode.LIST)
    workspace = WorkspaceSpec(name="task_ws", regions=[region])
    results = check_component_relevance(
        entities=[entity],
        surfaces=[],
        workspaces=[workspace],
    )
    kg_entities = [r.kg_entity for r in results]
    assert "capability:component_toggle_group" not in kg_entities


def test_toggle_group_not_triggered_when_entity_has_no_enum_status() -> None:
    """Entity with no enum status field + grid workspace → no toggle group."""
    entity = _make_entity_no_status("Task")
    workspace = _make_grid_workspace("task_ws", source="Task")
    results = check_component_relevance(
        entities=[entity],
        surfaces=[],
        workspaces=[workspace],
    )
    kg_entities = [r.kg_entity for r in results]
    assert "capability:component_toggle_group" not in kg_entities


def test_toggle_group_triggered_when_status_field_name_contains_status() -> None:
    """Field named 'task_status' (contains 'status') → toggle group triggered."""
    status_field = FieldSpec(
        name="task_status",
        type=FieldType(
            kind=FieldTypeKind.ENUM,
            enum_values=["open", "closed"],
        ),
    )
    entity = EntitySpec(name="Task", fields=[status_field])
    workspace = _make_grid_workspace("task_ws", source="Task")
    results = check_component_relevance(
        entities=[entity],
        surfaces=[],
        workspaces=[workspace],
    )
    kg_entities = [r.kg_entity for r in results]
    assert "capability:component_toggle_group" in kg_entities


def test_empty_inputs_return_empty_list() -> None:
    """No entities, surfaces, or workspaces → empty results."""
    results = check_component_relevance(entities=[], surfaces=[], workspaces=[])
    assert results == []


def test_fragments_none_default_does_not_suppress_palette() -> None:
    """When fragments is None (default), command palette rule still fires."""
    surfaces = [_make_surface(f"s{i}") for i in range(5)]
    results = check_component_relevance(entities=[], surfaces=surfaces, workspaces=[])
    kg_entities = [r.kg_entity for r in results]
    assert "capability:component_command_palette" in kg_entities
