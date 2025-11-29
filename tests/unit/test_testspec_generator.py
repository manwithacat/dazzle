"""
Unit tests for the E2E TestSpec Generator.

Tests that the generator correctly produces E2ETestSpec from AppSpec.
"""

import pytest

from dazzle.core.ir import (
    AppSpec,
    DomainSpec,
    EntitySpec,
    FieldModifier,
    FieldSpec,
    FieldType,
    FieldTypeKind,
    FlowAssertionKind,
    FlowPriority,
    FlowStepKind,
    SurfaceMode,
    SurfaceSpec,
)
from dazzle.testing.testspec_generator import (
    generate_e2e_testspec,
    generate_entity_crud_flows,
    generate_entity_fixtures,
    generate_fixtures,
    generate_surface_flows,
    generate_validation_flows,
)


@pytest.fixture
def task_entity() -> EntitySpec:
    """Create a sample Task entity for testing."""
    return EntitySpec(
        name="Task",
        title="Task",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind=FieldTypeKind.STR, max_length=200),
                modifiers=[FieldModifier.REQUIRED],
            ),
            FieldSpec(
                name="description",
                type=FieldType(kind=FieldTypeKind.TEXT),
            ),
            FieldSpec(
                name="completed",
                type=FieldType(kind=FieldTypeKind.BOOL),
                default=False,
            ),
            FieldSpec(
                name="priority",
                type=FieldType(kind=FieldTypeKind.ENUM, enum_values=["low", "medium", "high"]),
            ),
            FieldSpec(
                name="due_date",
                type=FieldType(kind=FieldTypeKind.DATE),
            ),
        ],
    )


@pytest.fixture
def task_surfaces() -> list[SurfaceSpec]:
    """Create sample surfaces for Task entity."""
    return [
        SurfaceSpec(
            name="task_list",
            title="Tasks",
            entity_ref="Task",
            mode=SurfaceMode.LIST,
        ),
        SurfaceSpec(
            name="task_create",
            title="Create Task",
            entity_ref="Task",
            mode=SurfaceMode.CREATE,
        ),
        SurfaceSpec(
            name="task_edit",
            title="Edit Task",
            entity_ref="Task",
            mode=SurfaceMode.EDIT,
        ),
    ]


@pytest.fixture
def simple_appspec(task_entity: EntitySpec, task_surfaces: list[SurfaceSpec]) -> AppSpec:
    """Create a simple AppSpec for testing."""
    return AppSpec(
        name="todo",
        title="Todo App",
        version="0.1.0",
        domain=DomainSpec(entities=[task_entity]),
        surfaces=task_surfaces,
    )


class TestFixtureGeneration:
    """Tests for fixture generation."""

    def test_generate_entity_fixtures(self, task_entity: EntitySpec) -> None:
        """Test generating fixtures for an entity."""
        fixtures = generate_entity_fixtures(task_entity)

        # Should generate at least 2 fixtures (valid and updated)
        assert len(fixtures) >= 2

        # Check valid fixture
        valid = next((f for f in fixtures if f.id == "Task_valid"), None)
        assert valid is not None
        assert valid.entity == "Task"
        assert "title" in valid.data
        assert valid.data["completed"] is True  # bool defaults to True

        # Check updated fixture
        updated = next((f for f in fixtures if f.id == "Task_updated"), None)
        assert updated is not None
        assert updated.entity == "Task"

    def test_generate_fixtures_all_entities(self, simple_appspec: AppSpec) -> None:
        """Test generating fixtures for all entities in AppSpec."""
        fixtures = generate_fixtures(simple_appspec)

        # Should have fixtures for each entity
        assert len(fixtures) >= 2  # At least valid + updated for Task

        # All should be for Task entity
        for fixture in fixtures:
            assert fixture.entity == "Task"

    def test_fixture_values_match_field_types(self, task_entity: EntitySpec) -> None:
        """Test that fixture values are appropriate for field types."""
        fixtures = generate_entity_fixtures(task_entity)
        valid = next((f for f in fixtures if f.id == "Task_valid"), None)
        assert valid is not None

        # String field should have string value
        assert isinstance(valid.data["title"], str)

        # Bool field should have bool value
        assert isinstance(valid.data["completed"], bool)

        # Enum field should have valid enum value
        assert valid.data["priority"] in ["low", "medium", "high"]

        # Date field should have date string
        assert isinstance(valid.data["due_date"], str)
        assert "-" in valid.data["due_date"]  # ISO format

    def test_fixtures_skip_pk_fields(self, task_entity: EntitySpec) -> None:
        """Test that fixtures don't include PK fields."""
        fixtures = generate_entity_fixtures(task_entity)
        valid = next((f for f in fixtures if f.id == "Task_valid"), None)
        assert valid is not None

        # PK field should not be in data
        assert "id" not in valid.data


