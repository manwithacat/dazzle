"""RuntimeServices carries the renderer and primitive registries."""

from dazzle.http.runtime.services import RuntimeServices
from dazzle.render.fragment.registry import PrimitiveRegistry, RendererRegistry


def test_runtime_services_has_renderer_registry() -> None:
    services = RuntimeServices()
    assert isinstance(services.renderer_registry, RendererRegistry)


def test_runtime_services_has_primitive_registry() -> None:
    services = RuntimeServices()
    assert isinstance(services.primitive_registry, PrimitiveRegistry)


def test_runtime_services_registries_are_independent_per_instance() -> None:
    """Each RuntimeServices instance gets its own registry — no shared state."""
    a = RuntimeServices()
    b = RuntimeServices()
    a.renderer_registry.register(name="x", handler=object())
    assert b.renderer_registry.resolve("x") is None
