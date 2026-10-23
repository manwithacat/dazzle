"""The product name shown in auth-page chrome, resolved once.

This lookup — ``request.app.state.sitespec`` → ``brand`` → ``product_name``,
then ``app.state.app_title``, defaulting to ``"Dazzle"`` — was copy-pasted into six auth route modules. One of
the six (``forbidden_org.py``) carried a docstring explaining why; the other five
carried nothing, so a reader could not tell whether the copy was load-bearing.
That is the actual cost of the duplication, not the six lines themselves (#1746).

It lives here, in a module with no router imports, so every login route can import
it without pulling in a router dependency — which is the constraint the original
per-router copies were written to satisfy. The auth package already holds plain
non-router modules (``cookie_name.py``, ``redirect_safety.py``, ``current.py``),
so this is that pattern, not a new one.

The value is user-visible: page titles, email subjects, and the sign-in page's
copy all read it, so a change to the sitespec brand shape lands here once.
"""

from __future__ import annotations

from typing import Any


def product_name(request: Any) -> str:
    """The configured product name for auth-page chrome.

    Order: the sitespec ``brand.product_name``, then the DSL ``app`` title
    (``app.state.app_title``, set by ``assemble_post_build_routes``), then
    ``"Dazzle"`` (#1842, WCAG 3.2.4 — the auth pages named the framework, not
    the product, because nothing set ``app.state.sitespec``).

    Accepts the Starlette ``Request`` but is typed ``Any`` so this module needs no
    runtime import of the web layer — see the module docstring on why that matters.
    """
    state = request.app.state
    sitespec = getattr(state, "sitespec", None) or {}
    brand = sitespec.get("brand", {}) if isinstance(sitespec, dict) else {}
    name = brand.get("product_name") if isinstance(brand, dict) else None
    return str(name or getattr(state, "app_title", None) or "Dazzle")
