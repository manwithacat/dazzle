"""Typed-Fragment two-factor pages (DD-014): challenge, step-up, setup, recovery codes,
settings.

Native form posts and 303s throughout — no client script. The enrolment QR, the
manual secret and the recovery-code grid are the HaTchi-MaXchi ``two-factor``
Hyperpart's chrome (``.dz-auth-qr-container``, ``.dz-auth-secret-inline``,
``.dz-auth-recovery-grid`` / ``.dz-auth-recovery-pill``) emitted through ``RawHTML``
from escaped, server-generated values only (a ``data:`` PNG, base32, ``XXXX-XXXX``).
Codes are never echoed back into a page; recovery codes are shown once, in the
response that minted them.
"""

from html import escape
from typing import Any
from urllib.parse import quote

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

_DEFAULT_CSS = ("/static/dist/dazzle.min.css",)
_DEFAULT_JS = ("/static/dist/dazzle.min.js",)

_MODE_COPY: dict[str, tuple[str, str, str]] = {
    "totp": ("Enter the 6-digit code from your authenticator app.", "Authenticator code", "000000"),
    "email_otp": ("Enter the 6-digit code we emailed you.", "Email code", "000000"),
    "recovery": ("Enter one of your saved recovery codes.", "Recovery code", "XXXX-XXXX"),
}
# #1842 (WCAG 3.3.8): numeric TOTP / email codes autofill from the OS and get
# a numeric keypad; recovery codes are alphanumeric (XXXX-XXXX), so neither.
_MODE_INPUT_HINTS: dict[str, tuple[str, str]] = {
    "totp": ("one-time-code", "numeric"),
    "email_otp": ("one-time-code", "numeric"),
    "recovery": ("", ""),
}
_MODE_LINKS: dict[str, str] = {
    "totp": "Use your authenticator app",
    "email_otp": "Email me a code",
    "recovery": "Use a recovery code",
}


def _with_query(base: str, **params: str) -> str:
    pairs = [f"{k}={quote(v, safe='/')}" for k, v in params.items() if v]
    return f"{base}?{'&'.join(pairs)}" if pairs else base


def build_code_entry_view(
    *,
    product_name: str,
    heading: str,
    mode: str,
    methods: tuple[str, ...],
    verify_action: str,
    send_action: str,
    page_path: str,
    next_url: str = "",
    code_sent: bool = False,
    error_message: str = "",
    css_links: tuple[str, ...] = _DEFAULT_CSS,
    js_scripts: tuple[str, ...] = _DEFAULT_JS,
) -> Page:
    """The code-entry page shared by the sign-in challenge and step-up.

    ``verify_action`` / ``send_action`` are form targets; ``?method=`` (and ``next``)
    ride on the action URL so the form carries one visible field: the code.
    """
    subtitle, label, placeholder = _MODE_COPY[mode]
    autocomplete, inputmode = _MODE_INPUT_HINTS[mode]
    children: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body=heading, level=1),
        Text(body=subtitle, tone="muted"),
    ]
    if error_message:
        children.append(Text(body=error_message, tone="danger"))
    if mode == "email_otp" and not code_sent:
        children.append(
            FormStack(
                action=URL(_with_query(send_action, next=next_url)),
                method="POST",
                fields=(),
                submit=Submit(label="Email me a code", variant="primary"),
            )
        )
    else:
        if mode == "email_otp":
            children.append(Text(body="Code sent. Check your email.", tone="muted"))
        children.append(
            FormStack(
                action=URL(_with_query(verify_action, method=mode, next=next_url)),
                method="POST",
                fields=(
                    Field(
                        name="code",
                        label=label,
                        kind="text",
                        required=True,
                        placeholder=placeholder,
                        autofocus=True,
                        autocomplete=autocomplete,
                        inputmode=inputmode,
                    ),
                ),
                submit=Submit(label="Verify", variant="primary"),
            )
        )
    others = [m for m in methods if m != mode]
    if others:
        children.append(Text(body="Or use a different method:", tone="muted"))
        for other in others:
            children.append(
                Link(
                    label=_MODE_LINKS[other],
                    href=URL(_with_query(page_path, method=other, next=next_url)),
                )
            )
    return Page(
        title=f"{heading} — {product_name}",
        body=Stack(children=tuple(children)),
        css_links=css_links,
        js_scripts=js_scripts,
    )


