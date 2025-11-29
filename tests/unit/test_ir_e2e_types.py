"""
Unit tests for E2E testing IR types (FlowSpec, FixtureSpec, E2ETestSpec).

These tests verify the Semantic E2E Testing IR extensions work correctly.
"""

from dazzle.core.ir import (
    A11yRule,
    AppSpec,
    DomainSpec,
    E2ETestSpec,
    EntitySpec,
    FieldSpec,
    FieldType,
    FieldTypeKind,
    FixtureSpec,
    FlowAssertion,
    FlowAssertionKind,
    FlowPrecondition,
    FlowPriority,
    FlowSpec,
    FlowStep,
    FlowStepKind,
    UsabilityRule,
)


class TestFlowSpec:
    """Tests for FlowSpec and related types."""

    def test_flow_step_kinds(self) -> None:
        """Verify all flow step kinds are defined."""
        assert FlowStepKind.NAVIGATE == "navigate"
        assert FlowStepKind.FILL == "fill"
        assert FlowStepKind.CLICK == "click"
        assert FlowStepKind.WAIT == "wait"
        assert FlowStepKind.ASSERT == "assert"
        assert FlowStepKind.SNAPSHOT == "snapshot"

    def test_flow_priority_levels(self) -> None:
        """Verify all flow priority levels are defined."""
        assert FlowPriority.HIGH == "high"
        assert FlowPriority.MEDIUM == "medium"
        assert FlowPriority.LOW == "low"

    def test_flow_assertion_kinds(self) -> None:
        """Verify all flow assertion kinds are defined."""
        assert FlowAssertionKind.ENTITY_EXISTS == "entity_exists"
        assert FlowAssertionKind.ENTITY_NOT_EXISTS == "entity_not_exists"
        assert FlowAssertionKind.VALIDATION_ERROR == "validation_error"
        assert FlowAssertionKind.VISIBLE == "visible"
        assert FlowAssertionKind.NOT_VISIBLE == "not_visible"
        assert FlowAssertionKind.TEXT_CONTAINS == "text_contains"
        assert FlowAssertionKind.REDIRECTS_TO == "redirects_to"
        assert FlowAssertionKind.COUNT == "count"
        assert FlowAssertionKind.FIELD_VALUE == "field_value"

    def test_flow_step_creation(self) -> None:
        """Test creating a flow step."""
        step = FlowStep(
            kind=FlowStepKind.FILL,
            target="field:Task.title",
            value="Test Task",
            description="Fill in the title field",
        )
        assert step.kind == FlowStepKind.FILL
        assert step.target == "field:Task.title"
        assert step.value == "Test Task"
        assert step.description == "Fill in the title field"

    def test_flow_step_with_assertion(self) -> None:
        """Test creating a flow step with an assertion."""
        assertion = FlowAssertion(
            kind=FlowAssertionKind.ENTITY_EXISTS,
            target="Task",
            expected={"title": "Test Task"},
        )
        step = FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=assertion,
        )
        assert step.kind == FlowStepKind.ASSERT
        assert step.assertion is not None
        assert step.assertion.kind == FlowAssertionKind.ENTITY_EXISTS
        assert step.assertion.target == "Task"

    def test_flow_step_with_fixture_ref(self) -> None:
        """Test creating a flow step that references a fixture."""
        step = FlowStep(
            kind=FlowStepKind.FILL,
            target="field:Task.title",
            fixture_ref="Task_valid_title",
        )
        assert step.fixture_ref == "Task_valid_title"

    def test_flow_precondition(self) -> None:
        """Test creating flow preconditions."""
        precondition = FlowPrecondition(
            user_role="admin",
            fixtures=["user_fixture", "task_fixture"],
            authenticated=True,
            view="task_list",
        )
        assert precondition.user_role == "admin"
        assert len(precondition.fixtures) == 2
        assert precondition.authenticated is True
        assert precondition.view == "task_list"

    def test_flow_spec_creation(self) -> None:
        """Test creating a complete flow spec."""
        steps = [
            FlowStep(kind=FlowStepKind.NAVIGATE, target="view:task_list"),
            FlowStep(kind=FlowStepKind.CLICK, target="action:Task.create"),
            FlowStep(kind=FlowStepKind.FILL, target="field:Task.title", value="New Task"),
            FlowStep(kind=FlowStepKind.CLICK, target="action:Task.save"),
            FlowStep(
                kind=FlowStepKind.ASSERT,
                assertion=FlowAssertion(
                    kind=FlowAssertionKind.ENTITY_EXISTS,
                    target="Task",
                ),
            ),
        ]

        flow = FlowSpec(
            id="Task_create_valid",
            description="Create a valid Task entity",
            priority=FlowPriority.HIGH,
            steps=steps,
            tags=["crud", "create"],
            entity="Task",
            auto_generated=True,
        )

        assert flow.id == "Task_create_valid"
        assert flow.priority == FlowPriority.HIGH
        assert len(flow.steps) == 5
        assert flow.entity == "Task"
        assert flow.auto_generated is True
        assert "crud" in flow.tags


