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
from dazzle.core.ir.computed import (
    AggregateCall,
    AggregateFunction,
    ComputedFieldSpec,
    FieldReference,
)
from dazzle.core.ir.domain import AccessSpec, PermissionKind, PermissionRule
from dazzle.core.ir.state_machine import StateMachineSpec, StateTransition
from dazzle.testing.testspec_generator import (
    generate_access_control_flows,
    generate_computed_field_flows,
    generate_e2e_testspec,
    generate_entity_crud_flows,
    generate_entity_fixtures,
    generate_fixtures,
    generate_reference_flows,
    generate_state_machine_flows,
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
            name="task_detail",
            title="Task Detail",
            entity_ref="Task",
            mode=SurfaceMode.VIEW,
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


# =============================================================================
# v0.13.0 Generator Tests
# =============================================================================


class TestStateMachineFlowGeneration:
    """Tests for state machine transition flow generation."""

    @pytest.fixture
    def ticket_entity_with_state_machine(self) -> EntitySpec:
        """Create a Ticket entity with state machine for testing."""
        return EntitySpec(
            name="Ticket",
            title="Support Ticket",
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
                    name="status",
                    type=FieldType(
                        kind=FieldTypeKind.ENUM,
                        enum_values=["open", "in_progress", "resolved", "closed"],
                    ),
                ),
            ],
            state_machine=StateMachineSpec(
                status_field="status",
                states=["open", "in_progress", "resolved", "closed"],
                transitions=[
                    StateTransition(from_state="open", to_state="in_progress"),
                    StateTransition(from_state="in_progress", to_state="resolved"),
                    StateTransition(from_state="resolved", to_state="closed"),
                ],
            ),
        )

    @pytest.fixture
    def ticket_appspec(self, ticket_entity_with_state_machine: EntitySpec) -> AppSpec:
        """Create AppSpec with ticket entity."""
        return AppSpec(
            name="support",
            title="Support App",
            domain=DomainSpec(entities=[ticket_entity_with_state_machine]),
            surfaces=[
                SurfaceSpec(
                    name="ticket_list",
                    entity_ref="Ticket",
                    mode=SurfaceMode.LIST,
                ),
            ],
        )

    def test_generate_valid_transition_flows(
        self, ticket_entity_with_state_machine: EntitySpec, ticket_appspec: AppSpec
    ) -> None:
        """Test generating flows for valid state transitions."""
        flows = generate_state_machine_flows(ticket_entity_with_state_machine, ticket_appspec)

        # Should have flows for valid transitions (3) and some invalid (varies)
        assert len(flows) >= 3

        # Check for valid transition flow (ID format: Ticket_transition_open_to_in_progress)
        valid_flow = next(
            (
                f
                for f in flows
                if "transition_open_to_in_progress" in f.id and "invalid" not in f.id
            ),
            None,
        )
        assert valid_flow is not None
        assert valid_flow.entity == "Ticket"
        assert "state_machine" in valid_flow.tags
        assert "transition" in valid_flow.tags

    def test_generate_invalid_transition_flows(
        self, ticket_entity_with_state_machine: EntitySpec, ticket_appspec: AppSpec
    ) -> None:
        """Test generating flows for invalid state transitions."""
        flows = generate_state_machine_flows(ticket_entity_with_state_machine, ticket_appspec)

        # Check for invalid transition flow
        invalid_flows = [f for f in flows if "transition_invalid" in f.id]
        assert len(invalid_flows) >= 1

        invalid_flow = invalid_flows[0]
        assert "invalid_transition" in invalid_flow.tags

        # Should assert transition was blocked
        assert_steps = [s for s in invalid_flow.steps if s.kind == FlowStepKind.ASSERT]
        assert len(assert_steps) >= 1
        assert assert_steps[0].assertion.kind == FlowAssertionKind.STATE_TRANSITION_BLOCKED

    def test_no_flows_for_entity_without_state_machine(
        self, task_entity: EntitySpec, simple_appspec: AppSpec
    ) -> None:
        """Test that no flows are generated for entity without state machine."""
        flows = generate_state_machine_flows(task_entity, simple_appspec)
        assert flows == []


