"""Right-by-default resolution for a list surface's `peek:` mode (#1494, 2c).

Mirrors the #1492 `resolve_region_display_mode` pattern: an explicit author value
is authoritative; an *unset* surface (`peek_unset`) routes through the default
step. The default is staged — **Slice 1 keeps it `off`** (byte-stable on the
fleet); the Slice-4 default-flip makes an unset surface whose entity has a detail
surface resolve to `expand` (the 2c level-4 right-by-default move).
"""

from __future__ import annotations

from typing import Any

from dazzle.core.ir import PeekMode


def resolve_peek_mode(surface: Any, entity: Any = None) -> PeekMode:
    """Resolve the effective `peek:` mode for a list surface.

    - Explicit author value (`surface.peek is not None`) wins — incl. `peek: off`.
    - Unset (`peek is None`) → the default. **Slice 1: always `off`** (no
      behaviour change). The Slice-4 flip will make this `expand` when *entity*
      has a detail surface.
    """
    explicit = getattr(surface, "peek", None)
    if explicit is not None:
        # Normalise to PeekMode (surface is duck-typed `Any`; `getattr` yields
        # `Any`, and a raw string value validates here too).
        return PeekMode(explicit)
    # Unset → default. Staged: off for now (Slice 1). The `entity` arg is the
    # seam the Slice-4 flip uses (detail-surface presence → expand).
    return PeekMode.OFF
