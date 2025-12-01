"""
E2E flow test types for DAZZLE IR.

This module contains E2E user journey specifications including
flows, fixtures, usability rules, and accessibility checks.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .tests import TestComparisonOperator


class FlowPriority(str, Enum):
    """Flow priority levels for regression gating."""

    HIGH = "high"  # Must pass for PR merge
    MEDIUM = "medium"  # Important but not blocking
    LOW = "low"  # Nice-to-have coverage


class FlowStepKind(str, Enum):
    """Types of flow steps in a user journey."""

    NAVIGATE = "navigate"  # Go to a view/URL
    FILL = "fill"  # Fill a form field
    CLICK = "click"  # Click an action/button
    WAIT = "wait"  # Wait for element/condition
    ASSERT = "assert"  # Assert a condition
    SNAPSHOT = "snapshot"  # Take database/UI snapshot


class FlowAssertionKind(str, Enum):
    """Types of flow assertions."""

    ENTITY_EXISTS = "entity_exists"  # Entity was created/exists
    ENTITY_NOT_EXISTS = "entity_not_exists"  # Entity doesn't exist
    VALIDATION_ERROR = "validation_error"  # Field has validation error
    VISIBLE = "visible"  # Element is visible
    NOT_VISIBLE = "not_visible"  # Element is not visible
    TEXT_CONTAINS = "text_contains"  # Element contains text
    REDIRECTS_TO = "redirects_to"  # Navigation to view
    COUNT = "count"  # Count of elements/entities
    FIELD_VALUE = "field_value"  # Field has specific value

    # Auth-related assertions (v0.3.3)
    IS_AUTHENTICATED = "is_authenticated"  # User is logged in
    IS_NOT_AUTHENTICATED = "is_not_authenticated"  # User is logged out
    LOGIN_SUCCEEDED = "login_succeeded"  # Login was successful
    LOGIN_FAILED = "login_failed"  # Login attempt failed with error
    ROUTE_PROTECTED = "route_protected"  # Route requires auth (modal/redirect)
    HAS_PERSONA = "has_persona"  # User has specific persona/role


class FlowAssertion(BaseModel):
    """
    Assertion within a flow step.

    Defines what to check after an action is performed.

    Attributes:
        kind: Type of assertion (entity_exists, validation_error, etc.)
        target: Semantic target (entity name, field identifier, view name)
        expected: Expected value for comparison
        operator: Comparison operator (equals, contains, greater_than)
    """

    kind: FlowAssertionKind
    target: str | None = None  # e.g., "Task", "field:Task.title", "view:task_list"
    expected: Any | None = None  # Expected value
    operator: TestComparisonOperator | None = None  # Comparison operator

    model_config = ConfigDict(frozen=True)


class FlowStep(BaseModel):
    """
    Single step in a user flow/journey.

    Represents one action in an E2E test scenario.

    Attributes:
        kind: Type of step (navigate, fill, click, wait, assert, snapshot)
        target: Semantic target (e.g., "view:task_list", "field:Task.title", "action:Task.create")
        value: Value for fill steps or wait duration (ms)
        fixture_ref: Reference to fixture for dynamic values
        assertion: For assert steps, the assertion to check
        description: Optional human-readable description
    """

    kind: FlowStepKind
    target: str | None = None  # Semantic target
    value: str | None = None  # For fill steps or wait duration
    fixture_ref: str | None = None  # Reference to fixture data
    assertion: FlowAssertion | None = None  # For assert steps
    description: str | None = None  # Human-readable step description

    model_config = ConfigDict(frozen=True)


class FlowPrecondition(BaseModel):
    """
    Preconditions for a flow to execute.

    Defines what state must exist before running the flow.

    Attributes:
        user_role: Required user role (e.g., "admin", "member")
        fixtures: List of fixture IDs to seed before test
        authenticated: Whether user must be authenticated
        view: Starting view (if specific view required)
    """

    user_role: str | None = None
    fixtures: list[str] = Field(default_factory=list)
    authenticated: bool = True
    view: str | None = None  # Starting view

    model_config = ConfigDict(frozen=True)


class FlowSpec(BaseModel):
    """
    User journey/flow specification for E2E testing.

    Defines a complete user journey from start to assertion.
    Flows are generated from AppSpec or defined in DSL.

    Attributes:
        id: Unique flow identifier
        description: Human-readable description
        priority: Flow priority for CI gating (high, medium, low)
        preconditions: Required state before flow execution
        steps: List of steps in the flow
        tags: Tags for filtering/categorization
        entity: Primary entity this flow tests (optional)
        auto_generated: Whether flow was auto-generated from AppSpec
    """

    id: str
    description: str | None = None
    priority: FlowPriority = FlowPriority.MEDIUM
    preconditions: FlowPrecondition | None = None
    steps: list[FlowStep] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    entity: str | None = None  # Primary entity being tested
    auto_generated: bool = False  # True if generated from AppSpec

    model_config = ConfigDict(frozen=True)


class FixtureSpec(BaseModel):
    """
    Test fixture/data definition.

    Defines reusable test data that can be seeded before tests.

    Attributes:
        id: Unique fixture identifier
        entity: Entity this fixture is for
        data: Field values for the fixture
        refs: References to other fixtures (for relationships)
        description: Human-readable description
    """

    id: str
    entity: str | None = None  # Entity name
    data: dict[str, Any] = Field(default_factory=dict)  # Field values
    refs: dict[str, str] = Field(default_factory=dict)  # Field -> fixture_id
    description: str | None = None

    model_config = ConfigDict(frozen=True)


class UsabilityRule(BaseModel):
    """
    Usability rule for automated UX validation.

    Defines rules that are checked during E2E test runs.

    Attributes:
        id: Rule identifier
        description: Human-readable description
        check: Rule type (max_steps, primary_action_visible, etc.)
        threshold: Numeric threshold for rule
        target: Target element/flow for rule
        severity: warning or error
    """

    id: str
    description: str
    check: str  # e.g., "max_steps", "primary_action_visible"
    threshold: int | float | None = None
    target: str | None = None
    severity: str = "warning"  # "warning" or "error"

    model_config = ConfigDict(frozen=True)


class A11yRule(BaseModel):
    """
    Accessibility rule for WCAG compliance checks.

    Attributes:
        id: Rule identifier (e.g., "color-contrast", "label")
        level: WCAG level (A, AA, AAA)
        enabled: Whether rule is enabled
    """

    id: str
    level: str = "AA"  # WCAG level
    enabled: bool = True

    model_config = ConfigDict(frozen=True)


class E2ETestSpec(BaseModel):
    """
    Complete E2E test specification generated from AppSpec.

    This is the output of the test generator, containing all flows,
    fixtures, and rules for comprehensive E2E testing.

    Attributes:
        app_name: Application name
        version: AppSpec version
        fixtures: List of test fixtures
        flows: List of user flows/journeys
        usability_rules: Usability rules to check
        a11y_rules: Accessibility rules to check
        metadata: Additional metadata
    """

    app_name: str
    version: str
    fixtures: list[FixtureSpec] = Field(default_factory=list)
    flows: list[FlowSpec] = Field(default_factory=list)
    usability_rules: list[UsabilityRule] = Field(default_factory=list)
    a11y_rules: list[A11yRule] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)

    def get_flow(self, flow_id: str) -> FlowSpec | None:
        """Get flow by ID."""
        for flow in self.flows:
            if flow.id == flow_id:
                return flow
        return None

    def get_fixture(self, fixture_id: str) -> FixtureSpec | None:
        """Get fixture by ID."""
        for fixture in self.fixtures:
            if fixture.id == fixture_id:
                return fixture
        return None

    def get_flows_by_priority(self, priority: FlowPriority) -> list[FlowSpec]:
        """Get all flows with given priority."""
        return [f for f in self.flows if f.priority == priority]

    def get_flows_by_entity(self, entity: str) -> list[FlowSpec]:
        """Get all flows for a given entity."""
        return [f for f in self.flows if f.entity == entity]

    def get_flows_by_tag(self, tag: str) -> list[FlowSpec]:
        """Get all flows with given tag."""
        return [f for f in self.flows if tag in f.tags]
