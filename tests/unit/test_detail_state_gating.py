"""#1558 (3c): the detail view offers only transitions valid from the record's
current state."""

from dazzle.http.runtime.page_routes import gate_detail_transitions
from dazzle.render.context import TransitionContext


def _t(frm, to):
    return TransitionContext(from_state=frm, to_state=to, label=to, api_url="/x")


def test_detail_transitions_gated_to_current_state():
    ts = [_t("open", "in_progress"), _t("in_progress", "resolved"), _t("*", "open")]
    out = gate_detail_transitions(ts, {"status": "resolved"}, "status")
    assert [t.to_state for t in out] == ["open"]  # only wildcard reopen from resolved


def test_detail_missing_status_field_yields_nothing():
    ts = [_t("open", "in_progress")]
    assert gate_detail_transitions(ts, {}, "status") == []
