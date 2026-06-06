"""Typed-Fragment connection-admin page (auth Plan: org-admin connection surface).

Renders an org admin's view of their org's enterprise connections. **Secret-free** — it
shows type / status / domains / readiness only; a connection's encrypted secret material
(OIDC client_secret, SCIM bearer) is NEVER read or rendered here. Domain management (claim +
DNS-TXT verify) is the in-app counterpart to the operator CLI.
"""

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


def _connection_block(conn: dict[str, Any]) -> Stack:
    """One connection: type/status, verified + claimed domains, domain controls.

    ``conn`` keys: id, type, status, verified (list[str]), unverified
    (list[{domain, txt}]), active_for_sso (bool — has ≥1 verified domain).
    """
    children: list[Any] = [
        Text(body=f"{conn['type'].upper()} connection — {conn['id']}"),
        Badge(
            label=conn["status"],
            variant="default" if conn["status"] == "active" else "warning",
        ),
        Badge(
            label="Verified domain ✓" if conn["active_for_sso"] else "No verified domain",
            variant="default" if conn["active_for_sso"] else "warning",
        ),
    ]

    verified = conn["verified"]
    children.append(
        Text(
            body="Verified domains: " + (", ".join(verified) if verified else "none"),
            tone="muted",
        )
    )

    # Claimed-but-unverified domains: show the DNS TXT record to publish + a Verify button.
    for entry in conn["unverified"]:
        domain = entry["domain"]
        children.append(Text(body=f"Pending: {domain}"))
        children.append(Text(body=f'  publish TXT  "{entry["txt"]}"', tone="muted"))
        children.append(
            Button(
                label=f"Verify {domain}",
                variant="secondary",
                hx_post=URL(
                    f"/auth/connections/verify-domain?connection_id={conn['id']}&domain={domain}"
                ),
                hx_target=TargetSelector("body"),
            )
        )

    # Claim a new domain (plain form → prints its TXT on the refreshed page).
    children.append(
        FormStack(
            action=URL(f"/auth/connections/add-domain?connection_id={conn['id']}"),
            method="POST",
            fields=(Field(name="domain", label="Add domain", kind="text"),),
            submit=Submit(label="Claim domain", variant="secondary"),
        )
    )
    return Stack(children=tuple(children))


def build_connections_view(
    *,
    product_name: str,
    org_name: str,
    connections: list[dict[str, Any]],
) -> Page:
    body: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body=f"SSO connections for {org_name}", level=1),
        Text(
            body="Verify a domain to activate a connection: claim it, publish the DNS TXT "
            "record, then Verify. Creating connections (with IdP secrets) is done by your "
            "operator with the dazzle CLI.",
            tone="muted",
        ),
    ]
    if not connections:
        body.append(Text(body="No connections for this organization yet.", tone="muted"))
    else:
        for conn in connections:
            body.append(_connection_block(conn))
    return Page(
        title=f"SSO connections — {product_name}",
        body=Stack(children=tuple(body)),
        css_links=_CSS,
        js_scripts=_JS,
    )
