"""Analytics, consent & privacy compliance (v0.61.0).

See docs/superpowers/specs/2026-04-24-analytics-privacy-design.md for the
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
from .pii_filter import (
    PIIFilterResult,
    strip_pii,
)
from .privacy_page import (
    PrivacyPageArtefacts,
    generate_privacy_page_markdown,
    merge_regenerated_into_existing,
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
    merge_app_subprocessors,
)
from .render import resolve_active_providers

__all__ = [
    "CONSENT_COOKIE_MAX_AGE_SECONDS",
    "CONSENT_COOKIE_NAME",
    "CONSENT_COOKIE_VERSION",
    "ConsentDefaults",
    "ConsentState",
    "FRAMEWORK_PROVIDERS",
    "FRAMEWORK_SUBPROCESSORS",
    "PIIFilterResult",
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
    "merge_app_subprocessors",
    "merge_regenerated_into_existing",
    "parse_consent_cookie",
    "resolve_active_providers",
    "strip_pii",
    "write_privacy_artefacts",
]
