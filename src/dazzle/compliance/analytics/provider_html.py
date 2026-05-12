"""HTML emitters for analytics provider script blocks (post-#1044).

Pre-#1044 these were Jinja templates under
``site/includes/analytics/`` (gtm_head.html, gtm_noscript.html,
plausible_head.html). Inline Python ports — no Jinja env needed.

Each renderer takes the provider's ``params`` dict and the current
``consent`` dict (analytics/advertising/personalization/functional
booleans) and returns the HTML snippet that the site shell would
inject in the appropriate document slot.

Consent gating semantics are preserved from the original templates:
- GTM bootstraps under Consent Mode v2 with deny-by-default, so the
  scripts always emit; the consent dict drives the ``gtag('consent',
  'default', ...)`` payload.
- Plausible is cookieless + opt-in and only emits when analytics
  consent is granted (the resolve-active-providers gate filters this
  before reaching the renderer; the renderer doesn't re-check).
"""

from __future__ import annotations

from typing import Any

from dazzle.render.html import esc as _esc


def _consent_value(consent: dict[str, Any], key: str) -> str:
    return "granted" if consent.get(key) else "denied"


def render_gtm_head(params: dict[str, Any], consent: dict[str, Any]) -> str:
    """Port of ``site/includes/analytics/gtm_head.html``."""
    gtm_id = _esc(params.get("id", ""), quote=True)
    analytics = _consent_value(consent, "analytics")
    advertising = _consent_value(consent, "advertising")
    personalization = _consent_value(consent, "personalization")
    # ad_personalization granted only when both advertising AND personalization granted.
    ad_personalization = (
        "granted" if consent.get("advertising") and consent.get("personalization") else "denied"
    )
    return (
        "<script>\n"
        "  window.dataLayer = window.dataLayer || [];\n"
        "  function gtag(){dataLayer.push(arguments);}\n"
        "  gtag('consent', 'default', {\n"
        f"    'analytics_storage': '{analytics}',\n"
        f"    'ad_storage': '{advertising}',\n"
        f"    'ad_user_data': '{advertising}',\n"
        f"    'ad_personalization': '{ad_personalization}',\n"
        "    'functionality_storage': 'granted',\n"
        f"    'personalization_storage': '{personalization}',\n"
        "    'security_storage': 'granted',\n"
        "    'wait_for_update': 500\n"
        "  });\n"
        "</script>\n"
        "<!-- Google Tag Manager -->\n"
        "<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':\n"
        "new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],\n"
        "j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=\n"
        "'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);\n"
        f"}})(window,document,'script','dataLayer','{gtm_id}');</script>\n"
        "<!-- End Google Tag Manager -->"
    )


def render_gtm_noscript(params: dict[str, Any], consent: dict[str, Any]) -> str:
    """Port of ``site/includes/analytics/gtm_noscript.html``."""
    gtm_id = _esc(params.get("id", ""), quote=True)
    return (
        f'<noscript><iframe src="https://www.googletagmanager.com/ns.html?id={gtm_id}"\n'
        'height="0" width="0" style="display:none;visibility:hidden"\n'
        'title="Google Tag Manager"></iframe></noscript>'
    )


def render_plausible_head(params: dict[str, Any], consent: dict[str, Any]) -> str:
    """Port of ``site/includes/analytics/plausible_head.html``."""
    domain = _esc(params.get("domain", ""), quote=True)
    script_origin = _esc(
        params.get("script_origin") or "https://plausible.io/js/script.js",
        quote=True,
    )
    api_host_attr = ""
    if params.get("api_host"):
        api_host_attr = f' data-api="{_esc(params["api_host"], quote=True)}"'
    return f'<script defer data-domain="{domain}"{api_host_attr} src="{script_origin}"></script>'
