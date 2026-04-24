"""Framework provider registry (v0.61.0 Phase 3).

Ships GTM and Plausible as the two first-class providers. Adding more
(PostHog, Segment, Fathom, GA4 direct) is one entry + one template away.

App authors:

    analytics:
      providers:
        gtm:
          id: "GTM-XXXXXX"
        plausible:
          domain: "example.com"

App-level analytics instances resolve against this registry at link time.
Unknown provider names are parser errors.
"""

from __future__ import annotations

from dazzle.core.ir import ConsentCategory

from .base import ProviderCSPRequirements, ProviderDefinition

FRAMEWORK_PROVIDERS: list[ProviderDefinition] = [
    ProviderDefinition(
        name="gtm",
        label="Google Tag Manager",
        consent_category=ConsentCategory.ANALYTICS,
        csp=ProviderCSPRequirements(
            # GTM loads from www.googletagmanager.com; containers often load
            # GA4 and other tags which talk to analytics.google.com and
            # region-specific google-analytics.com subdomains.
            script_src=(
                "https://www.googletagmanager.com",
                "https://www.google-analytics.com",
                # 'unsafe-inline' is required by GTM's bootstrap snippet.
                # Strict-CSP projects should nonce-based injection via
                # GTM's server-side container instead.
                "'unsafe-inline'",
            ),
            connect_src=(
                "https://www.google-analytics.com",
                "https://analytics.google.com",
                "https://*.google-analytics.com",
                "https://*.analytics.google.com",
                "https://www.googletagmanager.com",
            ),
            img_src=(
                "https://www.google-analytics.com",
                "https://*.google-analytics.com",
            ),
        ),
        head_template="site/includes/analytics/gtm_head.html",
        noscript_template="site/includes/analytics/gtm_noscript.html",
        supports_server_side=True,
        linked_subprocessor_name="google_tag_manager",
        required_params=("id",),
        optional_params=(),
    ),
    ProviderDefinition(
        name="plausible",
        label="Plausible Analytics",
        consent_category=ConsentCategory.ANALYTICS,
        csp=ProviderCSPRequirements(
            # plausible.io hosts the default script; self-hosted tenants
            # override this via analytics.providers.plausible.script_origin.
            script_src=("https://plausible.io",),
            connect_src=("https://plausible.io",),
        ),
        head_template="site/includes/analytics/plausible_head.html",
        supports_server_side=True,
        linked_subprocessor_name="plausible",
        required_params=("domain",),
        optional_params=("script_origin", "api_host"),
    ),
]

_BY_NAME: dict[str, ProviderDefinition] = {p.name: p for p in FRAMEWORK_PROVIDERS}


def get_provider_definition(name: str) -> ProviderDefinition | None:
    """Return the registered definition for a provider name, or None."""
    return _BY_NAME.get(name)


def list_provider_definitions() -> list[ProviderDefinition]:
    """Return a copy of the registered provider list."""
    return list(FRAMEWORK_PROVIDERS)
