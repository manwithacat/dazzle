"""Tests for entity event bus wiring to CRUD services (#339).

Verifies that entity lifecycle events from CRUD services are emitted
to the EntityEventBus, enabling integration mapping triggers to fire.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle_back.runtime.event_bus import EntityEvent, EntityEventBus, EntityEventType


def _make_mock_ctx(service_names: list[str] | None = None) -> Any:
    """Create a mock SubsystemContext with mock CRUD services."""
    from dazzle_back.runtime.service_generator import CRUDService

    if service_names is None:
        service_names = ["Company"]

    services: dict[str, Any] = {}
    for name in service_names:
        svc = MagicMock(spec=CRUDService)
        svc.entity_name = name
        svc._on_created_callbacks: list[Any] = []
        svc._on_updated_callbacks: list[Any] = []
        svc._on_deleted_callbacks: list[Any] = []
        svc.on_created = MagicMock(
            side_effect=lambda cb, cbs=svc._on_created_callbacks: cbs.append(cb)
        )
        svc.on_updated = MagicMock(
            side_effect=lambda cb, cbs=svc._on_updated_callbacks: cbs.append(cb)
        )
        svc.on_deleted = MagicMock(
            side_effect=lambda cb, cbs=svc._on_deleted_callbacks: cbs.append(cb)
        )
        services[name] = svc

    ctx = MagicMock()
    ctx.services = services
    return ctx, services


class TestWireEntityEventsToBus:
    """Test _wire_entity_events_to_bus connects services to event bus."""

    def test_callbacks_registered_on_services(self) -> None:
        """Services get on_created/on_updated/on_deleted callbacks."""
        from dazzle_back.runtime.subsystems.system_routes import SystemRoutesSubsystem

        ctx, services = _make_mock_ctx(["Company", "Contact"])

        subsystem = SystemRoutesSubsystem()
        bus = EntityEventBus()
        subsystem._wire_entity_events_to_bus(ctx, bus)

        for name in ("Company", "Contact"):
            svc = services[name]
            svc.on_created.assert_called_once()
            svc.on_updated.assert_called_once()
            svc.on_deleted.assert_called_once()

    @pytest.mark.asyncio
    async def test_created_callback_emits_to_bus(self) -> None:
        """on_created callback emits entity:created event to bus."""
        from dazzle_back.runtime.subsystems.system_routes import SystemRoutesSubsystem

        ctx, services = _make_mock_ctx(["Company"])

        subsystem = SystemRoutesSubsystem()
        bus = EntityEventBus()
        handler = AsyncMock()
        bus.add_handler(handler)

        subsystem._wire_entity_events_to_bus(ctx, bus)

        created_cb = services["Company"]._on_created_callbacks[0]
        await created_cb("Company", "abc-123", {"name": "Acme"}, None)

        handler.assert_called_once()
        event: EntityEvent = handler.call_args[0][0]
        assert event.event_type == EntityEventType.CREATED
        assert event.entity_name == "Company"
        assert event.entity_id == "abc-123"
        assert event.data == {"name": "Acme"}

    @pytest.mark.asyncio
    async def test_updated_callback_emits_to_bus(self) -> None:
        """on_updated callback emits entity:updated event to bus."""
        from dazzle_back.runtime.subsystems.system_routes import SystemRoutesSubsystem

        ctx, services = _make_mock_ctx(["Company"])

        subsystem = SystemRoutesSubsystem()
        bus = EntityEventBus()
        handler = AsyncMock()
        bus.add_handler(handler)

        subsystem._wire_entity_events_to_bus(ctx, bus)

        updated_cb = services["Company"]._on_updated_callbacks[0]
        await updated_cb(
            "Company",
            "abc-123",
            {"name": "Acme", "status": "active"},
            {"name": "Acme", "status": "draft"},
        )

        handler.assert_called_once()
        event: EntityEvent = handler.call_args[0][0]
        assert event.event_type == EntityEventType.UPDATED
        assert event.entity_name == "Company"
        assert event.data is not None
        assert event.data["_previous_state"] == "draft"

    @pytest.mark.asyncio
    async def test_updated_callback_no_previous_state_when_unchanged(self) -> None:
        """No _previous_state when status hasn't changed."""
        from dazzle_back.runtime.subsystems.system_routes import SystemRoutesSubsystem

        ctx, services = _make_mock_ctx(["Company"])

        subsystem = SystemRoutesSubsystem()
        bus = EntityEventBus()
        handler = AsyncMock()
        bus.add_handler(handler)

        subsystem._wire_entity_events_to_bus(ctx, bus)

        updated_cb = services["Company"]._on_updated_callbacks[0]
        await updated_cb(
            "Company",
            "abc-123",
            {"name": "New Name", "status": "active"},
            {"name": "Old Name", "status": "active"},
        )

        event: EntityEvent = handler.call_args[0][0]
        assert event.data is not None
        assert "_previous_state" not in event.data

    @pytest.mark.asyncio
    async def test_deleted_callback_emits_to_bus(self) -> None:
        """on_deleted callback emits entity:deleted event to bus."""
        from dazzle_back.runtime.subsystems.system_routes import SystemRoutesSubsystem

        ctx, services = _make_mock_ctx(["Company"])

        subsystem = SystemRoutesSubsystem()
        bus = EntityEventBus()
        handler = AsyncMock()
        bus.add_handler(handler)

        subsystem._wire_entity_events_to_bus(ctx, bus)

        deleted_cb = services["Company"]._on_deleted_callbacks[0]
        await deleted_cb("Company", "abc-123", {"name": "Acme"}, None)

        handler.assert_called_once()
        event: EntityEvent = handler.call_args[0][0]
        assert event.event_type == EntityEventType.DELETED
        assert event.entity_name == "Company"
        assert event.entity_id == "abc-123"

    def test_no_services_no_error(self) -> None:
        """Wiring with empty services dict doesn't raise."""
        from dazzle_back.runtime.subsystems.system_routes import SystemRoutesSubsystem

        ctx = MagicMock()
        ctx.services = {}

        subsystem = SystemRoutesSubsystem()
        bus = EntityEventBus()
        subsystem._wire_entity_events_to_bus(ctx, bus)
        # No error = pass

    @pytest.mark.asyncio
    async def test_updated_with_no_old_data(self) -> None:
        """on_updated with None old_data still emits event."""
        from dazzle_back.runtime.subsystems.system_routes import SystemRoutesSubsystem

        ctx, services = _make_mock_ctx(["Company"])

        subsystem = SystemRoutesSubsystem()
        bus = EntityEventBus()
        handler = AsyncMock()
        bus.add_handler(handler)

        subsystem._wire_entity_events_to_bus(ctx, bus)

        updated_cb = services["Company"]._on_updated_callbacks[0]
        await updated_cb("Company", "abc-123", {"name": "Acme"}, None)

        event: EntityEvent = handler.call_args[0][0]
        assert event.event_type == EntityEventType.UPDATED
        assert "_previous_state" not in (event.data or {})
