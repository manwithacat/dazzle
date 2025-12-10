"""
Unit tests for E2E flow parsing.

Tests the parsing of flow declarations in DSL files.
"""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import (
    FlowAssertionKind,
    FlowPriority,
    FlowStepKind,
)


class TestFlowParsing:
    """Tests for flow parsing."""

    def test_parse_minimal_flow(self) -> None:
        """Test parsing a minimal flow with just steps."""
        dsl = """
module test_app

flow simple_flow "A simple flow":
  steps:
    navigate view:task_list
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.e2e_flows) == 1
        flow = fragment.e2e_flows[0]
        assert flow.id == "simple_flow"
        assert flow.description == "A simple flow"
        assert flow.priority == FlowPriority.MEDIUM  # default
        assert len(flow.steps) == 1
        assert flow.steps[0].kind == FlowStepKind.NAVIGATE
        assert flow.steps[0].target == "view:task_list"

    def test_parse_flow_with_priority(self) -> None:
        """Test parsing a flow with priority."""
        dsl = """
module test_app

flow high_priority_flow "Critical flow":
  priority: high
  steps:
    navigate view:task_list
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        flow = fragment.e2e_flows[0]
        assert flow.priority == FlowPriority.HIGH

    def test_parse_flow_with_tags(self) -> None:
        """Test parsing a flow with tags."""
        dsl = """
module test_app

flow tagged_flow "Tagged flow":
  tags: smoke, crud, regression
  steps:
    navigate view:task_list
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        flow = fragment.e2e_flows[0]
        assert flow.tags == ["smoke", "crud", "regression"]

    def test_parse_flow_with_preconditions(self) -> None:
        """Test parsing a flow with preconditions."""
        dsl = """
module test_app

flow auth_flow "Auth required flow":
  preconditions:
    authenticated: true
    user_role: admin
    view: dashboard
    fixtures: task_valid, task_completed
  steps:
    navigate view:task_list
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        flow = fragment.e2e_flows[0]
        assert flow.preconditions is not None
        assert flow.preconditions.authenticated is True
        assert flow.preconditions.user_role == "admin"
        assert flow.preconditions.view == "dashboard"
        assert flow.preconditions.fixtures == ["task_valid", "task_completed"]

    def test_parse_navigate_step(self) -> None:
        """Test parsing navigate step."""
        dsl = """
module test_app

flow navigate_flow "Navigate test":
  steps:
    navigate view:task_list
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        step = fragment.e2e_flows[0].steps[0]
        assert step.kind == FlowStepKind.NAVIGATE
        assert step.target == "view:task_list"

    def test_parse_fill_step_with_value(self) -> None:
        """Test parsing fill step with literal value."""
        dsl = """
module test_app

flow fill_flow "Fill test":
  steps:
    fill field:Task.title "Test Task"
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        step = fragment.e2e_flows[0].steps[0]
        assert step.kind == FlowStepKind.FILL
        assert step.target == "field:Task.title"
        assert step.value == "Test Task"

    def test_parse_click_step(self) -> None:
        """Test parsing click step."""
        dsl = """
module test_app

flow click_flow "Click test":
  steps:
    click action:Task.save
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        step = fragment.e2e_flows[0].steps[0]
        assert step.kind == FlowStepKind.CLICK
        assert step.target == "action:Task.save"

    def test_parse_wait_step_with_time(self) -> None:
        """Test parsing wait step with time value."""
        dsl = """
module test_app

flow wait_flow "Wait test":
  steps:
    wait 1000
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        step = fragment.e2e_flows[0].steps[0]
        assert step.kind == FlowStepKind.WAIT
        assert step.value == "1000"

    def test_parse_wait_step_with_target(self) -> None:
        """Test parsing wait step with target."""
        dsl = """
module test_app

flow wait_target_flow "Wait for element":
  steps:
    wait view:task_detail
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        step = fragment.e2e_flows[0].steps[0]
        assert step.kind == FlowStepKind.WAIT
        assert step.target == "view:task_detail"

    def test_parse_snapshot_step(self) -> None:
        """Test parsing snapshot step."""
        dsl = """
module test_app

flow snapshot_flow "Snapshot test":
  steps:
    snapshot
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        step = fragment.e2e_flows[0].steps[0]
        assert step.kind == FlowStepKind.SNAPSHOT

    def test_parse_assert_entity_exists(self) -> None:
        """Test parsing entity_exists assertion."""
        dsl = """
module test_app

flow assert_flow "Assert entity exists":
  steps:
    expect entity_exists Task
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        step = fragment.e2e_flows[0].steps[0]
        assert step.kind == FlowStepKind.ASSERT
        assert step.assertion is not None
        assert step.assertion.kind == FlowAssertionKind.ENTITY_EXISTS
        assert step.assertion.target == "entity:Task"

    def test_parse_assert_entity_exists_with_where(self) -> None:
        """Test parsing entity_exists assertion with where clause."""
        dsl = """