class TestComputedFieldFlowGeneration:
    """Tests for computed field verification flow generation."""

    @pytest.fixture
    def invoice_entity_with_computed(self) -> EntitySpec:
        """Create an Invoice entity with computed fields for testing."""
        return EntitySpec(
            name="Invoice",
            title="Invoice",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                FieldSpec(
                    name="number",
                    type=FieldType(kind=FieldTypeKind.STR, max_length=50),
                    modifiers=[FieldModifier.REQUIRED],
                ),
            ],
            computed_fields=[
                ComputedFieldSpec(
                    name="item_count",
                    expression=AggregateCall(
                        function=AggregateFunction.COUNT,
                        field=FieldReference(path=["line_items"]),
                    ),
                ),
                ComputedFieldSpec(
                    name="total",
                    expression=AggregateCall(
                        function=AggregateFunction.SUM,
                        field=FieldReference(path=["line_items", "amount"]),
                    ),
                ),
            ],
        )

    @pytest.fixture
    def invoice_appspec(self, invoice_entity_with_computed: EntitySpec) -> AppSpec:
        """Create AppSpec with invoice entity."""
        return AppSpec(
            name="billing",
            title="Billing App",
            domain=DomainSpec(entities=[invoice_entity_with_computed]),
            surfaces=[
                SurfaceSpec(
                    name="invoice_list",
                    entity_ref="Invoice",
                    mode=SurfaceMode.LIST,
                ),
            ],
        )

    def test_generate_computed_field_flows(
        self, invoice_entity_with_computed: EntitySpec, invoice_appspec: AppSpec
    ) -> None:
        """Test generating flows for computed fields."""
        flows = generate_computed_field_flows(invoice_entity_with_computed, invoice_appspec)

        # Should have one flow per computed field
        assert len(flows) == 2

        # Check for item_count flow
        item_count_flow = next((f for f in flows if "item_count" in f.id), None)
        assert item_count_flow is not None
        assert item_count_flow.entity == "Invoice"
        assert "computed" in item_count_flow.tags

        # Check for total flow
        total_flow = next((f for f in flows if "total" in f.id), None)
        assert total_flow is not None

    def test_computed_field_flow_asserts_value(
        self, invoice_entity_with_computed: EntitySpec, invoice_appspec: AppSpec
    ) -> None:
        """Test that computed field flow asserts the computed value."""
        flows = generate_computed_field_flows(invoice_entity_with_computed, invoice_appspec)
        flow = flows[0]

        # Should have assertion for computed value
        assert_steps = [s for s in flow.steps if s.kind == FlowStepKind.ASSERT]
        assert len(assert_steps) >= 1

        computed_value_assert = next(
            (s for s in assert_steps if s.assertion.kind == FlowAssertionKind.COMPUTED_VALUE),
            None,
        )
        assert computed_value_assert is not None

    def test_no_flows_for_entity_without_computed(
        self, task_entity: EntitySpec, simple_appspec: AppSpec
    ) -> None:
        """Test that no flows are generated for entity without computed fields."""
        flows = generate_computed_field_flows(task_entity, simple_appspec)
        assert flows == []


