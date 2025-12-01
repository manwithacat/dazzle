"""
Test specification types for DAZZLE IR.

This module contains test case specifications for API testing
including setup steps, actions, and assertions.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TestActionKind(str, Enum):
    """Types of test actions."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    CALL = "call"
    GET = "get"


class TestAssertionKind(str, Enum):
    """Types of test assertions."""

    STATUS = "status"
    CREATED = "created"
    FIELD = "field"
    ERROR = "error"
    COUNT = "count"


class TestComparisonOperator(str, Enum):
    """Comparison operators for test assertions."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"


class TestSetupStep(BaseModel):
    """
    Setup step in a test.

    Creates objects or sets up state before test action.
    """

    variable_name: str
    action: TestActionKind
    entity_name: str
    data: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class TestAction(BaseModel):
    """
    Main action to test.

    Attributes:
        kind: Type of action (create, update, delete, etc.)
        target: Entity or object being acted upon
        data: Data for the action
    """

    kind: TestActionKind
    target: str  # Entity name or variable reference
    data: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class TestAssertion(BaseModel):
    """
    Test assertion/expectation.

    Attributes:
        kind: Type of assertion
        field_name: Field being asserted (for FIELD assertions)
        operator: Comparison operator
        expected_value: Expected value
    """

    kind: TestAssertionKind
    field_name: str | None = None
    operator: TestComparisonOperator | None = None
    expected_value: Any | None = None
    error_message: str | None = None

    model_config = ConfigDict(frozen=True)


class TestSpec(BaseModel):
    """
    Test specification from DSL.

    Defines a test case with setup, action, and expectations.

    Attributes:
        name: Test identifier
        description: Human-readable description
        setup_steps: Objects to create before test
        action: Main action to test
        assertions: List of expected outcomes
    """

    name: str
    description: str | None = None
    setup_steps: list[TestSetupStep] = Field(default_factory=list)
    action: TestAction
    assertions: list[TestAssertion] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)
