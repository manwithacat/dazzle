"""Tests for ActionResult (cycle 197 — L1 action feedback extensions)."""

from dazzle.agent.models import ActionResult


class TestActionResultDefaults:
    def test_minimal_construction_sets_new_fields_to_none_or_empty(self) -> None:
        """ActionResult(message=...) leaves the new fields at safe defaults."""
        result = ActionResult(message="Clicked button")
        assert result.message == "Clicked button"
        assert result.error is None
        assert result.data == {}
        # Cycle 197 additions — all default to None / empty list
        assert result.from_url is None
        assert result.to_url is None
        assert result.state_changed is None
        assert result.console_errors_during_action == []

    def test_explicit_values_are_preserved(self) -> None:
        result = ActionResult(
            message="navigated",
            from_url="/a",
            to_url="/b",
            state_changed=True,
            console_errors_during_action=["TypeError: x is undefined"],
        )
        assert result.from_url == "/a"
        assert result.to_url == "/b"
        assert result.state_changed is True
        assert result.console_errors_during_action == ["TypeError: x is undefined"]

    def test_legacy_positional_construction_still_works(self) -> None:
        """Existing callers (fitness engine, tests) construct with only the old fields."""
        r1 = ActionResult(message="Tool invocation: propose_component")
        r2 = ActionResult(message="", error="Selector not found")
        assert r1.state_changed is None
        assert r2.state_changed is None
