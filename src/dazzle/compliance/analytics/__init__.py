"""Analytics, consent & privacy compliance (v0.61.0).

See archive/docs-superpowers/specs/2026-04-24-analytics-privacy-design.md for the
overall design. Phase 1 ships the PII + subprocessor primitives and the
filtering utilities that downstream phases (consent, providers, privacy-page
generation) depend on.
"""

from .consent import (
    CONSENT_COOKIE_MAX_AGE_SECONDS,
    CONSENT_COOKIE_NAME,
    CONSENT_COOKIE_VERSION,
    ConsentDefaults,
    ConsentState,
    build_decided_state,
    parse_consent_cookie,
)
from .privacy_page import (
    PrivacyPageArtefacts,
    generate_privacy_page_markdown,
    merge_regenerated_into_existing,
    scaffold_terms_of_service,
    sync_privacy_site_content,
    write_privacy_artefacts,
)
from .providers import (
    FRAMEWORK_PROVIDERS,
    ProviderCSPRequirements,
    ProviderDefinition,
    ProviderInstance,
    get_provider_definition,
    list_provider_definitions,
)
from .registry import (
    FRAMEWORK_SUBPROCESSORS,
    get_framework_subprocessor,
    list_framework_subprocessors,
)
from .render import analytics_globally_disabled, resolve_active_providers
from .tenant_resolver import (
    TenantAnalyticsConfig,
    TenantAnalyticsResolver,
    clear_tenant_analytics_resolvers,
    get_tenant_analytics_resolver,
    make_app_wide_resolver,
    resolve_for_request,
    set_tenant_analytics_resolver,
)

__all__ = [
    "CONSENT_COOKIE_MAX_AGE_SECONDS",
    "CONSENT_COOKIE_NAME",
    "CONSENT_COOKIE_VERSION",
    "ConsentDefaults",
    "ConsentState",
    "FRAMEWORK_PROVIDERS",
    "FRAMEWORK_SUBPROCESSORS",
    "PrivacyPageArtefacts",
    "ProviderCSPRequirements",
    "ProviderDefinition",
    "ProviderInstance",
    "build_decided_state",
    "generate_privacy_page_markdown",
    "get_framework_subprocessor",
    "get_provider_definition",
    "list_framework_subprocessors",
    "list_provider_definitions",
    "merge_regenerated_into_existing",
    "TenantAnalyticsConfig",
    "TenantAnalyticsResolver",
    "clear_tenant_analytics_resolvers",
    "get_tenant_analytics_resolver",
    "make_app_wide_resolver",
    "resolve_for_request",
    "set_tenant_analytics_resolver",
    "analytics_globally_disabled",
    "parse_consent_cookie",
    "resolve_active_providers",
    "scaffold_terms_of_service",
    "sync_privacy_site_content",
    "write_privacy_artefacts",
]
