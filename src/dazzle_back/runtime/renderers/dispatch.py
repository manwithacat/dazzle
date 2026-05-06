"""Dispatch helper: route a surface render through the right renderer.

Plan 5 simplified the dispatcher to a single uniform call. Every
registered renderer exposes `render(surface, ctx) -> str` via its adapter
(JinjaRenderer wraps the legacy template path; FragmentSurfaceRenderer
wraps the typed Fragment substrate). The dispatcher's only job is to
look up the handler by name and call it.
"""

from typing import Any

from dazzle.core.ir.surfaces import SurfaceSpec
from dazzle.render.fragment.errors import FragmentError
from dazzle_back.runtime.services import RuntimeServices


def dispatch_render(
    surface: SurfaceSpec,
    *,
    ctx: dict[str, Any],
    services: RuntimeServices,
) -> str:
    """Render `surface` using the renderer named by `surface.render`,
    or `"jinja"` if unset. Returns the HTML string.

    Raises FragmentError if the named renderer is not registered.
    """
    renderer_name = surface.render or "jinja"
    handler = services.renderer_registry.resolve(renderer_name)
    if handler is None:
        raise FragmentError(
            f"surface {surface.name!r}: unknown renderer {renderer_name!r}; "
            f"registered renderers: {sorted(services.renderer_registry.registered_names())}"
        )

    return handler.render(surface, ctx)
