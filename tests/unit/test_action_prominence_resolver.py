"""Tests for the 3a action-prominence default-flip resolver (#1491).

`resolve_action_prominence` keeps the top-K workspace heading actions prominent
by declaration order and demotes the tail to overflow, so an action-heavy heading
declutters by default. A within-budget heading is a no-op (empty overflow).
"""

from __future__ import annotations

from dazzle.page.runtime.action_prominence_resolver import (
    resolve_action_prominence,
    resolve_action_prominence_by_usage,
)


def _actions(n: int) -> list[dict[str, str]]:
    return [{"label": f"a{i}", "route": f"/{i}"} for i in range(n)]


def _route(a: dict[str, str]) -> str:
    return a["route"]


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


# --- usage-weighted prominence (ADR-0050 3a → L4) ----------------------------


def test_by_usage_below_floor_is_byte_identical_to_declaration_order() -> None:
    """Cold start / thin signal: below min_samples → exactly the declared split."""
    src = _actions(5)
    usage = {"/0": 2, "/4": 3}  # total 5 < floor 10
    got = resolve_action_prominence_by_usage(src, usage, route_of=_route, min_samples=10)
    assert got == resolve_action_prominence(src, budget=3)


def test_by_usage_zero_usage_is_byte_identical() -> None:
    src = _actions(5)
    got = resolve_action_prominence_by_usage(src, {}, route_of=_route)
    assert got == resolve_action_prominence(src, budget=3)


def test_by_usage_above_floor_promotes_frequent_demotes_rare() -> None:
    """Above the floor: a heavily-used tail action is promoted; a rarely-used
    leading action demotes to overflow."""
    src = _actions(4)  # /0.. /3, declared order
    # /3 is by far the most used; /0 least. Floor met (total 30 >= 10).
    usage = {"/3": 20, "/2": 7, "/1": 3, "/0": 0}
    primary, overflow = resolve_action_prominence_by_usage(
        src, usage, route_of=_route, budget=3, min_samples=10
    )
    assert [a["route"] for a in primary] == ["/3", "/2", "/1"]
    assert [a["route"] for a in overflow] == ["/0"]


def test_by_usage_stable_sort_preserves_declared_order_on_ties() -> None:
    """Equal usage keeps declared order — protects the create-CTA-first ordering."""
    src = _actions(4)
    usage = {"/0": 5, "/1": 5, "/2": 5, "/3": 5}  # all tied, total 20 >= floor
    primary, overflow = resolve_action_prominence_by_usage(
        src, usage, route_of=_route, budget=3, min_samples=10
    )
    assert [a["route"] for a in primary] == ["/0", "/1", "/2"]
    assert [a["route"] for a in overflow] == ["/3"]
