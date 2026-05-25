"""Tests for dazzle.result — Ok / Err / Result / UnwrapError."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from dazzle.result import Err, Ok, Result, UnwrapError

# ---------------------------------------------------------------------------
# Construction + field access
# ---------------------------------------------------------------------------


def test_ok_carries_value() -> None:
    assert Ok(42).value == 42


def test_err_carries_error() -> None:
    assert Err("oops").error == "oops"


# ---------------------------------------------------------------------------
# unwrap / unwrap_or
# ---------------------------------------------------------------------------


def test_ok_unwrap_returns_value() -> None:
    assert Ok(7).unwrap() == 7


def test_err_unwrap_raises_unwrap_error() -> None:
    e = Err("boom")
    with pytest.raises(UnwrapError) as exc_info:
        e.unwrap()
    assert exc_info.value.error == "boom"


def test_ok_unwrap_or_returns_value_default_unused() -> None:
    assert Ok(1).unwrap_or(99) == 1


def test_err_unwrap_or_returns_default() -> None:
    assert Err("boom").unwrap_or(99) == 99


# ---------------------------------------------------------------------------
# is_ok / is_err
# ---------------------------------------------------------------------------


def test_ok_is_ok_true_is_err_false() -> None:
    o = Ok(1)
    assert o.is_ok() is True
    assert o.is_err() is False


def test_err_is_ok_false_is_err_true() -> None:
    e = Err("x")
    assert e.is_ok() is False
    assert e.is_err() is True


# ---------------------------------------------------------------------------
# Match-pattern consumption
# ---------------------------------------------------------------------------


def test_match_pattern_ok_branch() -> None:
    match Ok(7):
        case Ok(value):
            assert value == 7
        case Err(_):
            pytest.fail("matched Err for Ok input")


def test_match_pattern_err_branch() -> None:
    match Err("nope"):
        case Ok(_):
            pytest.fail("matched Ok for Err input")
        case Err(error):
            assert error == "nope"


# ---------------------------------------------------------------------------
# Equality + identity
# ---------------------------------------------------------------------------


def test_ok_and_err_not_equal_across_types() -> None:
    assert Ok(1) != Err(1)
    assert Err(1) != Ok(1)


def test_ok_value_equality() -> None:
    assert Ok(1) == Ok(1)
    assert Ok(1) != Ok(2)


# ---------------------------------------------------------------------------
# Frozen + slots
# ---------------------------------------------------------------------------


def test_frozen_assignment_raises() -> None:
    o = Ok(1)
    with pytest.raises(FrozenInstanceError):
        o.value = 2  # type: ignore[misc]


def test_slots_no_dict() -> None:
    with pytest.raises(AttributeError):
        Ok(1).__dict__  # noqa: B018


# ---------------------------------------------------------------------------
# Public re-export surface
# ---------------------------------------------------------------------------


def test_public_imports_from_dazzle_root() -> None:
    """Ok, Err, Result, UnwrapError are importable from `dazzle` top-level."""
    from dazzle import Err as RootErr
    from dazzle import Ok as RootOk
    from dazzle import Result as RootResult
    from dazzle import UnwrapError as RootUnwrapError

    assert RootOk is Ok
    assert RootErr is Err
    assert RootResult is Result
    assert RootUnwrapError is UnwrapError
