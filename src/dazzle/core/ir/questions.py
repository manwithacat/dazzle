"""
Question specification types for DAZZLE Convergent BDD.

Questions are typed specification gaps that block artefacts until resolved.
They make "we don't know yet" a first-class part of the spec rather than
a hidden gap.

DSL Syntax (v0.41.0):
    question Q-001 "Which approval workflow applies to high-value invoices?":
      blocks: [RULE-A-002, ST-014]
      raised_by: reviewer
      status: open
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .location import SourceLocation


class QuestionStatus(StrEnum):
    """Resolution status of a question."""

    OPEN = "open"
    RESOLVED = "resolved"
    DEFERRED = "deferred"


class QuestionSpec(BaseModel):
    """
    Typed specification gap that blocks artefacts until resolved.

    Questions make unknowns explicit.  They reference the artefacts they
    block (rules or stories by ID) so the system can track which parts
    of the spec are incomplete.

    DSL Syntax:
        question Q-001 "Which approval workflow applies?":
          blocks: [RULE-A-002, ST-014]
          raised_by: reviewer
          status: open

    Attributes:
        question_id: Stable identifier (e.g., Q-001)
        title: Short human-readable description of the gap
        description: Optional longer context
        blocks: List of artefact IDs this question blocks
        raised_by: Who raised the question (persona or role name)
        status: Resolution status (open, resolved, deferred)
        resolution: Answer text once resolved
    """

    question_id: str = Field(..., description="Stable identifier (e.g., Q-001)")
    title: str = Field(..., description="Short description of the gap")
    description: str | None = Field(default=None, description="Longer context")
    blocks: list[str] = Field(default_factory=list, description="Artefact IDs this blocks")
    raised_by: str | None = Field(default=None, description="Who raised this question")
    status: QuestionStatus = Field(default=QuestionStatus.OPEN, description="Resolution status")
    resolution: str | None = Field(default=None, description="Answer text once resolved")
    source: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)