class TestAccessControlFlowGeneration:
    """Tests for access control flow generation."""

    @pytest.fixture
    def document_entity_with_access(self) -> EntitySpec:
        """Create a Document entity with access rules for testing."""
        return EntitySpec(
            name="Document",
            title="Document",
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
            access=AccessSpec(
                permissions=[
                    PermissionRule(operation=PermissionKind.CREATE, require_auth=True),
                    PermissionRule(operation=PermissionKind.UPDATE, require_auth=True),
                    PermissionRule(operation=PermissionKind.DELETE, require_auth=True),
                ],
            ),
        )

    @pytest.fixture
    def document_appspec(self, document_entity_with_access: EntitySpec) -> AppSpec:
        """Create AppSpec with document entity."""
        return AppSpec(
            name="docs",
            title="Document App",
            domain=DomainSpec(entities=[document_entity_with_access]),
            surfaces=[
                SurfaceSpec(
                    name="document_list",
                    entity_ref="Document",
                    mode=SurfaceMode.LIST,
                ),
            ],
        )

    def test_generate_access_control_flows(
        self, document_entity_with_access: EntitySpec, document_appspec: AppSpec
    ) -> None:
        """Test generating access control flows."""
        flows = generate_access_control_flows(document_entity_with_access, document_appspec)

        # Should have flows for allowed and denied for each permission
        assert len(flows) >= 3  # At least one pair per operation

        # Check for allowed flows
        allowed_flows = [f for f in flows if "_allowed" in f.id]
        assert len(allowed_flows) >= 1

        # Check for denied flows (anonymous user)
        denied_flows = [f for f in flows if "_denied" in f.id]
        assert len(denied_flows) >= 1

    def test_access_allowed_flow_structure(
        self, document_entity_with_access: EntitySpec, document_appspec: AppSpec
    ) -> None:
        """Test structure of access allowed flows."""
        flows = generate_access_control_flows(document_entity_with_access, document_appspec)
        allowed_flow = next((f for f in flows if "create_allowed" in f.id), None)

        assert allowed_flow is not None
        assert allowed_flow.priority == FlowPriority.HIGH
        assert allowed_flow.preconditions is not None
        assert allowed_flow.preconditions.authenticated is True
        assert "access_control" in allowed_flow.tags

        # Should assert permission granted
        assert_steps = [s for s in allowed_flow.steps if s.kind == FlowStepKind.ASSERT]
        assert len(assert_steps) >= 1
        assert assert_steps[0].assertion.kind == FlowAssertionKind.PERMISSION_GRANTED

    def test_access_denied_flow_structure(
        self, document_entity_with_access: EntitySpec, document_appspec: AppSpec
    ) -> None:
        """Test structure of access denied flows."""
        flows = generate_access_control_flows(document_entity_with_access, document_appspec)
        denied_flow = next((f for f in flows if "_denied_anon" in f.id), None)

        assert denied_flow is not None
        assert denied_flow.preconditions is not None
        assert denied_flow.preconditions.authenticated is False
        assert "denied" in denied_flow.tags

        # Should assert permission denied
        assert_steps = [s for s in denied_flow.steps if s.kind == FlowStepKind.ASSERT]
        assert len(assert_steps) >= 1
        assert assert_steps[0].assertion.kind == FlowAssertionKind.PERMISSION_DENIED

    def test_no_flows_for_entity_without_access(
        self, task_entity: EntitySpec, simple_appspec: AppSpec
    ) -> None:
        """Test that no flows are generated for entity without access rules."""
        flows = generate_access_control_flows(task_entity, simple_appspec)
        assert flows == []


class TestReferenceFlowGeneration:
    """Tests for reference integrity flow generation."""

    @pytest.fixture
    def task_entity_with_ref(self) -> EntitySpec:
        """Create a Task entity with a ref field for testing."""
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
                    name="project_id",
                    type=FieldType(kind=FieldTypeKind.REF, ref_entity="Project"),
                    modifiers=[FieldModifier.REQUIRED],
                ),
            ],
        )

    @pytest.fixture
    def project_entity(self) -> EntitySpec:
        """Create a Project entity for ref target."""
        return EntitySpec(
            name="Project",
            title="Project",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                FieldSpec(
                    name="name",
                    type=FieldType(kind=FieldTypeKind.STR, max_length=200),
                    modifiers=[FieldModifier.REQUIRED],
                ),
            ],
        )

    @pytest.fixture
    def task_ref_appspec(
        self, task_entity_with_ref: EntitySpec, project_entity: EntitySpec
    ) -> AppSpec:
        """Create AppSpec with task and project entities."""
        return AppSpec(
            name="projects",
            title="Project Management",
            domain=DomainSpec(entities=[task_entity_with_ref, project_entity]),
            surfaces=[
                SurfaceSpec(
                    name="task_list",
                    entity_ref="Task",
                    mode=SurfaceMode.LIST,
                ),
                SurfaceSpec(
                    name="task_create",
                    entity_ref="Task",
                    mode=SurfaceMode.CREATE,
                ),
            ],
        )

    def test_generate_reference_flows(
        self, task_entity_with_ref: EntitySpec, task_ref_appspec: AppSpec
    ) -> None:
        """Test generating reference integrity flows."""
        flows = generate_reference_flows(task_entity_with_ref, task_ref_appspec)

        # Should have valid and invalid ref flows
        assert len(flows) == 2

        # Check for valid ref flow
        valid_flow = next((f for f in flows if "_valid" in f.id), None)
        assert valid_flow is not None
        assert valid_flow.entity == "Task"
        assert "reference" in valid_flow.tags
        assert "valid" in valid_flow.tags

        # Check for invalid ref flow
        invalid_flow = next((f for f in flows if "_invalid" in f.id), None)
        assert invalid_flow is not None
        assert "invalid" in invalid_flow.tags

    def test_valid_ref_flow_uses_fixture(
        self, task_entity_with_ref: EntitySpec, task_ref_appspec: AppSpec
    ) -> None:
        """Test that valid ref flow uses fixture reference."""
        flows = generate_reference_flows(task_entity_with_ref, task_ref_appspec)
        valid_flow = next((f for f in flows if "_valid" in f.id), None)

        assert valid_flow is not None
        assert valid_flow.priority == FlowPriority.HIGH
        assert valid_flow.preconditions is not None

        # Should reference the Project fixture
        assert "Project_valid" in valid_flow.preconditions.fixtures

        # Should have fixture_ref in fill step
        fill_steps = [s for s in valid_flow.steps if s.kind == FlowStepKind.FILL and s.fixture_ref]
        assert len(fill_steps) >= 1

        # Should assert ref is valid
        assert_steps = [s for s in valid_flow.steps if s.kind == FlowStepKind.ASSERT]
        ref_valid_assert = next(
            (s for s in assert_steps if s.assertion.kind == FlowAssertionKind.REF_VALID),
            None,
        )
        assert ref_valid_assert is not None

    def test_invalid_ref_flow_uses_fake_uuid(
        self, task_entity_with_ref: EntitySpec, task_ref_appspec: AppSpec
    ) -> None:
        """Test that invalid ref flow uses non-existent UUID."""
        flows = generate_reference_flows(task_entity_with_ref, task_ref_appspec)
        invalid_flow = next((f for f in flows if "_invalid" in f.id), None)

        assert invalid_flow is not None
        assert invalid_flow.priority == FlowPriority.MEDIUM

        # Should have fill step with fake UUID value
        fill_steps = [
            s
            for s in invalid_flow.steps
            if s.kind == FlowStepKind.FILL and s.value and "00000000" in s.value
        ]
        assert len(fill_steps) >= 1

        # Should assert ref is invalid
        assert_steps = [s for s in invalid_flow.steps if s.kind == FlowStepKind.ASSERT]
        ref_invalid_assert = next(
            (s for s in assert_steps if s.assertion.kind == FlowAssertionKind.REF_INVALID),
            None,
        )
        assert ref_invalid_assert is not None

    def test_no_flows_for_entity_without_refs(
        self, task_entity: EntitySpec, simple_appspec: AppSpec
    ) -> None:
        """Test that no flows are generated for entity without ref fields."""
        flows = generate_reference_flows(task_entity, simple_appspec)
        assert flows == []


