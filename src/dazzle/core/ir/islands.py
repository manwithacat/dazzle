"""
UI Island types for DAZZLE IR.

Self-contained client-side interactive components embedded
within server-rendered htmx pages.

DSL Syntax:

    island task_chart "Task Progress Chart":
      entity: Task
      src: "islands/task-chart/index.js"
      fallback: "Loading task chart..."
      prop chart_type: str = "bar"
      prop date_range: str = "30d"
      event chart_clicked:
        detail: [task_id, series]
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class IslandPropSpec(BaseModel):
    """A typed property passed to an island component."""

    name: str
    type: str = "str"  # str, int, bool, float
    default: str | int | float | bool | None = None

    model_config = ConfigDict(frozen=True)


class IslandEventSpec(BaseModel):
    """A CustomEvent schema an island may emit."""

    name: str
    detail_fields: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class IslandSpec(BaseModel):
    """
    A UI island definition for client-side interactive components.

    Attributes:
        name: Island identifier
        title: Human-readable title
        entity: Optional entity reference for auto-generated CRUD API
        src: JS entry point (defaults to /static/islands/{name}/index.js)
        fallback: Server-rendered fallback content shown before JS loads
        props: Typed key-value properties passed as data-island-props JSON
        events: CustomEvent schemas the island may emit
    """

    name: str
    title: str | None = None
    entity: str | None = None
    src: str | None = None
    fallback: str | None = None
    props: list[IslandPropSpec] = Field(default_factory=list)
    events: list[IslandEventSpec] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)
