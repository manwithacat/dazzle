"""Analytics provider abstraction (v0.61.0 Phase 3).

A **provider** is a discrete analytics / tag-management service that the
framework can load on behalf of the app — GTM, Plausible, PostHog,
Segment, etc. Each provider declares:

- Which consent category gates its scripts
- What CSP origins need to be allowed for its scripts to load
- Which cookies it sets (feeds the cookie-policy generator)
- What Jinja snippet template renders its ``<head>`` / ``<body>`` markup

A provider is distinct from a **subprocessor** (see
``compliance/analytics/registry.py``): the subprocessor declaration exists
for compliance documentation (privacy page, ROPA, DPA hub), while the
provider declaration exists for *runtime behaviour* (script injection,
CSP, consent gating). Most providers have both, and the framework ships
matched pairs — e.g. the ``gtm`` provider aligns with the
``google_tag_manager`` subprocessor by ``linked_subprocessor_name``.

See ``docs/superpowers/specs/2026-04-24-analytics-privacy-design.md`` §2.2.
"""

from __future__ import annotations

from .base import (
    ProviderCSPRequirements,
    ProviderDefinition,
    ProviderInstance,
)
from .registry import (
    FRAMEWORK_PROVIDERS,
    get_provider_definition,
    list_provider_definitions,
)

__all__ = [
    "FRAMEWORK_PROVIDERS",
    "ProviderCSPRequirements",
    "ProviderDefinition",
    "ProviderInstance",
    "get_provider_definition",
    "list_provider_definitions",
]
