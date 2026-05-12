"""
Public API boundary for the Dazzle event system.

This module re-exports the minimal contract that alternative event bus
implementations need. Everything here is zero-dep (stdlib only) or comes
from the null module, so it is always importable regardless of whether
the full event system extras are installed.

Usage:
    from dazzle.back.events.api import EventBus, NullBus, EVENTS_AVAILABLE
"""

from dazzle.back.events.bus import (
    ConsumerStatus,
    EventBus,
    EventBusError,
    EventHandler,
    NackReason,
    SubscriptionInfo,
)
from dazzle.back.events.envelope import EventEnvelope
from dazzle.back.events.null import EVENTS_AVAILABLE, NullBus, NullEventFramework

__all__ = [
    # Core interface
    "EventBus",
    "EventHandler",
    "EventEnvelope",
    "SubscriptionInfo",
    "ConsumerStatus",
    "NackReason",
    "EventBusError",
    # Null implementations
    "NullBus",
    "NullEventFramework",
    # Availability flag
    "EVENTS_AVAILABLE",
]
