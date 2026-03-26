"""Tests for RuntimeServices container."""

from unittest.mock import MagicMock

from dazzle_back.runtime.services import RuntimeServices


class TestRuntimeServices:
    def test_creates_default_event_bus(self) -> None:
        services = RuntimeServices()
        assert services.event_bus is not None

    def test_creates_default_presence_tracker(self) -> None:
        services = RuntimeServices()
        assert services.presence_tracker is not None

    def test_optional_fields_default_none(self) -> None:
        services = RuntimeServices()
        assert services.event_framework is None
        assert services.metrics_collector is None
        assert services.system_collector is None
        assert services.metrics_emitter is None

    def test_independent_instances(self) -> None:
        s1 = RuntimeServices()
        s2 = RuntimeServices()
        assert s1.event_bus is not s2.event_bus
        assert s1.presence_tracker is not s2.presence_tracker

    def test_accepts_custom_services(self) -> None:
        mock_framework = MagicMock()
        services = RuntimeServices(event_framework=mock_framework)
        assert services.event_framework is mock_framework

    def test_process_manager_defaults_none(self) -> None:
        services = RuntimeServices()
        assert services.process_manager is None
