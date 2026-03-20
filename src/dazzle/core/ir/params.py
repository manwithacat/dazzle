"""Runtime parameter specification types for DAZZLE IR."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ParamConstraints(BaseModel):
    """Validation constraints for a runtime parameter."""

    model_config = ConfigDict(frozen=True)

    min_value: float | None = None
    max_value: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    ordered: str | None = None  # "ascending" | "descending"
    range: list[float] | None = None  # [min, max] for list elements
    enum_values: list[str] | None = None
    pattern: str | None = None  # regex for string params


class ParamSpec(BaseModel):
    """Declaration of a runtime-configurable parameter."""

    model_config = ConfigDict(frozen=True)

    key: str
    param_type: str  # "int", "float", "bool", "str", "list[float]", "list[str]", "json"
    default: Any
    scope: Literal["system", "tenant", "user"]
    constraints: ParamConstraints | None = None
    description: str | None = None
    category: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    sensitive: bool = False


class ParamRef(BaseModel):
    """Reference to a runtime parameter, used in place of literal values."""

    model_config = ConfigDict(frozen=True)

    key: str
    param_type: str
    default: Any
