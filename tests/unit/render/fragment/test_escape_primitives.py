"""Tests for the escape-hatch primitives (RawHTML, Slot)."""

import dataclasses

import pytest

from dazzle.render.fragment.escape import RawHTML, Slot


def test_raw_html_holds_string() -> None:
    r = RawHTML("<div>already rendered</div>")
    assert r.html == "<div>already rendered</div>"


def test_raw_html_rejects_none() -> None:
    with pytest.raises(TypeError):
        RawHTML(None)  # type: ignore[arg-type]


def test_slot_named() -> None:
    s = Slot(name="dynamic_region")
    assert s.name == "dynamic_region"


def test_slot_rejects_invalid_name() -> None:
    with pytest.raises(ValueError, match="invalid slot name"):
        Slot(name="dynamic region")


def test_raw_html_is_frozen() -> None:
    r = RawHTML("<p/>")
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.html = "<div/>"  # type: ignore[misc]
