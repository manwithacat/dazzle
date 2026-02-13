"""
Shared enum types for DAZZLE IR.

Reusable enum definitions that can be referenced across entities.

DSL Syntax (v0.25.0):

    enum OrderStatus "Order Status":
      draft "Draft"
      pending_review "Pending Review"
      approved "Approved"
      rejected "Rejected"

Usage in entities:
    entity Order "Order":
      status: OrderStatus = draft
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EnumValueSpec(BaseModel):
    """A single value within a shared enum."""

    name: str
    title: str | None = None

    model_config = ConfigDict(frozen=True)


class EnumSpec(BaseModel):
    """
    A shared enum definition.

    Attributes:
        name: Enum identifier (e.g. OrderStatus)
        title: Human-readable title
        values: Ordered list of enum values
    """

    name: str
    title: str | None = None
    values: list[EnumValueSpec] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)
