"""Typed-Fragment views for Phase-2 org context (auth Plan 1b).

``build_select_org_view`` lists the identity's active memberships as a select
form posting to ``/auth/select-org``. ``build_no_orgs_view`` is the honest
"no orgs yet" page (an app that has not opted into the membership model never
reaches it; Plan 1c auto-provisions a single-org membership so single-org apps
never see it either).
"""

from __future__ import annotations

from typing import Any

from dazzle.render.fragment import (
    URL,
    Combobox,
    FormStack,
    Heading,
    Link,
    Page,
    Stack,
    Submit,
    Text,
)


def _membership_label(m: Any) -> str:
    """Display name for a membership option — its org name when known, else the
    tenant discriminator."""
    name = getattr(m, "name", None)
    return str(name) if name else str(m.tenant_id)


def build_select_org_view(
    *,
    product_name: str,
    memberships: tuple[Any, ...],
    next_url: str = "/app",
    css_links: tuple[str, ...] = ("/static/dist/dazzle.min.css",),
    js_scripts: tuple[str, ...] = ("/static/dist/dazzle.min.js",),
) -> Page:
    """Org picker — a select of the identity's active memberships."""
    form_action = "/auth/select-org"
    if next_url and next_url != "/":
        form_action = f"{form_action}?next={next_url}"

    body_children: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body="Choose an organization", level=1),
    ]
    if memberships:
        options = tuple((m.id, _membership_label(m)) for m in memberships)
        body_children.append(
            FormStack(
                action=URL(form_action),
                method="POST",
                fields=(
                    Combobox(
                        name="membership_id",
                        label="Organization",
                        options=options,
                        required=True,
                    ),
                ),
                submit=Submit(label="Continue", variant="primary"),
            )
        )
    else:
        body_children.append(Text(body="You don't belong to any organization yet.", tone="muted"))

    return Page(
        title=f"Choose an organization — {product_name}",
        body=Stack(children=tuple(body_children)),
        css_links=css_links,
        js_scripts=js_scripts,
    )


def build_no_orgs_view(
    *,
    product_name: str,
    css_links: tuple[str, ...] = ("/static/dist/dazzle.min.css",),
    js_scripts: tuple[str, ...] = ("/static/dist/dazzle.min.js",),
) -> Page:
    """ "No orgs yet" — the identity is proven but has no active membership."""
    body_children: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body="No organizations yet", level=1),
        Text(
            body="You're signed in, but you don't belong to any organization yet. "
            "Ask an admin for an invitation, or create one.",
            tone="muted",
        ),
    ]
    return Page(
        title=f"No organizations yet — {product_name}",
        body=Stack(children=tuple(body_children)),
        css_links=css_links,
        js_scripts=js_scripts,
    )