module test_app

flow assert_where_flow "Assert with condition":
  steps:
    expect entity_exists Task where title="Test"
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        step = fragment.e2e_flows[0].steps[0]
        assert step.assertion is not None
        assert step.assertion.kind == FlowAssertionKind.ENTITY_EXISTS
        assert step.assertion.expected == {"title": "Test"}

    def test_parse_assert_validation_error(self) -> None:
        """Test parsing validation_error assertion."""
        dsl = """
module test_app

flow assert_validation_flow "Assert validation":
  steps:
    expect validation_error field:Task.title
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        step = fragment.e2e_flows[0].steps[0]
        assert step.assertion is not None
        assert step.assertion.kind == FlowAssertionKind.VALIDATION_ERROR
        assert step.assertion.target == "field:Task.title"

    def test_parse_assert_visible(self) -> None:
        """Test parsing visible assertion."""
        dsl = """
module test_app

flow assert_visible_flow "Assert visible":
  steps:
    expect visible view:task_list
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        step = fragment.e2e_flows[0].steps[0]
        assert step.assertion is not None
        assert step.assertion.kind == FlowAssertionKind.VISIBLE
        assert step.assertion.target == "view:task_list"

    def test_parse_assert_text_contains(self) -> None:
        """Test parsing text_contains assertion."""
        dsl = """
module test_app

flow assert_text_flow "Assert text":
  steps:
    expect text_contains "Success"
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        step = fragment.e2e_flows[0].steps[0]
        assert step.assertion is not None
        assert step.assertion.kind == FlowAssertionKind.TEXT_CONTAINS
        assert step.assertion.expected == "Success"

    def test_parse_complete_flow(self) -> None:
        """Test parsing a complete flow with all elements."""
        dsl = """
module test_app

flow create_task_complete "Create a task end to end":
  priority: high
  tags: smoke, crud
  preconditions:
    authenticated: true
    user_role: admin
    view: task_list
  steps:
    navigate view:task_list
    click action:Task.new
    fill field:Task.title "Test Task"
    fill field:Task.description "A test task"
    click action:Task.save
    wait 500
    expect entity_exists Task where title="Test Task"
    expect visible view:task_detail
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.e2e_flows) == 1
        flow = fragment.e2e_flows[0]
        assert flow.id == "create_task_complete"
        assert flow.description == "Create a task end to end"
        assert flow.priority == FlowPriority.HIGH
        assert flow.tags == ["smoke", "crud"]
        assert flow.preconditions is not None
        assert flow.preconditions.authenticated is True
        assert len(flow.steps) == 8

    def test_parse_multiple_flows(self) -> None:
        """Test parsing multiple flows in a file."""
        dsl = """
module test_app

flow flow_one "First flow":
  steps:
    navigate view:task_list

flow flow_two "Second flow":
  priority: low
  steps:
    click action:Task.save
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.e2e_flows) == 2
        assert fragment.e2e_flows[0].id == "flow_one"
        assert fragment.e2e_flows[1].id == "flow_two"
        assert fragment.e2e_flows[1].priority == FlowPriority.LOW

    def test_flow_with_entity(self) -> None:
        """Test parsing flow alongside entity."""
        dsl = """
module test_app

entity Task "Task":
  id: uuid pk
  title: str(200) required

flow create_task "Create a task":
  steps:
    navigate view:task_list
    fill field:Task.title "Test"
    click action:Task.save
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.entities) == 1
        assert len(fragment.e2e_flows) == 1
        assert fragment.entities[0].name == "Task"
        assert fragment.e2e_flows[0].id == "create_task"


class TestFlowStepParsing:
    """Tests for individual flow step parsing."""

    def test_dotted_target(self) -> None:
        """Test parsing targets with dotted notation."""
        dsl = """
module test_app

flow dotted_flow "Dotted target":
  steps:
    fill field:Task.title "Test"
    click action:Task.save
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        steps = fragment.e2e_flows[0].steps
        assert steps[0].target == "field:Task.title"
        assert steps[1].target == "action:Task.save"


class TestFlowPriorityParsing:
    """Tests for flow priority parsing."""

    def test_parse_high_priority(self) -> None:
        """Test parsing high priority."""
        dsl = """
module test_app

flow high_flow "High priority":
  priority: high
  steps:
    navigate view:task_list
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        assert fragment.e2e_flows[0].priority == FlowPriority.HIGH

    def test_parse_medium_priority(self) -> None:
        """Test parsing medium priority."""
        dsl = """
module test_app

flow medium_flow "Medium priority":
  priority: medium
  steps:
    navigate view:task_list
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        assert fragment.e2e_flows[0].priority == FlowPriority.MEDIUM

    def test_parse_low_priority(self) -> None:
        """Test parsing low priority."""
        dsl = """
module test_app

flow low_flow "Low priority":
  priority: low
  steps:
    navigate view:task_list
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        assert fragment.e2e_flows[0].priority == FlowPriority.LOW
