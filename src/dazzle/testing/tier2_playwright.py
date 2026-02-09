"""
Tier 2 Playwright Test Generator.

Generates deterministic, DSL-driven Playwright test scripts using the
semantic DOM contract (data-dazzle-* attributes) for reliable element selection.

Tier 2 tests are:
- Scripted (not AI-driven)
- Use predictable selectors from DSL definitions
- Use scenarios for state setup
- Cover surface flows (create, edit, list, view modes)

DOM Contract Reference:
----------------------
Views:     data-dazzle-view="surface_name"
Entity:    data-dazzle-entity="EntityName"
Entity ID: data-dazzle-entity-id="uuid"
Fields:    data-dazzle-field="field_name"
Actions:   data-dazzle-action="Entity.action" data-dazzle-action-role="primary|secondary|destructive"
Forms:     data-dazzle-form="EntityName" data-dazzle-form-mode="create|edit"
Tables:    data-dazzle-table="EntityName"
Rows:      data-dazzle-row="row_id"
Nav:       data-dazzle-nav="target" data-dazzle-nav-target="/path"
Dialog:    data-dazzle-dialog="name" data-dazzle-dialog-open="true|false"

Auth Elements:
  data-dazzle-auth-user
  data-dazzle-auth-action="login|logout"
  data-dazzle-persona="persona_id"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dazzle.core.ir import (
    AppSpec,
    EntitySpec,
    SurfaceMode,
    SurfaceSpec,
)

# =============================================================================
# Selector Builder - The Semantic DOM Contract
# =============================================================================


class DazzleSelector:
    """
    Build Playwright selectors using the Dazzle semantic DOM contract.

    All selectors use data-dazzle-* attributes for stack-agnostic,
    deterministic element targeting.
    """

    @staticmethod
    def view(surface_name: str) -> str:
        """Select a view/surface by name."""
        return f'[data-dazzle-view="{surface_name}"]'

    @staticmethod
    def entity(entity_name: str) -> str:
        """Select elements for a specific entity."""
        return f'[data-dazzle-entity="{entity_name}"]'

    @staticmethod
    def entity_row(entity_name: str, row_id: str | None = None) -> str:
        """Select a table row for an entity."""
        if row_id:
            return f'[data-dazzle-table="{entity_name}"] [data-dazzle-row="{row_id}"]'
        return f'[data-dazzle-table="{entity_name}"] [data-dazzle-row]'

    @staticmethod
    def entity_row_any(entity_name: str) -> str:
        """Select any row in an entity table."""
        return f'[data-dazzle-table="{entity_name}"] [data-dazzle-row]'

    @staticmethod
    def entity_row_first(entity_name: str) -> str:
        """Select first row in an entity table."""
        return f'[data-dazzle-table="{entity_name}"] [data-dazzle-row]:first-child'

    @staticmethod
    def field(field_name: str, entity: str | None = None) -> str:
        """Select a form field by name.

        The field attribute format is Entity.field_name per the DOM contract.
        """
        if entity:
            return f'[data-dazzle-form="{entity}"] [data-dazzle-field="{entity}.{field_name}"]'
        return f'[data-dazzle-field="{field_name}"]'

    @staticmethod
    def action(action_name: str, entity: str | None = None) -> str:
        """Select an action button."""
        if entity:
            return f'[data-dazzle-action="{entity}.{action_name}"]'
        return f'[data-dazzle-action="{action_name}"]'

    @staticmethod
    def action_by_role(role: str) -> str:
        """Select action by role (primary, secondary, destructive)."""
        return f'[data-dazzle-action-role="{role}"]'

    @staticmethod
    def form(entity_name: str, mode: str | None = None) -> str:
        """Select a form for an entity."""
        if mode:
            return f'[data-dazzle-form="{entity_name}"][data-dazzle-form-mode="{mode}"]'
        return f'[data-dazzle-form="{entity_name}"]'

    @staticmethod
    def table(entity_name: str) -> str:
        """Select a table for an entity."""
        return f'[data-dazzle-table="{entity_name}"]'

    @staticmethod
    def nav(target: str) -> str:
        """Select a navigation element."""
        return f'[data-dazzle-nav-target="{target}"]'

    @staticmethod
    def dialog(name: str | None = None, open_state: bool | None = None) -> str:
        """Select a dialog element."""
        if name and open_state is not None:
            return f'[data-dazzle-dialog="{name}"][data-dazzle-dialog-open="{str(open_state).lower()}"]'
        if name:
            return f'[data-dazzle-dialog="{name}"]'
        return "[data-dazzle-dialog]"

    # Auth elements
    @staticmethod
    def auth_user() -> str:
        """Select the authenticated user indicator."""
        return "[data-dazzle-auth-user]"

    @staticmethod
    def auth_login() -> str:
        """Select the login button."""
        return '[data-dazzle-auth-action="login"]'

    @staticmethod
    def auth_logout() -> str:
        """Select the logout button."""
        return '[data-dazzle-auth-action="logout"]'

    @staticmethod
    def persona(persona_id: str) -> str:
        """Select element with specific persona."""
        return f'[data-dazzle-persona="{persona_id}"]'

    @staticmethod
    def scenario_select() -> str:
        """Select the scenario dropdown in the dev control plane."""
        return '[data-dazzle-control="scenario-select"]'

    @staticmethod
    def persona_select() -> str:
        """Select the persona dropdown in the dev control plane."""
        return '[data-dazzle-control="persona-select"]'


# Convenience alias
S = DazzleSelector


# =============================================================================
# Test Step Templates
# =============================================================================


@dataclass
class PlaywrightStep:
    """A single step in a Playwright test."""

    code: str
    comment: str | None = None

    def to_code(self, indent: int = 4) -> str:
        """Generate Python code for this step."""
        prefix = " " * indent
        lines = []
        if self.comment:
            lines.append(f"{prefix}# {self.comment}")
        lines.append(f"{prefix}{self.code}")
        return "\n".join(lines)


@dataclass
class PlaywrightTest:
    """A complete Playwright test case."""

    name: str
    description: str
    steps: list[PlaywrightStep] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    scenario: str | None = None  # Scenario to seed before test
    persona: str | None = None  # Persona to use (dev control plane)
    priority: str = "medium"

    def add_step(self, code: str, comment: str | None = None) -> None:
        """Add a step to the test."""
        self.steps.append(PlaywrightStep(code=code, comment=comment))


# =============================================================================
# Surface Flow Generators
# =============================================================================


def _get_sample_value_for_field(field_spec: Any, field_name: str) -> tuple[str, str] | None:
    """Generate a sample value for a field based on its type.

    Returns (value, interaction_type) where interaction_type is 'fill' or 'select'.
    """
    if field_spec is None:
        return (f"Test {field_name.replace('_', ' ').title()}", "fill")

    kind = (
        field_spec.type.kind.value
        if hasattr(field_spec.type.kind, "value")
        else str(field_spec.type.kind)
    )
    if kind == "str":
        return (f"Test {field_name.replace('_', ' ').title()}", "fill")
    elif kind == "text":
        return (f"Sample text for {field_name}", "fill")
    elif kind == "int":
        return ("42", "fill")
    elif kind == "decimal":
        return ("99.99", "fill")
    elif kind == "bool":
        # Booleans are usually checkboxes, handle specially
        return None
    elif kind == "email":
        return ("test@example.com", "fill")
    elif kind == "date":
        return ("2025-01-15", "fill")
    elif kind == "datetime":
        return ("2025-01-15T10:30", "fill")
    elif kind == "enum" and field_spec.type.enum_values:
        # Enum fields are Select elements - use select_option
        return (field_spec.type.enum_values[0], "select")
    else:
        return None


def _get_fillable_fields(entity: EntitySpec) -> list[tuple[str, str, str]]:
    """Get all entity fields that can be filled in a form.

    Returns list of (field_name, value, interaction_type).
    """
    fillable = []
    for field_spec in entity.fields:
        if field_spec.is_primary_key:
            continue
        if field_spec.name in ("created_at", "updated_at"):
            continue

        result = _get_sample_value_for_field(field_spec, field_spec.name)
        if result:
            value, interaction = result
            fillable.append((field_spec.name, value, interaction))

    return fillable


def _get_surface_fillable_fields(
    surface: SurfaceSpec, entity: EntitySpec
) -> list[tuple[str, str, str]]:
    """Get fillable fields from a surface's defined fields (not all entity fields).

    Returns list of (field_name, value, interaction_type).
    """
    # Build field lookup from entity
    field_specs = {f.name: f for f in entity.fields}

    fillable = []
    for section in surface.sections:
        for element in section.elements:
            field_name = element.field_name
            if field_name in ("id", "created_at", "updated_at"):
                continue

            field_spec = field_specs.get(field_name)
            result = _get_sample_value_for_field(field_spec, field_name)
            if result:
                value, interaction = result
                fillable.append((field_name, value, interaction))

    return fillable


def generate_create_flow(
    surface: SurfaceSpec,
    entity: EntitySpec,
    appspec: AppSpec,
) -> PlaywrightTest:
    """Generate a Playwright test for a create surface."""
    test = PlaywrightTest(
        name=f"test_{surface.name}_create",
        description=f"Create a new {entity.name} via {surface.title or surface.name}",
        tags=["tier2", "playwright", "crud", "create", entity.name.lower()],
        priority="high",
    )

    # Navigate to create surface
    route = f"/{entity.name.lower()}/create"
    test.add_step(
        f'page.goto(f"{{base_url}}{route}")',
        f"Navigate to {surface.title or surface.name}",
    )
    test.add_step('page.wait_for_load_state("networkidle")')

    # Assert form is visible
    test.add_step(
        f"expect(page.locator('{S.form(entity.name, 'create')}')).to_be_visible()",
        "Assert create form is visible",
    )

    # Fill fields from the surface (not all entity fields)
    fillable = _get_surface_fillable_fields(surface, entity)
    for field_name, value, interaction in fillable:
        selector = S.field(field_name, entity.name)
        if interaction == "select":
            test.add_step(
                f"page.locator('{selector}').select_option('{value}')",
                f"Select {value} for {field_name} field",
            )
        else:  # fill
            test.add_step(
                f"page.locator('{selector}').fill(\"{value}\")",
                f"Fill {field_name} field",
            )

    # Submit form (look for primary action or submit)
    test.add_step(
        f"page.locator('{S.action('create', entity.name)}, {S.action_by_role('primary')}').first.click()",
        "Click create/submit button",
    )
    test.add_step('page.wait_for_load_state("networkidle")')

    # Assert success - should redirect to list or show success
    test.add_step(
        f"expect(page.locator('{S.table(entity.name)}, {S.view(surface.name.replace('_create', '_list'))}')).to_be_visible(timeout=5000)",
        "Assert redirected to list or table visible",
    )

    return test


def generate_list_flow(
    surface: SurfaceSpec,
    entity: EntitySpec,
    appspec: AppSpec,
    scenario: str | None = None,
) -> PlaywrightTest:
    """Generate a Playwright test for a list surface."""
    test = PlaywrightTest(
        name=f"test_{surface.name}_list",
        description=f"View list of {entity.name} records via {surface.title or surface.name}",
        tags=["tier2", "playwright", "crud", "list", entity.name.lower()],
        scenario=scenario,
        priority="medium",
    )

    # Navigate to list surface
    route = f"/{entity.name.lower()}"
    test.add_step(
        f'page.goto(f"{{base_url}}{route}")',
        f"Navigate to {surface.title or surface.name}",
    )
    test.add_step('page.wait_for_load_state("networkidle")')

    # Assert table/list is visible
    test.add_step(
        f"expect(page.locator('{S.table(entity.name)}')).to_be_visible()",
        f"Assert {entity.name} table is visible",
    )

    # If scenario seeded data, assert rows exist
    if scenario:
        test.add_step(
            f"_expect_count_greater_than(page.locator('{S.entity_row_any(entity.name)}'), 0)",
            "Assert seeded data rows are visible",
        )

    return test


def generate_view_flow(
    surface: SurfaceSpec,
    entity: EntitySpec,
    appspec: AppSpec,
    scenario: str | None = None,
) -> PlaywrightTest:
    """Generate a Playwright test for viewing a single record."""
    test = PlaywrightTest(
        name=f"test_{surface.name}_view",
        description=f"View a single {entity.name} record via {surface.title or surface.name}",
        tags=["tier2", "playwright", "crud", "view", entity.name.lower()],
        scenario=scenario,
        priority="medium",
    )

    # First go to list
    list_route = f"/{entity.name.lower()}"
    test.add_step(
        f'page.goto(f"{{base_url}}{list_route}")',
        "Navigate to list view first",
    )
    test.add_step('page.wait_for_load_state("networkidle")')

    # Click first row to view
    test.add_step(
        f"page.locator('{S.entity_row_first(entity.name)}').click()",
        "Click first row to view details",
    )
    test.add_step('page.wait_for_load_state("networkidle")')

    # Assert view surface is visible
    test.add_step(
        f"expect(page.locator('{S.view(surface.name)}')).to_be_visible()",
        f"Assert {surface.title or surface.name} view is visible",
    )

    return test


def generate_edit_flow(
    surface: SurfaceSpec,
    entity: EntitySpec,
    appspec: AppSpec,
    scenario: str | None = None,
) -> PlaywrightTest:
    """Generate a Playwright test for editing a record."""
    test = PlaywrightTest(
        name=f"test_{surface.name}_edit",
        description=f"Edit a {entity.name} record via {surface.title or surface.name}",
        tags=["tier2", "playwright", "crud", "edit", entity.name.lower()],
        scenario=scenario,
        priority="high",
    )

    # First go to list and click first row
    list_route = f"/{entity.name.lower()}"
    test.add_step(
        f'page.goto(f"{{base_url}}{list_route}")',
        "Navigate to list view",
    )
    test.add_step('page.wait_for_load_state("networkidle")')

    # Click edit on first row
    test.add_step(
        f"page.locator('{S.entity_row_first(entity.name)} {S.action('edit', entity.name)}').click()",
        "Click edit on first row",
    )
    test.add_step('page.wait_for_load_state("networkidle")')

    # Assert edit form is visible
    test.add_step(
        f"expect(page.locator('{S.form(entity.name, 'edit')}')).to_be_visible()",
        "Assert edit form is visible",
    )

    # Modify a field
    fillable = _get_fillable_fields(entity)
    if fillable:
        field_name, _, interaction = fillable[0]
        selector = S.field(field_name, entity.name)
        if interaction == "select":
            # For select, pick a different option if available
            test.add_step(
                f"page.locator('{selector}').select_option(value=\"\")",
                f"Update {field_name} field by changing selection",
            )
        else:
            test.add_step(
                f"page.locator('{selector}').fill(\"Updated value\")",
                f"Update {field_name} field",
            )

    # Submit
    test.add_step(
        f"page.locator('{S.action('save', entity.name)}, {S.action('update', entity.name)}, {S.action_by_role('primary')}').first.click()",
        "Click save/update button",
    )
    test.add_step('page.wait_for_load_state("networkidle")')

    return test


def generate_delete_flow(
    surface: SurfaceSpec,
    entity: EntitySpec,
    appspec: AppSpec,
    scenario: str | None = None,
) -> PlaywrightTest:
    """Generate a Playwright test for deleting a record."""
    test = PlaywrightTest(
        name=f"test_{entity.name.lower()}_delete",
        description=f"Delete a {entity.name} record",
        tags=["tier2", "playwright", "crud", "delete", entity.name.lower()],
        scenario=scenario,
        priority="high",
    )

    # Navigate to list
    list_route = f"/{entity.name.lower()}"
    test.add_step(
        f'page.goto(f"{{base_url}}{list_route}")',
        "Navigate to list view",
    )
    test.add_step('page.wait_for_load_state("networkidle")')

    # Count rows before
    test.add_step(
        f"initial_count = page.locator('{S.entity_row_any(entity.name)}').count()",
        "Count rows before delete",
    )

    # Click delete on first row
    test.add_step(
        f"page.locator('{S.entity_row_first(entity.name)} {S.action('delete', entity.name)}, {S.entity_row_first(entity.name)} [data-dazzle-action-role=\"destructive\"]').first.click()",
        "Click delete on first row",
    )
    test.add_step('page.wait_for_load_state("networkidle")')

    # Confirm if dialog appears
    dialog_sel = S.dialog()
    confirm_sel = f"{S.dialog()} {S.action_by_role('destructive')}"
    confirm_code = (
        f"if page.locator('{dialog_sel}').is_visible():\n"
        f"        page.locator('{confirm_sel}').click()\n"
        "        page.wait_for_load_state('networkidle')"
    )
    test.add_step(confirm_code, "Confirm delete if dialog appears")

    # Assert row count decreased
    test.add_step(
        f"expect(page.locator('{S.entity_row_any(entity.name)}')).to_have_count(initial_count - 1)",
        "Assert row count decreased by 1",
    )

    return test


# =============================================================================
# Scenario Setup Generator
# =============================================================================


def generate_scenario_setup(scenario_id: str) -> list[PlaywrightStep]:
    """Generate steps to set up a scenario via the dev control plane."""
    steps = []

    # First navigate to app root to access the dev control plane
    steps.append(
        PlaywrightStep(
            code="page.goto(base_url)",
            comment="Navigate to app to access dev control plane",
        )
    )
    steps.append(
        PlaywrightStep(
            code='page.wait_for_load_state("networkidle")',
        )
    )

    # Select scenario via the scenario dropdown
    steps.append(
        PlaywrightStep(
            code=f"page.locator('{S.scenario_select()}').select_option('{scenario_id}')",
            comment=f"Set scenario to '{scenario_id}' via dev control plane",
        )
    )
    steps.append(
        PlaywrightStep(
            code='page.wait_for_load_state("networkidle")',
        )
    )

    return steps


def generate_persona_setup(persona_id: str) -> list[PlaywrightStep]:
    """Generate steps to set persona via the dev control plane."""
    steps = []

    steps.append(
        PlaywrightStep(
            code=f"page.locator('{S.persona_select()}').select_option('{persona_id}')",
            comment=f"Set persona to '{persona_id}' via dev control plane",
        )
    )
    steps.append(
        PlaywrightStep(
            code='page.wait_for_load_state("networkidle")',
        )
    )

    return steps


# =============================================================================
# Code Generator
# =============================================================================


def _sanitize_name(name: str) -> str:
    """Convert a name to a valid Python identifier."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", name).lower()


