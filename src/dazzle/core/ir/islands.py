"""
UI Island types for DAZZLE IR.

Self-contained client-side interactive components embedded
within server-rendered htmx pages.

DSL Syntax:

    island task_chart "Task Progress Chart":
      entity: Task
      src: "islands/task-chart/index.js"
      fallback: "Loading task chart..."
"""

from pydantic import BaseModel, ConfigDict


class IslandSpec(BaseModel):
    """
    A UI island definition for client-side interactive components.

    Attributes:
        name: Island identifier
        title: Human-readable title
        entity: Optional entity reference for auto-generated CRUD API
        src: JS entry point (defaults to /static/islands/{name}/index.js)
        fallback: Server-rendered fallback content shown before JS loads
    """

    name: str
    title: str | None = None
    entity: str | None = None
    src: str | None = None
    fallback: str | None = None

    model_config = ConfigDict(frozen=True)
