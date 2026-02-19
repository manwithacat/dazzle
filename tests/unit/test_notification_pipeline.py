"""
Unit tests for the notification delivery pipeline (issue #304).

Tests:
- Channel conversion from IR to BackendSpec (trigger metadata preservation)
- Process SEND step → ChannelManager wiring
- Entity event → channel dispatch wiring
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.core.ir.messaging import (
    ChannelKind,
    EntityEvent,
    SendTriggerKind,
    SendTriggerSpec,
)
from dazzle.core.ir.messaging import (
    ChannelSpec as IRChannelSpec,
)
from dazzle.core.ir.messaging import (
    SendOperationSpec as IRSendOperationSpec,
)
from dazzle_back.converters import _convert_channels
from dazzle_back.specs.channel import ChannelSpec, SendOperationSpec

# =============================================================================
# Channel conversion tests
# =============================================================================


class TestConvertChannels:
    """Tests for _convert_channels (IR → BackendSpec)."""

    def test_empty_channels(self) -> None:
        assert _convert_channels([]) == []

    def test_basic_channel_without_triggers(self) -> None:
        ir_ch = IRChannelSpec(
            name="notifications",
            kind=ChannelKind.EMAIL,
            provider="auto",
        )
        result = _convert_channels([ir_ch])
        assert len(result) == 1
        assert result[0].name == "notifications"
        assert result[0].kind == "email"
        assert result[0].provider == "auto"
        assert result[0].send_operations == []
        assert result[0].metadata == {}

    def test_channel_with_send_operation_no_trigger(self) -> None:
        ir_ch = IRChannelSpec(
            name="emails",
            kind=ChannelKind.EMAIL,
            send_operations=[
                IRSendOperationSpec(
                    name="welcome",
                    message_name="WelcomeEmail",
                ),
            ],
        )
        result = _convert_channels([ir_ch])
        assert len(result[0].send_operations) == 1
        assert result[0].send_operations[0].name == "welcome"
        assert result[0].send_operations[0].message == "WelcomeEmail"
        # No trigger → no send_triggers in metadata
        assert result[0].metadata == {}

    def test_channel_with_entity_event_trigger(self) -> None:
        ir_ch = IRChannelSpec(
            name="notifications",
            kind=ChannelKind.EMAIL,
            send_operations=[
                IRSendOperationSpec(
                    name="order_confirmation",
                    message_name="OrderConfirmation",
                    trigger=SendTriggerSpec(
                        kind=SendTriggerKind.ENTITY_EVENT,
                        entity_name="Order",
                        event=EntityEvent.CREATED,
                    ),
                ),
            ],
        )
        result = _convert_channels([ir_ch])
        triggers = result[0].metadata.get("send_triggers", {})
        assert "order_confirmation" in triggers
        assert triggers["order_confirmation"]["kind"] == "entity_event"
        assert triggers["order_confirmation"]["entity_name"] == "Order"
        assert triggers["order_confirmation"]["event"] == "created"

    def test_channel_with_status_transition_trigger(self) -> None:
        ir_ch = IRChannelSpec(
            name="notifications",
            kind=ChannelKind.EMAIL,
            send_operations=[
                IRSendOperationSpec(
                    name="shipped_notification",
                    message_name="ShippedEmail",
                    trigger=SendTriggerSpec(
                        kind=SendTriggerKind.ENTITY_STATUS_TRANSITION,
                        entity_name="Order",
                        from_state="processing",
                        to_state="shipped",
                    ),
                ),
            ],
        )
        result = _convert_channels([ir_ch])
        triggers = result[0].metadata.get("send_triggers", {})
        t = triggers["shipped_notification"]
        assert t["kind"] == "entity_status_transition"
        assert t["entity_name"] == "Order"
        assert t["from_state"] == "processing"
        assert t["to_state"] == "shipped"

    def test_multiple_send_operations_mixed_triggers(self) -> None:
        ir_ch = IRChannelSpec(
            name="notifications",
            kind=ChannelKind.EMAIL,
            send_operations=[
                IRSendOperationSpec(
                    name="welcome",
                    message_name="WelcomeEmail",
                    trigger=SendTriggerSpec(
                        kind=SendTriggerKind.ENTITY_EVENT,
                        entity_name="User",
                        event=EntityEvent.CREATED,
                    ),
                ),
                IRSendOperationSpec(
                    name="manual_send",
                    message_name="Announcement",
                    # No trigger
                ),
            ],
        )
        result = _convert_channels([ir_ch])
        triggers = result[0].metadata.get("send_triggers", {})
        assert "welcome" in triggers
        assert "manual_send" not in triggers

    def test_template_options_preserved(self) -> None:
        ir_ch = IRChannelSpec(
            name="emails",
            kind=ChannelKind.EMAIL,
            send_operations=[
                IRSendOperationSpec(
                    name="welcome",
                    message_name="WelcomeEmail",
                    options={
                        "template": "welcome.html",
                        "subject_template": "Welcome, {{ name }}!",
                    },
                ),
            ],
        )
        result = _convert_channels([ir_ch])
        op = result[0].send_operations[0]
        assert op.template == "welcome.html"
        assert op.subject_template == "Welcome, {{ name }}!"

    def test_queue_channel_kind(self) -> None:
        ir_ch = IRChannelSpec(
            name="jobs",
            kind=ChannelKind.QUEUE,
            provider="redis",
        )
        result = _convert_channels([ir_ch])
        assert result[0].kind == "queue"
        assert result[0].provider == "redis"


# =============================================================================
# Send handler wiring tests
# =============================================================================


class TestWireSendHandlerToChannels:
    """Tests for _wire_send_handler_to_channels."""

    def _make_app(
        self,
        *,
        channel_mgr: Any = None,
        process_adapter: Any = None,
    ) -> Any:
        """Create a minimal mock DazzleBackendApp."""
        app = MagicMock()
        app.channel_manager = channel_mgr
        app._process_adapter = process_adapter
        app.spec = MagicMock()
        app._services = {}
        return app

    def test_no_channel_manager_skips(self) -> None:
        from dazzle_back.runtime.server import DazzleBackendApp

        app = self._make_app(channel_mgr=None)
        # Call the unbound method with our mock
        DazzleBackendApp._wire_send_handler_to_channels(app)
        # Should not raise

    def test_no_process_adapter_skips(self) -> None:
        from dazzle_back.runtime.server import DazzleBackendApp

        app = self._make_app(channel_mgr=MagicMock(), process_adapter=None)
        DazzleBackendApp._wire_send_handler_to_channels(app)

    def test_adapter_without_set_send_handler_skips(self) -> None:
        from dazzle_back.runtime.server import DazzleBackendApp

        adapter = MagicMock(spec=[])  # No attributes
        app = self._make_app(channel_mgr=MagicMock(), process_adapter=adapter)
        DazzleBackendApp._wire_send_handler_to_channels(app)

    def test_wires_handler_to_adapter(self) -> None:
        from dazzle_back.runtime.server import DazzleBackendApp

        adapter = MagicMock()
        adapter.set_send_handler = MagicMock()
        channel_mgr = MagicMock()

        app = self._make_app(channel_mgr=channel_mgr, process_adapter=adapter)
        DazzleBackendApp._wire_send_handler_to_channels(app)

        adapter.set_send_handler.assert_called_once()
        handler = adapter.set_send_handler.call_args[0][0]
        assert callable(handler)

    @pytest.mark.asyncio
    async def test_handler_calls_channel_manager_send(self) -> None:
        from dazzle_back.runtime.server import DazzleBackendApp

        adapter = MagicMock()
        channel_mgr = MagicMock()
        channel_mgr.send = AsyncMock()

        app = self._make_app(channel_mgr=channel_mgr, process_adapter=adapter)
        DazzleBackendApp._wire_send_handler_to_channels(app)

        handler = adapter.set_send_handler.call_args[0][0]
        await handler("notifications", "WelcomeEmail", {"to": "user@example.com"})

        channel_mgr.send.assert_awaited_once_with(
            channel="notifications",
            operation="process_send",
            message_type="WelcomeEmail",
            payload={"to": "user@example.com"},
            recipient="user@example.com",
        )


# =============================================================================
# Entity event → channel dispatch wiring tests
# =============================================================================


class TestWireEntityEventsToChannels:
    """Tests for _wire_entity_events_to_channels."""

    def _make_app(
        self,
        *,
        channels: list[ChannelSpec] | None = None,
        services: dict[str, Any] | None = None,
        channel_mgr: Any = None,
    ) -> Any:
        """Create a minimal mock DazzleBackendApp."""
        app = MagicMock()
        spec = MagicMock()
        spec.channels = channels or []
        app.spec = spec
        app.channel_manager = channel_mgr
        app._services = services or {}
        return app

    def test_no_channel_manager_skips(self) -> None:
        from dazzle_back.runtime.server import DazzleBackendApp

        app = self._make_app(channel_mgr=None)
        DazzleBackendApp._wire_entity_events_to_channels(app)

    def test_no_services_skips(self) -> None:
        from dazzle_back.runtime.server import DazzleBackendApp

        app = self._make_app(channel_mgr=MagicMock(), services=None)
        app._services = None
        DazzleBackendApp._wire_entity_events_to_channels(app)

    def test_no_triggers_skips(self) -> None:
        from dazzle_back.runtime.server import DazzleBackendApp

        ch = ChannelSpec(
            name="emails",
            kind="email",
            send_operations=[
                SendOperationSpec(name="manual", message="Msg"),
            ],
            metadata={},
        )
        service = MagicMock()
        app = self._make_app(
            channels=[ch],
            services={"Order": service},
            channel_mgr=MagicMock(),
        )
        DazzleBackendApp._wire_entity_events_to_channels(app)
        # No triggers → no callbacks registered
        service.on_created.assert_not_called()

    def test_registers_callbacks_for_triggered_entity(self) -> None:
        from dazzle_back.runtime.server import DazzleBackendApp
        from dazzle_back.runtime.service_generator import CRUDService

        ch = ChannelSpec(
            name="notifications",
            kind="email",
            send_operations=[
                SendOperationSpec(name="order_created", message="OrderEmail"),
            ],
            metadata={
                "send_triggers": {
                    "order_created": {
                        "kind": "entity_event",
                        "entity_name": "Order",
                        "event": "created",
                    },
                },
            },
        )

        service = MagicMock(spec=CRUDService)
        service.entity_name = "Order"

        app = self._make_app(
            channels=[ch],
            services={"OrderService": service},
            channel_mgr=MagicMock(),
        )
        DazzleBackendApp._wire_entity_events_to_channels(app)

        service.on_created.assert_called_once()
        service.on_updated.assert_called_once()
        service.on_deleted.assert_called_once()

    def test_skips_non_triggered_entities(self) -> None:
        from dazzle_back.runtime.server import DazzleBackendApp
        from dazzle_back.runtime.service_generator import CRUDService

        ch = ChannelSpec(
            name="notifications",
            kind="email",
            send_operations=[
                SendOperationSpec(name="order_created", message="OrderEmail"),
            ],
            metadata={
                "send_triggers": {
                    "order_created": {
                        "kind": "entity_event",
                        "entity_name": "Order",
                        "event": "created",
                    },
                },
            },
        )

        # Service for User entity — should not get callbacks
        user_service = MagicMock(spec=CRUDService)
        user_service.entity_name = "User"

        app = self._make_app(
            channels=[ch],
            services={"UserService": user_service},
            channel_mgr=MagicMock(),
        )
        DazzleBackendApp._wire_entity_events_to_channels(app)

        user_service.on_created.assert_not_called()

    @pytest.mark.asyncio
    async def test_callback_dispatches_correct_event(self) -> None:
        from dazzle_back.runtime.server import DazzleBackendApp
        from dazzle_back.runtime.service_generator import CRUDService

        ch = ChannelSpec(
            name="notifications",
            kind="email",
            send_operations=[
                SendOperationSpec(name="order_created", message="OrderEmail"),
            ],
            metadata={
                "send_triggers": {
                    "order_created": {
                        "kind": "entity_event",
                        "entity_name": "Order",
                        "event": "created",
                    },
                },
            },
        )

        channel_mgr = MagicMock()
        channel_mgr.send = AsyncMock()

        service = MagicMock(spec=CRUDService)
        service.entity_name = "Order"

        app = self._make_app(
            channels=[ch],
            services={"OrderService": service},
            channel_mgr=channel_mgr,
        )
        DazzleBackendApp._wire_entity_events_to_channels(app)

        # Get the on_created callback
        on_created_cb = service.on_created.call_args[0][0]

        # Simulate entity creation
        await on_created_cb("Order", "123", {"email": "buyer@example.com"}, None)

        channel_mgr.send.assert_awaited_once_with(
            channel="notifications",
            operation="order_created",
            message_type="OrderEmail",
            payload={
                "entity_id": "123",
                "entity_name": "Order",
                "event_type": "created",
                "email": "buyer@example.com",
            },
            recipient="buyer@example.com",
        )

    @pytest.mark.asyncio
    async def test_callback_only_fires_for_matching_event(self) -> None:
        """on_updated callback should not dispatch 'created' triggers."""
        from dazzle_back.runtime.server import DazzleBackendApp
        from dazzle_back.runtime.service_generator import CRUDService

        ch = ChannelSpec(
            name="notifications",
            kind="email",
            send_operations=[
                SendOperationSpec(name="order_created", message="OrderEmail"),
            ],
            metadata={
                "send_triggers": {
                    "order_created": {
                        "kind": "entity_event",
                        "entity_name": "Order",
                        "event": "created",
                    },
                },
            },
        )

        channel_mgr = MagicMock()
        channel_mgr.send = AsyncMock()

        service = MagicMock(spec=CRUDService)
        service.entity_name = "Order"

        app = self._make_app(
            channels=[ch],
            services={"OrderService": service},
            channel_mgr=channel_mgr,
        )
        DazzleBackendApp._wire_entity_events_to_channels(app)

        # Get the on_updated callback — should NOT dispatch because
        # trigger is only for "created"
        on_updated_cb = service.on_updated.call_args[0][0]
        await on_updated_cb("Order", "123", {"email": "buyer@example.com"}, {})

        channel_mgr.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_channel_send_failure_does_not_propagate(self) -> None:
        """Channel send errors should be logged, not raised."""
        from dazzle_back.runtime.server import DazzleBackendApp
        from dazzle_back.runtime.service_generator import CRUDService

        ch = ChannelSpec(
            name="notifications",
            kind="email",
            send_operations=[
                SendOperationSpec(name="order_created", message="OrderEmail"),
            ],
            metadata={
                "send_triggers": {
                    "order_created": {
                        "kind": "entity_event",
                        "entity_name": "Order",
                        "event": "created",
                    },
                },
            },
        )

        channel_mgr = MagicMock()
        channel_mgr.send = AsyncMock(side_effect=RuntimeError("provider down"))

        service = MagicMock(spec=CRUDService)
        service.entity_name = "Order"

        app = self._make_app(
            channels=[ch],
            services={"OrderService": service},
            channel_mgr=channel_mgr,
        )
        DazzleBackendApp._wire_entity_events_to_channels(app)

        on_created_cb = service.on_created.call_args[0][0]

        # Should not raise despite channel_mgr.send failing
        await on_created_cb("Order", "123", {"email": "x@y.com"}, None)
