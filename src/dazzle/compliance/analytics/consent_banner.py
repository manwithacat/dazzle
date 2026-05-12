"""Consent banner HTML renderer (v0.67.85+).

Inline Python port of `site/includes/consent_banner.html` (150 lines of
Jinja) — emits the GDPR/Consent-Mode-v2 four-category banner via
`html.escape` + string composition. No Jinja env required.

The bridge contract is preserved byte-for-byte: the wrapper carries
`id="dz-consent-banner"`, `role="dialog"`, the per-category data-*
hooks, and the JSON payload in `data-consent-state`. The keyboard
handler and focus trap in `static/js/dz-consent.js` mount unchanged.
"""

from __future__ import annotations

import html as _html_mod
import json as _json
from typing import Any


def _esc(value: Any, *, quote: bool = False) -> str:
    if value is None:
        return ""
    return _html_mod.escape(str(value), quote=quote)


_DEFAULT_TITLE = "Your privacy choices"
_DEFAULT_DESCRIPTION = (
    "We use cookies and similar technologies to run this service, measure how "
    "it's used, and improve it. You can choose which categories you're "
    "comfortable with. Functional cookies are required for the service to "
    "work."
)


def render_consent_banner(
    *,
    consent: dict[str, Any],
    consent_state_json: str,
    privacy_page_url: str | None = None,
    cookie_policy_url: str | None = None,
    consent_banner_title: str | None = None,
    consent_banner_description: str | None = None,
) -> str:
    """Render the consent banner HTML or "" when consent is decided.

    Args:
        consent: Resolved consent dict — see
            `resolve_consent_for_request`. Banner is only emitted when
            `consent["undecided"]` is truthy.
        consent_state_json: JSON-encoded consent dict, embedded in the
            wrapper's `data-consent-state` attribute for the banner JS.
        privacy_page_url: Href rendered into the Privacy-notice link.
            When None, the entire links block is omitted.
        cookie_policy_url: Href rendered into the Cookie-policy link.
            When None, only the Privacy-notice link renders.
        consent_banner_title: Optional override for the dialog title.
        consent_banner_description: Optional override for the dialog
            description copy.
    """
    if not consent or not consent.get("undecided"):
        return ""

    title = consent_banner_title or _DEFAULT_TITLE
    description = consent_banner_description or _DEFAULT_DESCRIPTION
    state_attr = _esc(consent_state_json, quote=True)

    links_block = ""
    if privacy_page_url:
        privacy_link = f'<a href="{_esc(privacy_page_url, quote=True)}">Privacy notice</a>'
        cookie_link = ""
        if cookie_policy_url:
            cookie_link = (
                "\n&nbsp;·&nbsp;\n"
                f'<a href="{_esc(cookie_policy_url, quote=True)}">Cookie policy</a>'
            )
        links_block = f'<p class="dz-consent-links">{privacy_link}{cookie_link}</p>'

    return (
        f'<div id="dz-consent-banner" class="dz-consent-banner" '
        f'role="dialog" aria-labelledby="dz-consent-title" '
        f'aria-describedby="dz-consent-description" '
        f"data-consent-state='{state_attr}'>"
        '<div class="dz-consent-panel">'
        f'<h2 id="dz-consent-title" class="dz-consent-title">{_esc(title)}</h2>'
        f'<p id="dz-consent-description" class="dz-consent-description">'
        f"{_esc(description)}</p>"
        '<div class="dz-consent-actions" data-consent-panel="summary">'
        '<button type="button" class="dz-consent-btn dz-consent-btn-primary" '
        'data-dz-consent-action="accept-all">Accept all</button>'
        '<button type="button" class="dz-consent-btn dz-consent-btn-secondary" '
        'data-dz-consent-action="reject-all">Reject non-essential</button>'
        '<button type="button" class="dz-consent-btn dz-consent-btn-link" '
        'data-dz-consent-action="customize">Customise</button>'
        "</div>"
        '<div class="dz-consent-customize" data-consent-panel="customize" hidden>'
        '<fieldset class="dz-consent-category">'
        '<div class="dz-consent-category-header"><label>'
        '<input type="checkbox" name="functional" checked disabled '
        'data-dz-consent-category="functional">'
        '<span class="dz-consent-category-label">Functional (always on)</span>'
        '</label><p class="dz-consent-category-hint">'
        "Required for sign-in, session management, and security. Cannot be "
        "disabled.</p></div></fieldset>"
        '<fieldset class="dz-consent-category">'
        '<div class="dz-consent-category-header"><label>'
        '<input type="checkbox" name="analytics" data-dz-consent-category="analytics">'
        '<span class="dz-consent-category-label">Analytics</span>'
        '</label><p class="dz-consent-category-hint">'
        "How you use the service, how long pages take to load, which features "
        "are useful.</p></div></fieldset>"
        '<fieldset class="dz-consent-category">'
        '<div class="dz-consent-category-header"><label>'
        '<input type="checkbox" name="personalization" '
        'data-dz-consent-category="personalization">'
        '<span class="dz-consent-category-label">Personalization</span>'
        '</label><p class="dz-consent-category-hint">'
        "Remember preferences (theme, layout, saved filters) across sessions."
        "</p></div></fieldset>"
        '<fieldset class="dz-consent-category">'
        '<div class="dz-consent-category-header"><label>'
        '<input type="checkbox" name="advertising" '
        'data-dz-consent-category="advertising">'
        '<span class="dz-consent-category-label">Advertising</span>'
        '</label><p class="dz-consent-category-hint">'
        "Ad targeting and measurement with third-party advertising networks."
        "</p></div></fieldset>"
        f"{links_block}"
        '<div class="dz-consent-actions">'
        '<button type="button" class="dz-consent-btn dz-consent-btn-primary" '
        'data-dz-consent-action="save">Save preferences</button>'
        '<button type="button" class="dz-consent-btn dz-consent-btn-link" '
        'data-dz-consent-action="back">Back</button>'
        "</div></div></div></div>"
    )


def render_consent_banner_from_state(
    *,
    consent: dict[str, Any],
    privacy_page_url: str | None = None,
    cookie_policy_url: str | None = None,
) -> str:
    """Convenience entry — serialises `consent` to JSON for the data attr."""
    return render_consent_banner(
        consent=consent,
        consent_state_json=_json.dumps(consent),
        privacy_page_url=privacy_page_url,
        cookie_policy_url=cookie_policy_url,
    )
