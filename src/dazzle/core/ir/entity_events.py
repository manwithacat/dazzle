"""Entity lifecycle event names shared by the runtime event bus and LLM triggers."""

from enum import StrEnum


class EntityEvent(StrEnum):
    """Entity lifecycle events emitted by CRUD services."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
