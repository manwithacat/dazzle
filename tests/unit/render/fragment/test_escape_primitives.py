"""Tests for the escape-hatch primitives (RawHTML, Slot)."""

from dataclasses import FrozenInstanceError

import pytest

from dazzle.render.fragment.escape import RawHTML, Slot


def test_raw_html_holds_string() -> None:
    r = RawHTML("<div>already rendered</div>")
    assert r.html == "<div>already rendered</div>"


def test_raw_html_accepts_empty_string() -> None:
    """Empty verbatim is a valid emit, not a misuse."""
    r = RawHTML("")
    assert r.html == ""


def test_raw_html_rejects_none() -> None:
    with pytest.raises(TypeError):
        RawHTML(None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "name",
    ["a", "a1", "a_b", "region_2", "dynamic_region"],
)
def test_slot_accepts_valid_names(name: str) -> None:
    s = Slot(name=name)
    assert s.name == name


@pytest.mark.parametrize(
    "name",
    ["1foo", "Foo", "foo-bar", "_foo", "dynamic region", ""],
)
def test_slot_rejects_invalid_names(name: str) -> None:
    with pytest.raises(ValueError, match="invalid slot name"):
        Slot(name=name)


def test_slot_rejects_non_string_name() -> None:
    with pytest.raises(TypeError):
        Slot(name=42)  # type: ignore[arg-type]


def test_raw_html_is_frozen() -> None:
    r = RawHTML("<p/>")
    with pytest.raises(FrozenInstanceError):
        r.html = "<div/>"  # type: ignore[misc]
