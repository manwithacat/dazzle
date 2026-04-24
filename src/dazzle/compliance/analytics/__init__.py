"""Analytics, consent & privacy compliance (v0.61.0).

See docs/superpowers/specs/2026-04-24-analytics-privacy-design.md for the
overall design. Phase 1 ships the PII + subprocessor primitives and the
filtering utilities that downstream phases (consent, providers, privacy-page
generation) depend on.
"""

from .pii_filter import (
    PIIFilterResult,
    strip_pii,
)
from .registry import (
    FRAMEWORK_SUBPROCESSORS,
    get_framework_subprocessor,
    list_framework_subprocessors,
    merge_app_subprocessors,
)

__all__ = [
    "FRAMEWORK_SUBPROCESSORS",
    "PIIFilterResult",
    "get_framework_subprocessor",
    "list_framework_subprocessors",
    "merge_app_subprocessors",
    "strip_pii",
]
