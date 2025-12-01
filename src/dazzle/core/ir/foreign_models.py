"""
Foreign model types for DAZZLE IR.

This module contains foreign model specifications representing
data owned by external services.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .fields import FieldSpec


class ForeignConstraintKind(str, Enum):
    """Constraint types for foreign models."""

    READ_ONLY = "read_only"
    EVENT_DRIVEN = "event_driven"
    BATCH_IMPORT = "batch_import"


class ForeignConstraint(BaseModel):
    """
    Constraint on a foreign model.

    Attributes:
        kind: Type of constraint
        options: Additional constraint options
    """

    kind: ForeignConstraintKind
    options: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class ForeignModelSpec(BaseModel):
    """
    Specification for a foreign (external) data model.

    Foreign models represent data owned by external services.

    Attributes:
        name: Foreign model name
        title: Human-readable title
        service_ref: Reference to service this model comes from
        key_fields: Fields that form the key
        constraints: List of constraints
        fields: List of field specifications
    """

    name: str
    title: str | None = None
    service_ref: str
    key_fields: list[str]
    constraints: list[ForeignConstraint] = Field(default_factory=list)
    fields: list[FieldSpec] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)

    def get_field(self, name: str) -> FieldSpec | None:
        """Get field by name."""
        for field in self.fields:
            if field.name == name:
                return field
        return None
