"""Event framework subsystem.

Initialises the Dazzle event framework (pub/sub) and wires ``EventEmittingMixin``
on CRUD services.  Falls back to ``NullEventFramework`` when the optional
``dazzle.http.events`` package is unavailable.
"""

import logging
import os
from typing import Any

from dazzle.http.runtime.subsystems import SubsystemContext

logger = logging.getLogger(__name__)


class EventsSubsystem:
    name = "events"

    def __init__(self) -> None:
        self._framework: Any | None = None

    def startup(self, ctx: SubsystemContext) -> None:
        from dazzle.http.events.null import EVENTS_AVAILABLE, NullEventFramework

        if EVENTS_AVAILABLE:
            try:
                from dazzle.http.events.framework import EventFramework, EventFrameworkConfig

                config = EventFrameworkConfig(
                    auto_start_publisher=True,
                    auto_start_consumers=True,
                    database_url=ctx.config.database_url,
                    redis_url=os.environ.get("REDIS_URL"),
                )
                self._framework = EventFramework(config)
            except Exception as exc:
                logger.warning("Failed to init event framework: %s", exc)
                self._framework = NullEventFramework()
        else:
            self._framework = NullEventFramework()

        ctx.event_framework = self._framework

        # Store on RuntimeServices for dependency injection
        if hasattr(ctx.app.state, "services"):
            ctx.app.state.services.event_framework = self._framework

        # Configure auth event publishing with the framework reference
        from dazzle.http.runtime.auth.events import configure_auth_events

        configure_auth_events(self._framework)

        # Wire lifecycle
        framework = self._framework

        from dazzle.http.runtime.lifespan_hooks import register_lifespan_hook

        async def _start_events() -> None:
            await framework.start()

        async def _stop_events() -> None:
            await framework.stop()

        register_lifespan_hook(ctx.app, startup=_start_events, shutdown=_stop_events)

        # Wire EventEmittingMixin on services
        for service in ctx.services.values():
            if hasattr(service, "set_event_framework"):
                service.set_event_framework(self._framework)

    def shutdown(self) -> None:
        pass  # teardown runs via the registered lifespan shutdown hook
