"""Two-factor sign-in primitives without a database (DD-014, #1805).

The HTTP flows run against Postgres in tests/integration/test_two_factor_pg.py.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.ir.security import TwoFactorConfig
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.parser import parse_modules
from dazzle.http.converters.entity_converter import convert_entities
from dazzle.http.runtime.auth.connections import AssertedIdentity
from dazzle.http.runtime.auth.enterprise_routes import idp_second_factor
from dazzle.http.runtime.auth.second_factor import TwoFactorBootError, require_two_factor_runtime
from dazzle.http.runtime.auth.store_two_factor import is_plaintext_totp_secret
from dazzle.http.runtime.auth.totp import generate_totp, match_totp_step
from dazzle.http.runtime.state_machine import SecondFactorGuardError, TransitionValidator
from dazzle.http.runtime.step_up import step_up_url

# RFC 6238 appendix B, SHA-1 seed "12345678901234567890" (6-digit truncation).
_RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


@pytest.mark.parametrize(
    ("timestamp", "code"),
    [(59, "287082"), (1111111109, "081804"), (1234567890, "005924"), (2000000000, "279037")],
)
def test_totp_matches_the_rfc_6238_vectors(timestamp: int, code: str) -> None:
    assert generate_totp(_RFC_SECRET, timestamp) == code
    assert match_totp_step(_RFC_SECRET, code, timestamp=timestamp + 30) == timestamp // 30
    assert match_totp_step(_RFC_SECRET, code, timestamp=timestamp + 90) is None


_DSL = """module t
app t "T"

entity VatReturn "VAT Return":
  id: uuid pk
  status: enum[draft, ready, filed]=draft
  transitions:
    draft -> ready:
      guard: session.second_factor
    ready -> filed:
      guard: session.second_factor within 15 minutes
"""


def _state_machine(tmp_path: Path, two_factor: TwoFactorConfig | None) -> tuple[object, object]:
    path = tmp_path / "t.dsl"
    path.write_text(_DSL, encoding="utf-8")
    appspec = build_appspec(parse_modules([path]), "t", two_factor=two_factor)
    entity = next(e for e in convert_entities(appspec.domain.entities) if e.name == "VatReturn")
    return appspec, entity.state_machine


@pytest.mark.parametrize(
    ("from_state", "to_state", "verified_ago", "allowed"),
    [
        pytest.param("draft", "ready", None, False, id="no_second_factor"),
        pytest.param("draft", "ready", timedelta(days=3), True, id="any_second_factor"),
        pytest.param("ready", "filed", timedelta(minutes=5), True, id="fresh_enough"),
        pytest.param("ready", "filed", timedelta(minutes=20), False, id="too_old"),
    ],
)
def test_session_second_factor_guard(
    tmp_path: Path,
    from_state: str,
    to_state: str,
    verified_ago: timedelta | None,
    allowed: bool,
) -> None:
    _appspec, sm = _state_machine(tmp_path, TwoFactorConfig(enabled=True))
    at = datetime.now(UTC) - verified_ago if verified_ago is not None else None
    result = TransitionValidator(sm).validate_transition(  # type: ignore[arg-type]
        from_state, to_state, {}, ["accountant"], "u-1", second_factor_at=at
    )
    assert result.is_valid is allowed
    if not allowed:
        assert isinstance(result.error, SecondFactorGuardError)
        assert result.error.step_up_url == "/2fa/step-up"


def test_second_factor_guard_without_two_factor_enabled_warns(tmp_path: Path) -> None:
    on, _sm = _state_machine(tmp_path, TwoFactorConfig(enabled=True))
    off, _sm = _state_machine(tmp_path, None)
    assert not [w for w in lint_appspec(on)[1] if "session.second_factor" in w]
    assert [w for w in lint_appspec(off)[1] if "[auth.two_factor] is not enabled" in w]


def test_session_second_factor_rejects_a_trailing_clause() -> None:
    body = _DSL.replace("within 15 minutes", "or role(admin)")
    with pytest.raises(ParseError, match="minutes"):
        parse_dsl(body, Path("t.dsl"))


def _asserted(source: str = "id_token", **claims: object) -> AssertedIdentity:
    return AssertedIdentity(email="a@b.test", attributes=dict(claims), claims_source=source)


@pytest.mark.parametrize(
    ("asserted", "method"),
    [
        pytest.param(_asserted(amr=["pwd", "mfa"], auth_time=1_700_000_000), "idp", id="mfa"),
        pytest.param(_asserted(amr=["hwk"]), "idp", id="hardware_key"),
        pytest.param(_asserted(amr=["pwd"]), None, id="password_only"),
        pytest.param(_asserted(), None, id="no_amr"),
        pytest.param(_asserted("userinfo_endpoint", amr=["mfa"]), None, id="unsigned_claims"),
    ],
)
def test_enterprise_idp_amr_records_the_second_factor(
    asserted: AssertedIdentity, method: str | None
) -> None:
    user = SimpleNamespace(id="u-1")
    proof = idp_second_factor(asserted, user, SimpleNamespace(id="conn-1"))
    assert (proof.method if proof else None) == method
    if proof is not None and "auth_time" in asserted.attributes:
        assert proof.verified_at == datetime.fromtimestamp(1_700_000_000, UTC)


@pytest.mark.parametrize(
    ("next_path", "url"),
    [
        ("/app/vat/1", "/2fa/step-up?next=/app/vat/1"),
        ("//evil.test/x", "/2fa/step-up"),
        ("https://evil.test", "/2fa/step-up"),
        ("", "/2fa/step-up"),
    ],
)
def test_step_up_url_returns_only_to_same_site_paths(next_path: str, url: str) -> None:
    assert step_up_url(next_path) == url


@pytest.mark.parametrize(
    ("value", "plaintext"),
    [("JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP", True), ("q1Zx+8a/b0==", False), (None, False)],
)
def test_pre_dd014_plaintext_totp_secrets_are_recognised(
    value: str | None, plaintext: bool
) -> None:
    assert is_plaintext_totp_secret(value) is plaintext


def test_boot_fails_when_totp_secrets_cannot_be_encrypted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DAZZLE_CONNECTION_SECRET", raising=False)
    with pytest.raises(TwoFactorBootError, match="DAZZLE_CONNECTION_SECRET"):
        require_two_factor_runtime(TwoFactorConfig(enabled=True))


@pytest.mark.parametrize(
    ("totp", "email_otp", "labels"),
    [
        (True, False, ("New recovery codes", "Turn off the authenticator app")),
        (False, True, ("New recovery codes", "Turn off email codes")),
        (False, False, ()),
    ],
)
def test_settings_view_renders_manage_actions(
    totp: bool, email_otp: bool, labels: tuple[str, ...]
) -> None:
    """#1844: a user with a second factor got a 500 (empty-field FormStack)."""
    from dazzle.http.runtime.auth.two_factor_views import build_2fa_settings_view
    from dazzle.render.fragment import FragmentRenderer

    html = FragmentRenderer().render(
        build_2fa_settings_view(
            product_name="Acme",
            totp_enabled=totp,
            email_otp_enabled=email_otp,
            email_otp_allowed=True,
            recovery_remaining=5,
        )
    )
    for label in labels:
        assert label in html
    assert html.count("/auth/2fa/settings/submit?action=") == len(labels)
