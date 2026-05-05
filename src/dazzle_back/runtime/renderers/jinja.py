"""Jinja renderer adapter — wraps the existing template-rendering path.

This adapter exists so the renderer registry has a uniform interface across
Jinja, Fragment, and any future renderer (PDF, native). The Plan 2 scope
deliberately does NOT route requests through the registry — Jinja remains
the request-time default. This adapter is a placeholder ensuring
`register_default_renderers` produces a complete registry.
"""

from typing import Any


class JinjaRenderer:
    """Stub adapter for the existing Jinja rendering path.

    Plan 2 registers this so the registry has a `"jinja"` entry; the actual
    Jinja invocation continues to live in the legacy rendering code. Plan 3
    connects the registry to the request path, at which point this adapter
    will gain a real `render(fragment, ctx)` method that dispatches to the
    existing template rendering.
    """

    def render(self, fragment: Any, ctx: Any | None = None) -> str:
        raise NotImplementedError(
            "JinjaRenderer.render is not yet wired up; Plan 2 registers the "
            "adapter for completeness but does not route requests through it. "
            "The legacy Jinja rendering path remains active."
        )
