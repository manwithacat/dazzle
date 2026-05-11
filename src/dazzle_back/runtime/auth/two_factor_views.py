"""Typed-Fragment 2FA views (Phase 1.D.1, v0.67.35).

First slice of the 2FA Jinja retirement: the mid-login challenge page
that a user lands on when their account has TOTP, email-OTP, or recovery
codes enabled. Same composition pattern as the Phase 1 auth views in
`auth_views.py` — explicit primitives, no template inheritance, native
HTML form submission (no JS).

`2fa_setup.html` and `2fa_settings.html` stay on Jinja in this ship —
they involve heavier client-side interaction (QR code generation,
dynamic recovery-code display, async status loading) and need a
separate planning pass.
"""

from __future__ import annotations

from typing import Any, Literal

from dazzle.render.fragment import (
    URL,
    Field,
    FormStack,
    Heading,
    Link,
    Page,
    RawHTML,
    Stack,
    Submit,
    Text,
)

ChallengeMode = Literal["totp", "email_otp", "recovery"]


def _mode_copy(mode: ChallengeMode) -> tuple[str, str, str, str, int]:
    """Return (subtitle, label, placeholder, pattern_input_kind, maxlen) for ``mode``.

    The TOTP and email-OTP modes accept 6-digit numeric codes;
    recovery codes are alphanumeric+dash up to 9 chars.
    """
    if mode == "recovery":
        return (
            "Enter one of your saved recovery codes.",
            "Recovery code",
            "XXXX-XXXX",
            "text",
            9,
        )
    if mode == "email_otp":
        return (
            "Enter the code we sent to your email.",
            "Email code",
            "000000",
            "text",
            6,
        )
    return (
        "Enter the code from your authenticator app.",
        "Authenticator code",
        "000000",
        "text",
        6,
    )


def build_2fa_challenge_view(
    *,
    product_name: str,
    session_token: str,
    mode: ChallengeMode = "totp",
    email_otp_enabled: bool = False,
    code_sent: bool = False,
    error_message: str = "",
    css_links: tuple[str, ...] = ("/static/dist/dazzle.min.css",),
    js_scripts: tuple[str, ...] = ("/static/dist/dazzle.min.js",),
) -> Page:
    """Render the mid-login 2FA challenge page.

    Native form submission — no JS. The verify form posts to
    `/auth/2fa/verify/submit`; the "send code to email" affordance
    (visible only when ``mode == "email_otp"`` AND ``code_sent`` is
    False) posts to `/auth/2fa/email-otp-send/submit`.

    Mode switching happens via simple links to
    `/2fa/challenge?session=<token>&mode=<other>` — the GET handler
    re-renders the page with the new mode. This is functionally
    equivalent to the legacy JS-driven mode toggle but works without
    client-side script.
    """
    subtitle, code_label, placeholder, _kind, maxlen = _mode_copy(mode)
    _ = maxlen  # length cap enforced server-side in `_verify_2fa`

    body_children: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body="Verify your identity", level=1),
        Text(body=subtitle, tone="muted"),
    ]
    if error_message:
        body_children.append(Text(body=error_message, tone="danger"))

    # The "Code sent" status when the user just requested an email OTP.
    if mode == "email_otp" and code_sent:
        body_children.append(Text(body="Code sent — check your email.", tone="muted"))

    # Email-OTP "Send code" affordance: shown only when the user is on
    # the email-otp mode and hasn't requested delivery yet. Posts to
    # a dedicated form-encoded endpoint, then 303s back here with
    # ?sent=1 so the verify form renders.
    if mode == "email_otp" and not code_sent:
        body_children.append(
            FormStack(
                action=URL("/auth/2fa/email-otp-send/submit"),
                method="POST",
                fields=(
                    Field(
                        name="session_token",
                        label="Session",
                        kind="text",
                        initial_value=session_token,
                        required=True,
                        readonly=True,
                    ),
                ),
                submit=Submit(label="Send code to email", variant="secondary"),
            )
        )
    else:
        body_children.append(
            FormStack(
                action=URL("/auth/2fa/verify/submit"),
                method="POST",
                fields=(
                    Field(
                        name="session_token",
                        label="Session",
                        kind="text",
                        initial_value=session_token,
                        required=True,
                        readonly=True,
                    ),
                    Field(
                        name="method",
                        label="Method",
                        kind="text",
                        initial_value=mode,
                        required=True,
                        readonly=True,
                    ),
                    Field(
                        name="code",
                        label=code_label,
                        kind="text",
                        required=True,
                        placeholder=placeholder,
                    ),
                ),
                submit=Submit(label="Verify", variant="primary"),
            )
        )

    # Mode-switch affordances. Render links to the other available
    # modes so the user can pick whichever they have access to.
    body_children.append(Text(body="Or use a different method:", tone="muted"))
    if mode != "totp":
        body_children.append(
            Link(
                label="Use authenticator app",
                href=URL(f"/2fa/challenge?session={session_token}&mode=totp"),
            )
        )
    if mode != "email_otp" and email_otp_enabled:
        body_children.append(
            Link(
                label="Use email code",
                href=URL(f"/2fa/challenge?session={session_token}&mode=email_otp"),
            )
        )
    if mode != "recovery":
        body_children.append(
            Link(
                label="Use a recovery code",
                href=URL(f"/2fa/challenge?session={session_token}&mode=recovery"),
            )
        )

    return Page(
        title=f"Verify your identity — {product_name}",
        body=Stack(children=tuple(body_children)),
        css_links=css_links,
        js_scripts=js_scripts,
    )


