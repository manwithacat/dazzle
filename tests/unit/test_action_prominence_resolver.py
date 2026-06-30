"""Tests for the 3a action-prominence default-flip resolver (#1491).

`resolve_action_prominence` keeps the top-K workspace heading actions prominent
by declaration order and demotes the tail to overflow, so an action-heavy heading
declutters by default. A within-budget heading is a no-op (empty overflow).
"""

from __future__ import annotations

from dazzle.page.runtime.action_prominence_resolver import resolve_action_prominence


def _actions(n: int) -> list[dict[str, str]]:
    return [{"label": f"a{i}", "route": f"/{i}"} for i in range(n)]


def test_within_budget_is_a_noop() -> None:
    for n in (0, 1, 2, 3):
        primary, overflow = resolve_action_prominence(_actions(n))
        assert len(primary) == n
        assert overflow == []


def test_over_budget_demotes_tail_preserving_order() -> None:
    primary, overflow = resolve_action_prominence(_actions(5))
    assert [a["label"] for a in primary] == ["a0", "a1", "a2"]
    assert [a["label"] for a in overflow] == ["a3", "a4"]


def test_custom_budget() -> None:
    primary, overflow = resolve_action_prominence(_actions(4), budget=2)
    assert len(primary) == 2
    assert len(overflow) == 2


def test_zero_or_negative_budget_overflows_everything() -> None:
    primary, overflow = resolve_action_prominence(_actions(3), budget=0)
    assert primary == []
    assert len(overflow) == 3
    # negative is clamped to 0, not used as a slice index
    primary2, overflow2 = resolve_action_prominence(_actions(3), budget=-2)
    assert primary2 == []
    assert len(overflow2) == 3


def test_does_not_mutate_input() -> None:
    src = _actions(5)
    resolve_action_prominence(src)
    assert len(src) == 5  # returned lists are copies
