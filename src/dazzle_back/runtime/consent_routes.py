"""Consent banner HTTP routes (v0.61.0 Phase 2).

Exposes three endpoints:

- ``POST /dz/consent`` — write the user's choices as the ``dz_consent_v2``
  cookie; returns 204. Accepts JSON ``{analytics, advertising, personalization,
  functional}`` with boolean values.
- ``GET /dz/consent/banner`` — re-render just the banner HTML fragment for
  the Manage-cookies reopen flow. Returns 200 + the ``<div id="dz-consent-banner">``
  element or 204 if the banner is not applicable (e.g. analytics disabled).
- ``GET /dz/consent/state`` — diagnostic/read endpoint returning the user's
  current resolved consent state. Useful for server-side gating decisions in
  downstream integrations.

The cookie is scoped to ``path=/`` with ``SameSite=Lax``. Secure flag is
automatically applied when the request arrived over HTTPS.

Resolution order for the tenant's default consent state:

    1. Tenant-level override (``TenantAnalyticsConfig.consent_default``) — TODO
       in Phase 6 once the Tenant model extension lands.
    2. Tenant data residency → EU/UK/EEA = denied, else granted.
    3. None → treat as EU (safest default).

Until Phase 6, step 2 reads ``analytics.consent_default`` from the project
TOML if present, or falls back to EU defaults.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from dazzle.compliance.analytics.consent import (
    CONSENT_COOKIE_MAX_AGE_SECONDS,
    CONSENT_COOKIE_NAME,
    ConsentDefaults,
    build_decided_state,
    parse_consent_cookie,
)

logger = logging.getLogger("dazzle.consent")


def create_consent_routes(
    *,
    default_jurisdiction: str = "EU",
    consent_override: str | None = None,
    privacy_page_url: str | None = "/privacy",
    cookie_policy_url: str | None = None,
) -> APIRouter:
    """Create the consent-banner router.

    Args:
        default_jurisdiction: Country or region for the app-level default.
            Overridden per-tenant once Phase 6 ships.
        consent_override: ``"granted"`` or ``"denied"`` to force a default
            regardless of jurisdiction.
        privacy_page_url: Href rendered into the banner's Privacy-notice link.
        cookie_policy_url: Href rendered into the banner's Cookie-policy link
            (optional — link omitted when None).
    """
    router = APIRouter(tags=["Consent"])

    defaults = ConsentDefaults.for_jurisdiction(
        default_jurisdiction,
        override=consent_override if consent_override in ("granted", "denied") else None,  # type: ignore[arg-type]
    )

    @router.post("/dz/consent", include_in_schema=False)
    async def post_consent(request: Request) -> Response:
        """Persist the user's consent choices as a cookie."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid json"}, status_code=400)

        if not isinstance(body, dict):
            return JSONResponse({"error": "expected object"}, status_code=400)

        # Coerce to explicit booleans; missing keys default False.
        analytics = bool(body.get("analytics", False))
        advertising = bool(body.get("advertising", False))
        personalization = bool(body.get("personalization", False))
        # Functional is always granted; any falsy input is overridden.
        functional = True

        decided = build_decided_state(
            analytics=analytics,
            advertising=advertising,
            personalization=personalization,
            functional=functional,
        )

        cookie_value = decided.serialize()
        response = Response(status_code=204)
        secure = request.url.scheme == "https"
        response.set_cookie(
            key=CONSENT_COOKIE_NAME,
            value=cookie_value,
            max_age=CONSENT_COOKIE_MAX_AGE_SECONDS,
            path="/",
            secure=secure,
            httponly=False,  # banner JS needs read access
            samesite="lax",
        )
        return response

    @router.get("/dz/consent/state", include_in_schema=False)
    async def get_consent_state(request: Request) -> JSONResponse:
        """Return the user's current resolved consent state as JSON."""
        raw = request.cookies.get(CONSENT_COOKIE_NAME)
        state = parse_consent_cookie(raw, defaults)
        return JSONResponse(
            {
                "analytics": state.analytics,
                "advertising": state.advertising,
                "personalization": state.personalization,
                "functional": state.functional,
                "undecided": state.undecided,
                "decided_at": state.decided_at,
            }
        )

    # Build a Jinja2Templates wrapper around the framework's existing
    # environment so FastAPI's TemplateResponse path renders safely
    # (autoescape is on by default). This avoids wrapping raw HTML strings
    # in HTMLResponse, which defeats semgrep's rule for this class of XSS.
    from dazzle_ui.runtime.template_renderer import get_jinja_env

    _consent_templates = Jinja2Templates(env=get_jinja_env())

    @router.get("/dz/consent/banner", include_in_schema=False)
    async def get_consent_banner(request: Request) -> Response:
        """Return the consent banner HTML fragment for reopen flows."""
        raw = request.cookies.get(CONSENT_COOKIE_NAME)
        state = parse_consent_cookie(raw, defaults)
        # Reopen always re-presents the banner regardless of prior decision.
        consent_dict = {
            "analytics": state.analytics == "granted",
            "advertising": state.advertising == "granted",
            "personalization": state.personalization == "granted",
            "functional": state.functional == "granted",
            "undecided": True,
            "decided_at": state.decided_at,
        }
        return _consent_templates.TemplateResponse(
            request,
            "site/includes/consent_banner.html",
            {
                "consent": consent_dict,
                "consent_state_json": json.dumps(consent_dict),
                "privacy_page_url": privacy_page_url,
                "cookie_policy_url": cookie_policy_url,
            },
        )

    return router


def resolve_consent_for_request(
    request: Request,
    defaults: ConsentDefaults,
) -> dict[str, Any]:
    """Template-context helper — returns the consent state as a dict.

    Use from context builders so every page render can see consent:

        context["consent"] = resolve_consent_for_request(request, defaults)
        context["consent_state_json"] = json.dumps(context["consent"])

    The template then passes ``context.consent`` to the banner include.
    """
    raw = request.cookies.get(CONSENT_COOKIE_NAME)
    state = parse_consent_cookie(raw, defaults)
    return {
        "analytics": state.analytics == "granted",
        "advertising": state.advertising == "granted",
        "personalization": state.personalization == "granted",
        "functional": state.functional == "granted",
        "undecided": state.undecided,
        "decided_at": state.decided_at,
    }


def resolve_consent_state_json(
    request: Request,
    defaults: ConsentDefaults,
) -> str:
    """Serialize the resolved consent dict for embedding in a `data-*` attribute."""
    return json.dumps(resolve_consent_for_request(request, defaults))
