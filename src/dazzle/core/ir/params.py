"""Runtime parameter specification types for DAZZLE IR.

ParamRef is globally JSON-serializable: stdlib ``json.dumps()`` will
never crash on a ParamRef object, regardless of where it appears in
the object graph.  This is achieved by patching ``json.JSONEncoder.default``
at import time — a deliberate design choice so that every code path
(Pydantic, FastAPI, spec versioning, pg_backend) handles ParamRef
transparently without ``default=str`` annotations.
"""

from __future__ import annotations  # required: forward self-reference in class definitions

import json
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
    """Reference to a runtime parameter, used in place of literal values.

    Globally JSON-serializable: the module-level encoder patch ensures
    ``json.dumps(obj_containing_paramref)`` always works, serializing
    ParamRef as ``{"$param": key, "default": default}``.
    """

    model_config = ConfigDict(frozen=True)

    key: str
    param_type: str
    default: Any

    def resolve(self) -> Any:
        """Return the default value — use when a concrete value is needed."""
        return self.default


# ---------------------------------------------------------------------------
# Global JSON encoder patch — makes ParamRef serializable everywhere
# ---------------------------------------------------------------------------
_original_default = json.JSONEncoder.default


def _paramref_aware_default(self: json.JSONEncoder, o: Any) -> Any:
    """Extended JSON encoder that handles ParamRef (and falls through for others)."""
    if isinstance(o, ParamRef):
        return {"$param": o.key, "default": o.default}
    return _original_default(self, o)


json.JSONEncoder.default = _paramref_aware_default  # type: ignore[method-assign,unused-ignore]
