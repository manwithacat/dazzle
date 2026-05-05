"""PrimitiveRegistry and @primitive decorator tests."""

from dataclasses import dataclass

import pytest

from dazzle.render.fragment.errors import PrimitiveRegistrationError
from dazzle.render.fragment.registry import PrimitiveRegistry, primitive


def test_register_and_resolve() -> None:
    registry = PrimitiveRegistry()

    @primitive(name="test_widget", registry=registry)
    @dataclass(frozen=True, slots=True)
    class TestWidget:
        label: str

    assert registry.resolve("test_widget") is TestWidget


def test_duplicate_registration_rejected() -> None:
    registry = PrimitiveRegistry()

    @primitive(name="dup", registry=registry)
    @dataclass(frozen=True, slots=True)
    class A:
        x: int = 0

    with pytest.raises(PrimitiveRegistrationError, match="already registered"):

        @primitive(name="dup", registry=registry)
        @dataclass(frozen=True, slots=True)
        class B:
            y: int = 0


def test_resolve_unknown_returns_none() -> None:
    registry = PrimitiveRegistry()
    assert registry.resolve("does_not_exist") is None


def test_registered_names_listing() -> None:
    registry = PrimitiveRegistry()

    @primitive(name="alpha", registry=registry)
    @dataclass(frozen=True, slots=True)
    class A:
        pass

    @primitive(name="beta", registry=registry)
    @dataclass(frozen=True, slots=True)
    class B:
        pass

    assert sorted(registry.registered_names()) == ["alpha", "beta"]


def test_registration_rejects_non_dataclass() -> None:
    registry = PrimitiveRegistry()
    with pytest.raises(PrimitiveRegistrationError, match="must be a dataclass"):

        @primitive(name="not_a_dataclass", registry=registry)
        class NotADataclass:
            pass
