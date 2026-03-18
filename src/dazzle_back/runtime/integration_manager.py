"""Integration manager — channel and integration executor setup.

Houses ``IntegrationManager`` and the ``_convert_channels`` helper that were
previously defined inline in ``server.py``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from dazzle.core.ir import AppSpec

if TYPE_CHECKING:
    from fastapi import FastAPI

    from dazzle_back.runtime.pg_backend import PostgresBackend

logger = logging.getLogger(__name__)


# =============================================================================
# Channel conversion (moved from dazzle_back.converters)
# =============================================================================


def _convert_channels(ir_channels: list[Any]) -> list[Any]:
    """Convert IR ChannelSpecs to backend ChannelSpecs.

    Trigger info from IR send operations is serialized into channel
    metadata under ``send_triggers`` so the runtime can wire entity
    lifecycle events to channel dispatches.
    """
    from dazzle_back.specs.channel import ChannelSpec, SendOperationSpec

    result: list[ChannelSpec] = []
    for ch in ir_channels:
        send_ops: list[SendOperationSpec] = []
        send_triggers: dict[str, dict[str, Any]] = {}

        for op in ch.send_operations:
            send_ops.append(
                SendOperationSpec(
                    name=op.name,
                    message=op.message_name,
                    template=op.options.get("template"),
                    subject_template=op.options.get("subject_template"),
                )
            )
            if op.trigger:
                trigger_data: dict[str, Any] = {"kind": str(op.trigger.kind)}
                if op.trigger.entity_name:
                    trigger_data["entity_name"] = op.trigger.entity_name
                if op.trigger.event:
                    trigger_data["event"] = str(op.trigger.event)
                if op.trigger.field_name:
                    trigger_data["field_name"] = op.trigger.field_name
                if op.trigger.field_value:
                    trigger_data["field_value"] = op.trigger.field_value
                if op.trigger.from_state:
                    trigger_data["from_state"] = op.trigger.from_state
                if op.trigger.to_state:
                    trigger_data["to_state"] = op.trigger.to_state
                send_triggers[op.name] = trigger_data

        metadata: dict[str, Any] = {}
        if send_triggers:
            metadata["send_triggers"] = send_triggers

        result.append(
            ChannelSpec(
                name=ch.name,
                kind=ch.kind.value,
                provider=ch.provider,
                send_operations=send_ops,
                metadata=metadata,
            )
        )
    return result


# =============================================================================
# IntegrationManager
# =============================================================================


class IntegrationManager:
    """Manages integration executor and messaging channels for DazzleBackendApp."""

    def __init__(
        self,
        *,
        app: FastAPI,
        appspec: AppSpec,
        channels: list[Any],
        db_manager: PostgresBackend | None,
        fragment_sources: dict[str, dict[str, Any]],
    ) -> None:
        self._app = app
        self._appspec = appspec
        self._channels = channels
        self._db_manager = db_manager
        self._fragment_sources = fragment_sources
        self.channel_manager: Any | None = None
        self.integration_executor: Any | None = None

    def init_channel_manager(self) -> None:
        """Initialize the channel manager for messaging."""
        try:
            from dazzle.core.ir import ChannelKind
            from dazzle.core.ir import ChannelSpec as IRChannelSpec
            from dazzle_back.channels import create_channel_manager

            ir_channels = []
            for channel in self._channels:
                kind_map = {
                    "email": ChannelKind.EMAIL,
                    "queue": ChannelKind.QUEUE,
                    "stream": ChannelKind.STREAM,
                }
                ir_channel = IRChannelSpec(
                    name=channel.name,
                    kind=kind_map.get(channel.kind, ChannelKind.EMAIL),
                    provider=channel.provider,
                )
                ir_channels.append(ir_channel)

            self.channel_manager = create_channel_manager(
                db_manager=self._db_manager,
                channel_specs=ir_channels,
                build_id=f"{self._appspec.name}-{self._appspec.version}",
            )

            self._add_channel_routes()

        except ImportError:
            pass
        except Exception as e:
            logging.getLogger("dazzle.server").warning("Failed to init channels: %s", e)

    def _add_channel_routes(self) -> None:
        """Add channel management routes to the FastAPI app."""
        if not self.channel_manager or not self._app:
            return

        from fastapi import HTTPException

        channel_manager = self.channel_manager  # Capture for closures

        @self._app.on_event("startup")
        async def startup_channels() -> None:
            await channel_manager.initialize()
            await channel_manager.start_processor()

        @self._app.on_event("shutdown")
        async def shutdown_channels() -> None:
            await channel_manager.shutdown()

        @self._app.get("/_dazzle/channels", tags=["Channels"])
        async def list_channels() -> dict[str, Any]:
            statuses = channel_manager.get_all_statuses()
            return {
                "channels": [s.to_dict() for s in statuses],
                "outbox_stats": channel_manager.get_outbox_stats(),
            }

        @self._app.get("/_dazzle/channels/{channel_name}", tags=["Channels"])
        async def get_channel_status(channel_name: str) -> dict[str, Any]:
            status = channel_manager.get_channel_status(channel_name)
            if not status:
                raise HTTPException(status_code=404, detail=f"Channel '{channel_name}' not found")
            result: dict[str, Any] = status.to_dict()
            return result

        @self._app.post("/_dazzle/channels/{channel_name}/send", tags=["Channels"])
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
            except Exception as e:
                logger.error("Channel test message failed: %s", e)
                raise HTTPException(status_code=500, detail="Failed to send test message")

        @self._app.post("/_dazzle/channels/health", tags=["Channels"])
        async def check_channel_health() -> dict[str, Any]:
            results = await channel_manager.health_check_all()
            return {"health": results}

        @self._app.get("/_dazzle/channels/outbox/recent", tags=["Channels"])
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

    def init_integration_executor(self) -> None:
        """Initialize integration action executor (v0.20.0)."""
        if not self._app:
            return

        try:
            from dazzle_back.runtime.integration_executor import IntegrationExecutor

            has_actions = False
            for integration in self._appspec.integrations:
                if getattr(integration, "actions", []):
                    has_actions = True
                    break

            if not has_actions:
                return

            self.integration_executor = IntegrationExecutor(
                app_spec=self._appspec,
                fragment_sources=self._fragment_sources,
            )

            logging.getLogger("dazzle.server").info("Integration executor initialized")

        except ImportError as e:
            logging.getLogger("dazzle.server").debug("Integration executor not available: %s", e)

        except Exception as e:
            logging.getLogger("dazzle.server").warning("Failed to init integration executor: %s", e)
