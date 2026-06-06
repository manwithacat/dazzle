"""Capability opt-in registry (#1342).

Import side effect: registers the framework's built-in capabilities.
"""

from dazzle.core.capabilities.cognition import (
    active_capabilities_for,
    enable_suggestion,
    partition_by_capability,
)
from dazzle.core.capabilities.models import (
    Capability,
    CapabilityUnavailableError,
    ResolvedCapabilities,
)
from dazzle.core.capabilities.registry import (
    active_capability_ids,
    all_capabilities,
    get,
    is_available,
    known_capability_ids,
    register,
    resolve_capabilities,
    suggest_capability,
    unknown_capability_ids,
)

__all__ = [
    "Capability",
    "CapabilityUnavailableError",
    "ResolvedCapabilities",
    "active_capabilities_for",
    "active_capability_ids",
    "all_capabilities",
    "enable_suggestion",
    "partition_by_capability",
    "get",
    "is_available",
    "known_capability_ids",
    "register",
    "resolve_capabilities",
    "suggest_capability",
    "unknown_capability_ids",
]
