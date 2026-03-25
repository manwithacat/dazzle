"""Runtime service container — replaces module-level singletons.

Attached to app.state.services at startup.  Each app instance gets its own
services, enabling multi-tenant isolation and clean test fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fastapi import Request

from dazzle_back.runtime.event_bus import EntityEventBus
from dazzle_back.runtime.presence_tracker import PresenceTracker

if TYPE_CHECKING:
    from dazzle_back.metrics.collector import MetricsCollector
    from dazzle_back.metrics.system_collector import SystemMetricsCollector
    from dazzle_back.runtime.metrics.emitter import MetricsEmitter


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
    metrics_collector: MetricsCollector | None = None
    system_collector: SystemMetricsCollector | None = None
    metrics_emitter: MetricsEmitter | None = None


def get_services(request: Request) -> RuntimeServices:
    """FastAPI dependency — typed access to runtime services."""
    services: RuntimeServices = request.app.state.services
    return services
