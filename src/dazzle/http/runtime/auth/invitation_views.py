"""Typed-Fragment pages for org invitations (auth Plan 3a).

``build_accept_invite_view`` shows who invited the user, into which org, with
which roles. When the visitor is signed in it posts the token (a hidden field) to
``POST /auth/accept-invite``; otherwise it routes to sign-in with a ``next`` back
to the accept page (the verified-email join is enforced server-side regardless).
``build_invite_result_view`` is a simple invite-sent / error page.
"""

from __future__ import annotations

from typing import Any

from dazzle.render.fragment import (
    URL,
    Field,
    FormStack,
    Heading,
    Link,
    Page,
    Stack,
    Submit,
    Text,
)

_CSS = ("/static/dist/dazzle.min.css",)
_JS = ("/static/dist/dazzle.min.js",)


def build_accept_invite_view(
    *,
    product_name: str,
    org_name: str,
    roles: list[str],
    token: str,
    signed_in_email: str | None,
) -> Page:
    """The accept-invitation page (posts the token to ``POST /auth/accept-invite``)."""
    role_text = ", ".join(roles) if roles else "member"
    body_children: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body=f"Join {org_name}", level=1),
        Text(body=f"You've been invited to join {org_name} as {role_text}."),
    ]
    if signed_in_email:
        # The token rides in the form action query (the Fragment substrate has no
        # hidden-input primitive); the readonly field is a visible confirmation.
        # The route reads `token` from the query and re-validates the verified-email
        # join server-side, so the action URL is not a trust boundary.
        body_children.append(
            FormStack(
                action=URL(f"/auth/accept-invite?token={token}"),
                method="POST",
                fields=(
                    Field(
                        name="accepting_as",
                        label="Accepting as",
                        kind="text",
                        initial_value=signed_in_email,
                        readonly=True,
                    ),
                ),
                submit=Submit(label="Accept invitation", variant="primary"),
            )
        )
    else:
        body_children.append(
            Text(body="Sign in with the invited email address to accept.", tone="muted")
        )
        body_children.append(
            Link(label="Sign in to accept", href=URL(f"/login?next=/auth/accept-invite/{token}"))
        )
    return Page(
        title=f"Join {org_name} — {product_name}",
        body=Stack(children=tuple(body_children)),
        css_links=_CSS,
        js_scripts=_JS,
    )


def build_invite_result_view(*, product_name: str, message: str) -> Page:
    """A simple result page (invitation sent / error)."""
    return Page(
        title=f"Invitation — {product_name}",
        body=Stack(
            children=(
                Link(label=product_name, href=URL("/")),
                Heading(body="Invitation", level=1),
                Text(body=message),
            )
        ),
        css_links=_CSS,
        js_scripts=_JS,
    )
