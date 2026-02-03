"""
Test design types for DAZZLE IR.

This module contains types for LLM-proposed test designs that represent
high-level test specifications awaiting implementation. Test designs are
an intermediate representation between DSL analysis and Playwright tests.

Test designs are persona-centric and outcome-focused, describing WHAT
should be tested rather than HOW (implementation details).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    """Return current UTC datetime (timezone-aware)."""
    return datetime.now(UTC)


class TestDesignTrigger(StrEnum):
    """Triggers that initiate a test scenario."""

    FORM_SUBMITTED = "form_submitted"
    STATUS_CHANGED = "status_changed"
    TIMER_ELAPSED = "timer_elapsed"
    EXTERNAL_EVENT = "external_event"
    USER_CLICK = "user_click"
    PAGE_LOAD = "page_load"
    CRON_DAILY = "cron_daily"
    CRON_HOURLY = "cron_hourly"


class TestDesignAction(StrEnum):
    """High-level actions that can be performed in a test step."""

    LOGIN_AS = "login_as"
    LOGOUT = "logout"
    NAVIGATE_TO = "navigate_to"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    WAIT_FOR = "wait_for"
    ASSERT_VISIBLE = "assert_visible"
    ASSERT_NOT_VISIBLE = "assert_not_visible"
    ASSERT_TEXT = "assert_text"
    ASSERT_COUNT = "assert_count"
    TRIGGER_TRANSITION = "trigger_transition"
    FILL_FORM = "fill_form"
    SUBMIT_FORM = "submit_form"
    UPLOAD = "upload"
    DOWNLOAD = "download"


class TestDesignStep(BaseModel):
    """
    High-level step in a test design.

    Steps are semantic and not tied to Playwright implementation.
    They describe what action to take, not how to implement it.

    Attributes:
        action: High-level action (login_as, navigate_to, create, etc.)
        target: Semantic target (persona name, view name, entity name)
        data: Any data needed for the action
        rationale: Why this step matters for the test
    """

    action: TestDesignAction
    target: str  # Semantic target
    data: dict[str, Any] | None = None  # Additional data for the action
    rationale: str | None = None  # Why this step matters

    model_config = ConfigDict(frozen=True)


class TestDesignStatus(StrEnum):
    """Status of a test design in the review workflow."""

    PROPOSED = "proposed"  # LLM proposed, awaiting review
    ACCEPTED = "accepted"  # Human accepted, ready for implementation
    IMPLEMENTED = "implemented"  # Test code generated
    VERIFIED = "verified"  # Test code verified working
    REJECTED = "rejected"  # Human rejected this design


class TestDesignSpec(BaseModel):
    """
    LLM-proposed test design awaiting implementation.

    Test designs are intermediate representations that bridge the gap
    between DSL analysis and actual test code. They capture:
    - Which persona's perspective the test is from
    - What scenario or workflow is being tested
    - High-level steps in semantic terms
    - Expected outcomes (not implementation assertions)

    Attributes:
        test_id: Unique identifier (e.g., TD-001)
        title: Human-readable test title
        description: Detailed description of what's being tested
        persona: Which persona's perspective (from DSL)
        scenario: Which DSL scenario this tests (optional)
        trigger: What initiates the test

        steps: High-level semantic steps
        expected_outcomes: Outcome-based assertions (not Playwright)

        status: Current status in review workflow
        implementation_path: Path to generated test file (if implemented)

        notes: Human notes on design quality
        prompt_version: Which prompt version generated this
        created_at: When this design was created
        updated_at: When this design was last updated
    """

    test_id: str
    title: str
    description: str | None = None

    # Context
    persona: str | None = None  # Persona from DSL
    scenario: str | None = None  # Scenario from DSL
    trigger: TestDesignTrigger = TestDesignTrigger.USER_CLICK

    # Test content
    steps: list[TestDesignStep] = Field(default_factory=list)
    expected_outcomes: list[str] = Field(default_factory=list)

    # Coverage metadata
    entities: list[str] = Field(default_factory=list)  # Entities touched
    surfaces: list[str] = Field(default_factory=list)  # Surfaces tested
    tags: list[str] = Field(default_factory=list)

    # Implementation tracking
    status: TestDesignStatus = TestDesignStatus.PROPOSED
    implementation_path: str | None = None

    # Quality tracking
    notes: str | None = None
    prompt_version: str = "v1"
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    model_config = ConfigDict(frozen=False)  # Mutable for status updates


class TestGapCategory(StrEnum):
    """Categories of test coverage gaps."""

    UNTESTED_ENTITY = "untested_entity"
    UNTESTED_PERSONA_GOAL = "untested_persona_goal"
    UNTESTED_STATE_TRANSITION = "untested_state_transition"
    UNTESTED_SURFACE = "untested_surface"
    UNTESTED_SCENARIO = "untested_scenario"
    LOW_COVERAGE_ENTITY = "low_coverage_entity"


class TestGap(BaseModel):
    """
    A gap in test coverage identified by analysis.

    Attributes:
        category: Type of gap (untested entity, persona goal, etc.)
        target: What's missing coverage (entity name, goal description, etc.)
        severity: How important this gap is (high, medium, low)
        suggestion: Suggested test to fill this gap
    """

    category: TestGapCategory
    target: str
    severity: Literal["high", "medium", "low"] = "medium"
    suggestion: str | None = None
    related_entities: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class TestGapAnalysis(BaseModel):
    """
    Complete analysis of test coverage gaps.

    Attributes:
        project_name: Name of the analyzed project
        total_entities: Total entities in the project
        total_surfaces: Total surfaces in the project
        total_personas: Total personas in the project
        gaps: List of identified gaps
        coverage_score: Overall coverage percentage (0-100)
        suggested_designs: Suggested test designs to fill gaps
    """

    project_name: str
    total_entities: int = 0
    total_surfaces: int = 0
    total_personas: int = 0
    total_scenarios: int = 0

    gaps: list[TestGap] = Field(default_factory=list)
    coverage_score: float = 0.0  # 0-100

    suggested_designs: list[TestDesignSpec] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)

    @property
    def high_severity_gaps(self) -> list[TestGap]:
        """Get gaps with high severity."""
        return [g for g in self.gaps if g.severity == "high"]

    @property
    def gap_count_by_category(self) -> dict[str, int]:
        """Get count of gaps by category."""
        counts: dict[str, int] = {}
        for gap in self.gaps:
            counts[gap.category.value] = counts.get(gap.category.value, 0) + 1
        return counts
