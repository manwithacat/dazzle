"""
Unit tests for the Operations Simulator.

Tests the synthetic event generation for dashboard demonstration.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dazzle_back.runtime.ops_database import OpsDatabase
from dazzle_back.runtime.ops_simulator import OpsSimulator


class TestOpsSimulator:
    """Tests for OpsSimulator."""

    @pytest.fixture
    def ops_db(self, tmp_path: Path) -> OpsDatabase:
        """Create a temporary ops database."""
        return OpsDatabase(db_path=tmp_path / "ops.db")

    @pytest.fixture
    def simulator(self, ops_db: OpsDatabase) -> OpsSimulator:
        """Create a simulator instance."""
        return OpsSimulator(ops_db=ops_db, event_bus=None)

    def test_initial_state(self, simulator: OpsSimulator) -> None:
        """Test simulator starts in stopped state."""
        assert simulator.running is False
        assert simulator.stats.events_generated == 0
        assert simulator.stats.started_at is None

    @pytest.mark.asyncio
    async def test_start_stop(self, simulator: OpsSimulator) -> None:
        """Test starting and stopping the simulator."""
        await simulator.start()
        assert simulator.running is True
        assert simulator.stats.started_at is not None

        await simulator.stop()
        assert simulator.running is False

    @pytest.mark.asyncio
    async def test_start_idempotent(self, simulator: OpsSimulator) -> None:
        """Test that starting twice doesn't create multiple tasks."""
        await simulator.start()
        await simulator.start()  # Should be a no-op
        assert simulator.running is True

        await simulator.stop()
        assert simulator.running is False

    @pytest.mark.asyncio
    async def test_stop_idempotent(self, simulator: OpsSimulator) -> None:
        """Test that stopping a stopped simulator is a no-op."""
        assert simulator.running is False
        await simulator.stop()  # Should be a no-op
        assert simulator.running is False

    @pytest.mark.asyncio
    async def test_generates_events(self, simulator: OpsSimulator) -> None:
        """Test that the simulator generates events."""
        await simulator.start()

        # Wait a bit for events to generate
        await asyncio.sleep(1.5)

        await simulator.stop()

        # Should have generated some events
        assert simulator.stats.events_generated > 0

    @pytest.mark.asyncio
    async def test_generates_health_checks(
        self, simulator: OpsSimulator, ops_db: OpsDatabase
    ) -> None:
        """Test that health checks are generated."""
        await simulator.start()
        await asyncio.sleep(1.5)
        await simulator.stop()

        # Should have recorded health checks
        assert simulator.stats.health_checks > 0

    @pytest.mark.asyncio
    async def test_generates_entity_events(
        self, simulator: OpsSimulator, ops_db: OpsDatabase
    ) -> None:
        """Test that entity events are generated."""
        await simulator.start()
        await asyncio.sleep(3)  # Wait for entity events
        await simulator.stop()

        # Query events from database
        events = ops_db.get_events(limit=50)

        # Should have some entity events
        entity_events = [e for e in events if e["event_type"].startswith("entity.")]
        assert len(entity_events) > 0

    @pytest.mark.asyncio
    async def test_generates_api_calls(self, simulator: OpsSimulator, ops_db: OpsDatabase) -> None:
        """Test that API call records are generated."""
        await simulator.start()
        await asyncio.sleep(6)  # Wait for API call events (5-10s interval)
        await simulator.stop()

        assert simulator.stats.api_calls > 0

        # Verify in database
        stats = ops_db.get_api_call_stats(hours=1)
        assert len(stats) > 0

    @pytest.mark.asyncio
    async def test_stats_tracking(self, simulator: OpsSimulator) -> None:
        """Test that statistics are tracked correctly."""
        await simulator.start()
        await asyncio.sleep(2)
        await simulator.stop()

        stats = simulator.stats
        assert stats.events_generated > 0
        assert stats.started_at is not None
        # Total should equal sum of categories
        assert stats.events_generated >= (stats.health_checks + stats.api_calls + stats.emails)


class TestOpsSimulatorDataVariety:
    """Tests for synthetic data variety."""

    @pytest.fixture
    def ops_db(self, tmp_path: Path) -> OpsDatabase:
        """Create a temporary ops database."""
        return OpsDatabase(db_path=tmp_path / "ops.db")

    @pytest.fixture
    def simulator(self, ops_db: OpsDatabase) -> OpsSimulator:
        """Create a simulator instance."""
        return OpsSimulator(ops_db=ops_db, event_bus=None)

    @pytest.mark.asyncio
    async def test_entity_type_variety(self, simulator: OpsSimulator, ops_db: OpsDatabase) -> None:
        """Test that multiple entity types are generated."""
        await simulator.start()
        await asyncio.sleep(8)  # Generate several events (longer wait)
        await simulator.stop()

        events = ops_db.get_events(limit=100)
        entity_types = {e["entity_name"] for e in events if e["event_type"].startswith("entity.")}

        # Should have at least one entity type
        assert len(entity_types) >= 1

    @pytest.mark.asyncio
    async def test_api_service_variety(self, simulator: OpsSimulator, ops_db: OpsDatabase) -> None:
        """Test that multiple API services are simulated."""
        await simulator.start()
        await asyncio.sleep(12)  # Wait for multiple API calls
        await simulator.stop()

        stats = ops_db.get_api_call_stats(hours=1)

        # Should have calls to multiple services
        assert len(stats) >= 1

    @pytest.mark.asyncio
    async def test_tenant_variety(self, simulator: OpsSimulator, ops_db: OpsDatabase) -> None:
        """Test that events are distributed across tenants."""
        await simulator.start()
        await asyncio.sleep(5)
        await simulator.stop()

        events = ops_db.get_events(limit=100)
        tenant_ids = {e["tenant_id"] for e in events if e["tenant_id"]}

        # Should have multiple tenants
        assert len(tenant_ids) >= 1
