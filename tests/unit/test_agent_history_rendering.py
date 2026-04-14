"""Tests for DazzleAgent history rendering (cycle 197)."""

from __future__ import annotations

from dazzle.agent.core import _format_history_line, _is_stuck
from dazzle.agent.models import ActionResult, ActionType, AgentAction, PageState, Step


def _make_step(
    step_number: int,
    action_type: ActionType,
    target: str = "",
    result_kwargs: dict | None = None,
) -> Step:
    result_kwargs = result_kwargs or {}
    return Step(
        state=PageState(url="http://localhost/", title="t"),
        action=AgentAction(type=action_type, target=target),
        result=ActionResult(message="", **result_kwargs),
        step_number=step_number,
        duration_ms=10.0,
        prompt_text="",
        response_text="",
        tokens_used=0,
    )


class TestFormatHistoryLine:
    def test_no_state_change_is_explicit_and_loud(self) -> None:
        step = _make_step(
            3,
            ActionType.CLICK,
            target="a.stuck",
            result_kwargs={
                "from_url": "http://localhost/app",
                "to_url": "http://localhost/app",
                "state_changed": False,
            },
        )
        line = _format_history_line(step)
        assert "NO state change" in line
        assert "still at http://localhost/app" in line

    def test_url_transition_shown_on_navigate(self) -> None:
        step = _make_step(
            4,
            ActionType.CLICK,
            target="a.good",
            result_kwargs={
                "from_url": "http://localhost/app",
                "to_url": "http://localhost/app/contacts/1",
                "state_changed": True,
            },
        )
        line = _format_history_line(step)
        assert "http://localhost/app" in line
        assert "http://localhost/app/contacts/1" in line
        assert "→" in line  # unicode arrow between from_url and to_url

    def test_state_changed_same_url_shows_state_changed(self) -> None:
        """Type into a field doesn't change URL but changes DOM — generic signal."""
        step = _make_step(
            5,
            ActionType.TYPE,
            target="#field-email",
            result_kwargs={
                "from_url": "http://localhost/app/form",
                "to_url": "http://localhost/app/form",
                "state_changed": True,
            },
        )
        line = _format_history_line(step)
        assert "state changed" in line
        assert "NO state change" not in line

    def test_console_errors_appended(self) -> None:
        step = _make_step(
            6,
            ActionType.CLICK,
            target="button.broken",
            result_kwargs={
                "from_url": "/a",
                "to_url": "/b",
                "state_changed": True,
                "console_errors_during_action": [
                    "TypeError: undefined property at line 42",
                    "ReferenceError: foo is not defined",
                ],
            },
        )
        line = _format_history_line(step)
        assert "[+2 console errors:" in line
        assert "TypeError: undefined property" in line

    def test_single_console_error_singular(self) -> None:
        step = _make_step(
            7,
            ActionType.CLICK,
            target="button.x",
            result_kwargs={
                "from_url": "/a",
                "to_url": "/b",
                "state_changed": True,
                "console_errors_during_action": ["Uncaught Error"],
            },
        )
        line = _format_history_line(step)
        assert "[+1 console error:" in line
        assert "errors" not in line  # singular form

    def test_error_path_shows_error_not_state(self) -> None:
        step = _make_step(
            8,
            ActionType.CLICK,
            target="button.missing",
            result_kwargs={"error": "Selector not found", "state_changed": None},
        )
        line = _format_history_line(step)
        assert "ERROR" in line
        assert "Selector not found" in line

    def test_legacy_rendering_when_state_fields_none(self) -> None:
        """Tool invocations come through with state_changed=None + message set."""
        step = _make_step(
            9,
            ActionType.TOOL,
            target="propose_component",
            result_kwargs={"state_changed": None},
        )
        step.result.message = "Proposed: contact-card"
        line = _format_history_line(step)
        assert "Proposed: contact-card" in line
        assert "NO state change" not in line


class TestIsStuck:
    def test_empty_history_not_stuck(self) -> None:
        assert _is_stuck([], window=3) is False

    def test_fewer_than_window_not_stuck(self) -> None:
        steps = [
            _make_step(1, ActionType.CLICK, result_kwargs={"state_changed": False}),
            _make_step(2, ActionType.CLICK, result_kwargs={"state_changed": False}),
        ]
        assert _is_stuck(steps, window=3) is False

    def test_three_consecutive_no_ops_is_stuck(self) -> None:
        steps = [
            _make_step(i, ActionType.CLICK, result_kwargs={"state_changed": False})
            for i in (1, 2, 3)
        ]
        assert _is_stuck(steps, window=3) is True

    def test_mixed_history_not_stuck(self) -> None:
        steps = [
            _make_step(1, ActionType.CLICK, result_kwargs={"state_changed": False}),
            _make_step(2, ActionType.CLICK, result_kwargs={"state_changed": True}),
            _make_step(3, ActionType.CLICK, result_kwargs={"state_changed": False}),
        ]
        assert _is_stuck(steps, window=3) is False

    def test_state_changed_none_does_not_count_as_noop(self) -> None:
        """Tool actions have state_changed=None and should NOT trigger stuck."""
        steps = [
            _make_step(1, ActionType.CLICK, result_kwargs={"state_changed": False}),
            _make_step(2, ActionType.TOOL, result_kwargs={"state_changed": None}),
            _make_step(3, ActionType.CLICK, result_kwargs={"state_changed": False}),
        ]
        assert _is_stuck(steps, window=3) is False
