"""Confirmation page for a pending self-service domain-join (#1424 Task 3.5).

``GET /auth/join-requested`` is the landing page for users whose email domain
maps to a tenant that requires admin approval before auto-provisioning a
membership (``domain_join_policy = admin_approval``).

Security invariant (enumeration #4): the page MUST NOT confirm any tenant
identity or reveal that a specific organisation exists. Copy is generic.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from dazzle.render.fragment import (
    URL,
    EmptyState,
    Link,
    Page,
    Stack,
)

_CONFIRMATION_MESSAGE = "Your request to join has been submitted and is awaiting approval."
_PAGE_TITLE = "Request submitted"


def _build_join_requested_view(
    *,
    product_name: str = "Dazzle",
    css_links: tuple[str, ...] = ("/static/dist/dazzle.min.css",),
    js_scripts: tuple[str, ...] = ("/static/dist/dazzle.min.js",),
) -> Page:
    """Render the generic join-request-submitted confirmation page.

    Account-enumeration safe — generic copy only; no tenant name, no org slug,
    no email echo. The same page is shown regardless of which tenant the domain
    resolved to.
    """
    return Page(
        title=f"{_PAGE_TITLE} — {product_name}",
        body=Stack(
            children=(
                Link(label=product_name, href=URL("/")),
                EmptyState(
                    title=_PAGE_TITLE,
                    description=_CONFIRMATION_MESSAGE,
                ),
                Link(label="Return to sign in", href=URL("/login")),
            )
        ),
        css_links=css_links,
        js_scripts=js_scripts,
    )


def create_join_request_routes() -> APIRouter:
    """Build the join-request confirmation router.

    Exposes a single endpoint:

    ``GET /auth/join-requested`` — informational confirmation page shown after
    a self-service domain-join attempt is queued for admin approval.
    """
    router = APIRouter(tags=["auth"])

    @router.get("/auth/join-requested", response_class=HTMLResponse, include_in_schema=False)
    async def join_requested_page(request: Request) -> str:
        from dazzle.render.fragment.renderer import FragmentRenderer

        sitespec = getattr(request.app.state, "sitespec", None) or {}
        brand = sitespec.get("brand", {}) if isinstance(sitespec, dict) else {}
        product_name = str(brand.get("product_name", "Dazzle"))

        page = _build_join_requested_view(product_name=product_name)
        return FragmentRenderer().render(page)

    return router