# ── Setup + settings views (Phase 1.D.2, v0.67.37) ──
#
# Both surfaces drive multi-step, fetch-based interactions that don't fit
# the "native form post + 303" pattern used elsewhere in Phase 1. We
# render the DOM scaffold (same element-IDs the legacy template emitted)
# via `RawHTML`, and reference the extracted ES2015 client script via
# `Page.js_scripts`. This keeps the typed-view migration honest about
# what's substrate-modelled and what's hand-crafted: every `RawHTML(...)`
# is a lint-counted escape hatch.

_SETUP_BODY_HTML = """\
<div class="dz-auth-page">
  <div class="dz-auth-card">
    <h1 class="dz-auth-card-title">Set Up 2FA</h1>
    <p class="dz-auth-card-subtitle">{product_name}</p>
    <div id="dz-auth-error" class="dz-auth-error hidden" role="alert"></div>
    <div id="dz-auth-success" class="dz-auth-success hidden" role="status"></div>

    <div id="dz-totp-section">
      <h2 class="dz-auth-section-title">Authenticator App</h2>
      <p class="dz-auth-section-body">
        Scan this QR code with your authenticator app (Google Authenticator, Authy, etc.)
      </p>
      <div id="dz-qr-container" class="dz-auth-qr-container">
        <button id="dz-setup-totp" class="dz-button dz-button-outline">
          Generate QR Code
        </button>
      </div>
      <div id="dz-totp-verify" class="hidden">
        <p class="dz-auth-section-body">
          Or enter the secret manually:
          <code id="dz-totp-secret" class="dz-auth-secret-inline"></code>
        </p>
        <form id="dz-totp-form" class="dz-auth-form">
          <div class="dz-auth-field">
            <label for="totp_code" class="dz-auth-label">Enter code from app</label>
            <input type="text" id="totp_code" name="code" required
                   inputmode="numeric" pattern="[0-9]*" maxlength="6"
                   placeholder="000000" class="dz-auth-input-code">
          </div>
          <button type="submit" class="dz-button dz-button-primary dz-auth-submit">
            Verify &amp; Enable
          </button>
        </form>
      </div>
    </div>

    <hr class="dz-auth-hr">

    <div id="dz-email-otp-section">
      <h2 class="dz-auth-section-title">Email Verification</h2>
      <p class="dz-auth-section-body">
        Receive a one-time code via email when you sign in.
      </p>
      <button id="dz-enable-email-otp" class="dz-button dz-button-outline dz-auth-submit">
        Enable Email OTP
      </button>
    </div>

    <div id="dz-recovery-section" class="hidden">
      <div class="dz-auth-recovery-alert" role="alert">
        <h3 class="dz-auth-recovery-alert-title">Save Your Recovery Codes</h3>
        <p class="dz-auth-recovery-alert-body">
          Store these codes in a safe place. Each code can only be used once.
        </p>
      </div>
      <div id="dz-recovery-codes" class="dz-auth-recovery-grid"></div>
    </div>

    <a href="/app" class="dz-auth-back-link">Back to App</a>
  </div>
</div>"""


_SETTINGS_BODY_HTML = """\
<div class="dz-auth-page">
  <div class="dz-auth-card">
    <h1 class="dz-auth-card-title">2FA Settings</h1>
    <p class="dz-auth-card-subtitle">{product_name}</p>
    <div id="dz-auth-error" class="dz-auth-error hidden" role="alert"></div>
    <div id="dz-auth-success" class="dz-auth-success hidden" role="status"></div>
    <div id="dz-status">
      <p class="dz-auth-status-loading">Loading status...</p>
    </div>
    <a href="/app" class="dz-auth-back-link">Back to App</a>
  </div>
</div>"""


def _escape_attr(value: str) -> str:
    """Minimal HTML-attribute escape for product_name interpolation."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def build_2fa_setup_view(
    *,
    product_name: str,
    css_links: tuple[str, ...] = ("/static/dist/dazzle.min.css",),
    js_scripts: tuple[str, ...] = (
        "/static/dist/dazzle.min.js",
        "/static/js/dz-2fa-setup.js",
    ),
) -> Page:
    """Render the 2FA setup page (Phase 1.D.2, v0.67.37).

    The body is a `RawHTML` scaffold with stable element IDs; the
    extracted `dz-2fa-setup.js` client script (referenced via
    `js_scripts`) wires up TOTP-secret fetch, QR display, code-verify
    submission, email-OTP enable, and recovery-code reveal. Auth state
    transitions still go through the existing JSON endpoints in
    `routes_2fa.py` — only the rendering layer changed.
    """
    safe_name = _escape_attr(product_name)
    return Page(
        title=f"Set Up 2FA — {product_name}",
        body=RawHTML(html=_SETUP_BODY_HTML.format(product_name=safe_name)),
        css_links=css_links,
        js_scripts=js_scripts,
    )


def build_2fa_settings_view(
    *,
    product_name: str,
    css_links: tuple[str, ...] = ("/static/dist/dazzle.min.css",),
    js_scripts: tuple[str, ...] = (
        "/static/dist/dazzle.min.js",
        "/static/js/dz-2fa-settings.js",
    ),
) -> Page:
    """Render the 2FA settings page (Phase 1.D.2, v0.67.37).

    Body scaffold + extracted `dz-2fa-settings.js` that loads the
    user's current factor status via `/auth/2fa/status` and emits
    enable/disable/regenerate controls per row.
    """
    safe_name = _escape_attr(product_name)
    return Page(
        title=f"2FA Settings — {product_name}",
        body=RawHTML(html=_SETTINGS_BODY_HTML.format(product_name=safe_name)),
        css_links=css_links,
        js_scripts=js_scripts,
    )
