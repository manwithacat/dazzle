"""Tests for layout primitives — Stack, Row, Split, Grid."""

import pytest

from dazzle.render.fragment.primitives.layout import Grid, Row, Split, Stack


def test_stack_holds_children() -> None:
    s = Stack(children=(_dummy("a"), _dummy("b")))
    assert len(s.children) == 2


def test_stack_rejects_empty_children() -> None:
    with pytest.raises(ValueError, match="at least one child"):
        Stack(children=())


def test_row_default_gap() -> None:
    r = Row(children=(_dummy("x"),))
    assert r.gap == "md"


def test_row_invalid_gap() -> None:
    with pytest.raises(ValueError, match="invalid gap"):
        Row(children=(_dummy("x"),), gap="ginormous")  # type: ignore[arg-type]


def test_split_two_panels() -> None:
    s = Split(start=_dummy("L"), end=_dummy("R"))
    assert s.start is not None
    assert s.end is not None


def test_grid_columns_clamp() -> None:
    with pytest.raises(ValueError, match="columns must be"):
        Grid(children=(_dummy("a"),), columns=0)
    with pytest.raises(ValueError, match="columns must be"):
        Grid(children=(_dummy("a"),), columns=13)


def test_split_invalid_ratio() -> None:
    with pytest.raises(ValueError, match="invalid ratio"):
        Split(start=_dummy("L"), end=_dummy("R"), ratio="2:3")  # type: ignore[arg-type]


def test_row_invalid_align() -> None:
    with pytest.raises(ValueError, match="invalid align"):
        Row(children=(_dummy("x"),), align="middle")  # type: ignore[arg-type]


def test_grid_rejects_empty_children() -> None:
    with pytest.raises(ValueError, match="at least one child"):
        Grid(children=())


def _dummy(label: str):
    """Stand-in primitive for layout-children testing.

    Layout primitives accept any Fragment in their `children` field; until
    the Fragment union is declared in Task 16, we use a frozen dataclass
    placeholder that satisfies the structural type expected.
    """
    from dazzle.render.fragment.escape import RawHTML

    return RawHTML(html=f"<span>{label}</span>")
