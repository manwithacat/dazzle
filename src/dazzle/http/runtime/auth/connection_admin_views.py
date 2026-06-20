"""Typed-Fragment connection-admin page (auth Plan: org-admin connection surface).

Renders an org admin's view of their org's enterprise connections. **Secret-free** — it
shows type / status / domains / readiness only; a connection's encrypted secret material
(OIDC client_secret, SCIM bearer) is NEVER read or rendered here. Domain management (claim +
DNS-TXT verify) is the in-app counterpart to the operator CLI.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

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


def _readiness_block(readiness: dict[str, Any]) -> list[Any]:
    """Activation-readiness panel (secret-free — presence checks + remedies only)."""
    out: list[Any] = [
        Badge(
            label="Activation-ready ✓" if readiness["ready"] else "Not activation-ready",
            variant="default" if readiness["ready"] else "warning",
        )
    ]
    for check in readiness["checks"]:
        mark = "✓" if check["ok"] else "✗"
        out.append(Text(body=f"{mark} {check['name']}: {check['detail']}", tone="muted"))
    if not readiness["ready"] and readiness["next_steps"]:
        out.append(Text(body="What's left:", tone="muted"))
        for step in readiness["next_steps"]:
            out.append(Text(body=f"  • {step}", tone="muted"))
    return out


def _history_block(events: list[dict[str, Any]]) -> list[Any]:
    """Read-only secret-rotation history (event names + timestamps; never a secret)."""
    out: list[Any] = [Text(body="Secret-rotation history")]
    if not events:
        out.append(Text(body="No rotation events yet.", tone="muted"))
        return out
    for e in events:
        line = f"{e['at']}  {e['event']}  ({e['actor']})"
        if e.get("grace_until"):
            line += f"  → grace until {e['grace_until']}"
        out.append(Text(body=line, tone="muted"))
    return out


def _connection_block(conn: dict[str, Any]) -> Stack:
    """One connection: type/status, verified + claimed domains, domain controls.

    ``conn`` keys: id, type, status, verified (list[str]), unverified
    (list[{domain, txt}]), active_for_sso (bool — has ≥1 verified domain), plus the
    secret-free readiness/events/grace fields attached by the route.
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

    children.extend(
        _readiness_block(conn.get("readiness", {"ready": False, "checks": [], "next_steps": []}))
    )
    grace = conn.get("grace") or {}
    if grace.get("active"):
        children.append(
            Badge(label=f"Grace window active until {grace['expires_at']}", variant="warning")
        )

    verified = conn["verified"]
    children.append(
        Text(
            body="Verified domains: " + (", ".join(verified) if verified else "none"),
            tone="muted",
        )
    )

    cid_q = quote(conn["id"], safe="")
    # Claimed-but-unverified domains: show the DNS TXT record to publish + a Verify button.
    for entry in conn["unverified"]:
        domain = entry["domain"]
        children.append(Text(body=f"Pending: {domain}"))
        children.append(Text(body=f'  publish TXT  "{entry["txt"]}"', tone="muted"))
        # Percent-encode the query values: a domain stored out-of-band (bypassing the
        # add-domain `_is_valid_domain` guard) can't then inject extra query params.
        children.append(
            Button(
                label=f"Verify {domain}",
                variant="secondary",
                hx_post=URL(
                    f"/auth/connections/verify-domain?connection_id={cid_q}"
                    f"&domain={quote(domain, safe='')}"
                ),
                hx_target=TargetSelector("body"),
            )
        )

    # Claim a new domain (plain form → prints its TXT on the refreshed page).
    children.append(
        FormStack(
            action=URL(f"/auth/connections/add-domain?connection_id={cid_q}"),
            method="POST",
            fields=(Field(name="domain", label="Add domain", kind="text"),),
            submit=Submit(label="Claim domain", variant="secondary"),
        )
    )
    children.extend(_history_block(conn.get("events", [])))
    return Stack(children=tuple(children))


