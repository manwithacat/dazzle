"""RendererRegistry contract tests."""

import pytest

from dazzle.render.fragment.errors import PrimitiveRegistrationError
from dazzle.render.fragment.registry import RendererRegistry


class _FakeRenderer:
    """Minimal stub satisfying the renderer protocol."""

    def render(self, fragment: object, ctx: object | None = None) -> str:
        return "<stub/>"


def test_register_and_resolve() -> None:
    registry = RendererRegistry()
    handler = _FakeRenderer()
    registry.register(name="stub", handler=handler)
    assert registry.resolve("stub") is handler


def test_duplicate_registration_rejected() -> None:
    registry = RendererRegistry()
    registry.register(name="dup", handler=_FakeRenderer())
    with pytest.raises(PrimitiveRegistrationError, match="already registered"):
        registry.register(name="dup", handler=_FakeRenderer())


def test_resolve_unknown_returns_none() -> None:
    registry = RendererRegistry()
    assert registry.resolve("absent") is None


def test_registered_names_listing() -> None:
    registry = RendererRegistry()
    registry.register(name="a", handler=_FakeRenderer())
    registry.register(name="b", handler=_FakeRenderer())
    assert sorted(registry.registered_names()) == ["a", "b"]
