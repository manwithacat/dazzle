"""Runtime service container — replaces module-level singletons.

Attached to app.state.services at startup.  Each app instance gets its own
services, enabling multi-tenant isolation and clean test fixtures.
"""

from dataclasses import dataclass, field
from typing import Any

from fastapi import Request

from dazzle_back.runtime.event_bus import EntityEventBus
from dazzle_back.runtime.presence_tracker import PresenceTracker


@dataclass
class RuntimeServices:
    """Container for runtime service instances.

    Required services (event_bus, presence_tracker) are created by default.
    Optional services (metrics, event framework) are attached during their
    respective async init phases.
    """

    event_bus: EntityEventBus = field(default_factory=EntityEventBus)
    presence_tracker: PresenceTracker = field(default_factory=PresenceTracker)
    event_framework: Any = None  # EventFramework | NullEventFramework | None
    metrics_collector: Any = None
    system_collector: Any = None
    metrics_emitter: Any = None
    process_manager: Any = None


def get_services(request: Request) -> RuntimeServices:
    """FastAPI dependency — typed access to runtime services."""
    services: RuntimeServices = request.app.state.services
    return services
