"""Per-subtype surface dispatch for `subtype_panel:` blocks (#1217 Phase 3e.v).

Given a section that carries a `subtype_panel:` block + the current row's
``kind`` value, return the per-subtype surface to render inline (or None
if no branch matches).

This is the lookup primitive. The renderer integration that actually
substitutes the resolved surface's content for the parent section's
content lands in a follow-up.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dazzle.core.ir.appspec_queries import get_surface

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec, SurfaceSection, SurfaceSpec


def resolve_subtype_panel_surface(
    section: SurfaceSection,
    row_kind: str | None,
    appspec: AppSpec,
) -> SurfaceSpec | None:
    """Look up the surface a subtype_panel section should render for ``row_kind``.

    Returns None when:
    - The section has no subtype_panel block (caller should render normally).
    - row_kind is None (caller should render normally — incoming row has no kind).
    - No branch matches row_kind (caller should render normally — handles
      W_SUBTYPE_PANEL_INCOMPLETE gracefully without crashing).
    - The named include_surface is not found in the appspec (defensive — linker
      rule 9 validates this but defence-in-depth is cheap).

    Returns the matching SurfaceSpec when a branch's when_kind equals row_kind
    AND the named include_surface resolves.
    """
    if section.subtype_panel is None or row_kind is None:
        return None
    for branch in section.subtype_panel.branches:
        if branch.when_kind == row_kind:
            return get_surface(appspec, branch.include_surface)
    return None
