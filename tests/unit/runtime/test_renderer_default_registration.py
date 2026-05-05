"""Default Jinja and Fragment renderers register at startup."""

import pytest

from dazzle.render.fragment.errors import PrimitiveRegistrationError
from dazzle.render.fragment.renderer import FragmentRenderer
from dazzle_back.runtime.renderers.init import register_default_renderers
from dazzle_back.runtime.services import RuntimeServices


def test_register_default_renderers_adds_jinja_and_fragment() -> None:
    services = RuntimeServices()
    register_default_renderers(services)
    assert sorted(services.renderer_registry.registered_names()) == ["fragment", "jinja"]


def test_fragment_handler_is_a_FragmentRenderer() -> None:
    services = RuntimeServices()
    register_default_renderers(services)
    handler = services.renderer_registry.resolve("fragment")
    assert isinstance(handler, FragmentRenderer)


def test_default_registration_is_not_idempotent() -> None:
    """Calling twice on the same services raises (registry rejects duplicates)."""
    services = RuntimeServices()
    register_default_renderers(services)
    with pytest.raises(PrimitiveRegistrationError):
        register_default_renderers(services)
