"""Unit tests for Phase 1.D.1 typed 2FA challenge view.

Covers `build_2fa_challenge_view` shape across the three challenge
modes (totp / email_otp / recovery), the email-OTP send-vs-verify
toggle, error rendering, mode-switch link visibility, and escape
safety on user-supplied input.
"""

from __future__ import annotations

from dazzle.http.runtime.auth.two_factor_views import (
    build_2fa_challenge_view,
    build_2fa_settings_view,
    build_2fa_setup_view,
)
from dazzle.render.fragment.renderer import FragmentRenderer


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


# ───────────────── build_2fa_setup_view (Phase 1.D.2) ─────────────────


def test_setup_view_renders_required_element_ids() -> None:
    """The DOM contract the extracted JS depends on must be intact."""
    html = _render(build_2fa_setup_view(product_name="Acme"))
    for element_id in (
        "dz-auth-error",
        "dz-auth-success",
        "dz-setup-totp",
        "dz-qr-container",
        "dz-totp-verify",
        "dz-totp-secret",
        "dz-totp-form",
        "totp_code",
        "dz-enable-email-otp",
        "dz-recovery-section",
        "dz-recovery-codes",
    ):
        assert f'id="{element_id}"' in html, f"missing required element id: {element_id}"


def test_setup_view_references_extracted_js() -> None:
    html = _render(build_2fa_setup_view(product_name="Acme"))
    assert "/static/js/dz-2fa-setup.js" in html
    # No inline `<script>` block — JS lives in the extracted file.
    assert "<script>" not in html


def test_setup_view_totp_code_input_attributes() -> None:
    """The TOTP code input must keep the canonical attributes for
    iOS/Android keyboard hints and validation."""
    html = _render(build_2fa_setup_view(product_name="Acme"))
    for attr in (
        'inputmode="numeric"',
        'pattern="[0-9]*"',
        'maxlength="6"',
        'placeholder="000000"',
    ):
        assert attr in html, f"missing required TOTP attribute: {attr}"


def test_setup_view_links_back_to_app() -> None:
    html = _render(build_2fa_setup_view(product_name="Acme"))
    assert 'href="/app"' in html
    assert "Back to App" in html


def test_setup_view_escapes_product_name() -> None:
    html = _render(build_2fa_setup_view(product_name="<Evil>"))
    assert "<Evil>" not in html
    assert "&lt;Evil&gt;" in html


def test_setup_view_recovery_section_initially_hidden() -> None:
    """The recovery-codes section is hidden until the JS reveals it
    after a successful verify — pin via class membership."""
    html = _render(build_2fa_setup_view(product_name="Acme"))
    import re

    m = re.search(r'<div\s+id="dz-recovery-section"[^>]*>', html)
    assert m is not None
    assert "hidden" in m.group(0)


def test_setup_view_totp_verify_block_initially_hidden() -> None:
    html = _render(build_2fa_setup_view(product_name="Acme"))
    import re

    m = re.search(r'<div\s+id="dz-totp-verify"[^>]*>', html)
    assert m is not None
    assert "hidden" in m.group(0)


# ───────────────── build_2fa_settings_view (Phase 1.D.2) ─────────────────


def test_settings_view_renders_required_element_ids() -> None:
    html = _render(build_2fa_settings_view(product_name="Acme"))
    for element_id in ("dz-auth-error", "dz-auth-success", "dz-status"):
        assert f'id="{element_id}"' in html, f"missing required element id: {element_id}"


def test_settings_view_references_extracted_js() -> None:
    html = _render(build_2fa_settings_view(product_name="Acme"))
    assert "/static/js/dz-2fa-settings.js" in html
    assert "<script>" not in html


def test_settings_view_status_loading_placeholder() -> None:
    html = _render(build_2fa_settings_view(product_name="Acme"))
    assert "Loading status" in html


def test_settings_view_links_back_to_app() -> None:
    html = _render(build_2fa_settings_view(product_name="Acme"))
    assert 'href="/app"' in html
    assert "Back to App" in html


def test_settings_view_escapes_product_name() -> None:
    html = _render(build_2fa_settings_view(product_name="<x>"))
    assert "<x>" not in html
    assert "&lt;x&gt;" in html


# ---------------------------------------------------------------------------
# #1550 — hidden sections use the NATIVE hidden attribute (house idiom).
# No `.hidden` utility class exists anywhere in the bundle, so
# class="hidden" rendered the verify form and recovery section always
# visible. The scaffold + dz-2fa-*.js + HM two-factor.css move together
# to attribute-based hiding.
# ---------------------------------------------------------------------------


def test_setup_scaffold_hides_sections_via_native_hidden_attribute() -> None:
    html = _render(build_2fa_setup_view(product_name="Acme"))
    assert 'class="hidden"' not in html
    assert '<div id="dz-totp-verify" hidden>' in html
    assert '<div id="dz-recovery-section" hidden>' in html


def test_setup_alerts_hidden_via_attribute_not_class() -> None:
    html = _render(build_2fa_setup_view(product_name="Acme"))
    assert 'class="dz-auth-error hidden"' not in html
    assert '<div id="dz-auth-error" class="dz-auth-error" role="alert" hidden>' in html
    assert '<div id="dz-auth-success" class="dz-auth-success" role="status" hidden>' in html


def test_settings_alerts_hidden_via_attribute_not_class() -> None:
    html = _render(build_2fa_settings_view(product_name="Acme"))
    assert 'class="dz-auth-error hidden"' not in html
    assert '<div id="dz-auth-error" class="dz-auth-error" role="alert" hidden>' in html


def test_2fa_js_toggles_hidden_property_not_class() -> None:
    """dz-2fa-*.js must move in lockstep: the reveal mechanic is the
    element's `hidden` property, never classList('hidden')."""
    from pathlib import Path

    js_dir = Path(__file__).resolve().parents[2] / "src/dazzle/page/runtime/static/js"
    for name in ("dz-2fa-setup.js", "dz-2fa-settings.js"):
        text = (js_dir / name).read_text(encoding="utf-8")
        assert 'classList.add("hidden")' not in text, name
        assert 'classList.remove("hidden")' not in text, name


def test_site_sections_css_carries_no_auth_rules() -> None:
    """#1549 — HM components/sitespec.css's fossil auth block collided with the
    HM two-factor Hyperpart (input-code font, card centering, gradient
    over centering). HM two-factor.css is the sole owner of dz-auth-*."""
    from pathlib import Path

    css = (
        Path(__file__).resolve().parents[2] / "packages/hatchi-maxchi/components/sitespec.css"
    ).read_text(encoding="utf-8")
    assert ".dz-auth-" not in css
