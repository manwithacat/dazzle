"""Event framework subsystem.

Initialises the Dazzle event framework (pub/sub) and wires ``EventEmittingMixin``
on CRUD services.  Falls back to ``NullEventFramework`` when the optional
``dazzle_back.events`` package is unavailable.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dazzle_back.runtime.subsystems import SubsystemContext

logger = logging.getLogger("dazzle.server")


class EventsSubsystem:
    name = "events"

    def __init__(self) -> None:
        self._framework: Any | None = None

    def startup(self, ctx: SubsystemContext) -> None:
        from dazzle_back.events.null import EVENTS_AVAILABLE, NullEventFramework

        if EVENTS_AVAILABLE:
            try:
                from dazzle_back.events.framework import EventFramework, EventFrameworkConfig

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
        from dazzle_back.runtime.auth.events import configure_auth_events

        configure_auth_events(self._framework)

        # Wire lifecycle
        framework = self._framework

        @ctx.app.on_event("startup")
        async def _start_events() -> None:
            await framework.start()

        @ctx.app.on_event("shutdown")
        async def _stop_events() -> None:
            await framework.stop()

        # Wire EventEmittingMixin on services
        for service in ctx.services.values():
            if hasattr(service, "set_event_framework"):
                service.set_event_framework(self._framework)

    def shutdown(self) -> None:
        pass  # handled by FastAPI on_event("shutdown") registered in startup
