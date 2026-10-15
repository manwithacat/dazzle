"""Tests for content primitives — Text, Heading, Icon, Badge, EmptyState, Skeleton."""

from collections.abc import Callable

import pytest

from dazzle.render.fragment.primitives.content import (
    Badge,
    EmptyState,
    Heading,
    Icon,
    Skeleton,
    Text,
)


@pytest.mark.parametrize(
    ("ctor", "match"),
    [
        pytest.param(lambda: Text("hello", tone="rainbow"), "invalid tone", id="text.tone"),  # type: ignore[arg-type]
        pytest.param(lambda: Heading("title", level=0), "level must be", id="heading.level_0"),
        pytest.param(lambda: Heading("title", level=7), "level must be", id="heading.level_7"),
        pytest.param(lambda: Icon(name="check", size="huge"), "invalid size", id="icon.size"),  # type: ignore[arg-type]
        pytest.param(
            lambda: Badge(label="bad", variant="purple"),  # type: ignore[arg-type]
            "invalid variant",
            id="badge.variant",
        ),
        pytest.param(lambda: Skeleton(lines=0), "lines must be", id="skeleton.lines_0"),
    ],
)
def test_rejects_invalid_value(ctor: Callable[[], object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        ctor()


@pytest.mark.parametrize(
    ("ctor", "expected"),
    [
        pytest.param(lambda: Text("hello"), {"tone": "default"}, id="text"),
        pytest.param(lambda: Heading("title"), {"level": 1}, id="heading"),
        pytest.param(lambda: Icon(name="check"), {"size": "md"}, id="icon"),
        pytest.param(
            lambda: EmptyState(title="Nothing here", description="Add an item"),
            {"action": None},
            id="empty_state",
        ),
        pytest.param(Skeleton, {"lines": 3}, id="skeleton"),
    ],
)
def test_defaults(ctor: Callable[[], object], expected: dict[str, object]) -> None:
    obj = ctor()
    assert {key: getattr(obj, key) for key in expected} == expected
