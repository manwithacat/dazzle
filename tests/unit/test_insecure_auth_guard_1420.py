"""#1420 Slice 1 — fail closed when auth is disabled in production."""

from __future__ import annotations

import pytest

from dazzle.back.runtime.auth.insecure_guard import (
    INSECURE_ACK_VAR,
    InsecureAuthConfigError,
    assert_secure_auth_config,
    insecure_ack_from_env,
)


class TestAssertSecureAuthConfig:
    def test_auth_enabled_is_always_ok(self) -> None:
        # Auth on → never a violation, even in production.
        assert_secure_auth_config(True, production=True, allow_insecure=False)

    def test_dev_with_auth_off_is_ok(self) -> None:
        # Not production → auth-off is the ergonomic local default.
        assert_secure_auth_config(False, production=False, allow_insecure=False)

    def test_prod_auth_off_unacknowledged_raises(self) -> None:
        with pytest.raises(InsecureAuthConfigError) as exc:
            assert_secure_auth_config(False, production=True, allow_insecure=False)
        # Message names the cause and the escape hatch.
        assert INSECURE_ACK_VAR in str(exc.value)

    def test_prod_auth_off_acknowledged_is_ok(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        with caplog.at_level(logging.WARNING):
            assert_secure_auth_config(False, production=True, allow_insecure=True)
        assert any("auth" in r.message.lower() for r in caplog.records)


class TestInsecureAckFromEnv:
    @pytest.mark.parametrize(
        "val,expected",
        [
            ("1", True),
            ("true", True),
            ("YES", True),
            ("on", True),
            ("0", False),
            ("", False),
            ("no", False),
        ],
    )
    def test_reads_env_truthy(
        self, monkeypatch: pytest.MonkeyPatch, val: str, expected: bool
    ) -> None:
        monkeypatch.setenv(INSECURE_ACK_VAR, val)
        assert insecure_ack_from_env() is expected

    def test_unset_is_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(INSECURE_ACK_VAR, raising=False)
        assert insecure_ack_from_env() is False


class TestPinProductionEnv:
    """#1420 M2 — production entry points must pin DAZZLE_ENV so is_production()
    agrees with the entry point's intent (else the guard reads a stale unset env)."""

    def test_pins_production_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        from dazzle.core.environment import is_production, pin_production_env

        monkeypatch.delenv("DAZZLE_ENV", raising=False)
        pin_production_env()
        assert os.environ["DAZZLE_ENV"] == "production"
        assert is_production() is True

    def test_respects_explicit_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        from dazzle.core.environment import pin_production_env

        monkeypatch.setenv("DAZZLE_ENV", "development")
        pin_production_env()
        assert os.environ["DAZZLE_ENV"] == "development"  # setdefault never overrides


class TestSetupAuthWiring:
    """The guard runs at the top of _setup_auth, before its enable_auth early-return,
    so it needs no database."""

    def _app(self, *, enable_auth: bool):
        from dazzle.back.runtime.server import DazzleBackendApp
        from tests.unit.test_build_server_config import _appspec  # minimal AppSpec helper

        return DazzleBackendApp(_appspec(), enable_auth=enable_auth)

    def test_prod_auth_off_build_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DAZZLE_ENV", "production")
        monkeypatch.delenv(INSECURE_ACK_VAR, raising=False)
        app = self._app(enable_auth=False)
        with pytest.raises(InsecureAuthConfigError):
            app._setup_auth()

    def test_prod_auth_off_acknowledged_does_not_raise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DAZZLE_ENV", "production")
        monkeypatch.setenv(INSECURE_ACK_VAR, "1")
        app = self._app(enable_auth=False)
        # Returns (None, None) — the guard allows it; no DB touched on this path.
        assert app._setup_auth() == (None, None)

    def test_dev_auth_off_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DAZZLE_ENV", "development")
        app = self._app(enable_auth=False)
        assert app._setup_auth() == (None, None)