class TestCRUDFlowGeneration:
    """Tests for CRUD flow generation."""

    def test_generate_crud_flows(self, task_entity: EntitySpec, simple_appspec: AppSpec) -> None:
        """Test generating CRUD flows for an entity."""
        flows = generate_entity_crud_flows(task_entity, simple_appspec)

        # Should generate 4 flows (create, view, update, delete)
        assert len(flows) == 4

        # Check flow IDs
        flow_ids = {f.id for f in flows}
        assert "Task_create_valid" in flow_ids
        assert "Task_view_detail" in flow_ids
        assert "Task_update_valid" in flow_ids
        assert "Task_delete" in flow_ids

    def test_create_flow_structure(self, task_entity: EntitySpec, simple_appspec: AppSpec) -> None:
        """Test the structure of a create flow."""
        flows = generate_entity_crud_flows(task_entity, simple_appspec)
        create_flow = next((f for f in flows if f.id == "Task_create_valid"), None)

        assert create_flow is not None
        assert create_flow.priority == FlowPriority.HIGH
        assert create_flow.entity == "Task"
        assert create_flow.auto_generated is True
        assert "crud" in create_flow.tags
        assert "create" in create_flow.tags

        # Check steps
        steps = create_flow.steps
        assert len(steps) >= 3  # navigate, click create, at least one fill, click save, assert

        # First step should be navigate
        assert steps[0].kind == FlowStepKind.NAVIGATE
        assert "view:" in steps[0].target

        # Should have a click for create action
        create_clicks = [
            s for s in steps if s.kind == FlowStepKind.CLICK and "create" in (s.target or "")
        ]
        assert len(create_clicks) >= 1

        # Last step should be assert
        assert steps[-1].kind == FlowStepKind.ASSERT
        assert steps[-1].assertion is not None
        assert steps[-1].assertion.kind == FlowAssertionKind.ENTITY_EXISTS

    def test_update_flow_has_preconditions(
        self, task_entity: EntitySpec, simple_appspec: AppSpec
    ) -> None:
        """Test that update flow has fixture preconditions."""
        flows = generate_entity_crud_flows(task_entity, simple_appspec)
        update_flow = next((f for f in flows if f.id == "Task_update_valid"), None)

        assert update_flow is not None
        assert update_flow.preconditions is not None
        assert "Task_valid" in update_flow.preconditions.fixtures

    def test_delete_flow_has_confirmation(
        self, task_entity: EntitySpec, simple_appspec: AppSpec
    ) -> None:
        """Test that delete flow includes confirmation step."""
        flows = generate_entity_crud_flows(task_entity, simple_appspec)
        delete_flow = next((f for f in flows if f.id == "Task_delete"), None)

        assert delete_flow is not None

        # Should have confirm action click
        confirm_steps = [
            s
            for s in delete_flow.steps
            if s.kind == FlowStepKind.CLICK and "confirm" in (s.target or "")
        ]
        assert len(confirm_steps) >= 1

        # Last assertion should be entity_not_exists
        assert_steps = [s for s in delete_flow.steps if s.kind == FlowStepKind.ASSERT]
        assert len(assert_steps) >= 1
        assert assert_steps[-1].assertion.kind == FlowAssertionKind.ENTITY_NOT_EXISTS