def generate_test_code(test: PlaywrightTest, base_url_fixture: bool = True) -> str:
    """Generate Python code for a single test."""
    marks = ["@pytest.mark.tier2"]
    if test.priority == "high":
        marks.append("@pytest.mark.high_priority")
    for tag in test.tags:
        safe_tag = _sanitize_name(tag)
        if safe_tag not in ("tier2", "high_priority"):
            marks.append(f"@pytest.mark.{safe_tag}")

    marks_str = "\n".join(marks)

    # Build steps code
    steps_code = []

    # Add scenario setup if specified
    if test.scenario:
        for step in generate_scenario_setup(test.scenario):
            steps_code.append(step.to_code())

    # Add persona setup if specified
    if test.persona:
        for step in generate_persona_setup(test.persona):
            steps_code.append(step.to_code())

    # Add test steps
    for step in test.steps:
        steps_code.append(step.to_code())

    steps_str = "\n".join(steps_code)

    fixture_params = "page: Page, base_url: str" if base_url_fixture else "page: Page"

    return f'''
{marks_str}
def {test.name}({fixture_params}) -> None:
    """
    {test.description}

    Tags: {", ".join(test.tags)}
    """
{steps_str}
'''


def generate_test_module(
    tests: list[PlaywrightTest],
    app_name: str,
) -> str:
    """Generate a complete Playwright test module."""
    test_code = "\n".join(generate_test_code(t, base_url_fixture=True) for t in tests)

    return f'''"""
Tier 2 Playwright E2E Tests for {app_name}.

Auto-generated by Dazzle tier2_playwright generator.
These tests use the semantic DOM contract (data-dazzle-* attributes)
for reliable, stack-agnostic element selection.

Usage:
    pytest tests/e2e/test_tier2_generated.py -m tier2 --base-url http://localhost:3000

With scenario seeding:
    Tests that specify a scenario will automatically seed data
    via the dev control plane before executing.

Note:
    The base_url is provided by pytest-playwright. Set via:
    - --base-url flag: pytest --base-url http://localhost:3000
    - Environment: export PLAYWRIGHT_BASE_URL=http://localhost:3000
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


# =============================================================================
# Helper: expect count greater than
# =============================================================================

def _expect_count_greater_than(locator, count: int, timeout: int = 5000):
    """Assert that a locator matches more than `count` elements."""
    import time
    start = time.time()
    while time.time() - start < timeout / 1000:
        if locator.count() > count:
            return
        time.sleep(0.1)
    raise AssertionError(f"Expected more than {{count}} elements, got {{locator.count()}}")


# Monkey-patch for convenience
expect.count_greater_than = lambda loc, n: _expect_count_greater_than(loc, n)


# =============================================================================
# Generated Tests
# =============================================================================
{test_code}
'''


