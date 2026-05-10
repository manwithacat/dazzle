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

from typing import Any

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


def build_login_magic_link_view(
    *,
    page_title: str,
    product_name: str,
    next_url: str = "/",
    error_message: str = "",
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
    """
    form_action = "/auth/login/magic-link"
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
