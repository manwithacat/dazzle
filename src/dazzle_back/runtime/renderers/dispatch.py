"""Dispatch helper: route a surface render through the right renderer."""

from typing import Any

from dazzle.core.ir.surfaces import SurfaceSpec
from dazzle.render.fragment.errors import FragmentError
from dazzle_back.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
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

    if renderer_name == "fragment":
        # Translate IR + ctx into a Fragment tree, then emit.
        fragment = FragmentSurfaceAdapter().build(surface, ctx)
        return handler.render(fragment)

    # Jinja and other (surface, ctx)-shaped renderers go directly.
    return handler.render(surface, ctx)
