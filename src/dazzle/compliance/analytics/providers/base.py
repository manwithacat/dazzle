"""Provider-definition IR + runtime instance types (v0.61.0 Phase 3).

Kept separate from the registry to make it easy to add custom providers
without importing the whole registry module (which in turn imports the
framework-default provider modules).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dazzle.core.ir import ConsentCategory


@dataclass(frozen=True)
class ProviderCSPRequirements:
    """CSP origin allowlists a provider needs for its scripts to load.

    Each field is a tuple of origin strings in CSP source-expression
    syntax — scheme+host form (``https://www.googletagmanager.com``),
    the keyword ``'self'``, ``'unsafe-inline'`` (avoid), or other
    directive values.

    Framework security_middleware unions these across all enabled
    providers when building the per-request CSP header.
    """

    script_src: tuple[str, ...] = ()
    connect_src: tuple[str, ...] = ()
    img_src: tuple[str, ...] = ()
    frame_src: tuple[str, ...] = ()
    style_src: tuple[str, ...] = ()
    font_src: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderDefinition:
    """Static provider declaration (framework-level or user-registered).

    Attributes:
        name: DSL identifier (``gtm``, ``plausible``, ``posthog``...).
            Matched against ``analytics.providers`` keys at render time.
        label: Human-readable name.
        consent_category: Which of the four Dazzle-native consent categories
            this provider's scripts fall under. Determines when the script
            actually loads.
        csp: Origins the provider needs in the CSP header.
        head_template: Jinja template path rendered inside ``<head>``.
            Relative to the framework templates root. Optional — provider
            may have body-only scripts.
        body_template: Jinja template path rendered at the start of ``<body>``
            (after opening tag). Optional.
        noscript_template: Jinja template path rendered inside ``<noscript>``
            (GTM convention — enables analytics when JS is disabled, if the
            provider supports it).
        supports_server_side: Whether this provider has a server-side sink
            implementation (Phase 5). Informational for audits.
        linked_subprocessor_name: Name of the matching subprocessor in
            the framework subprocessor registry. Used to surface GDPR
            compliance data for this provider automatically.
        required_params: Names of per-instance parameters the DSL must
            supply (``id`` for GTM, ``domain`` for Plausible, etc.). The
            parser rejects instances that omit them.
        optional_params: Names of per-instance params the DSL may supply.
    """

    name: str
    label: str
    consent_category: ConsentCategory
    csp: ProviderCSPRequirements
    head_template: str | None = None
    body_template: str | None = None
    noscript_template: str | None = None
    supports_server_side: bool = False
    linked_subprocessor_name: str | None = None
    required_params: tuple[str, ...] = ()
    optional_params: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderInstance:
    """A ProviderDefinition + DSL-supplied parameters for one deployment.

    This is what the template layer actually consumes. Produced by
    resolving an ``AnalyticsSpec`` against the framework registry:

        analytics:
          providers:
            gtm:
              id: "GTM-XXXXXX"

    yields a ``ProviderInstance(definition=<gtm def>, params={"id": "GTM-XXXXXX"})``.
    """

    definition: ProviderDefinition
    params: dict[str, str] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def consent_category(self) -> ConsentCategory:
        return self.definition.consent_category
