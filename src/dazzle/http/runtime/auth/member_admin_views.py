"""Typed-Fragment member-admin page (auth Plan 3b)."""

from __future__ import annotations

from typing import Any

from dazzle.render.fragment import (
    URL,
    Badge,
    Button,
    Field,
    FormStack,
    Heading,
    Link,
    Page,
    Stack,
    Submit,
    TargetSelector,
    Text,
)

_CSS = ("/static/dist/dazzle.min.css",)
_JS = ("/static/dist/dazzle.min.js",)


def _member_block(
    *, membership_id: str, email: str, roles: list[str], status: str, is_last_admin: bool
) -> Stack:
    """One member's row: identity + roles + status, plus role-change + action controls."""
    role_text = ", ".join(roles) if roles else "—"
    children: list[Any] = [
        Text(body=f"{email} — {role_text}"),
        Badge(label=status, variant="default" if status == "active" else "warning"),
        # Role change (plain form; comma-separated personas).
        FormStack(
            action=URL(f"/auth/members/roles?membership_id={membership_id}"),
            method="POST",
            fields=(
                Field(
                    name="roles",
                    label="Roles",
                    kind="text",
                    initial_value=", ".join(roles),
                ),
            ),
            submit=Submit(label="Update roles", variant="secondary"),
        ),
    ]
    # Suspend / reactivate (htmx action button → HX-Redirect back). The
    # hx_target is required by the Button validator but unused: the route returns
    # an HX-Redirect header, so htmx does a full-page redirect (no swap).
    if status == "active":
        children.append(
            Button(
                label="Suspend",
                variant="secondary",
                hx_post=URL(f"/auth/members/suspend?membership_id={membership_id}"),
                hx_target=TargetSelector("body"),
                hx_confirm="Suspend this member's access?",
            )
        )
    elif status == "suspended":
        children.append(
            Button(
                label="Reactivate",
                variant="secondary",
                hx_post=URL(f"/auth/members/reactivate?membership_id={membership_id}"),
                hx_target=TargetSelector("body"),
            )
        )
    # Remove — disabled for the last admin (the server also enforces this).
    children.append(
        Button(
            label="Remove",
            variant="danger",
            visibility="disabled" if is_last_admin else "visible",
            hx_post=URL(f"/auth/members/remove?membership_id={membership_id}"),
            hx_target=TargetSelector("body"),
            hx_confirm="Remove this member from the organization?",
        )
    )
    return Stack(children=tuple(children))


def build_members_view(
    *,
    product_name: str,
    org_name: str,
    members: list[dict[str, Any]],  # {membership_id, email, roles, status, is_last_admin}
    pending: list[dict[str, Any]],  # {email, roles}
) -> Page:
    body: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body=f"Members of {org_name}", level=1),
        Heading(body="Invite a member", level=2),
        FormStack(
            action=URL("/auth/invite"),
            method="POST",
            fields=(
                Field(name="email", label="Email", kind="email", required=True),
                Field(name="roles", label="Roles (comma-separated)", kind="text"),
            ),
            submit=Submit(label="Send invitation", variant="primary"),
        ),
        Heading(body="Members", level=2),
    ]
    for m in members:
        body.append(
            _member_block(
                membership_id=m["membership_id"],
                email=m["email"],
                roles=m["roles"],
                status=m["status"],
                is_last_admin=m["is_last_admin"],
            )
        )
    body.append(Heading(body="Pending invitations", level=2))
    if not pending:
        body.append(Text(body="No pending invitations.", tone="muted"))
    else:
        for p in pending:
            roles = ", ".join(p["roles"]) if p["roles"] else "member"
            body.append(Text(body=f"{p['email']} — invited as {roles}"))
    return Page(
        title=f"Members — {product_name}",
        body=Stack(children=tuple(body)),
        css_links=_CSS,
        js_scripts=_JS,
    )


def _join_request_block(*, request_id: str, email: str) -> Stack:
    """One pending join request: identity + approve/deny action buttons.

    Approve CREATES a membership, so it carries a confirm. Both buttons return an
    HX-Redirect back to the queue (the ``hx_target`` is required by the Button
    validator but unused — the route returns an HX-Redirect header).
    """
    return Stack(
        children=(
            Text(body=email),
            Button(
                label="Approve",
                variant="primary",
                hx_post=URL(f"/auth/join-requests/approve?request_id={request_id}"),
                hx_target=TargetSelector("body"),
                hx_confirm="Approve this join request? This creates a membership.",
            ),
            Button(
                label="Deny",
                variant="secondary",
                hx_post=URL(f"/auth/join-requests/deny?request_id={request_id}"),
                hx_target=TargetSelector("body"),
                hx_confirm="Deny this join request?",
            ),
        )
    )


def build_join_requests_view(
    *,
    product_name: str,
    org_name: str,
    requests: list[dict[str, Any]],  # {request_id, email}
) -> Page:
    """The pending join-requests approval queue for one org.

    Mirrors ``build_members_view``'s list idiom: a heading, then one block per row,
    with a muted empty-state when the queue is clear.
    """
    body: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Link(label="← Members", href=URL("/auth/members")),
        Heading(body=f"Join requests for {org_name}", level=1),
    ]
    if not requests:
        body.append(Text(body="No pending join requests.", tone="muted"))
    else:
        for r in requests:
            body.append(_join_request_block(request_id=r["request_id"], email=r["email"]))
    return Page(
        title=f"Join requests — {product_name}",
        body=Stack(children=tuple(body)),
        css_links=_CSS,
        js_scripts=_JS,
    )
