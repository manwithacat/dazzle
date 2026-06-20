"""Default Fragment renderer registers at startup.

Post-#1051 (v0.67.85+) the legacy "jinja" renderer adapter is retired;
only the typed Fragment renderer is shipped as a default.
"""

import pytest

from dazzle.http.runtime.renderers.fragment import FragmentSurfaceRenderer
from dazzle.http.runtime.renderers.init import register_default_renderers
from dazzle.http.runtime.services import RuntimeServices
from dazzle.render.fragment.errors import PrimitiveRegistrationError


def test_register_default_renderers_adds_fragment() -> None:
    services = RuntimeServices()
    register_default_renderers(services)
    assert sorted(services.renderer_registry.registered_names()) == ["fragment"]


def test_fragment_handler_is_a_FragmentSurfaceRenderer() -> None:
    """Plan 5: registered handler is the (surface, ctx) adapter, not the
    bare Fragment-tree renderer. The dispatcher calls .render(surface, ctx)
    uniformly across renderers; the adapter does the IR→Fragment translation
    internally."""
    services = RuntimeServices()
    register_default_renderers(services)
    handler = services.renderer_registry.resolve("fragment")
    assert isinstance(handler, FragmentSurfaceRenderer)


def test_default_registration_is_not_idempotent() -> None:
    """Calling twice on the same services raises (registry rejects duplicates)."""
    services = RuntimeServices()
    register_default_renderers(services)
    with pytest.raises(PrimitiveRegistrationError):
        register_default_renderers(services)
