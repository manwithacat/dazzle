"""Branded host-pin 403 response (#1393 branded-403 slice).

The host-pinned login flows (`resolve_activation` → `HostForbidden` →
`FORBIDDEN_SENTINEL`) denied a non-member with a bare
``HTTPException(403, "no membership for this organization")`` — a raw JSON
error page in the browser. This module is the single shared helper the five
browser login routes (password ×2, magic-link, SSO, 2FA) now return instead:
a branded "this isn't your organisation" page.

The JSON API login path (`routes._json_active_membership_id`) deliberately
keeps the JSON 403 — an API client wants the machine-readable error, not HTML.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from dazzle.http.runtime.auth.product_name import product_name


def forbidden_org_response(request: Request) -> HTMLResponse:
    """Render the branded host-pin 403 page as an ``HTMLResponse`` (status 403).

    Returned (not raised) by the browser login flows when a proven identity is
    pinned by the host to an organisation it isn't a member of.
    """
    from dazzle.http.runtime.auth.org_context_views import build_forbidden_org_view
    from dazzle.render.fragment.renderer import FragmentRenderer

    html = FragmentRenderer().render(build_forbidden_org_view(product_name=product_name(request)))
    return HTMLResponse(html, status_code=403)
