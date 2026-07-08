"""#1558 (3c → L4): gated_row_transitions — the single current-state gating rule."""

from dazzle.render.context import TransitionContext
from dazzle.render.fragment.state_affordance import gated_row_transitions


def _t(frm, to):
    return TransitionContext(from_state=frm, to_state=to, label=to.title(), api_url="/x")


def test_only_transitions_from_current_state():
    ts = [_t("open", "in_progress"), _t("in_progress", "resolved")]
    out = gated_row_transitions(ts, "open")
    assert [t.to_state for t in out] == ["in_progress"]


def test_wildcard_from_any_state():
    ts = [_t("open", "in_progress"), _t("*", "open")]
    out = gated_row_transitions(ts, "resolved")
    assert [t.to_state for t in out] == ["open"]  # only the wildcard reopen


def test_empty_current_state_yields_nothing():
    ts = [_t("open", "in_progress")]
    assert gated_row_transitions(ts, "") == []


def test_unknown_state_yields_only_wildcards():
    ts = [_t("open", "in_progress"), _t("*", "archived")]
    assert [t.to_state for t in gated_row_transitions(ts, "weird")] == ["archived"]
