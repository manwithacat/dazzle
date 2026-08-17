"""Consent banner HTTP routes (v0.61.0 Phase 2).

Exposes three endpoints:

- ``POST /_dazzle/consent`` — write the user's choices as the ``dz_consent_v2``
  cookie; returns 204. Accepts JSON ``{analytics, advertising, personalization,
  functional}`` with boolean values.
- ``GET /_dazzle/consent/banner`` — re-render just the banner HTML fragment for
  the Manage-cookies reopen flow. Returns 200 + the ``<div id="dz-consent-banner">``
  element or 204 if the banner is not applicable (e.g. analytics disabled).
- ``GET /_dazzle/consent/state`` — diagnostic/read endpoint returning the user's
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

import json
import logging
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from dazzle.compliance.analytics.consent import (
    CONSENT_COOKIE_MAX_AGE_SECONDS,
    CONSENT_COOKIE_NAME,
    ConsentDefaults,
    build_decided_state,
    parse_consent_cookie,
)
from dazzle.compliance.analytics.consent_banner import render_consent_banner

logger = logging.getLogger(__name__)

_CONSENT_TRUE = frozenset({"true", "1", "yes", "on", "granted"})
_CONSENT_FALSE = frozenset({"false", "0", "no", "off", "denied"})
_CONSENT_CHOICE_KEYS = ("analytics", "advertising", "personalization")


def leftover_honest_consent_bool(raw: Any) -> bool | None:
    """Valid consent tokens ride. Leftover junk restores None (stay put).

    Leftover ``analytics=zzz`` / ``"maybe"`` used to invent granted
    via ``bool(nonempty)``. The string ``"false"`` also invented
    grant. Valid bools and true/false tokens ride. Missing / empty
    is the caller's default (deny). Live simple_task consent
    banner. Cycle 2210.
    """
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int) and raw in (0, 1):
        return bool(raw)
    text = str(raw if raw is not None else "").strip()
    if not text:
        return False
    token = text.lower()
    if token in _CONSENT_TRUE:
        return True
    if token in _CONSENT_FALSE:
        return False
    return None


def leftover_consent_stay_put(body: dict[str, Any]) -> bool:
    """True when leftover junk would invent a granted/denied write."""
    for key in _CONSENT_CHOICE_KEYS:
        if key not in body:
            continue
        if leftover_honest_consent_bool(body[key]) is None:
            return True
    return False


def leftover_honest_consent_choices(body: dict[str, Any]) -> dict[str, bool] | None:
    """Valid tokens ride. Any leftover restores None so the caller stays put."""
    if leftover_consent_stay_put(body):
        return None
    out: dict[str, bool] = {}
    for key in _CONSENT_CHOICE_KEYS:
        honest = leftover_honest_consent_bool(body.get(key))
        out[key] = False if honest is None else honest
    return out


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
    router = APIRouter(prefix="/_dazzle/consent", tags=["Consent"])

    defaults = ConsentDefaults.for_jurisdiction(
        default_jurisdiction,
        override=consent_override if consent_override in ("granted", "denied") else None,  # type: ignore[arg-type]
    )

    @router.post("", include_in_schema=False)
    async def post_consent(request: Request) -> Response:
        """Persist the user's consent choices as a cookie."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid json"}, status_code=400)

        if not isinstance(body, dict):
            return JSONResponse({"error": "expected object"}, status_code=400)

        choices = leftover_honest_consent_choices(body)
        if choices is None:
            # Leftover analytics=zzz / "maybe" used to invent granted
            # via bool(nonempty). Stay put — do not write the cookie.
            return JSONResponse({"error": "invalid consent choice"}, status_code=400)

        analytics = choices["analytics"]
        advertising = choices["advertising"]
        personalization = choices["personalization"]
        # Functional is always granted; any leftover input is ignored.
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

    @router.get("/state", include_in_schema=False)
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

    @router.get("/banner", include_in_schema=False)
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
        # All variable interpolation in render_consent_banner is
        # html.escape'd at the renderer; the output is framework-owned
        # static markup with two URL params (privacy_page_url,
        # cookie_policy_url) that come from server config, not request
        # input — so no untrusted user input reaches the HTML body.
        body = render_consent_banner(
            consent=consent_dict,
            consent_state_json=json.dumps(consent_dict),
            privacy_page_url=privacy_page_url,
            cookie_policy_url=cookie_policy_url,
        )
        return HTMLResponse(content=body)  # nosemgrep

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
