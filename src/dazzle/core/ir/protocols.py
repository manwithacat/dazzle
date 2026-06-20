"""Read-only structural protocols for IR types.

These ``typing.Protocol`` classes expose the narrow attribute subset
each non-core layer actually reads on an IR object. They exist so that
``dazzle.http.runtime.*`` and ``dazzle.render.*`` can declare their
contracts against the IR without importing the concrete Pydantic
classes from ``dazzle.core.ir.appspec`` / ``surfaces`` / ``domain`` /
etc. — a 30-importer fan-in that the smells run (#1086 pattern P5)
identified as the codebase's biggest change-amplifier.

Layer policy (enforced by the future #1095 gate):

- Concrete ``dazzle.core.ir.*`` imports are allowed inside
  ``dazzle.core/`` and ``dazzle.http.specs/`` (the IR→runtime bridge).
- Everywhere else, import from ``dazzle.core.ir.protocols`` instead.

These protocols are structural (no ``@runtime_checkable``) — mypy alone
enforces conformance, so existing IR classes implement them
automatically without needing to declare inheritance. Adding a new
attribute to a concrete class never breaks the protocol; removing one
fails mypy at every consumer that reads it.

Workstream C1 ships ``SurfaceLike`` only — the renderers are the first
caller subset. ``EntityLike``, ``FieldLike``, ``PersonaLike``,
``WorkspaceLike`` etc. land in C2 (#1093) as their callers are
migrated, with each protocol scoped to the actual attrs used.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

# Re-export SurfaceMode here so consumers reading ``surface.mode`` can
# compare values against canonical enum members without reaching back
# to the concrete ``dazzle.core.ir.surfaces`` module. This keeps the
# value-enum contract co-located with the protocol that exposes it.
from dazzle.core.ir.surfaces import SurfaceMode

__all__ = ["SurfaceLike", "SurfaceMode"]


@runtime_checkable
class SurfaceLike(Protocol):
    """Minimal read-only surface contract used by renderers.

    Currently scoped to the four attrs read by
    ``dazzle.http.runtime.renderers.fragment`` /
    ``fragment_adapter`` and ``dazzle.render.dispatch``. Concrete
    ``dazzle.core.ir.surfaces.SurfaceSpec`` instances satisfy it
    structurally — no inheritance declaration needed.

    Extending the contract: if a renderer (or any new consumer in
    ``back/runtime/renderers/``) starts reading another attribute,
    add it here rather than reaching back to the concrete
    ``SurfaceSpec`` import. That's the whole point of the facade.
    """

    @property
    def name(self) -> str: ...

    @property
    def title(self) -> str | None: ...

    @property
    def mode(self) -> SurfaceMode: ...

    @property
    def render(self) -> str | None: ...
