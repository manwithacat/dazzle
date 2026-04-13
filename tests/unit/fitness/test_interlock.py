"""Tests for the EXPECT-before-ACTION interlock (v1 fitness task 5)."""

from __future__ import annotations

import pytest

from dazzle.fitness.interlock import InterlockError, interlocked_tool_call


class _NoExpect:
    """Stub ledger with no intent recorded."""

    def current_step(self) -> None:
        return None


class _WithExpect:
    """Stub ledger with intent recorded."""

    def __init__(self) -> None:
        self.observed: str | None = None

    def current_step(self) -> object:
        class _S:
            expected = "the button is clicked"

        return _S()

    def record_observation(self, step: int, observed: str) -> None:
        self.observed = observed


def test_interlock_rejects_when_no_expect() -> None:
    def tool(x: int) -> int:
        return x + 1

    with pytest.raises(InterlockError, match="no EXPECT"):
        interlocked_tool_call(_NoExpect(), tool, {"x": 1})


def test_interlock_passes_through_when_expect_present() -> None:
    ledger = _WithExpect()

    def tool(x: int) -> int:
        return x + 1

    result = interlocked_tool_call(ledger, tool, {"x": 1})
    assert result == 2
    # The interlock does NOT call record_observation — that's the ledger's
    # observe_step's job. It only guards the pre-condition.
    assert ledger.observed is None
