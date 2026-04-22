"""
Wiring tests for TwoFactorConfig (#838).

Pins the fact that `SecurityConfig.two_factor` reaches the runtime 2FA
routes and that the policy-knob fields (`recovery_code_count`) are read
by the handlers. Previously the IR type sat as a pure declaration — no
producer, no consumer — and the runtime hardcoded the same numbers that
happened to match the defaults.
"""

from __future__ import annotations

from dazzle.core.ir.security import SecurityConfig, TwoFactorConfig, TwoFactorMethod


class TestSecurityConfigComposition:
    """SecurityConfig now carries TwoFactorConfig."""

    def test_default_security_config_has_default_two_factor(self) -> None:
        cfg = SecurityConfig()
        assert isinstance(cfg.two_factor, TwoFactorConfig)
        assert cfg.two_factor.enabled is False
        assert cfg.two_factor.recovery_code_count == 8

    def test_custom_two_factor_roundtrips(self) -> None:
        tf = TwoFactorConfig(
            enabled=True,
            methods=[TwoFactorMethod.TOTP],
            otp_length=8,
            otp_expiry_seconds=600,
            recovery_code_count=12,
            enforce_for_roles=["admin"],
        )
        cfg = SecurityConfig(two_factor=tf)
        assert cfg.two_factor.enabled is True
        assert cfg.two_factor.recovery_code_count == 12
        assert cfg.two_factor.enforce_for_roles == ["admin"]

    def test_profile_builders_carry_default_two_factor(self) -> None:
        """from_profile doesn't override two_factor — callers compose separately."""
        from dazzle.core.ir.security import SecurityProfile

        for profile in (SecurityProfile.BASIC, SecurityProfile.STANDARD, SecurityProfile.STRICT):
            cfg = SecurityConfig.from_profile(profile)
            # The default TwoFactorConfig survives; per-profile overrides
            # would be added later (spec: #838 follow-up for mandatory 2FA
            # in `strict`).
            assert isinstance(cfg.two_factor, TwoFactorConfig)


class TestCreate2FARoutesAcceptsConfig:
    """create_2fa_routes accepts + stores a TwoFactorConfig."""

    def test_default_when_not_supplied(self) -> None:
        from unittest.mock import MagicMock

        from dazzle_back.runtime.auth.routes_2fa import _TwoFaDeps, create_2fa_routes

        mock_store = MagicMock()
        router = create_2fa_routes(mock_store)
        assert router is not None
        # The _TwoFaDeps default-factory populates a TwoFactorConfig
        deps = _TwoFaDeps(
            auth_store=mock_store, cookie_name="x", session_expires_days=1, database_url=None
        )
        assert isinstance(deps.two_factor_config, TwoFactorConfig)

    def test_custom_config_is_stored(self) -> None:
        from unittest.mock import MagicMock

        from dazzle_back.runtime.auth.routes_2fa import _TwoFaDeps, create_2fa_routes

        tf = TwoFactorConfig(enabled=True, recovery_code_count=12)
        mock_store = MagicMock()
        router = create_2fa_routes(mock_store, two_factor_config=tf)
        assert router is not None
        # Can't inspect deps directly from the router, so verify via a
        # direct _TwoFaDeps construction that the field roundtrips.
        deps = _TwoFaDeps(
            auth_store=mock_store,
            cookie_name="x",
            session_expires_days=1,
            database_url=None,
            two_factor_config=tf,
        )
        assert deps.two_factor_config.recovery_code_count == 12


class TestRecoveryCodeCountIsRead:
    """The policy knob actually reaches generate_recovery_codes()."""

    def test_generate_uses_supplied_count(self) -> None:
        from dazzle_back.runtime.recovery_codes import generate_recovery_codes

        codes_default = generate_recovery_codes()
        assert len(codes_default) == 8  # TwoFactorConfig default

        codes_custom = generate_recovery_codes(count=12)
        assert len(codes_custom) == 12

    def test_routes_2fa_references_two_factor_config(self) -> None:
        """Structural ratchet: the handler source reads recovery_code_count."""
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "dazzle_back"
            / "runtime"
            / "auth"
            / "routes_2fa.py"
        ).read_text()

        # Used in three places: _verify_totp_setup, _setup_email_otp, _regenerate.
        assert source.count("deps.two_factor_config.recovery_code_count") >= 3


class TestSubsystemWiring:
    """AuthSubsystem reads ctx.appspec.security.two_factor."""

    def test_auth_subsystem_reads_two_factor_from_appspec(self) -> None:
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "dazzle_back"
            / "runtime"
            / "subsystems"
            / "auth.py"
        ).read_text()
        assert "ctx.appspec.security" in source
        assert "two_factor" in source
        assert "two_factor_config=" in source