class TestValidationFlowGeneration:
    """Tests for validation flow generation."""

    def test_generate_validation_flows(
        self, task_entity: EntitySpec, simple_appspec: AppSpec
    ) -> None:
        """Test generating validation flows for required fields."""
        flows = generate_validation_flows(task_entity, simple_appspec)

        # Should have at least one flow for the required 'title' field
        assert len(flows) >= 1

        # Find the title validation flow
        title_flow = next((f for f in flows if "title" in f.id), None)
        assert title_flow is not None
        assert title_flow.priority == FlowPriority.MEDIUM
        assert "validation" in title_flow.tags

    def test_validation_flow_asserts_error(
        self, task_entity: EntitySpec, simple_appspec: AppSpec
    ) -> None:
        """Test that validation flow asserts validation error."""
        flows = generate_validation_flows(task_entity, simple_appspec)
        title_flow = next((f for f in flows if "title" in f.id), None)

        assert title_flow is not None

        # Should assert validation error
        assert_steps = [s for s in title_flow.steps if s.kind == FlowStepKind.ASSERT]
        assert len(assert_steps) >= 1
        assert assert_steps[0].assertion.kind == FlowAssertionKind.VALIDATION_ERROR
        assert "title" in assert_steps[0].assertion.target


class TestSurfaceFlowGeneration:
    """Tests for surface navigation flow generation."""

    def test_generate_surface_flows(
        self, task_surfaces: list[SurfaceSpec], simple_appspec: AppSpec
    ) -> None:
        """Test generating navigation flows for surfaces."""
        surface = task_surfaces[0]  # task_list
        flows = generate_surface_flows(surface, simple_appspec)

        assert len(flows) >= 1

        nav_flow = flows[0]
        assert nav_flow.id == "navigate_task_list"
        assert nav_flow.priority == FlowPriority.LOW
        assert "navigation" in nav_flow.tags

    def test_surface_flow_asserts_visible(
        self, task_surfaces: list[SurfaceSpec], simple_appspec: AppSpec
    ) -> None:
        """Test that surface flow asserts visibility."""
        surface = task_surfaces[0]
        flows = generate_surface_flows(surface, simple_appspec)
        nav_flow = flows[0]

        # Last step should assert visibility
        assert_steps = [s for s in nav_flow.steps if s.kind == FlowStepKind.ASSERT]
        assert len(assert_steps) >= 1
        assert assert_steps[0].assertion.kind == FlowAssertionKind.VISIBLE


class TestFullE2ETestSpecGeneration:
    """Tests for complete E2ETestSpec generation."""

    def test_generate_complete_testspec(self, simple_appspec: AppSpec) -> None:
        """Test generating a complete E2ETestSpec."""
        testspec = generate_e2e_testspec(simple_appspec)

        assert testspec.app_name == "todo"
        assert testspec.version == "0.1.0"

        # Should have fixtures
        assert len(testspec.fixtures) >= 2

        # Should have flows (CRUD + validation + navigation)
        assert len(testspec.flows) >= 5

        # Should have usability rules
        assert len(testspec.usability_rules) >= 1

        # Should have a11y rules
        assert len(testspec.a11y_rules) >= 1

        # Should have metadata
        assert "entity_count" in testspec.metadata
        assert testspec.metadata["entity_count"] == 1

    def test_testspec_flows_have_correct_priority(self, simple_appspec: AppSpec) -> None:
        """Test that generated flows have appropriate priorities."""
        testspec = generate_e2e_testspec(simple_appspec)

        high_priority = testspec.get_flows_by_priority(FlowPriority.HIGH)
        medium_priority = testspec.get_flows_by_priority(FlowPriority.MEDIUM)
        low_priority = testspec.get_flows_by_priority(FlowPriority.LOW)

        # Create and update should be high priority
        assert len(high_priority) >= 2

        # Validation and delete should be medium
        assert len(medium_priority) >= 2

        # Navigation should be low
        assert len(low_priority) >= 1

    def test_testspec_flows_by_entity(self, simple_appspec: AppSpec) -> None:
        """Test querying flows by entity."""
        testspec = generate_e2e_testspec(simple_appspec)

        task_flows = testspec.get_flows_by_entity("Task")
        assert len(task_flows) >= 4  # At least CRUD flows

    def test_testspec_can_get_fixture(self, simple_appspec: AppSpec) -> None:
        """Test getting fixtures by ID."""
        testspec = generate_e2e_testspec(simple_appspec)

        valid_fixture = testspec.get_fixture("Task_valid")
        assert valid_fixture is not None
        assert valid_fixture.entity == "Task"

    def test_testspec_usability_rules(self, simple_appspec: AppSpec) -> None:
        """Test that usability rules are generated."""
        testspec = generate_e2e_testspec(simple_appspec)

        # Should have max steps rule
        max_steps = next(
            (r for r in testspec.usability_rules if r.id == "high_priority_max_steps"),
            None,
        )
        assert max_steps is not None
        assert max_steps.threshold == 5

    def test_testspec_a11y_rules(self, simple_appspec: AppSpec) -> None:
        """Test that a11y rules are generated."""
        testspec = generate_e2e_testspec(simple_appspec)

        # Should have color contrast rule
        contrast = next(
            (r for r in testspec.a11y_rules if r.id == "color-contrast"),
            None,
        )
        assert contrast is not None
        assert contrast.level == "AA"


