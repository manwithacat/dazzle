"""
Rule specification types for DAZZLE Convergent BDD.

Rules are domain-level business invariants that stories exercise.
They bridge the gap between high-level requirements and testable
behaviour specifications.

DSL Syntax (v0.41.0):
    rule RULE-C-001 "Customer can identify their next required action":
      kind: constraint
      origin: top_down
      invariant: customer dashboard shows actionable items with clear next steps
      scope: [Customer, Task]
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .location import SourceLocation


class RuleKind(StrEnum):
    """Kind of business rule."""

    CONSTRAINT = "constraint"
    PRECONDITION = "precondition"
    AUTHORIZATION = "authorization"
    DERIVATION = "derivation"


class RuleOrigin(StrEnum):
    """How the rule was discovered."""

    TOP_DOWN = "top_down"
    BOTTOM_UP = "bottom_up"


class RuleStatus(StrEnum):
    """Lifecycle status of a rule."""

    DRAFT = "draft"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class RuleSpec(BaseModel):
    """
    Domain-level business invariant.

    A rule captures a requirement or constraint that one or more stories
    must exercise.  Rules are the anchor points for convergent BDD:
    every rule should be exercised by at least one story, and every
    story should exercise at least one rule.

    DSL Syntax:
        rule RULE-C-001 "Customer can identify their next required action":
          kind: constraint
          origin: top_down
          invariant: customer dashboard shows actionable items
          scope: [Customer, Task]
          status: accepted

    Attributes:
        rule_id: Stable identifier (e.g., RULE-C-001)
        title: Short human-readable name
        description: Optional longer description
        kind: Type of rule (constraint, precondition, authorization, derivation)
        origin: How the rule was discovered (top_down, bottom_up)
        invariant: The invariant statement this rule asserts
        scope: List of entity names the rule applies to
        status: Lifecycle status (draft, accepted, rejected)
    """

    rule_id: str = Field(..., description="Stable identifier (e.g., RULE-C-001)")
    title: str = Field(..., description="Short human-readable name")
    description: str | None = Field(default=None, description="Longer description")
    kind: RuleKind = Field(default=RuleKind.CONSTRAINT, description="Type of rule")
    origin: RuleOrigin = Field(default=RuleOrigin.TOP_DOWN, description="Discovery origin")
    invariant: str | None = Field(default=None, description="Invariant statement")
    scope: list[str] = Field(default_factory=list, description="Entity names this rule applies to")
    status: RuleStatus = Field(default=RuleStatus.DRAFT, description="Lifecycle status")
    source: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)
