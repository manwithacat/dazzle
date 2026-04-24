"""Analytics, consent & privacy compliance (v0.61.0).

See docs/superpowers/specs/2026-04-24-analytics-privacy-design.md for the
overall design. Phase 1 ships the PII + subprocessor primitives and the
filtering utilities that downstream phases (consent, providers, privacy-page
generation) depend on.
"""

from .bridge import (
    AnalyticsBridge,
    build_bridge_from_spec,
    match_topic_glob,
    start_bridge_consumer,
)
from .consent import (
    CONSENT_COOKIE_MAX_AGE_SECONDS,
    CONSENT_COOKIE_NAME,
    CONSENT_COOKIE_VERSION,
    ConsentDefaults,
    ConsentState,
    build_decided_state,
    parse_consent_cookie,
)
from .event_vocabulary import (
    COMMON_PARAMS,
    EVENT_SCHEMAS,
    VOCABULARY_ID,
    VOCABULARY_VERSION,
    EventParam,
    EventSchema,
    get_event_schema,
    list_event_names,
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
from .render import analytics_globally_disabled, resolve_active_providers
from .sinks import (
    FRAMEWORK_SINKS,
    AnalyticsEvent,
    AnalyticsSink,
    GA4MeasurementProtocolSink,
    SinkMetrics,
    SinkResult,
    TenantContext,
    get_sink_factory,
    list_sink_names,
)
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
    "COMMON_PARAMS",
    "EVENT_SCHEMAS",
    "EventParam",
    "EventSchema",
    "VOCABULARY_ID",
    "VOCABULARY_VERSION",
    "get_event_schema",
    "list_event_names",
    "AnalyticsBridge",
    "AnalyticsEvent",
    "AnalyticsSink",
    "build_bridge_from_spec",
    "match_topic_glob",
    "start_bridge_consumer",
    "FRAMEWORK_SINKS",
    "GA4MeasurementProtocolSink",
    "SinkMetrics",
    "SinkResult",
    "TenantAnalyticsConfig",
    "TenantAnalyticsResolver",
    "TenantContext",
    "clear_tenant_analytics_resolvers",
    "get_tenant_analytics_resolver",
    "make_app_wide_resolver",
    "resolve_for_request",
    "set_tenant_analytics_resolver",
    "analytics_globally_disabled",
    "get_sink_factory",
    "list_sink_names",
    "parse_consent_cookie",
    "resolve_active_providers",
    "strip_pii",
    "write_privacy_artefacts",
]
