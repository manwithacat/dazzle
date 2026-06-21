"""Shared identity-display helper for specs / graph nodes.

Centralizes the ``getattr(x, "name", None) or getattr(x, "id", ...)`` fallback
that call sites re-derived because ``PersonaSpec`` identity is ``.id`` not ``.name``
(a known footgun) while most other specs/nodes carry ``.name``. One accessor means
the footgun lives in one place instead of being copy-pasted defensively.

Two orderings, one helper (#1442):
- ``prefer="name"`` (default): ``.name`` then ``.id`` — most specs/graph nodes.
- ``prefer="id"``: ``.id`` then ``.name`` — ``PersonaSpec`` and anything whose
  ``.id`` is the canonical identity and ``.name`` is a display label.
"""

from typing import Literal, overload


@overload
def spec_display_id(
    spec: object, default: str = ..., *, prefer: Literal["name", "id"] = ...
) -> str: ...
@overload
def spec_display_id(
    spec: object, default: None, *, prefer: Literal["name", "id"] = ...
) -> str | None: ...
def spec_display_id(
    spec: object,
    default: str | None = "unknown",
    *,
    prefer: Literal["name", "id"] = "name",
) -> str | None:
    """Best display id for a spec/node, then ``default``.

    ``prefer`` chooses the attribute order: ``"name"`` (default) tries ``.name``
    first, ``"id"`` tries ``.id`` first (the ``PersonaSpec`` orientation). Pass
    ``default=None`` to preserve the "None when both absent" behaviour some callers
    rely on; the str default ("unknown") suits human-facing labels and types as
    ``str`` via the overloads.
    """
    first, second = ("id", "name") if prefer == "id" else ("name", "id")
    return getattr(spec, first, None) or getattr(spec, second, None) or default
