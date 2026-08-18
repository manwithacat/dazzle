"""Issue #1037 follow-on (Phase 1.A, v0.67.29): typed-Fragment auth views.

First module of the Jinja2 retirement Phase 1 work. Replaces
`site/auth/login.html` (and follow-on auth templates) with typed-
Fragment composition.

v1 default: email-link passwordless login. The form posts to
`/auth/login/magic-link`, server issues a token via
`magic_link.create_magic_link`, and the user receives the link by
email (or — if no mailer configured — via the application log
during development). Password + SSO + MFA are secondary paths the
deployment opts into.

The chrome=on path renders these typed views; chrome=off keeps
calling the legacy Jinja templates so non-flipped deployments
don't regress during the migration. The chrome=off branch is
removed in Phase 4.C of the Jinja2 retirement plan.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi.responses import HTMLResponse

from dazzle.http.runtime.mailbox_shape import is_mailbox_shape
from dazzle.render.fragment import (
    URL,
    EmptyState,
    Field,
    FormStack,
    Heading,
    Link,
    Page,
    Stack,
    Submit,
    Text,
)
from dazzle.render.fragment.renderer._render_interactive import (
    leftover_honest_catalog_id,
    leftover_honest_catalog_option_values,
)

LOGIN_ERROR_TOKENS: frozenset[str] = frozenset(
    {
        "invalid_magic_link",
        "invalid_credentials",
        "sso_failed",
        "sso_no_email",
        "sso_email_unverified",
        "sso_provider_unknown",
        "sso_no_connection",
        "sso_unavailable",
        "sso_domain_not_verified",
        "sso_unverified_fallback",
        "sso_no_membership",
    }
)
SIGNUP_ERROR_TOKENS: frozenset[str] = frozenset(
    {
        "mismatch",
        "already_registered",
        "create_failed",
        "invalid_email",
    }
)
RESET_ERROR_TOKENS: frozenset[str] = frozenset({"mismatch", "invalid"})
CHALLENGE_ERROR_TOKENS: frozenset[str] = frozenset({"invalid_code"})
SELECT_ORG_ERROR_TOKENS: frozenset[str] = frozenset({"invalid_org"})

LOGIN_ERROR_MESSAGES: dict[str, str] = {
    "invalid_magic_link": ("That sign-in link is invalid or expired. Request a new one below."),
    "invalid_credentials": "That email and password didn't match. Try again.",
    "sso_failed": "We couldn't complete the sign-in. Please try again.",
    "sso_no_email": (
        "That SSO provider didn't share an email address with us — try a different sign-in method."
    ),
    "sso_email_unverified": (
        "Your SSO email address isn't verified with the provider yet. Verify it and try again."
    ),
    "sso_provider_unknown": "That SSO provider isn't configured on this deployment.",
    "sso_no_connection": "No SSO connection is available for that organization.",
    "sso_unavailable": "SSO isn't available right now. Please try again.",
    "sso_domain_not_verified": ("That email domain isn't verified for this organization."),
    "sso_unverified_fallback": (
        "We couldn't verify your email with that sign-in method. "
        "Try again or use a different method."
    ),
    "sso_no_membership": (
        "You don't have a membership in that organization. Ask an admin to invite you."
    ),
}
SIGNUP_ERROR_MESSAGES: dict[str, str] = {
    "mismatch": "The two password fields didn't match. Try again.",
    "already_registered": ("An account with that email already exists. Try signing in instead."),
    "create_failed": "We couldn't create that account. Please try again.",
    "invalid_email": "That email address doesn't look right.",
}
RESET_ERROR_MESSAGES: dict[str, str] = {
    "mismatch": "The two password fields didn't match. Try again.",
    "invalid": "That reset link is invalid or expired. Request a new one.",
}
CHALLENGE_ERROR_MESSAGES: dict[str, str] = {
    "invalid_code": "That code didn't match. Try again.",
}
SELECT_ORG_ERROR_MESSAGES: dict[str, str] = {
    "invalid_org": "That organization isn't available. Choose another.",
}


def leftover_honest_auth_error(raw: Any, declared: Any) -> str | None:
    """Valid declared ``?error=`` tokens ride. Leftover junk restores None.

    Leftover ``?error=zzz`` used to invent a clean page (no banner)
    via omit-as-absent. Enterprise/SAML already emit
    ``sso_no_connection`` / ``sso_unavailable`` /
    ``sso_domain_not_verified`` / ``sso_unverified_fallback`` /
    ``sso_no_membership`` — those vanished the same way. Valid
    declared tokens ride. Absent / blank is the honest first-visit
    default (``""``). Rest is stay-put (None). Distinct from leftover
    2FA sent (oral #94) and leftover 2FA mode (oral #92). Live
    simple_task ``/login``. Cycle 2221.
    """
    text = "" if raw is None else str(raw).strip()
    if not text:
        return ""
    known = leftover_honest_catalog_option_values(declared)
    honest = leftover_honest_catalog_id(text, known, "", allow_empty_rest=True)
    if honest and honest in set(known):
        return honest
    return None


# secrets.token_urlsafe(32) — session ids, reset tokens, invitation tokens.
_AUTH_URLSAFE_TOKEN = re.compile(r"\A[A-Za-z0-9_-]{32,256}\Z")


def leftover_honest_auth_email(raw: Any) -> str | None:
    """Valid mailbox emails ride. Leftover junk restores None.

    Leftover ``email=zzz`` / ``ghost`` / ``zzz@ghost`` on magic-link
    login/signup used to invent ``/login/sent`` theater (nonempty
    leftover omitted as unknown). The same leftover on
    forgot-password invented ``/forgot-password/sent``. Leftover
    on invite invented a persist. Leftover ``?email=zzz`` on
    enterprise/SAML login invented the host-pinned default IdP
    (no ``@`` treated as absent). Valid mailboxes ride
    (lowercased). Absent / blank is the honest first-visit
    default (``""``). Rest is stay-put (None → 400). Distinct
    from leftover GET list email VALUE (oral #80) and leftover
    SCIM userName (oral #102). Live simple_task
    ``/auth/login/magic-link``. Cycle 2233.
    """
    if raw is None:
        return ""
    if type(raw) is not str:
        return None
    text = raw.strip()
    if not text:
        return ""
    if not is_mailbox_shape(text):
        return None
    return text.lower()


def leftover_auth_email_or_400(raw: Any) -> str | HTMLResponse:
    """Stay-put 400 when leftover email would invent. Valid / absent ride.

    HTMLResponse (not Response(content=)) — oral #93. Callers return the
    response as-is when it is not a str.
    """
    honest = leftover_honest_auth_email(raw)
    if honest is None:
        return HTMLResponse("Invalid email", status_code=400)
    return honest


def leftover_honest_auth_token(raw: Any) -> str | None:
    """Valid urlsafe auth tokens ride. Leftover junk restores None.

    Leftover ``?token=zzz`` / ``?session=zzz`` used to invent a reset /
    2FA form (token echo theater). ``secrets.token_urlsafe(32)`` tokens
    ride. Absent / blank is the honest first-visit default (``""``).
    Rest is stay-put (None). Distinct from leftover auth error
    (oral #95) and leftover 2FA mode (oral #92). Live simple_task
    ``/reset-password`` + ``/2fa/challenge``. Cycle 2224.
    """
    text = "" if raw is None else str(raw).strip()
    if not text:
        return ""
    if _AUTH_URLSAFE_TOKEN.fullmatch(text):
        return text
    return None


def build_login_magic_link_view(
    *,
    page_title: str,
    product_name: str,
    next_url: str = "/",
    error_message: str = "",
    sso_providers: tuple[Any, ...] = (),
    css_links: tuple[str, ...] = ("/static/dist/dazzle.min.css",),
    js_scripts: tuple[str, ...] = ("/static/dist/dazzle.min.js",),
) -> Page:
    """Render the email-only magic-link login page.

    Single email field + "Send sign-in link" submit. POSTs to
    `/auth/login/magic-link`, which issues a token and redirects
    the user to `/login/sent` (regardless of whether the email
    matches a known user — defensive against account enumeration).

    `next_url` is preserved through the form as a hidden field so
    the post-link-consumption redirect lands the user on the page
    they originally requested. `error_message` renders as a
    visible-error block above the form when the previous attempt
    failed (e.g. invalid token).

    `sso_providers` is the tuple of `SsoProviderConfig`s configured
    on `app.state.sso_providers`. When non-empty, a "Continue with
    <provider>" link is rendered above the email form for each
    provider, with an "or continue with" divider.
    """
    from dazzle.http.runtime.auth.sso_views import build_sso_button_row

    form_action = "/auth/login/magic-link"
    if next_url and next_url != "/":
        form_action = f"{form_action}?next={next_url}"

    body_children: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body=page_title, level=1),
    ]
    if error_message:
        body_children.append(Text(body=error_message, tone="danger"))

    body_children.extend(build_sso_button_row(providers=sso_providers, next_url=next_url))

    body_children.append(
        FormStack(
            action=URL(form_action),
            method="POST",
            fields=(
                Field(
                    name="email",
                    label="Email",
                    kind="email",
                    required=True,
                    placeholder="you@example.com",
                ),
            ),
            submit=Submit(label="Send sign-in link", variant="primary"),
        )
    )

    return Page(
        title=f"{page_title} — {product_name}",
        body=Stack(children=tuple(body_children)),
        css_links=css_links,
        js_scripts=js_scripts,
    )


def build_login_password_view(
    *,
    page_title: str,
    product_name: str,
    next_url: str = "/",
    error_message: str = "",
    sso_providers: tuple[Any, ...] = (),
    css_links: tuple[str, ...] = ("/static/dist/dazzle.min.css",),
    js_scripts: tuple[str, ...] = ("/static/dist/dazzle.min.js",),
) -> Page:
    """Render the email+password login page (Phase 1.B.3, v0.67.32).

    Two-field form (email + password). POSTs to `/auth/login/password`,
    which authenticates the credentials, creates a session, sets the
    `dazzle_session` cookie, and redirects to `next_url` (or `/app` if
    missing). Failed authentication redirects back here with
    `?error=invalid_credentials`.

    A "Forgot password?" link to `/forgot-password` is included for the
    password-mode flow; a "Use sign-in link instead" link to `/login`
    is NOT included because in password mode the magic-link route is
    off — flipping deployments choose one mode at startup.

    `sso_providers` (Phase 1.C, v0.67.39): when non-empty, "Continue
    with <provider>" links render above the email/password form.
    """
    from dazzle.http.runtime.auth.sso_views import build_sso_button_row

    form_action = "/auth/login/password"
    if next_url and next_url != "/":
        form_action = f"{form_action}?next={next_url}"

    body_children: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body=page_title, level=1),
    ]
    if error_message:
        body_children.append(Text(body=error_message, tone="danger"))

    body_children.extend(build_sso_button_row(providers=sso_providers, next_url=next_url))

    body_children.append(
        FormStack(
            action=URL(form_action),
            method="POST",
            fields=(
                Field(
                    name="email",
                    label="Email",
                    kind="email",
                    required=True,
                    placeholder="you@example.com",
                ),
                Field(
                    name="password",
                    label="Password",
                    kind="password",
                    required=True,
                ),
            ),
            submit=Submit(label="Sign in", variant="primary"),
        )
    )
    body_children.append(Link(label="Forgot password?", href=URL("/forgot-password")))
    body_children.append(Text(body="New here? ", tone="muted"))
    body_children.append(Link(label="Create an account", href=URL("/signup")))

    return Page(
        title=f"{page_title} — {product_name}",
        body=Stack(children=tuple(body_children)),
        css_links=css_links,
        js_scripts=js_scripts,
    )


def build_signup_password_view(
    *,
    page_title: str,
    product_name: str,
    next_url: str = "/",
    error_message: str = "",
    css_links: tuple[str, ...] = ("/static/dist/dazzle.min.css",),
    js_scripts: tuple[str, ...] = ("/static/dist/dazzle.min.js",),
) -> Page:
    """Render the password-mode signup page (Phase 1.B.3, v0.67.32).

    Four fields: full name, email, password, confirm password. POSTs
    to `/auth/signup/password`, which:
      1. Checks new_password == confirm_password (server-side, no JS).
      2. Creates the user via `auth_store.create_user(email, password)`.
      3. Creates a session + sets the `dazzle_session` cookie.
      4. Redirects to `next_url` (or `/app`).
    Failure paths redirect back here with `?error=mismatch` /
    `?error=already_registered` / `?error=create_failed`.
    """
    form_action = "/auth/signup/password"
    if next_url and next_url != "/":
        form_action = f"{form_action}?next={next_url}"

    body_children: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body=page_title, level=1),
    ]
    if error_message:
        body_children.append(Text(body=error_message, tone="danger"))

    body_children.append(
        FormStack(
            action=URL(form_action),
            method="POST",
            fields=(
                Field(
                    name="name",
                    label="Full name",
                    kind="text",
                    required=True,
                    placeholder="Alice Wong",
                ),
                Field(
                    name="email",
                    label="Email",
                    kind="email",
                    required=True,
                    placeholder="you@example.com",
                ),
                Field(
                    name="password",
                    label="Password",
                    kind="password",
                    required=True,
                ),
                Field(
                    name="confirm_password",
                    label="Confirm password",
                    kind="password",
                    required=True,
                ),
            ),
            submit=Submit(label="Create account", variant="primary"),
        )
    )
    body_children.append(Text(body="Already have an account? ", tone="muted"))
    body_children.append(Link(label="Sign in", href=URL("/login")))

    return Page(
        title=f"{page_title} — {product_name}",
        body=Stack(children=tuple(body_children)),
        css_links=css_links,
        js_scripts=js_scripts,
    )


def build_signup_magic_link_view(
    *,
    page_title: str,
    product_name: str,
    next_url: str = "/",
    error_message: str = "",
    css_links: tuple[str, ...] = ("/static/dist/dazzle.min.css",),
    js_scripts: tuple[str, ...] = ("/static/dist/dazzle.min.js",),
) -> Page:
    """Render the signup page (email + name only — magic-link mode).

    POSTs to `/auth/signup/magic-link`, which is create-or-login:
    if the email already has an account, treat as login;
    otherwise, create a passwordless user record and issue the
    magic link. Either way the user lands on `/login/sent` with
    the same confirmation page (no leakage about account state).

    `name` is captured for the new-user path; existing users get
    a sign-in link regardless of whether they supply a name.
    """
    form_action = "/auth/signup/magic-link"
    if next_url and next_url != "/":
        form_action = f"{form_action}?next={next_url}"

    body_children: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body=page_title, level=1),
    ]
    if error_message:
        body_children.append(Text(body=error_message, tone="danger"))

    body_children.append(
        FormStack(
            action=URL(form_action),
            method="POST",
            fields=(
                Field(
                    name="name",
                    label="Full name",
                    kind="text",
                    required=True,
                    placeholder="Alice Wong",
                ),
                Field(
                    name="email",
                    label="Email",
                    kind="email",
                    required=True,
                    placeholder="you@example.com",
                ),
            ),
            submit=Submit(label="Send sign-up link", variant="primary"),
        )
    )
    body_children.append(Text(body="Already have an account? ", tone="muted"))
    body_children.append(Link(label="Sign in", href=URL("/login")))

    return Page(
        title=f"{page_title} — {product_name}",
        body=Stack(children=tuple(body_children)),
        css_links=css_links,
        js_scripts=js_scripts,
    )


def build_forgot_password_view(
    *,
    product_name: str,
    page_title: str = "Reset your password",
    error_message: str = "",
    css_links: tuple[str, ...] = ("/static/dist/dazzle.min.css",),
    js_scripts: tuple[str, ...] = ("/static/dist/dazzle.min.js",),
) -> Page:
    """Render the forgot-password request page (Phase 1.B.2, v0.67.31).

    Single email field + "Send reset link" submit. POSTs to
    `/auth/forgot-password/submit`, which (defensive against account
    enumeration) ALWAYS redirects to `/forgot-password/sent`
    regardless of whether the email matched a real user.
    """
    body_children: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body=page_title, level=1),
        Text(
            body="Enter the email you signed up with — we'll send you a link to set a new password.",
            tone="muted",
        ),
    ]
    if error_message:
        body_children.append(Text(body=error_message, tone="danger"))

    body_children.append(
        FormStack(
            action=URL("/auth/forgot-password/submit"),
            method="POST",
            fields=(
                Field(
                    name="email",
                    label="Email",
                    kind="email",
                    required=True,
                    placeholder="you@example.com",
                ),
            ),
            submit=Submit(label="Send reset link", variant="primary"),
        )
    )
    body_children.append(Text(body="Remembered it? ", tone="muted"))
    body_children.append(Link(label="Back to sign in", href=URL("/login")))

    return Page(
        title=f"{page_title} — {product_name}",
        body=Stack(children=tuple(body_children)),
        css_links=css_links,
        js_scripts=js_scripts,
    )


def build_forgot_password_sent_view(
    *,
    product_name: str,
    css_links: tuple[str, ...] = ("/static/dist/dazzle.min.css",),
    js_scripts: tuple[str, ...] = ("/static/dist/dazzle.min.js",),
) -> Page:
    """Render the post-forgot-password confirmation page.

    Account-enumeration safe — the same page is shown whether the
    email matched a real user or not. The user reaches this page
    only by POSTing the forgot-password form; the GET route is
    not exposed externally.
    """
    title = "Check your inbox"
    description = (
        "If an account exists for that address, we've sent a "
        "password-reset link. Open it from the same device to continue."
    )
    return Page(
        title=f"{title} — {product_name}",
        body=Stack(
            children=(
                Link(label=product_name, href=URL("/")),
                EmptyState(
                    title=title,
                    description=description,
                ),
                Text(body="Didn't get it? Check your spam folder, or "),
                Link(label="try a different email", href=URL("/forgot-password")),
            )
        ),
        css_links=css_links,
        js_scripts=js_scripts,
    )


def build_reset_password_view(
    *,
    product_name: str,
    token: str,
    page_title: str = "Set a new password",
    error_message: str = "",
    css_links: tuple[str, ...] = ("/static/dist/dazzle.min.css",),
    js_scripts: tuple[str, ...] = ("/static/dist/dazzle.min.js",),
) -> Page:
    """Render the reset-password form (Phase 1.B.2, v0.67.31).

    Hidden `token` field carries the validated reset token to
    `/auth/reset-password/submit`. New password + confirmation are
    server-side equality-checked; a mismatch redirects back here
    with an error message in the query.
    """
    body_children: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body=page_title, level=1),
    ]
    if error_message:
        body_children.append(Text(body=error_message, tone="danger"))

    body_children.append(
        FormStack(
            action=URL("/auth/reset-password/submit"),
            method="POST",
            fields=(
                Field(
                    name="token",
                    label="Reset token",
                    kind="text",
                    required=True,
                    initial_value=token,
                    readonly=True,
                ),
                Field(
                    name="new_password",
                    label="New password",
                    kind="password",
                    required=True,
                ),
                Field(
                    name="confirm_password",
                    label="Confirm new password",
                    kind="password",
                    required=True,
                ),
            ),
            submit=Submit(label="Save new password", variant="primary"),
        )
    )

    return Page(
        title=f"{page_title} — {product_name}",
        body=Stack(children=tuple(body_children)),
        css_links=css_links,
        js_scripts=js_scripts,
    )


def build_reset_password_done_view(
    *,
    product_name: str,
    css_links: tuple[str, ...] = ("/static/dist/dazzle.min.css",),
    js_scripts: tuple[str, ...] = ("/static/dist/dazzle.min.js",),
) -> Page:
    """Render the post-reset confirmation page.

    Shown after `/auth/reset-password/submit` succeeds. Includes a
    direct link to `/login` so the user can sign in with the new
    password immediately.
    """
    title = "Password updated"
    description = "Your password has been changed. You can now sign in with your new credentials."
    return Page(
        title=f"{title} — {product_name}",
        body=Stack(
            children=(
                Link(label=product_name, href=URL("/")),
                EmptyState(
                    title=title,
                    description=description,
                ),
                Link(label="Sign in", href=URL("/login")),
            )
        ),
        css_links=css_links,
        js_scripts=js_scripts,
    )


def build_login_sent_view(
    *,
    product_name: str,
    email: str = "",
    css_links: tuple[str, ...] = ("/static/dist/dazzle.min.css",),
    js_scripts: tuple[str, ...] = ("/static/dist/dazzle.min.js",),
) -> Page:
    """Render the post-magic-link confirmation page.

    "Check your inbox" message + a hint about what happens next.
    `email` is shown back to the user when supplied — defensive:
    omit if the issuance route can't safely echo the input (e.g.
    when account-enumeration protection is required).
    """
    title = "Check your inbox"
    description = (
        f"We've sent a sign-in link to {email}. Open it from the same device to continue."
        if email
        else (
            "If an account exists for that address, we've sent a "
            "sign-in link. Open it from the same device to continue."
        )
    )

    return Page(
        title=f"{title} — {product_name}",
        body=Stack(
            children=(
                Link(label=product_name, href=URL("/")),
                EmptyState(
                    title=title,
                    description=description,
                ),
                Text(body="Didn't get it? Check your spam folder, or "),
                Link(label="try a different email", href=URL("/login")),
            )
        ),
        css_links=css_links,
        js_scripts=js_scripts,
    )