class TestFixtureSpec:
    """Tests for FixtureSpec."""

    def test_fixture_creation(self) -> None:
        """Test creating a fixture."""
        fixture = FixtureSpec(
            id="task_valid",
            entity="Task",
            data={"title": "Test Task", "completed": False},
            description="A valid task fixture",
        )
        assert fixture.id == "task_valid"
        assert fixture.entity == "Task"
        assert fixture.data["title"] == "Test Task"
        assert fixture.data["completed"] is False

    def test_fixture_with_refs(self) -> None:
        """Test creating a fixture with references to other fixtures."""
        fixture = FixtureSpec(
            id="task_with_owner",
            entity="Task",
            data={"title": "Owned Task"},
            refs={"owner_id": "user_fixture"},
        )
        assert fixture.refs["owner_id"] == "user_fixture"


class TestE2ETestSpec:
    """Tests for E2ETestSpec."""

    def test_e2e_test_spec_creation(self) -> None:
        """Test creating a complete E2ETestSpec."""
        fixtures = [
            FixtureSpec(id="task_valid", entity="Task", data={"title": "Test"}),
        ]

        flows = [
            FlowSpec(
                id="Task_create",
                priority=FlowPriority.HIGH,
                steps=[FlowStep(kind=FlowStepKind.NAVIGATE, target="view:task_list")],
                entity="Task",
            ),
        ]

        usability_rules = [
            UsabilityRule(
                id="max_steps",
                description="High priority flows complete in <= 5 steps",
                check="max_steps",
                threshold=5,
                severity="error",
            ),
        ]

        a11y_rules = [
            A11yRule(id="color-contrast", level="AA", enabled=True),
        ]

        spec = E2ETestSpec(
            app_name="todo",
            version="0.1.0",
            fixtures=fixtures,
            flows=flows,
            usability_rules=usability_rules,
            a11y_rules=a11y_rules,
        )

        assert spec.app_name == "todo"
        assert spec.version == "0.1.0"
        assert len(spec.fixtures) == 1
        assert len(spec.flows) == 1
        assert len(spec.usability_rules) == 1
        assert len(spec.a11y_rules) == 1

    def test_e2e_test_spec_get_flow(self) -> None:
        """Test getting a flow by ID."""
        flows = [
            FlowSpec(id="flow1", steps=[]),
            FlowSpec(id="flow2", steps=[]),
        ]
        spec = E2ETestSpec(app_name="test", version="1.0", flows=flows)

        assert spec.get_flow("flow1") is not None
        assert spec.get_flow("flow1").id == "flow1"
        assert spec.get_flow("nonexistent") is None

    def test_e2e_test_spec_get_fixture(self) -> None:
        """Test getting a fixture by ID."""
        fixtures = [
            FixtureSpec(id="fixture1", entity="Task", data={}),
            FixtureSpec(id="fixture2", entity="User", data={}),
        ]
        spec = E2ETestSpec(app_name="test", version="1.0", fixtures=fixtures)

        assert spec.get_fixture("fixture1") is not None
        assert spec.get_fixture("fixture1").entity == "Task"
        assert spec.get_fixture("nonexistent") is None

    def test_e2e_test_spec_get_flows_by_priority(self) -> None:
        """Test getting flows by priority."""
        flows = [
            FlowSpec(id="high1", priority=FlowPriority.HIGH, steps=[]),
            FlowSpec(id="high2", priority=FlowPriority.HIGH, steps=[]),
            FlowSpec(id="medium1", priority=FlowPriority.MEDIUM, steps=[]),
            FlowSpec(id="low1", priority=FlowPriority.LOW, steps=[]),
        ]
        spec = E2ETestSpec(app_name="test", version="1.0", flows=flows)

        high_flows = spec.get_flows_by_priority(FlowPriority.HIGH)
        assert len(high_flows) == 2

        medium_flows = spec.get_flows_by_priority(FlowPriority.MEDIUM)
        assert len(medium_flows) == 1

    def test_e2e_test_spec_get_flows_by_entity(self) -> None:
        """Test getting flows by entity."""
        flows = [
            FlowSpec(id="task1", entity="Task", steps=[]),
            FlowSpec(id="task2", entity="Task", steps=[]),
            FlowSpec(id="user1", entity="User", steps=[]),
        ]
        spec = E2ETestSpec(app_name="test", version="1.0", flows=flows)

        task_flows = spec.get_flows_by_entity("Task")
        assert len(task_flows) == 2

        user_flows = spec.get_flows_by_entity("User")
        assert len(user_flows) == 1

    def test_e2e_test_spec_get_flows_by_tag(self) -> None:
        """Test getting flows by tag."""
        flows = [
            FlowSpec(id="crud1", tags=["crud", "create"], steps=[]),
            FlowSpec(id="crud2", tags=["crud", "update"], steps=[]),
            FlowSpec(id="nav1", tags=["navigation"], steps=[]),
        ]
        spec = E2ETestSpec(app_name="test", version="1.0", flows=flows)

        crud_flows = spec.get_flows_by_tag("crud")
        assert len(crud_flows) == 2

        nav_flows = spec.get_flows_by_tag("navigation")
        assert len(nav_flows) == 1


