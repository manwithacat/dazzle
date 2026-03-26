"""Tests for SystemEntityStore — virtual entity routing."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from dazzle_back.runtime.system_entity_store import SystemEntityStore


class TestSystemEntityStoreHealth:
    @pytest.mark.asyncio
    async def test_list_returns_component_statuses(self):
        mock_aggregator = MagicMock()
        db_comp = MagicMock()
        db_comp.name = "database"
        db_comp.status = MagicMock(value="healthy")
        db_comp.message = "OK"
        db_comp.latency_ms = 5.2
        db_comp.last_checked = datetime(2026, 3, 26, tzinfo=UTC)

        redis_comp = MagicMock()
        redis_comp.name = "redis"
        redis_comp.status = MagicMock(value="degraded")
        redis_comp.message = "High latency"
        redis_comp.latency_ms = 150.0
        redis_comp.last_checked = datetime(2026, 3, 26, tzinfo=UTC)

        mock_aggregator.get_latest.return_value = MagicMock(components=[db_comp, redis_comp])
        store = SystemEntityStore(entity_name="SystemHealth", health_aggregator=mock_aggregator)
        results = await store.list()
        assert len(results) == 2
        assert results[0]["component"] == "database"
        assert results[0]["status"] == "healthy"
        assert results[1]["component"] == "redis"
        assert results[1]["status"] == "degraded"


class TestSystemEntityStoreProcessRun:
    @pytest.mark.asyncio
    async def test_list_returns_recent_runs(self):
        mock_monitor = MagicMock()
        mock_monitor.get_recent_runs.return_value = [
            MagicMock(
                id="run-1",
                process_name="order_fulfillment",
                status="completed",
                started_at=1711411200.0,
                completed_at=1711411260.0,
                current_step=None,
                error=None,
            ),
        ]
        store = SystemEntityStore(entity_name="ProcessRun", process_monitor=mock_monitor)
        results = await store.list()
        assert len(results) == 1
        assert results[0]["process_name"] == "order_fulfillment"
        assert results[0]["status"] == "completed"


class TestSystemEntityStoreMetric:
    @pytest.mark.asyncio
    async def test_list_returns_metric_points(self):
        mock_store = MagicMock()
        mock_store.get_metric_names.return_value = ["api.latency", "api.errors"]
        mock_store.get_latest.side_effect = [42.5, 3.0]
        store = SystemEntityStore(entity_name="SystemMetric", metrics_store=mock_store)
        results = await store.list()
        assert len(results) == 2
        assert results[0]["name"] == "api.latency"
        assert results[0]["value"] == 42.5


class TestSystemEntityStoreWriteBlocked:
    @pytest.mark.asyncio
    async def test_create_raises(self):
        store = SystemEntityStore(entity_name="SystemHealth", health_aggregator=MagicMock())
        with pytest.raises(NotImplementedError, match="read-only"):
            await store.create({})

    @pytest.mark.asyncio
    async def test_update_raises(self):
        store = SystemEntityStore(entity_name="SystemHealth", health_aggregator=MagicMock())
        with pytest.raises(NotImplementedError, match="read-only"):
            await store.update("id", {})

    @pytest.mark.asyncio
    async def test_delete_raises(self):
        store = SystemEntityStore(entity_name="SystemHealth", health_aggregator=MagicMock())
        with pytest.raises(NotImplementedError, match="read-only"):
            await store.delete("id")
