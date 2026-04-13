"""Unit tests for the mode registry."""

import pytest

from dazzle.e2e.errors import UnknownModeError
from dazzle.e2e.modes import MODE_REGISTRY, get_mode


class TestModeRegistry:
    def test_registry_has_mode_a(self) -> None:
        names = [m.name for m in MODE_REGISTRY]
        assert "a" in names

    def test_registry_v1_has_only_mode_a(self) -> None:
        """v1 ships only Mode A; B/C/D land later."""
        assert len(MODE_REGISTRY) == 1
        assert MODE_REGISTRY[0].name == "a"

    def test_mode_a_fields(self) -> None:
        mode_a = get_mode("a")
        assert mode_a.name == "a"
        assert mode_a.db_policy_default == "preserve"
        assert "preserve" in mode_a.db_policies_allowed
        assert "fresh" in mode_a.db_policies_allowed
        assert "restore" in mode_a.db_policies_allowed
        assert mode_a.qa_flag_policy == "auto_if_personas"
        assert mode_a.log_output == "captured_tail_on_fail"
        assert mode_a.lifetime == "single_run"
        assert mode_a.description
        assert mode_a.intended_use


class TestModeSpec:
    def test_is_frozen(self) -> None:
        spec = get_mode("a")
        with pytest.raises((AttributeError, TypeError)):
            spec.name = "x"  # type: ignore[misc]


class TestGetMode:
    def test_returns_mode_spec_by_name(self) -> None:
        assert get_mode("a").name == "a"

    def test_raises_unknown_mode_error_on_miss(self) -> None:
        with pytest.raises(UnknownModeError, match="z"):
            get_mode("z")

    def test_raises_unknown_mode_error_for_unimplemented_modes(self) -> None:
        # Modes b/c/d are specced but not wired in v1.
        for name in ("b", "c", "d"):
            with pytest.raises(UnknownModeError):
                get_mode(name)

    def test_normalizes_input_whitespace_and_case(self) -> None:
        """Trailing whitespace and uppercase should be normalized."""
        assert get_mode("A").name == "a"
        assert get_mode("  a  ").name == "a"
        assert get_mode("\ta\n").name == "a"