class TestAppSpecE2EExtensions:
    """Tests for AppSpec E2E extensions (e2e_flows, fixtures)."""

    def test_app_spec_with_flows_and_fixtures(self) -> None:
        """Test creating an AppSpec with E2E flows and fixtures."""
        entity = EntitySpec(
            name="Task",
            title="Task",
            fields=[
                FieldSpec(name="id", type=FieldType(kind=FieldTypeKind.UUID)),
                FieldSpec(name="title", type=FieldType(kind=FieldTypeKind.STR)),
            ],
        )

        fixtures = [
            FixtureSpec(id="task_valid", entity="Task", data={"title": "Test"}),
        ]

        flows = [
            FlowSpec(
                id="Task_create",
                priority=FlowPriority.HIGH,
                steps=[FlowStep(kind=FlowStepKind.NAVIGATE, target="view:task_list")],
                entity="Task",
            ),
        ]

        app = AppSpec(
            name="todo",
            title="Todo App",
            domain=DomainSpec(entities=[entity]),
            e2e_flows=flows,
            fixtures=fixtures,
        )

        assert len(app.e2e_flows) == 1
        assert len(app.fixtures) == 1

    def test_app_spec_get_flow(self) -> None:
        """Test AppSpec.get_flow method."""
        flows = [
            FlowSpec(id="flow1", steps=[]),
            FlowSpec(id="flow2", steps=[]),
        ]

        app = AppSpec(
            name="test",
            domain=DomainSpec(entities=[]),
            e2e_flows=flows,
        )

        assert app.get_flow("flow1") is not None
        assert app.get_flow("flow1").id == "flow1"
        assert app.get_flow("nonexistent") is None

    def test_app_spec_get_fixture(self) -> None:
        """Test AppSpec.get_fixture method."""
        fixtures = [
            FixtureSpec(id="fixture1", entity="Task", data={}),
        ]

        app = AppSpec(
            name="test",
            domain=DomainSpec(entities=[]),
            fixtures=fixtures,
        )

        assert app.get_fixture("fixture1") is not None
        assert app.get_fixture("nonexistent") is None

    def test_app_spec_get_flows_by_entity(self) -> None:
        """Test AppSpec.get_flows_by_entity method."""
        flows = [
            FlowSpec(id="task1", entity="Task", steps=[]),
            FlowSpec(id="user1", entity="User", steps=[]),
        ]

        app = AppSpec(
            name="test",
            domain=DomainSpec(entities=[]),
            e2e_flows=flows,
        )

        task_flows = app.get_flows_by_entity("Task")
        assert len(task_flows) == 1
        assert task_flows[0].id == "task1"

    def test_app_spec_get_flows_by_priority(self) -> None:
        """Test AppSpec.get_flows_by_priority method."""
        flows = [
            FlowSpec(id="high1", priority=FlowPriority.HIGH, steps=[]),
            FlowSpec(id="medium1", priority=FlowPriority.MEDIUM, steps=[]),
        ]

        app = AppSpec(
            name="test",
            domain=DomainSpec(entities=[]),
            e2e_flows=flows,
        )

        high_flows = app.get_flows_by_priority(FlowPriority.HIGH)
        assert len(high_flows) == 1
        assert high_flows[0].id == "high1"


class TestUsabilityAndA11yRules:
    """Tests for UsabilityRule and A11yRule."""

    def test_usability_rule(self) -> None:
        """Test creating a usability rule."""
        rule = UsabilityRule(
            id="max_steps",
            description="Flows should complete in 5 steps or less",
            check="max_steps",
            threshold=5,
            target="high_priority_flows",
            severity="error",
        )
        assert rule.id == "max_steps"
        assert rule.threshold == 5
        assert rule.severity == "error"

    def test_a11y_rule(self) -> None:
        """Test creating an accessibility rule."""
        rule = A11yRule(
            id="color-contrast",
            level="AA",
            enabled=True,
        )
        assert rule.id == "color-contrast"
        assert rule.level == "AA"
        assert rule.enabled is True

    def test_a11y_rule_defaults(self) -> None:
        """Test A11yRule default values."""
        rule = A11yRule(id="test-rule")
        assert rule.level == "AA"
        assert rule.enabled is True
