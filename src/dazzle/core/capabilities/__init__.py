"""Capability opt-in registry (#1342).

Import side effect: registers the framework's built-in capabilities.
"""

from dazzle.core.capabilities.models import (
    Capability,
    CapabilityUnavailableError,
    ResolvedCapabilities,
)
from dazzle.core.capabilities.registry import (
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
    "all_capabilities",
    "get",
    "is_available",
    "known_capability_ids",
    "register",
    "resolve_capabilities",
    "suggest_capability",
    "unknown_capability_ids",
]
