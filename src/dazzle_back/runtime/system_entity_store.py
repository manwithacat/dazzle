"""
Virtual entity store for platform system entities.

Routes read operations to existing backing stores (health aggregator,
metrics store, process monitor) instead of PostgreSQL. Write operations
are blocked — these entities are read-only projections.
"""

import builtins
import uuid
from datetime import UTC, datetime
from typing import Any


class SystemEntityStore:
    """Read-only store adapter for virtual platform entities."""

    def __init__(
        self,
        entity_name: str,
        *,
        health_aggregator: Any | None = None,
        metrics_store: Any | None = None,
        process_monitor: Any | None = None,
        log_store: Any | None = None,
        event_framework: Any | None = None,
    ) -> None:
        self.entity_name = entity_name
        self._health_aggregator = health_aggregator
        self._metrics_store = metrics_store
        self._process_monitor = process_monitor
        self._log_store = log_store
        self._event_framework = event_framework

    async def list(
        self,
        filters: dict[str, Any] | None = None,
        sort: list[str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if self.entity_name == "SystemHealth":
            return self._list_health()
        elif self.entity_name == "SystemMetric":
            return self._list_metrics()
        elif self.entity_name == "ProcessRun":
            return self._list_process_runs(limit=limit)
        elif self.entity_name == "LogEntry":
            return self._list_log_entries(filters=filters, limit=limit)
        elif self.entity_name == "EventTrace":
            return await self._list_event_traces(limit=limit)
        raise ValueError(f"Unknown virtual entity: {self.entity_name}")

    async def get(self, record_id: str) -> dict[str, Any] | None:
        return None

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(f"{self.entity_name} is read-only")

    async def update(self, record_id: str, data: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(f"{self.entity_name} is read-only")

    async def delete(self, record_id: str) -> None:
        raise NotImplementedError(f"{self.entity_name} is read-only")

    def _list_health(self) -> builtins.list[dict[str, Any]]:
        assert self._health_aggregator is not None
        system_health = self._health_aggregator.get_latest()
        results: list[dict[str, Any]] = []
        for comp in system_health.components:
            status_val = comp.status.value if hasattr(comp.status, "value") else str(comp.status)
            results.append(
                {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, comp.name)),
                    "component": comp.name,
                    "status": status_val,
                    "message": comp.message,
                    "latency_ms": comp.latency_ms,
                    "checked_at": comp.last_checked or datetime.now(UTC),
                }
            )
        return results

    def _list_metrics(self) -> builtins.list[dict[str, Any]]:
        assert self._metrics_store is not None
        metric_names = self._metrics_store.get_metric_names()
        results: list[dict[str, Any]] = []
        for name in metric_names:
            latest = self._metrics_store.get_latest(name)
            if latest is not None:
                results.append(
                    {
                        "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, name)),
                        "name": name,
                        "value": latest,
                        "unit": None,
                        "tags": None,
                        "bucket_start": None,
                        "resolution": None,
                    }
                )
        return results

    def _list_process_runs(self, limit: int | None = None) -> builtins.list[dict[str, Any]]:
        assert self._process_monitor is not None
        runs = self._process_monitor.get_recent_runs(count=limit or 20)
        results: list[dict[str, Any]] = []
        for run in runs:
            started = None
            if run.started_at:
                started = datetime.fromtimestamp(run.started_at, tz=UTC)
            completed = None
            if run.completed_at:
                completed = datetime.fromtimestamp(run.completed_at, tz=UTC)
            results.append(
                {
                    "id": run.id,
                    "process_name": run.process_name,
                    "status": run.status,
                    "started_at": started,
                    "completed_at": completed,
                    "current_step": run.current_step,
                    "error": run.error,
                }
            )
        return results

    def _list_log_entries(
        self,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> builtins.list[dict[str, Any]]:
        from dazzle_back.runtime.logging import get_recent_logs

        level = None
        if filters and "level" in filters:
            level = filters["level"]
        raw = get_recent_logs(count=limit or 50, level=level)
        results: list[dict[str, Any]] = []
        for entry in raw:
            results.append(
                {
                    "id": str(
                        uuid.uuid5(
                            uuid.NAMESPACE_DNS,
                            f"log-{entry.get('timestamp', '')}-{entry.get('message', '')[:50]}",
                        )
                    ),
                    "timestamp": entry.get("timestamp"),
                    "level": entry.get("level", "INFO"),
                    "component": entry.get("logger", entry.get("component", "")),
                    "message": entry.get("message", ""),
                    "source": entry.get("source", entry.get("filename", "")),
                }
            )
        return results

    async def _list_event_traces(
        self,
        limit: int | None = None,
    ) -> builtins.list[dict[str, Any]]:
        if self._event_framework is None:
            return []
        results: list[dict[str, Any]] = []
        try:
            bus = self._event_framework.bus
            topics = await bus.list_topics()
            for topic in topics[: limit or 10]:
                events: list[Any] = []
                async for envelope in bus.replay(topic, limit=limit or 20):
                    events.append(envelope)
                for env in events:
                    payload_str = ""
                    if hasattr(env, "payload"):
                        import json

                        try:
                            payload_str = json.dumps(env.payload)[:200]
                        except (TypeError, ValueError):
                            payload_str = str(env.payload)[:200]
                    results.append(
                        {
                            "id": str(getattr(env, "id", uuid.uuid4())),
                            "topic": topic,
                            "event_type": getattr(env, "event_type", ""),
                            "key": getattr(env, "key", ""),
                            "timestamp": getattr(env, "timestamp", datetime.now(UTC)),
                            "payload_preview": payload_str,
                            "correlation_id": str(getattr(env, "correlation_id", "")),
                        }
                    )
        except Exception:
            pass  # best-effort — event bus may not be initialized
        return results