# =============================================================================
# Main Generator Function
# =============================================================================


def generate_tier2_tests(
    appspec: AppSpec,
    default_scenario: str | None = None,
) -> list[PlaywrightTest]:
    """
    Generate Tier 2 Playwright tests from AppSpec.

    Args:
        appspec: The application specification
        default_scenario: Scenario to use for tests requiring data

    Returns:
        List of generated PlaywrightTest objects
    """
    tests: list[PlaywrightTest] = []

    # Build entity lookup
    entities_by_name = {e.name: e for e in appspec.domain.entities}

    # Find scenarios that seed data
    scenarios_with_data = [s.id for s in appspec.scenarios if s.demo_fixtures]
    data_scenario = default_scenario or (scenarios_with_data[0] if scenarios_with_data else None)

    # Generate tests for each surface
    for surface in appspec.surfaces:
        entity_name = surface.entity_ref
        if not entity_name or entity_name not in entities_by_name:
            continue

        entity = entities_by_name[entity_name]

        if surface.mode == SurfaceMode.CREATE:
            tests.append(generate_create_flow(surface, entity, appspec))

        elif surface.mode == SurfaceMode.LIST:
            tests.append(generate_list_flow(surface, entity, appspec, data_scenario))

        elif surface.mode == SurfaceMode.VIEW:
            tests.append(generate_view_flow(surface, entity, appspec, data_scenario))

        elif surface.mode == SurfaceMode.EDIT:
            tests.append(generate_edit_flow(surface, entity, appspec, data_scenario))

    # Generate delete test for each entity with a list surface
    seen_entities = set()
    for surface in appspec.surfaces:
        entity_name = surface.entity_ref
        if not entity_name or entity_name in seen_entities:
            continue
        if surface.mode == SurfaceMode.LIST:
            entity_or_none = entities_by_name.get(entity_name)
            if entity_or_none:
                tests.append(generate_delete_flow(surface, entity_or_none, appspec, data_scenario))
                seen_entities.add(entity_name)

    return tests


