"""Channels subsystem.

Initialises the ChannelManager for messaging (email/queue/stream channels),
registers channel management REST endpoints, wires entity lifecycle events to
channel send operations, and connects the process adapter SEND step handler.
"""

from __future__ import annotations

import logging
from typing import Any

from dazzle_back.runtime.subsystems import SubsystemContext

logger = logging.getLogger("dazzle.server")


class ChannelsSubsystem:
    name = "channels"

    def __init__(self) -> None:
        self._ctx: SubsystemContext | None = None

    def startup(self, ctx: SubsystemContext) -> None:
        self._ctx = ctx

        if not (ctx.config.enable_channels and ctx.channels):
            return

        self._init_channel_manager(ctx)

        if ctx.channel_manager:
            self._add_channel_routes(ctx)
            self._wire_entity_events_to_channels(ctx)

    def _init_channel_manager(self, ctx: SubsystemContext) -> None:
        try:
            from dazzle.core.ir import ChannelKind
            from dazzle.core.ir import ChannelSpec as IRChannelSpec
            from dazzle_back.channels import create_channel_manager

            kind_map = {
                "email": ChannelKind.EMAIL,
                "queue": ChannelKind.QUEUE,
                "stream": ChannelKind.STREAM,
            }
            ir_channels = [
                IRChannelSpec(
                    name=ch.name,
                    kind=kind_map.get(ch.kind, ChannelKind.EMAIL),
                    provider=ch.provider,
                )
                for ch in ctx.channels
            ]

            channel_manager = create_channel_manager(
                db_manager=ctx.db_manager,
                channel_specs=ir_channels,
                build_id=f"{ctx.appspec.name}-{ctx.appspec.version}",
            )
            ctx.channel_manager = channel_manager

            channel_mgr = channel_manager

            @ctx.app.on_event("startup")
            async def _startup_channels() -> None:
                await channel_mgr.initialize()
                await channel_mgr.start_processor()

            @ctx.app.on_event("shutdown")
            async def _shutdown_channels() -> None:
                await channel_mgr.shutdown()

        except ImportError:
            pass
        except Exception as exc:
            logger.warning("Failed to init channels: %s", exc)

    def _add_channel_routes(self, ctx: SubsystemContext) -> None:
        from fastapi import HTTPException

        channel_manager: Any = ctx.channel_manager
        app = ctx.app

        @app.get("/_dazzle/channels", tags=["Channels"])
        async def list_channels() -> dict[str, Any]:
            statuses = channel_manager.get_all_statuses()
            return {
                "channels": [s.to_dict() for s in statuses],
                "outbox_stats": channel_manager.get_outbox_stats(),
            }

        @app.get("/_dazzle/channels/{channel_name}", tags=["Channels"])
        async def get_channel_status(channel_name: str) -> dict[str, Any]:
            status = channel_manager.get_channel_status(channel_name)
            if not status:
                raise HTTPException(status_code=404, detail=f"Channel '{channel_name}' not found")
            result: dict[str, Any] = status.to_dict()
            return result

        @app.post("/_dazzle/channels/{channel_name}/send", tags=["Channels"])
        async def send_message(
            channel_name: str,
            message: dict[str, Any],
        ) -> dict[str, Any]:
            try:
                result = await channel_manager.send(
                    channel=channel_name,
                    operation=message.get("operation", "test"),
                    message_type=message.get("type", "TestMessage"),
                    payload=message.get("payload", {}),
                    recipient=message.get("recipient", "test@example.com"),
                    metadata=message.get("metadata"),
                )
                if hasattr(result, "to_dict"):
                    return {"status": "queued", "message": result.to_dict()}
                elif hasattr(result, "is_success"):
                    return {
                        "status": "sent" if result.is_success else "failed",
                        "error": result.error,
                    }
                return {"status": "queued"}
            except Exception as exc:
                logger.error("Channel test message failed: %s", exc)
                raise HTTPException(status_code=500, detail="Failed to send test message")

        @app.post("/_dazzle/channels/health", tags=["Channels"])
        async def check_channel_health() -> dict[str, Any]:
            results = await channel_manager.health_check_all()
            return {"health": results}

        @app.get("/_dazzle/channels/outbox/recent", tags=["Channels"])
        async def get_recent_outbox(limit: int = 20) -> dict[str, Any]:
            messages = channel_manager.get_recent_messages(limit)
            return {
                "messages": [
                    {
                        "id": m.id,
                        "channel": m.channel_name,
                        "recipient": m.recipient,
                        "subject": m.payload.get("subject", m.message_type),
                        "status": m.status.value,
                        "created_at": m.created_at.isoformat(),
                        "last_error": m.last_error,
                    }
                    for m in messages
                ],
                "stats": channel_manager.get_outbox_stats(),
            }

    def _wire_entity_events_to_channels(self, ctx: SubsystemContext) -> None:
        from dazzle_back.runtime.service_generator import CRUDService

        channel_mgr = ctx.channel_manager
        if not channel_mgr or not ctx.services:
            return

        # Build trigger map: (entity_name, event_type) → [(channel, op, message)]
        trigger_map: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
        for channel in ctx.channels:
            trigger_meta = channel.metadata.get("send_triggers", {})
            for send_op in channel.send_operations:
                op_trigger = trigger_meta.get(send_op.name)
                if not op_trigger:
                    continue
                entity_name = op_trigger.get("entity_name")
                event_type = op_trigger.get("event")
                if entity_name and event_type:
                    key = (entity_name, event_type)
                    trigger_map.setdefault(key, []).append(
                        (channel.name, send_op.name, send_op.message)
                    )

        if not trigger_map:
            return

        def _make_callback(event_type: str) -> Any:
            async def _dispatch(
                entity_name: str,
                entity_id: str,
                entity_data: dict[str, Any],
                _old_data: dict[str, Any] | None,
            ) -> None:
                operations = trigger_map.get((entity_name, event_type), [])
                for channel_name, op_name, message_type in operations:
                    try:
                        await channel_mgr.send(
                            channel=channel_name,
                            operation=op_name,
                            message_type=message_type,
                            payload={
                                "entity_id": entity_id,
                                "entity_name": entity_name,
                                "event_type": event_type,
                                **entity_data,
                            },
                            recipient=entity_data.get("email", entity_data.get("to", "")),
                        )
                    except Exception:
                        logger.warning(
                            "Channel send failed for %s.%s on %s %s",
                            channel_name,
                            op_name,
                            entity_name,
                            event_type,
                        )

            return _dispatch

        on_created_cb = _make_callback("created")
        on_updated_cb = _make_callback("updated")
        on_deleted_cb = _make_callback("deleted")

        triggered_entities = {ename for (ename, _) in trigger_map}
        wired = 0
        for service in ctx.services.values():
            if isinstance(service, CRUDService):
                if service.entity_name in triggered_entities:
                    service.on_created(on_created_cb)
                    service.on_updated(on_updated_cb)
                    service.on_deleted(on_deleted_cb)
                    wired += 1

        if wired:
            logger.info("Wired entity events to channel sends for %d entities", wired)

    def shutdown(self) -> None:
        pass  # FastAPI on_event("shutdown") handles cleanup
