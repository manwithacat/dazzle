"""
Time-series metrics storage using Redis sorted sets.

Stores metrics at multiple resolutions for efficient querying:
- 1m buckets, kept for 1 hour (60 points)
- 5m buckets, kept for 24 hours (288 points)
- 1h buckets, kept for 7 days (168 points)
- 1d buckets, kept for 90 days (90 points)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from redis import Redis


class Resolution(Enum):
    """Time series resolutions."""

    MINUTE = ("1m", 60, 3600)  # 1 min buckets, 1 hour retention
    FIVE_MIN = ("5m", 300, 86400)  # 5 min buckets, 24 hour retention
    HOUR = ("1h", 3600, 604800)  # 1 hour buckets, 7 day retention
    DAY = ("1d", 86400, 7776000)  # 1 day buckets, 90 day retention

    def __init__(self, label: str, bucket_seconds: int, retention_seconds: int):
        self.label = label
        self.bucket_seconds = bucket_seconds
        self.retention_seconds = retention_seconds


@dataclass
class MetricPoint:
    """A single metric data point."""

    timestamp: float
    value: float
    count: int = 1


@dataclass
class AggregatedMetric:
    """Aggregated metric with statistics."""

    name: str
    resolution: str
    points: list[MetricPoint]

    @property
    def latest(self) -> float | None:
        """Get the most recent value."""
        return self.points[-1].value if self.points else None

    @property
    def avg(self) -> float | None:
        """Get average value."""
        if not self.points:
            return None
        return sum(p.value for p in self.points) / len(self.points)


class MetricsStore:
    """
    Redis-backed time-series metrics storage.

    Uses sorted sets with timestamp as score for efficient range queries.
    Key format: dazzle:metrics:{name}:{resolution}:{tags_hash}
    """

    PREFIX = "dazzle:metrics"

    def __init__(self, redis: Redis[Any]):
        self._redis = redis

    def _bucket_timestamp(self, ts: float, resolution: Resolution) -> int:
        """Round timestamp down to bucket boundary."""
        return int(ts // resolution.bucket_seconds) * resolution.bucket_seconds

    def _metric_key(
        self, name: str, resolution: Resolution, tags: dict[str, str] | None = None
    ) -> str:
        """Generate Redis key for a metric series."""
        tags_part = ""
        if tags:
            # Sort tags for consistent hashing
            sorted_tags = sorted(tags.items())
            tags_part = ":" + ",".join(f"{k}={v}" for k, v in sorted_tags)
        return f"{self.PREFIX}:{name}:{resolution.label}{tags_part}"

    def record(
        self,
        name: str,
        value: float,
        timestamp: float | None = None,
        tags: dict[str, str] | None = None,
    ) -> None:
        """
        Record a metric value.

        Values within the same bucket are averaged.
        """
        ts = timestamp or time.time()

        pipe = self._redis.pipeline()

        for resolution in Resolution:
            bucket_ts = self._bucket_timestamp(ts, resolution)
            key = self._metric_key(name, resolution, tags)

            # Use a sorted set with score=timestamp, member=JSON with sum/count
            existing_members = self._redis.zrangebyscore(key, bucket_ts, bucket_ts)

            if existing_members:
                # Update existing bucket - increment count and sum
                old_member = existing_members[0]
                data = json.loads(old_member)
                data["sum"] += value
                data["count"] += 1
                data["value"] = data["sum"] / data["count"]
                pipe.zrem(key, old_member)
                pipe.zadd(key, {json.dumps(data): bucket_ts})
            else:
                # New bucket
                data = {"sum": value, "count": 1, "value": value, "ts": bucket_ts}
                pipe.zadd(key, {json.dumps(data): bucket_ts})

            # Expire old data within the sorted set
            cutoff = ts - resolution.retention_seconds
            pipe.zremrangebyscore(key, "-inf", cutoff)

            # Set key TTL as safety net (2x retention so active keys survive)
            pipe.expire(key, resolution.retention_seconds * 2)

        pipe.execute()

    def record_batch(self, metrics: list[dict[str, Any]]) -> None:
        """Record multiple metrics efficiently."""
        for metric in metrics:
            self.record(
                name=metric["name"],
                value=metric["value"],
                timestamp=metric.get("ts"),
                tags=metric.get("tags"),
            )

    def query(
        self,
        name: str,
        resolution: Resolution = Resolution.MINUTE,
        start: float | None = None,
        end: float | None = None,
        tags: dict[str, str] | None = None,
    ) -> AggregatedMetric:
        """
        Query metric values over a time range.

        Args:
            name: Metric name
            resolution: Time resolution
            start: Start timestamp (default: retention period ago)
            end: End timestamp (default: now)
            tags: Filter by tags

        Returns:
            AggregatedMetric with data points
        """
        now = time.time()
        end = end or now
        start = start or (now - resolution.retention_seconds)

        key = self._metric_key(name, resolution, tags)

        # Query sorted set by score range
        raw_points = self._redis.zrangebyscore(key, start, end, withscores=True)

        points = []
        for member, _score in raw_points:
            data = json.loads(member)
            points.append(
                MetricPoint(
                    timestamp=data["ts"],
                    value=data["value"],
                    count=data["count"],
                )
            )

        return AggregatedMetric(
            name=name,
            resolution=resolution.label,
            points=points,
        )

    def get_metric_names(self) -> list[str]:
        """Get all known metric names."""
        keys = self._redis.keys(f"{self.PREFIX}:*:1m*")
        names = set()
        for key in keys:
            key_str = key if isinstance(key, str) else key.decode()
            parts = key_str.split(":")
            if len(parts) >= 4:
                names.add(parts[2])  # dazzle:metrics:{name}:1m
        return sorted(names)

    def get_latest(self, name: str, tags: dict[str, str] | None = None) -> float | None:
        """Get the most recent value for a metric."""
        key = self._metric_key(name, Resolution.MINUTE, tags)
        results = self._redis.zrevrange(key, 0, 0)
        if results:
            data = json.loads(results[0])
            return float(data["value"])
        return None

    def get_summary(self, name: str, duration_seconds: int = 300) -> dict[str, Any]:
        """
        Get summary statistics for a metric over recent duration.

        Aggregates across all tag combinations for the given metric name.

        Returns: {min, max, avg, count, latest}
        """
        now = time.time()
        start = now - duration_seconds

        # Find all keys matching this metric name (with any tags)
        pattern = f"{self.PREFIX}:{name}:{Resolution.MINUTE.label}*"
        keys = self._redis.keys(pattern)

        all_values: list[float] = []
        all_counts: list[int] = []
        latest_ts = 0.0
        latest_value: float | None = None

        for key in keys:
            key_str = key if isinstance(key, str) else key.decode()
            raw_points = self._redis.zrangebyscore(key_str, start, now, withscores=True)

            for member, _score in raw_points:
                data = json.loads(member)
                all_values.append(data["value"])
                all_counts.append(data["count"])
                if data["ts"] > latest_ts:
                    latest_ts = data["ts"]
                    latest_value = data["value"]

        if not all_values:
            return {"min": None, "max": None, "avg": None, "count": 0, "latest": None}

        return {
            "min": min(all_values),
            "max": max(all_values),
            "avg": sum(all_values) / len(all_values),
            "count": sum(all_counts),
            "latest": latest_value,
        }
