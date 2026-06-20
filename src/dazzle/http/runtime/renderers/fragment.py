"""Fragment renderer adapter — uniform (surface, ctx) interface.

Wraps `dazzle.render.fragment.renderer.FragmentRenderer` so the renderer
registry stores adapters with a uniform shape across Jinja, Fragment, and
future renderers (cytoscape, PDF, etc.). The dispatcher (`dispatch_render`)
calls every registered handler with `(surface, ctx)` — adapters know how
to translate that into whatever the underlying renderer needs.

For the Fragment path: `FragmentSurfaceAdapter` builds a `Fragment` tree
from the IR + ctx, then `FragmentRenderer` emits HTML from the tree.
"""

from typing import Any

from dazzle.core.ir.protocols import SurfaceLike
from dazzle.render.fragment.renderer import FragmentRenderer


class FragmentSurfaceRenderer:
    """Adapter — exposes FragmentRenderer through a (surface, ctx) interface.

    Holds an internal FragmentRenderer instance and a FragmentSurfaceAdapter
    instance, both stateless and reusable across requests. Construction is
    cheap (no I/O); the registry stores one instance per app.
    """

    def __init__(self) -> None:
        # Deferred import — fragment_adapter imports SurfaceSpec, no cycle
        # but matches the convention used by other adapter modules.
        from dazzle.http.runtime.renderers.fragment_adapter import (
            FragmentSurfaceAdapter,
        )

        self._renderer = FragmentRenderer()
        self._surface_adapter = FragmentSurfaceAdapter()

    def render(self, surface: SurfaceLike, ctx: dict[str, Any]) -> str:
        fragment = self._surface_adapter.build(surface, ctx)
        return self._renderer.render(fragment)


# Backwards-compat alias: any caller still importing the bare
# FragmentRenderer from this module keeps working through Plan 5.
__all__ = ["FragmentSurfaceRenderer", "FragmentRenderer"]
