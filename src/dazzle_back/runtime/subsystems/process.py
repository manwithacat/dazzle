"""Process engine subsystem.

Initialises the ProcessManager and ProcessAdapter, wires entity lifecycle
events to process triggers, wires the SideEffectExecutor for step effects,
connects the process adapter's SEND handler to ChannelManager, and registers
schedule-based triggers.
"""

from __future__ import annotations

import logging
from typing import Any

from dazzle_back.runtime.subsystems import SubsystemContext

logger = logging.getLogger("dazzle.server")


class ProcessSubsystem:
    name = "process"

    def __init__(self) -> None:
        self._manager: Any | None = None
        self._adapter: Any | None = None

    def startup(self, ctx: SubsystemContext) -> None:
        if not ctx.config.enable_processes:
            return

        try:
            import os

            from dazzle_back.runtime.process_manager import ProcessManager
            from dazzle_back.runtime.task_routes import router as task_router
            from dazzle_back.runtime.task_routes import set_process_manager

            adapter_cls: type | None = ctx.config.process_adapter_class
            if adapter_cls is None:
                redis_url = os.environ.get("REDIS_URL")
                if redis_url:
                    from dazzle.core.process import EventBusProcessAdapter

                    self._adapter = EventBusProcessAdapter(redis_url=redis_url)
                else:
                    logger.warning(
                        "Process manager requires REDIS_URL. Skipping process manager init."
                    )
                    return
            else:
                self._adapter = adapter_cls(database_url=ctx.config.database_url)

            self._manager = ProcessManager(
                adapter=self._adapter,
                process_specs=ctx.config.process_specs or None,
                schedule_specs=ctx.config.schedule_specs or None,
            )
            self._manager._entity_status_fields = ctx.config.entity_status_fields

            ctx.process_manager = self._manager
            ctx.process_adapter = self._adapter

            set_process_manager(self._manager)
            ctx.app.include_router(task_router, prefix="/api")

            self._wire_entity_events_to_processes(ctx)

            if hasattr(self._adapter, "set_side_effect_executor"):
                from dazzle_back.runtime.side_effect_executor import SideEffectExecutor

                side_effect_executor = SideEffectExecutor(
                    services=ctx.services,
                    repositories=ctx.repositories,
                )
                self._adapter.set_side_effect_executor(side_effect_executor)

            # Wire process SEND steps to ChannelManager (if available)
            self._wire_send_handler_to_channels(ctx)

            process_adapter = self._adapter
            process_manager = self._manager

            @ctx.app.on_event("startup")
            async def _startup_processes() -> None:
                await process_adapter.initialize()
                await process_manager.initialize()

            @ctx.app.on_event("shutdown")
            async def _shutdown_processes() -> None:
                await process_manager.shutdown()

            logger.info("Process manager initialized")

        except ImportError as exc:
            logger.debug("Process module not available: %s", exc)
        except Exception as exc:
            logger.warning("Failed to init process manager: %s", exc)

    def _wire_entity_events_to_processes(self, ctx: SubsystemContext) -> None:
        from dazzle_back.runtime.service_generator import CRUDService

        if not self._manager:
            return

        process_manager = self._manager

        async def on_created_callback(
            entity_name: str,
            entity_id: str,
            entity_data: dict[str, Any],
            _old_data: dict[str, Any] | None,
        ) -> Any:
            return await process_manager.on_entity_created(entity_name, entity_id, entity_data)

        async def on_updated_callback(
            entity_name: str,
            entity_id: str,
            entity_data: dict[str, Any],
            old_data: dict[str, Any] | None,
        ) -> Any:
            return await process_manager.on_entity_updated(
                entity_name, entity_id, entity_data, old_data
            )

        async def on_deleted_callback(
            entity_name: str,
            entity_id: str,
            entity_data: dict[str, Any],
            _old_data: dict[str, Any] | None,
        ) -> Any:
            return await process_manager.on_entity_deleted(entity_name, entity_id, entity_data)

        wired_count = 0
        for service in ctx.services.values():
            if isinstance(service, CRUDService):
                service.on_created(on_created_callback)
                service.on_updated(on_updated_callback)
                service.on_deleted(on_deleted_callback)
                wired_count += 1

        logger.debug(
            "Wired entity events to ProcessManager for %s services",
            wired_count,
        )

    def _wire_send_handler_to_channels(self, ctx: SubsystemContext) -> None:
        """Connect the process adapter SEND step to ChannelManager (if available)."""
        channel_mgr = ctx.channel_manager
        if not channel_mgr or not self._adapter:
            return

        if not hasattr(self._adapter, "set_send_handler"):
            return

        async def _send_via_channel(
            channel: str, message_type: str, payload: dict[str, Any]
        ) -> None:
            await channel_mgr.send(
                channel=channel,
                operation="process_send",
                message_type=message_type,
                payload=payload,
                recipient=payload.get("to", payload.get("recipient", "")),
            )

        self._adapter.set_send_handler(_send_via_channel)
        logger.info("Wired process SEND steps to ChannelManager")

    def shutdown(self) -> None:
        pass  # handled by FastAPI on_event("shutdown")