def build_2fa_setup_view(
    *,
    product_name: str,
    qr_data_uri: str,
    secret: str,
    email_otp_allowed: bool,
    totp_allowed: bool,
    email_code_sent: bool = False,
    error_message: str = "",
    required: bool = False,
    css_links: tuple[str, ...] = _DEFAULT_CSS,
    js_scripts: tuple[str, ...] = _DEFAULT_JS,
) -> Page:
    """Enrol an authenticator app (QR rendered on the server) and/or email codes.

    ``required`` is the enforce_for_roles enrolment-only state: finishing it signs in.
    """
    children: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body="Set up two-step verification", level=1),
    ]
    if required:
        children.append(
            Text(
                body="Your role needs two-step verification. Set it up to finish signing in.",
                tone="muted",
            )
        )
    if error_message:
        children.append(Text(body=error_message, tone="danger"))
    if totp_allowed and qr_data_uri:
        children.append(Heading(body="Authenticator app", level=2))
        children.append(Text(body="Scan this QR code with your authenticator app.", tone="muted"))
        children.append(
            RawHTML(
                html=(
                    '<div class="dz-auth-qr-container">'
                    f'<img src="{escape(qr_data_uri, quote=True)}" width="180" height="180" '
                    'alt="QR code for your authenticator app"></div>'
                    '<p class="dz-auth-section-body">Or enter the key manually: '
                    f'<code class="dz-auth-secret-inline">{escape(secret)}</code></p>'
                )
            )
        )
        children.append(
            FormStack(
                action=URL("/auth/2fa/setup/totp/submit"),
                method="POST",
                fields=(
                    Field(
                        name="code",
                        label="Code from the app",
                        kind="text",
                        required=True,
                        placeholder="000000",
                        autocomplete="one-time-code",
                        inputmode="numeric",
                    ),
                ),
                submit=Submit(label="Verify and turn on", variant="primary"),
            )
        )
    if email_otp_allowed:
        children.append(Heading(body="Email codes", level=2))
        if email_code_sent:
            children.append(Text(body="Code sent. Check your email.", tone="muted"))
            children.append(
                FormStack(
                    action=URL("/auth/2fa/verify/email-otp/submit"),
                    method="POST",
                    fields=(
                        Field(
                            name="code",
                            label="Code from the email",
                            kind="text",
                            required=True,
                            placeholder="000000",
                            autocomplete="one-time-code",
                            inputmode="numeric",
                        ),
                    ),
                    submit=Submit(label="Verify and turn on", variant="primary"),
                )
            )
        else:
            children.append(
                FormStack(
                    action=URL("/auth/2fa/setup/email-otp/submit"),
                    method="POST",
                    fields=(),
                    submit=Submit(label="Email me a code", variant="secondary"),
                )
            )
    return Page(
        title=f"Set up two-step verification — {product_name}",
        body=Stack(children=tuple(children)),
        css_links=css_links,
        js_scripts=js_scripts,
    )


def build_recovery_codes_view(
    *,
    product_name: str,
    codes: list[str],
    continue_url: str,
    css_links: tuple[str, ...] = _DEFAULT_CSS,
    js_scripts: tuple[str, ...] = _DEFAULT_JS,
) -> Page:
    """Show freshly minted recovery codes — once; they are stored only as hashes."""
    pills = "".join(f'<span class="dz-auth-recovery-pill">{escape(c)}</span>' for c in codes)
    children: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body="Save your recovery codes", level=1),
        Text(
            body=(
                "Each code works once, if you lose your authenticator or email. "
                "Store them somewhere safe: they will not be shown again."
            ),
            tone="muted",
        ),
        RawHTML(html=f'<div class="dz-auth-recovery-grid">{pills}</div>'),
        Link(label="Continue", href=URL(continue_url)),
    ]
    return Page(
        title=f"Recovery codes — {product_name}",
        body=Stack(children=tuple(children)),
        css_links=css_links,
        js_scripts=js_scripts,
    )


def _settings_status(
    totp_enabled: bool, email_otp_enabled: bool, email_otp_allowed: bool, recovery_remaining: int
) -> list[Any]:
    lines: list[Any] = [Text(body=f"Authenticator app: {'on' if totp_enabled else 'off'}")]
    if email_otp_allowed or email_otp_enabled:
        lines.append(Text(body=f"Email codes: {'on' if email_otp_enabled else 'off'}"))
    if totp_enabled or email_otp_enabled:
        lines.append(Text(body=f"Recovery codes left: {recovery_remaining}", tone="muted"))
    if not totp_enabled or (email_otp_allowed and not email_otp_enabled):
        lines.append(Link(label="Set up a method", href=URL("/2fa/setup")))
    return lines


def _settings_actions(totp_enabled: bool, email_otp_enabled: bool) -> list[tuple[str, str]]:
    actions: list[tuple[str, str]] = []
    if totp_enabled or email_otp_enabled:
        actions.append(("regenerate_recovery", "New recovery codes"))
    if totp_enabled:
        actions.append(("disable_totp", "Turn off the authenticator app"))
    if email_otp_enabled:
        actions.append(("disable_email_otp", "Turn off email codes"))
    return actions


def build_2fa_settings_view(
    *,
    product_name: str,
    totp_enabled: bool,
    email_otp_enabled: bool,
    email_otp_allowed: bool,
    recovery_remaining: int,
    message: str = "",
    css_links: tuple[str, ...] = _DEFAULT_CSS,
    js_scripts: tuple[str, ...] = _DEFAULT_JS,
) -> Page:
    """Factor status, recovery-code count and the manage actions (all form posts)."""
    children: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body="Two-step verification", level=1),
    ]
    if message:
        children.append(Text(body=message, tone="muted"))
    children.extend(
        _settings_status(totp_enabled, email_otp_enabled, email_otp_allowed, recovery_remaining)
    )
    for action, label in _settings_actions(totp_enabled, email_otp_enabled):
        children.append(
            FormStack(
                action=URL(f"/auth/2fa/settings/submit?action={action}"),
                method="POST",
                fields=(),
                submit=Submit(label=label, variant="secondary"),
            )
        )
    return Page(
        title=f"Two-step verification — {product_name}",
        body=Stack(children=tuple(children)),
        css_links=css_links,
        js_scripts=js_scripts,
    )
