"""Tests for content primitives — Text, Heading, Icon, Badge, EmptyState, Skeleton."""

import pytest

from dazzle.render.fragment.primitives.content import (
    Badge,
    EmptyState,
    Heading,
    Icon,
    Skeleton,
    Text,
)


def test_text_basic() -> None:
    t = Text("hello")
    assert t.body == "hello"
    assert t.tone == "default"


def test_text_invalid_tone() -> None:
    with pytest.raises(ValueError, match="invalid tone"):
        Text("hello", tone="rainbow")  # type: ignore[arg-type]


def test_heading_level_clamp() -> None:
    with pytest.raises(ValueError, match="level must be"):
        Heading("title", level=0)
    with pytest.raises(ValueError, match="level must be"):
        Heading("title", level=7)


def test_heading_default_level() -> None:
    h = Heading("title")
    assert h.level == 1


def test_icon_name() -> None:
    i = Icon(name="check")
    assert i.name == "check"
    assert i.size == "md"


def test_icon_invalid_size() -> None:
    with pytest.raises(ValueError, match="invalid size"):
        Icon(name="check", size="huge")  # type: ignore[arg-type]


def test_badge_variant() -> None:
    b = Badge(label="new", variant="success")
    assert b.variant == "success"


def test_badge_invalid_variant() -> None:
    with pytest.raises(ValueError, match="invalid variant"):
        Badge(label="bad", variant="purple")  # type: ignore[arg-type]


def test_empty_state_required_fields() -> None:
    e = EmptyState(title="Nothing here", description="Add an item to get started")
    assert e.title == "Nothing here"
    assert e.action is None


def test_skeleton_default_lines() -> None:
    s = Skeleton()
    assert s.lines == 3


def test_skeleton_invalid_lines() -> None:
    with pytest.raises(ValueError, match="lines must be"):
        Skeleton(lines=0)
