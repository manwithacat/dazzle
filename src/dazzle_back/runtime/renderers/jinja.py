"""Jinja renderer adapter — wraps the existing template-rendering path.

This adapter exists so the renderer registry has a uniform interface across
Jinja, Fragment, and any future renderer (PDF, native). Plan 3 Task 1
makes it real: ``render(surface, ctx)`` delegates to
``dazzle_ui.runtime.template_renderer.render_surface``, which builds a
minimal ``PageContext`` from the flat ctx dict and runs the existing
Jinja machinery.

The full request-time path in ``page_routes.py`` (auth, scope filtering,
persona overrides, drawer/fragment routing) is intentionally NOT
duplicated by this adapter. Callers that need those concerns continue to
use the legacy direct path. The adapter is for the typed-Fragment-first
conversion (Plan 3): a pure ``(SurfaceSpec, ctx) -> HTML`` entry point
that the renderer registry can dispatch to without dragging FastAPI
Request plumbing through the renderer protocol.
"""

from typing import Any

from dazzle.core.ir.surfaces import SurfaceSpec


class JinjaRenderer:
    """Real adapter — delegates to the legacy Jinja rendering path."""

    def render(self, surface: SurfaceSpec, ctx: dict[str, Any]) -> str:
        """Render ``surface`` to HTML using ``ctx`` as the data context.

        Currently supports ``mode == LIST``; further modes are added as
        Plan 3 advances. See ``render_surface`` for the recognised
        ``ctx`` keys.
        """
        from dazzle_ui.runtime.template_renderer import render_surface

        return render_surface(surface, ctx)