class TestE2ETestSpecWithV013Features:
    """Tests for E2ETestSpec generation with v0.13.0 features."""

    @pytest.fixture
    def full_featured_appspec(self) -> AppSpec:
        """Create AppSpec with all v0.13.0 features."""
        ticket = EntitySpec(
            name="Ticket",
            title="Ticket",
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
                    name="status",
                    type=FieldType(
                        kind=FieldTypeKind.ENUM,
                        enum_values=["open", "closed"],
                    ),
                ),
            ],
            state_machine=StateMachineSpec(
                status_field="status",
                states=["open", "closed"],
                transitions=[StateTransition(from_state="open", to_state="closed")],
            ),
            computed_fields=[
                ComputedFieldSpec(
                    name="comment_count",
                    expression=AggregateCall(
                        function=AggregateFunction.COUNT,
                        field=FieldReference(path=["comments"]),
                    ),
                ),
            ],
            access=AccessSpec(
                permissions=[
                    PermissionRule(operation=PermissionKind.CREATE, require_auth=True),
                ],
            ),
        )

        return AppSpec(
            name="support",
            title="Support App",
            domain=DomainSpec(entities=[ticket]),
            surfaces=[
                SurfaceSpec(
                    name="ticket_list",
                    entity_ref="Ticket",
                    mode=SurfaceMode.LIST,
                ),
            ],
        )

    def test_generate_testspec_with_all_features(self, full_featured_appspec: AppSpec) -> None:
        """Test that testspec includes all v0.13.0 flow types."""
        testspec = generate_e2e_testspec(full_featured_appspec)

        # Should have state machine flows
        sm_flows = [f for f in testspec.flows if "state_machine" in f.tags]
        assert len(sm_flows) >= 1

        # Should have computed field flows
        computed_flows = [f for f in testspec.flows if "computed" in f.tags]
        assert len(computed_flows) >= 1

        # Should have access control flows
        access_flows = [f for f in testspec.flows if "access_control" in f.tags]
        assert len(access_flows) >= 1

    def test_all_auto_generated_flows_marked(self, full_featured_appspec: AppSpec) -> None:
        """Test that all generated flows are marked as auto-generated."""
        testspec = generate_e2e_testspec(full_featured_appspec)

        for flow in testspec.flows:
            assert flow.auto_generated is True, f"Flow {flow.id} should be auto-generated"
