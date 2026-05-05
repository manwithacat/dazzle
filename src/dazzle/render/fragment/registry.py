"""Primitive registration — the extensibility seam.

Framework primitives are registered in `primitives/__init__.py` at module
load. App-local primitives use `@primitive(name="...")` in `app/ui/primitives/`,
registering against `RuntimeServices.primitive_registry` (Plan 2 wires this
up). The DSL `render: <name>` clause resolves through the registry.
"""

import dataclasses
from collections.abc import Callable
from typing import TypeVar

from dazzle.render.fragment.errors import PrimitiveRegistrationError

T = TypeVar("T", bound=type)


class PrimitiveRegistry:
    """Mutable registry mapping primitive names to dataclass types.

    Not thread-safe; registration happens at module import time before
    serving begins. Resolution is read-only at request time.
    """

    def __init__(self) -> None:
        self._types: dict[str, type] = {}

    def register(self, name: str, cls: type) -> None:
        if not dataclasses.is_dataclass(cls):
            raise PrimitiveRegistrationError(f"primitive {name!r} must be a dataclass; got {cls!r}")
        if name in self._types:
            existing = self._types[name]
            raise PrimitiveRegistrationError(
                f"primitive {name!r} already registered to {existing!r}; "
                f"cannot re-register to {cls!r}"
            )
        self._types[name] = cls

    def resolve(self, name: str) -> type | None:
        return self._types.get(name)

    def registered_names(self) -> list[str]:
        return list(self._types.keys())


# Module-level default registry for framework primitives. App-local primitives
# pass their own registry via the decorator's `registry=` argument or wire up
# through RuntimeServices in Plan 2.
DEFAULT_REGISTRY = PrimitiveRegistry()


def primitive(
    *,
    name: str,
    registry: PrimitiveRegistry | None = None,
) -> Callable[[T], T]:
    """Decorator: register a dataclass as a Fragment primitive under `name`.

    Usage:

        @primitive(name="aegismark_kanban_board")
        @dataclass(frozen=True, slots=True)
        class AegismarkKanbanBoard:
            columns: tuple[KanbanColumn, ...]
    """
    target = registry if registry is not None else DEFAULT_REGISTRY

    def decorator(cls: T) -> T:
        target.register(name, cls)
        return cls

    return decorator