_OIDC_FIELDS = (
    Field(name="issuer", label="Issuer URL (https://…)", kind="url", required=True),
    Field(name="client_id", label="Client id", kind="text", required=True),
    Field(name="client_secret", label="Client secret", kind="password", required=True),
    Field(name="group_map", label="Group→role map (eng=engineer, …)", kind="text"),
)
_SCIM_FIELDS = (Field(name="group_map", label="Group→role map (eng=engineer, …)", kind="text"),)
_SAML_FIELDS = (
    Field(name="idp_metadata_url", label="IdP metadata URL (https; auto-fills below)", kind="url"),
    Field(name="idp_entity_id", label="IdP entity id (or via metadata URL)", kind="text"),
    Field(name="idp_sso_url", label="IdP SSO URL (or via metadata URL)", kind="url"),
    Field(
        name="idp_x509_cert", label="IdP signing cert PEM (or via metadata URL)", kind="textarea"
    ),
    Field(name="email_attribute", label="Email attribute (optional)", kind="text"),
    Field(name="groups_attribute", label="Groups attribute (optional)", kind="text"),
    Field(name="group_map", label="Group→role map (eng=engineer, …)", kind="text"),
)
_CREATE_FORMS = {
    "oidc": ("Create OIDC connection", _OIDC_FIELDS),
    "scim": ("Create SCIM connection", _SCIM_FIELDS),
    "saml": ("Create SAML connection", _SAML_FIELDS),
}


def _create_area(new_form: str, secret_key_ok: bool) -> list[Any]:
    """The 'Add a connection' chooser links, plus the active type's create form (one at a time)."""
    out: list[Any] = [Heading(body="Add a connection", level=2)]
    out.append(
        Stack(
            children=(
                Link(label="Add OIDC", href=URL("/auth/connections?new=oidc")),
                Link(label="Add SCIM", href=URL("/auth/connections?new=scim")),
                Link(label="Add SAML", href=URL("/auth/connections?new=saml")),
            )
        )
    )
    if new_form not in _CREATE_FORMS:
        return out
    # OIDC/SCIM store an encrypted secret, so they need the at-rest key; SAML has no secret.
    if new_form in ("oidc", "scim") and not secret_key_ok:
        out.append(
            Text(
                body="Creating an OIDC or SCIM connection needs DAZZLE_CONNECTION_SECRET set "
                "(the at-rest key for the encrypted secret). Ask your operator to set it.",
                tone="muted",
            )
        )
        return out
    label, fields = _CREATE_FORMS[new_form]
    if new_form == "scim":
        out.append(
            Text(body="A SCIM bearer token is generated and shown once on creation.", tone="muted")
        )
    out.append(
        FormStack(
            action=URL(f"/auth/connections/create?type={new_form}"),
            method="POST",
            fields=fields,
            submit=Submit(label=label, variant="primary"),
        )
    )
    return out


def _scim_bearer_banner(bearer: str, base_url: str) -> Stack:
    """One-time display of a freshly-minted SCIM bearer — shown once, never re-rendered/stored."""
    scim_url = f"{base_url.rstrip('/')}/scim/v2" if base_url else "<base_url>/scim/v2"
    return Stack(
        children=(
            Heading(body="SCIM connection created — save the bearer now", level=2),
            Text(body="This token is shown only once. Configure it in your IdP:", tone="muted"),
            Text(body=f"SCIM base URL:  {scim_url}"),
            Text(body=f"Bearer token:   {bearer}"),
        )
    )


def build_connections_view(
    *,
    product_name: str,
    org_name: str,
    connections: list[dict[str, Any]],
    new_form: str = "",
    secret_key_ok: bool = True,
    scim_bearer_once: str = "",
    base_url: str = "",
) -> Page:
    body: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body=f"SSO connections for {org_name}", level=1),
        Text(
            body="Verify a domain to activate a connection: claim it, publish the DNS TXT "
            "record, then Verify. You can create a connection below, or with the dazzle CLI.",
            tone="muted",
        ),
    ]
    if scim_bearer_once:
        body.append(_scim_bearer_banner(scim_bearer_once, base_url))
    body.extend(_create_area(new_form, secret_key_ok))
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
