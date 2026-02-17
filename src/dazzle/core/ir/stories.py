"""
Story specification types for DAZZLE Behaviour Layer.

This module contains IR types for behavioural user stories that bridge
the gap between DSL specifications and implementation code.

Stories are non-Turing-complete specifications that describe:
- What should happen (outcomes)
- When it should happen (triggers)
- Who is involved (actors, entities)
- What constraints must be maintained

Stories can be defined in DSL syntax (v0.22.0) or as JSON artifacts
in .dazzle/stories/. DSL syntax provides Gherkin-style given/when/then
conditions for clearer acceptance criteria.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .location import SourceLocation


class StoryTrigger(StrEnum):
    """
    Constrained set of event triggers for stories.

    These represent the types of events that can initiate a story's behavior.
    The set is intentionally limited to maintain non-Turing-completeness.
    """

    FORM_SUBMITTED = "form_submitted"
    STATUS_CHANGED = "status_changed"
    TIMER_ELAPSED = "timer_elapsed"
    EXTERNAL_EVENT = "external_event"
    USER_CLICK = "user_click"
    CRON_DAILY = "cron_daily"
    CRON_HOURLY = "cron_hourly"


class StoryStatus(StrEnum):
    """
    Acceptance status of a story.

    Stories start as drafts (proposed by LLM), then are reviewed
    by humans who mark them as accepted or rejected.
    """

    DRAFT = "draft"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class StoryCondition(BaseModel):
    """
    A Gherkin-style condition (given/when/then).

    Represents a single condition in a story's acceptance criteria.
    Can optionally reference a field path for validation.

    Attributes:
        expression: Human-readable condition text
        field_path: Optional entity.field path for validation (e.g., "Invoice.status")

    Example:
        StoryCondition(
            expression="Invoice.status is 'draft'",
            field_path="Invoice.status"
        )
    """

    expression: str = Field(..., description="Human-readable condition text")
    field_path: str | None = Field(
        default=None, description="Optional entity.field path for validation"
    )

    model_config = ConfigDict(frozen=True)


class StoryException(BaseModel):
    """
    An 'unless' branch with alternative outcomes.

    Represents exception handling in a story - what happens when
    certain conditions prevent the happy path.

    Attributes:
        condition: The exception condition (e.g., "Client.email is missing")
        then_outcomes: What should happen instead

    Example:
        StoryException(
            condition="Client.email is missing",
            then_outcomes=["FollowupTask is created"]
        )
    """

    condition: str = Field(..., description="Exception condition")
    then_outcomes: list[str] = Field(default_factory=list, description="Alternative outcomes")

    model_config = ConfigDict(frozen=True)


class StorySpec(BaseModel):
    """
    Behavioural user story specification.

    A story describes a single coherent behavior from the perspective
    of an actor (persona). Stories are:
    - Defined in DSL syntax (v0.22.0) or proposed by LLM
    - Reviewed and edited by humans
    - Used to generate ProcessSpec implementations

    DSL Syntax (v0.22.0):
        story ST-001 "Staff sends invoice to client":
          actor: StaffUser
          trigger: status_changed
          scope: [Invoice, Client]

          given:
            - Invoice.status is 'draft'
            - Client.email is set

          when:
            - Invoice.status changes to 'sent'

          then:
            - Invoice email is sent to Client.email
            - Invoice.sent_at is recorded

          unless:
            - Client.email is missing:
                then: FollowupTask is created

    Attributes:
        story_id: Stable identifier (e.g., ST-001)
        title: Short human-readable name
        description: Optional longer description
        actor: Persona name from DSL (e.g., Admin, StaffUser)
        trigger: Event that initiates this story
        scope: List of entity names directly involved
        given: Preconditions (Gherkin-style)
        when: Trigger conditions (Gherkin-style)
        then: Expected outcomes (Gherkin-style)
        unless: Exception branches with alternative outcomes
        status: Acceptance status (draft, accepted, rejected)
        created_at: ISO 8601 timestamp when story was created
        accepted_at: ISO 8601 timestamp when story was accepted
        # Legacy fields for backward compatibility
        preconditions: Legacy field, maps to given
        happy_path_outcome: Legacy field, maps to then
        side_effects: Named effects (notifications, logs, integrations)
        constraints: Invariants that must never be violated
        variants: Edge cases or alternative flows

    Example:
        StorySpec(
            story_id="ST-001",
            title="Staff sends an invoice to a client",
            actor="StaffUser",
            trigger=StoryTrigger.STATUS_CHANGED,
            scope=["Invoice", "Client"],
            given=[StoryCondition(expression="Invoice.status is 'draft'")],
            when=[StoryCondition(expression="Invoice.status changes to 'sent'")],
            then=[StoryCondition(expression="Invoice email is sent to Client.email")],
            unless=[StoryException(
                condition="Client.email is missing",
                then_outcomes=["FollowupTask is created"]
            )],
        )
    """

    story_id: str = Field(..., description="Stable identifier (e.g., ST-001)")
    title: str = Field(..., description="Short human-readable name")
    description: str | None = Field(default=None, description="Longer description")
    actor: str = Field(..., description="Persona name from DSL")
    trigger: StoryTrigger = Field(..., description="Event that initiates this story")
    scope: list[str] = Field(default_factory=list, description="Entity names directly involved")

    # Gherkin-style conditions (v0.22.0)
    given: list[StoryCondition] = Field(default_factory=list, description="Preconditions (given)")
    when: list[StoryCondition] = Field(
        default_factory=list, description="Trigger conditions (when)"
    )
    then: list[StoryCondition] = Field(default_factory=list, description="Expected outcomes (then)")
    unless: list[StoryException] = Field(default_factory=list, description="Exception branches")

    # Legacy fields for backward compatibility with JSON stories
    preconditions: list[str] = Field(
        default_factory=list, description="Legacy: Conditions that must be true before"
    )
    happy_path_outcome: list[str] = Field(
        default_factory=list, description="Legacy: Statements true after success"
    )
    side_effects: list[str] = Field(
        default_factory=list, description="Named effects (notifications, logs)"
    )
    constraints: list[str] = Field(
        default_factory=list, description="Invariants that must never be violated"
    )
    variants: list[str] = Field(default_factory=list, description="Edge cases or alternative flows")

    status: StoryStatus = Field(default=StoryStatus.DRAFT, description="Acceptance status")
    created_at: str | None = Field(default=None, description="ISO 8601 timestamp when created")
    accepted_at: str | None = Field(default=None, description="ISO 8601 timestamp when accepted")
    # v0.31.0: Source location for error reporting
    source: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)

    def with_status(self, status: StoryStatus, accepted_at: str | None = None) -> StorySpec:
        """Create a copy with updated status."""
        return StorySpec(
            story_id=self.story_id,
            title=self.title,
            description=self.description,
            actor=self.actor,
            trigger=self.trigger,
            scope=self.scope,
            given=self.given,
            when=self.when,
            then=self.then,
            unless=self.unless,
            preconditions=self.preconditions,
            happy_path_outcome=self.happy_path_outcome,
            side_effects=self.side_effects,
            constraints=self.constraints,
            variants=self.variants,
            status=status,
            created_at=self.created_at,
            accepted_at=accepted_at or self.accepted_at,
        )

    @property
    def effective_given(self) -> list[str]:
        """Get given conditions as strings, merging Gherkin and legacy formats."""
        if self.given:
            return [c.expression for c in self.given]
        return self.preconditions

    @property
    def effective_then(self) -> list[str]:
        """Get then outcomes as strings, merging Gherkin and legacy formats."""
        if self.then:
            return [c.expression for c in self.then]
        return self.happy_path_outcome


class StoriesContainer(BaseModel):
    """
    Container for storing stories with version information.

    This is the root object stored in .dazzle/stories/stories.json.

    Attributes:
        version: Schema version for future migrations
        stories: List of story specifications
    """

    version: str = Field(default="1.0", description="Schema version")
    stories: list[StorySpec] = Field(default_factory=list, description="List of stories")

    model_config = ConfigDict(frozen=True)
