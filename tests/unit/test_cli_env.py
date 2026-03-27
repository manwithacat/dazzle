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

    def test_resolve_env_cli_flag_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DAZZLE_ENV", "production")
        from dazzle.cli.env import resolve_env_name

        assert resolve_env_name("staging") == "staging"

    def test_resolve_env_dazzle_env_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DAZZLE_ENV", "production")
        from dazzle.cli.env import resolve_env_name

        assert resolve_env_name("") == "production"

    def test_resolve_env_nothing_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DAZZLE_ENV", raising=False)
        from dazzle.cli.env import resolve_env_name

        assert resolve_env_name("") == ""
