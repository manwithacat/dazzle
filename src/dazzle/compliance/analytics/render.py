"""Analytics provider render resolution (v0.61.0 Phase 3).

Takes the declared `AnalyticsSpec` + current `ConsentState` and returns the
list of providers that should actually emit scripts on this request.

Consent gating rule: a provider is returned only if its
`consent_category` is granted in the current state, OR if the provider
needs Consent Mode v2 bootstrap for deny-by-default telemetry even before
the user chooses (GTM is the canonical case — its snippet must load to
receive the `gtag('consent','update',{...})` signal when the banner
saves, even though its tags won't fire until consent is granted).

For Phase 3, the simple rule is: GTM always loads (it's Consent Mode v2
aware and Google's guidance is to load the container with denied defaults).
Plausible is cookieless + consent-optional — we load it when analytics is
granted. Future providers declare their own gating semantics via a
`load_before_consent` flag on ProviderDefinition.

Returns a list of dicts shaped for template iteration (see
`site/includes/analytics/head_scripts.html`).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dazzle.compliance.analytics.consent import ConsentState
from dazzle.compliance.analytics.providers import (
    ProviderDefinition,
    get_provider_definition,
)
from dazzle.core.ir import AnalyticsSpec, ConsentCategory

logger = logging.getLogger(__name__)

# Providers that must load with deny-by-default consent so Consent Mode v2
# can signal the container when the user later grants. Listed by `name`.
_CONSENT_MODE_BOOTSTRAP_PROVIDERS: frozenset[str] = frozenset({"gtm"})

# Environment/mode values that hard-disable analytics. Overridable only
# by the `DAZZLE_ANALYTICS_FORCE=1` env var, which is intended for use by
# framework developers debugging the analytics stack itself.
_DISABLED_ENVS: frozenset[str] = frozenset({"dev", "development", "test"})
_DISABLED_MODES: frozenset[str] = frozenset({"trial", "qa"})


def analytics_globally_disabled() -> bool:
    """Return True when analytics must not emit on this process.

    Rules (evaluated in order):
        1. If ``DAZZLE_ANALYTICS_FORCE=1``, analytics runs regardless.
           Used by framework devs to exercise the stack in dev.
        2. If ``DAZZLE_ENV`` is in {dev, development, test}, disable.
        3. If ``DAZZLE_MODE`` is in {trial, qa}, disable.
        4. Otherwise enable.

    Documented in the design spec §2.4 (dev/trial/qa disable semantics).
    """
    if os.environ.get("DAZZLE_ANALYTICS_FORCE") == "1":
        return False
    env = (os.environ.get("DAZZLE_ENV") or "").lower()
    if env in _DISABLED_ENVS:
        return True
    mode = (os.environ.get("DAZZLE_MODE") or "").lower()
    if mode in _DISABLED_MODES:
        return True
    return False


def resolve_active_providers(
    analytics: AnalyticsSpec | None,
    consent: ConsentState | dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return the list of provider render entries for this request.

    Each entry is a dict with:
        name, consent_category, params, head_template, body_template,
        noscript_template, definition.

    Args:
        analytics: The AppSpec's analytics block (None → no providers).
        consent: Current consent state — ConsentState or dict with the
            four category booleans.

    Returns:
        List of render dicts, ordered as declared in the DSL.
    """
    if analytics is None or not analytics.providers:
        return []

    # Global disable gate — dev/trial/qa modes never emit to real providers.
    if analytics_globally_disabled():
        logger.debug(
            "Analytics providers suppressed (DAZZLE_ENV=%s, DAZZLE_MODE=%s).",
            os.environ.get("DAZZLE_ENV"),
            os.environ.get("DAZZLE_MODE"),
        )
        return []

    granted_set = _consent_granted_categories(consent)
    out: list[dict[str, Any]] = []

    for instance in analytics.providers:
        definition = get_provider_definition(instance.name)
        if definition is None:
            logger.warning(
                "Analytics provider %r is declared in DSL but not registered. Skipping.",
                instance.name,
            )
            continue

        missing = [p for p in definition.required_params if p not in instance.params]
        if missing:
            logger.warning(
                "Analytics provider %r missing required parameter(s): %s. Skipping.",
                instance.name,
                ", ".join(missing),
            )
            continue

        # Gating decision.
        bootstraps_always = instance.name in _CONSENT_MODE_BOOTSTRAP_PROVIDERS
        category_granted = definition.consent_category.value in granted_set
        if not bootstraps_always and not category_granted:
            continue

        out.append(_render_entry(definition, instance.params))

    return out


def _consent_granted_categories(
    consent: ConsentState | dict[str, Any] | None,
) -> set[str]:
    """Return the set of category names currently granted."""
    if consent is None:
        return set()
    if isinstance(consent, ConsentState):
        result: set[str] = set()
        if consent.is_granted(ConsentCategory.ANALYTICS):
            result.add("analytics")
        if consent.is_granted(ConsentCategory.ADVERTISING):
            result.add("advertising")
        if consent.is_granted(ConsentCategory.PERSONALIZATION):
            result.add("personalization")
        if consent.is_granted(ConsentCategory.FUNCTIONAL):
            result.add("functional")
        return result
    # Dict shape used by the site-context builder.
    result = set()
    for key in ("analytics", "advertising", "personalization", "functional"):
        if bool(consent.get(key, False)):
            result.add(key)
    return result


def _render_entry(
    definition: ProviderDefinition,
    params: dict[str, str],
) -> dict[str, Any]:
    """Build the template-ready dict for one provider instance."""
    return {
        "name": definition.name,
        "consent_category": definition.consent_category.value,
        "params": params,
        "head_template": definition.head_template,
        "body_template": definition.body_template,
        "noscript_template": definition.noscript_template,
        "definition": definition,
    }