class TestMultiEntityGeneration:
    """Tests for generating tests with multiple entities."""

    @pytest.fixture
    def multi_entity_appspec(self) -> AppSpec:
        """Create AppSpec with multiple entities."""
        task = EntitySpec(
            name="Task",
            title="Task",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                FieldSpec(
                    name="title",
                    type=FieldType(kind=FieldTypeKind.STR, max_length=200),
                    modifiers=[FieldModifier.REQUIRED],
                ),
            ],
        )

        user = EntitySpec(
            name="User",
            title="User",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                FieldSpec(
                    name="email",
                    type=FieldType(kind=FieldTypeKind.EMAIL),
                    modifiers=[FieldModifier.REQUIRED, FieldModifier.UNIQUE],
                ),
                FieldSpec(
                    name="name",
                    type=FieldType(kind=FieldTypeKind.STR, max_length=100),
                    modifiers=[FieldModifier.REQUIRED],
                ),
            ],
        )

        return AppSpec(
            name="multi_app",
            title="Multi Entity App",
            domain=DomainSpec(entities=[task, user]),
            surfaces=[
                SurfaceSpec(
                    name="task_list",
                    entity_ref="Task",
                    mode=SurfaceMode.LIST,
                ),
                SurfaceSpec(
                    name="user_list",
                    entity_ref="User",
                    mode=SurfaceMode.LIST,
                ),
            ],
        )

    def test_generates_fixtures_for_all_entities(self, multi_entity_appspec: AppSpec) -> None:
        """Test fixtures are generated for all entities."""
        testspec = generate_e2e_testspec(multi_entity_appspec)

        # Should have fixtures for both entities
        task_fixtures = [f for f in testspec.fixtures if f.entity == "Task"]
        user_fixtures = [f for f in testspec.fixtures if f.entity == "User"]

        assert len(task_fixtures) >= 2
        assert len(user_fixtures) >= 2

    def test_generates_flows_for_all_entities(self, multi_entity_appspec: AppSpec) -> None:
        """Test flows are generated for all entities."""
        testspec = generate_e2e_testspec(multi_entity_appspec)

        task_flows = testspec.get_flows_by_entity("Task")
        user_flows = testspec.get_flows_by_entity("User")

        assert len(task_flows) >= 4  # CRUD flows
        assert len(user_flows) >= 4  # CRUD flows

    def test_metadata_reflects_entity_count(self, multi_entity_appspec: AppSpec) -> None:
        """Test metadata has correct entity count."""
        testspec = generate_e2e_testspec(multi_entity_appspec)

        assert testspec.metadata["entity_count"] == 2
        assert testspec.metadata["surface_count"] == 2
