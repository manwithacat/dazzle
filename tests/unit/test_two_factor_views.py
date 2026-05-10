"""Unit tests for Phase 1.D.1 typed 2FA challenge view.

Covers `build_2fa_challenge_view` shape across the three challenge
modes (totp / email_otp / recovery), the email-OTP send-vs-verify
toggle, error rendering, mode-switch link visibility, and escape
safety on user-supplied input.
"""

from __future__ import annotations

from dazzle.render.fragment.renderer import FragmentRenderer
from dazzle_back.runtime.auth.two_factor_views import build_2fa_challenge_view


def _render(page: object) -> str:
    return FragmentRenderer().render(page)  # type: ignore[arg-type]


# ───────────────── TOTP mode (default) ─────────────────


def test_totp_mode_posts_to_verify_submit() -> None:
    page = build_2fa_challenge_view(product_name="Acme", session_token="sess-1")
    html = _render(page)
    assert "/auth/2fa/verify/submit" in html


def test_totp_mode_includes_session_token() -> None:
    page = build_2fa_challenge_view(product_name="Acme", session_token="sess-1")
    html = _render(page)
    assert 'name="session_token"' in html
    assert 'value="sess-1"' in html


def test_totp_mode_includes_method_hidden_field() -> None:
    page = build_2fa_challenge_view(product_name="Acme", session_token="sess-1")
    html = _render(page)
    assert 'name="method"' in html
    assert 'value="totp"' in html


def test_totp_mode_default_subtitle() -> None:
    page = build_2fa_challenge_view(product_name="Acme", session_token="sess-1")
    html = _render(page)
    assert "authenticator app" in html


def test_totp_mode_offers_recovery_link() -> None:
    page = build_2fa_challenge_view(product_name="Acme", session_token="sess-1")
    html = _render(page)
    assert "recovery code" in html
    assert "mode=recovery" in html


def test_totp_mode_offers_email_otp_link_when_enabled() -> None:
    page = build_2fa_challenge_view(
        product_name="Acme", session_token="sess-1", email_otp_enabled=True
    )
    html = _render(page)
    assert "mode=email_otp" in html


def test_totp_mode_hides_email_otp_link_when_disabled() -> None:
    page = build_2fa_challenge_view(
        product_name="Acme", session_token="sess-1", email_otp_enabled=False
    )
    html = _render(page)
    assert "mode=email_otp" not in html


def test_totp_mode_hides_self_mode_link() -> None:
    page = build_2fa_challenge_view(product_name="Acme", session_token="sess-1")
    html = _render(page)
    # No "use authenticator app" link when we're already on totp.
    assert "Use authenticator app" not in html


# ───────────────── Recovery mode ─────────────────


def test_recovery_mode_uses_recovery_label() -> None:
    page = build_2fa_challenge_view(product_name="Acme", session_token="sess-1", mode="recovery")
    html = _render(page)
    assert "Recovery code" in html
    assert 'value="recovery"' in html


def test_recovery_mode_subtitle() -> None:
    page = build_2fa_challenge_view(product_name="Acme", session_token="sess-1", mode="recovery")
    html = _render(page)
    assert "saved recovery codes" in html


def test_recovery_mode_links_back_to_totp() -> None:
    page = build_2fa_challenge_view(product_name="Acme", session_token="sess-1", mode="recovery")
    html = _render(page)
    assert "Use authenticator app" in html
    assert "mode=totp" in html


# ───────────────── Email-OTP mode (send vs verify) ─────────────────


def test_email_otp_mode_before_send_shows_send_button() -> None:
    page = build_2fa_challenge_view(
        product_name="Acme",
        session_token="sess-1",
        mode="email_otp",
        email_otp_enabled=True,
        code_sent=False,
    )
    html = _render(page)
    assert "/auth/2fa/email-otp-send/submit" in html
    assert "Send code to email" in html
    # Verify form NOT yet rendered.
    assert "/auth/2fa/verify/submit" not in html


def test_email_otp_mode_after_send_shows_verify_form() -> None:
    page = build_2fa_challenge_view(
        product_name="Acme",
        session_token="sess-1",
        mode="email_otp",
        email_otp_enabled=True,
        code_sent=True,
    )
    html = _render(page)
    assert "/auth/2fa/verify/submit" in html
    assert 'value="email_otp"' in html
    assert "Code sent" in html
    # Send button no longer shown after delivery confirmed.
    assert "/auth/2fa/email-otp-send/submit" not in html


def test_email_otp_mode_subtitle() -> None:
    page = build_2fa_challenge_view(
        product_name="Acme",
        session_token="sess-1",
        mode="email_otp",
        email_otp_enabled=True,
    )
    html = _render(page)
    assert "code we sent to your email" in html


# ───────────────── Error rendering ─────────────────


def test_error_message_renders_when_supplied() -> None:
    page = build_2fa_challenge_view(
        product_name="Acme",
        session_token="sess-1",
        error_message="That code didn't match. Try again.",
    )
    html = _render(page)
    assert "didn" in html and "match" in html


def test_error_message_escaped() -> None:
    page = build_2fa_challenge_view(
        product_name="Acme",
        session_token="sess-1",
        error_message="<script>alert(1)</script>",
    )
    html = _render(page)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ───────────────── Escape safety ─────────────────


def test_session_token_escaped_in_form_value() -> None:
    """A malicious session_token must NOT escape its attribute context."""
    page = build_2fa_challenge_view(
        product_name="Acme",
        session_token='"><script>alert(1)</script>',
    )
    html = _render(page)
    assert "<script>alert(1)</script>" not in html


def test_session_token_escaped_in_mode_switch_links() -> None:
    """Token threads into href= attributes for mode switches too."""
    page = build_2fa_challenge_view(
        product_name="Acme",
        session_token='"><x',
        email_otp_enabled=True,
    )
    html = _render(page)
    # The verbatim malicious payload must not appear unescaped in any
    # href= attribute.
    assert 'href="/2fa/challenge?session="><x' not in html
