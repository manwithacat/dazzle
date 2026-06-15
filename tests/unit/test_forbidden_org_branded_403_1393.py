"""#1393 branded-403 — the host-pin denial now returns a branded HTML 403
page (not a bare JSON ``HTTPException``) on the five browser login routes.
"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.responses import HTMLResponse

from dazzle.back.runtime.auth.forbidden_org import forbidden_org_response
from dazzle.back.runtime.auth.org_context_views import build_forbidden_org_view


def _request_with_brand(product_name: str | None) -> SimpleNamespace:
    sitespec = {"brand": {"product_name": product_name}} if product_name else {}
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(sitespec=sitespec)))


def test_forbidden_org_view_is_branded_and_non_blank():
    page = build_forbidden_org_view(product_name="Acme")
    # Render via the framework FragmentRenderer (same path the route uses).
    from dazzle.render.fragment.renderer import FragmentRenderer

    html = FragmentRenderer().render(page)
    assert html.strip()
    assert "isn't your organisation" in html
    assert "Acme" in html


def test_forbidden_org_response_is_html_403():
    resp = forbidden_org_response(_request_with_brand("Acme"))
    assert isinstance(resp, HTMLResponse)
    assert resp.status_code == 403
    body = resp.body.decode()
    assert "isn't your organisation" in body
    # Not a bare JSON error — it carries branded copy + the product name.
    assert "Acme" in body


def test_forbidden_org_response_defaults_product_name():
    """No sitespec brand → falls back to the default product name, never errors."""
    resp = forbidden_org_response(_request_with_brand(None))
    assert resp.status_code == 403
    assert "Dazzle" in resp.body.decode()
