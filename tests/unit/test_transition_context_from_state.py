"""#1558 (3c → L4): TransitionContext carries from_state so downstream can gate
transition affordances by the record's current state."""

from dazzle.render.context import TransitionContext


def test_transition_context_carries_from_state():
    t = TransitionContext(from_state="open", to_state="in_progress", label="Start", api_url="/x")
    assert t.from_state == "open"


def test_from_state_defaults_empty():
    t = TransitionContext(to_state="done", label="Done")
    assert t.from_state == ""
