"""Unit tests for the INTERACTION_WALK base types.

Exercises :class:`InteractionResult`, the :class:`Interaction`
protocol, and :func:`run_walk` without touching Playwright — each
test uses a stub page and a stub interaction so we can verify the
composition shape independently of the live-browser integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dazzle.testing.ux.interactions import (
    Interaction,
    InteractionResult,
    run_walk,
)


@dataclass
class _StubInteraction:
    """Minimal Interaction implementation for testing the base loop."""

    name: str
    _passed: bool = True
    _reason: str = ""

    def execute(self, page: Any) -> InteractionResult:
        return InteractionResult(name=self.name, passed=self._passed, reason=self._reason)


class _FailingInteraction:
    name = "failing"

    def execute(self, page: Any) -> InteractionResult:
        return InteractionResult(name=self.name, passed=False, reason="boom")


class _RaisingInteraction:
    name = "raises"

    def execute(self, page: Any) -> InteractionResult:
        raise RuntimeError("catastrophic")


class TestInteractionResult:
    def test_pass_default(self) -> None:
        r = InteractionResult(name="x", passed=True)
        assert r.passed
        assert r.reason == ""
        assert r.evidence == {}

    def test_fail_with_reason_and_evidence(self) -> None:
        r = InteractionResult(
            name="drag",
            passed=False,
            reason="card didn't move",
            evidence={"dx": 0, "dy": 0},
        )
        assert not r.passed
        assert r.reason == "card didn't move"
        assert r.evidence["dx"] == 0


class TestInteractionProtocol:
    def test_stub_matches_protocol(self) -> None:
        stub = _StubInteraction(name="x")
        # runtime_checkable on the Protocol means isinstance works.
        assert isinstance(stub, Interaction)

    def test_non_interaction_fails_isinstance(self) -> None:
        class NoExecute:
            name = "nope"

        assert not isinstance(NoExecute(), Interaction)


class TestRunWalk:
    def test_runs_in_order_returns_all_results(self) -> None:
        walk: list[Interaction] = [
            _StubInteraction(name="a"),
            _StubInteraction(name="b"),
            _StubInteraction(name="c"),
        ]
        results = run_walk(page=None, walk=walk)
        assert [r.name for r in results] == ["a", "b", "c"]
        assert all(r.passed for r in results)

    def test_does_not_short_circuit_on_failure(self) -> None:
        walk: list[Interaction] = [
            _FailingInteraction(),
            _StubInteraction(name="b"),
        ]
        results = run_walk(page=None, walk=walk)
        assert [r.name for r in results] == ["failing", "b"]
        assert not results[0].passed
        assert results[1].passed

    def test_exception_propagates(self) -> None:
        # Genuine errors (page closed, etc.) should propagate — only
        # assertion failures are suppressed into results.
        walk: list[Interaction] = [_RaisingInteraction()]
        import pytest

        with pytest.raises(RuntimeError, match="catastrophic"):
            run_walk(page=None, walk=walk)

    def test_empty_walk_returns_empty_list(self) -> None:
        assert run_walk(page=None, walk=[]) == []
