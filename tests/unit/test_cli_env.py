"""Tests for CLI environment profile resolution."""

import pytest


class TestCliEnv:
    def test_get_active_env_default_empty(self) -> None:
        from dazzle.cli.env import get_active_env, set_active_env

        set_active_env("")
        assert get_active_env() == ""

    def test_set_and_get_active_env(self) -> None:
        from dazzle.cli.env import get_active_env, set_active_env

        set_active_env("staging")
        assert get_active_env() == "staging"
        set_active_env("")

    @pytest.mark.parametrize(
        "dazzle_env,cli_flag,expected",
        [
            ("production", "staging", "staging"),
            ("production", "", "production"),
        ],
        ids=[
            "test_resolve_env_cli_flag_wins",
            "test_resolve_env_dazzle_env_fallback",
        ],
    )
    def test_resolve_env_with_dazzle_env_set(
        self,
        monkeypatch: pytest.MonkeyPatch,
        dazzle_env: str,
        cli_flag: str,
        expected: str,
    ) -> None:
        monkeypatch.setenv("DAZZLE_ENV", dazzle_env)
        from dazzle.cli.env import resolve_env_name

        assert resolve_env_name(cli_flag) == expected

    def test_resolve_env_nothing_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DAZZLE_ENV", raising=False)
        from dazzle.cli.env import resolve_env_name

        assert resolve_env_name("") == ""
