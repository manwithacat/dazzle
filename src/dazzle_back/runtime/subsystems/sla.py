"""SLA manager subsystem.

Tracks SLA timers in memory and runs a periodic background task to detect
tier transitions and execute breach actions.
"""

from __future__ import annotations

import logging
from typing import Any

from dazzle_back.runtime.subsystems import SubsystemContext

logger = logging.getLogger("dazzle.server")


class SLASubsystem:
    name = "sla"

    def __init__(self) -> None:
        self._manager: Any | None = None

    def startup(self, ctx: SubsystemContext) -> None:
        sla_specs = getattr(ctx.appspec, "slas", None)
        if not sla_specs:
            return

        try:
            from dazzle_back.runtime.service_generator import CRUDService
            from dazzle_back.runtime.sla_manager import SLAManager

            self._manager = SLAManager(
                sla_specs=sla_specs,
                services=ctx.services,
            )
            ctx.sla_manager = self._manager
            sla_manager = self._manager

            # Wire entity lifecycle events
            wired_count = 0
            for service in ctx.services.values():
                if isinstance(service, CRUDService):

                    async def _on_created(
                        entity_name: str,
                        entity_id: str,
                        entity_data: dict[str, Any],
                        _old_data: dict[str, Any] | None,
                        _mgr: Any = sla_manager,
                    ) -> None:
                        await _mgr.on_entity_event(entity_name, entity_id, entity_data)

                    async def _on_updated(
                        entity_name: str,
                        entity_id: str,
                        entity_data: dict[str, Any],
                        old_data: dict[str, Any] | None,
                        _mgr: Any = sla_manager,
                    ) -> None:
                        await _mgr.on_entity_event(entity_name, entity_id, entity_data, old_data)

                    service.on_created(_on_created)
                    service.on_updated(_on_updated)
                    wired_count += 1

            @ctx.app.on_event("startup")
            async def _startup_sla() -> None:
                await sla_manager.start()

            @ctx.app.on_event("shutdown")
            async def _shutdown_sla() -> None:
                await sla_manager.shutdown()

            logger.info(
                "SLA manager initialized — %d SLA(s), wired to %d service(s)",
                len(sla_specs),
                wired_count,
            )

        except Exception as exc:
            logger.warning("Failed to init SLA manager: %s", exc)

    def shutdown(self) -> None:
        pass  # handled by FastAPI on_event("shutdown")