def generate_tier2_test_file(
    appspec: AppSpec,
    output_path: str | Path,
    default_scenario: str | None = None,
) -> Path:
    """
    Generate a Tier 2 Playwright test file from AppSpec.

    Args:
        appspec: The application specification
        output_path: Path for the output file
        default_scenario: Scenario to use for tests requiring data

    Returns:
        Path to the generated file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tests = generate_tier2_tests(appspec, default_scenario)
    content = generate_test_module(tests, appspec.name)
    output_path.write_text(content)

    return output_path


def generate_tier2_tests_for_app(
    app_path: str | Path,
    output_dir: str | Path | None = None,
    default_scenario: str | None = None,
) -> Path:
    """
    Generate Tier 2 tests for a DAZZLE application.

    This is the main CLI entry point. It:
    1. Parses the DSL files
    2. Generates Tier 2 Playwright tests from surfaces
    3. Writes the test file

    Args:
        app_path: Path to the DAZZLE application directory
        output_dir: Output directory for tests (default: app_path/tests/e2e)
        default_scenario: Scenario to use for state setup

    Returns:
        Path to the generated test file
    """
    from glob import glob

    from dazzle.core import build_appspec, parse_modules
    from dazzle.core.manifest import load_manifest

    app_path = Path(app_path)
    output_dir = Path(output_dir) if output_dir else app_path / "tests" / "e2e"

    # Load manifest
    manifest_path = app_path / "dazzle.toml"
    manifest = load_manifest(manifest_path)

    # Parse all DSL files
    dsl_dir = app_path / "dsl"
    dsl_files = [Path(f) for f in glob(str(dsl_dir / "**/*.dsl"), recursive=True)]
    modules = parse_modules(dsl_files)

    # Build AppSpec
    appspec = build_appspec(modules, manifest.project_root)

    # Generate test file
    test_file = output_dir / f"test_{appspec.name.lower()}_tier2.py"
    return generate_tier2_test_file(appspec, test_file, default_scenario)
