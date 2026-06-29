"""Right-by-default resolution for a list surface's `peek:` mode (#1494, 2c).

Mirrors the #1492 `resolve_region_display_mode` pattern: an explicit author value
is authoritative; an *unset* surface (`peek is None`) routes through the default
step. **The default is now `expand`** when the entity has a detail surface — the
2c level-4 right-by-default move (#1494 default-flip): a list row whose entity is
drillable gets the inline expand-in-place chevron by default, so action-proximate
detail no longer needs an opt-in `peek: expand`. An entity with no detail target
stays `off` (the row has no detail body to expand into — the render also gates the
chevron on `detail_url_template`, so this is belt-and-braces).
"""

from __future__ import annotations

from typing import Any

from dazzle.core.ir import PeekMode


def resolve_peek_mode(surface: Any, entity: Any = None) -> PeekMode:
    """Resolve the effective `peek:` mode for a list surface.

    - Explicit author value (`surface.peek is not None`) wins — incl. `peek: off`.
    - Unset (`peek is None`) → the default-flip: `expand` when the entity has a
      detail surface (the drill target the panel expands into), else `off`.

    `entity` is the list surface's backing entity; `None` (no entity context) →
    `off`. In the runtime every entity reaching this resolver carries a generated
    detail route (`/app/{slug}/{id}`), so a list row is drillable ⇒ peekable — the
    right-by-default case. The level-4 adaptive property: the author writes
    nothing and gets action-proximate detail wherever a detail surface exists.
    """
    explicit = getattr(surface, "peek", None)
    if explicit is not None:
        # Normalise to PeekMode (surface is duck-typed `Any`; `getattr` yields
        # `Any`, and a raw string value validates here too).
        return PeekMode(explicit)
    # Unset → the default-flip. The entity's presence is the detail-surface
    # signal (every list entity is drillable in the runtime); no entity → off.
    return PeekMode.EXPAND if entity is not None else PeekMode.OFF
