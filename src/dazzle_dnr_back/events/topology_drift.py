"""
Topology Drift Detection for Event-First Architecture.

Detects and reports differences between the expected event topology
(defined in AppSpec) and the actual runtime state (topics, consumers,
partitions in the event bus).

Drift Types:
- MISSING_TOPIC: Topic defined in AppSpec but not in bus
- EXTRA_TOPIC: Topic in bus but not defined in AppSpec
- PARTITION_MISMATCH: Different partition count than expected
- MISSING_CONSUMER: Consumer group defined but not active
- EXTRA_CONSUMER: Consumer group active but not defined
- SCHEMA_DRIFT: Event schema differs from expected
- CONFIG_DRIFT: Topic configuration differs (retention, etc.)

Part of v0.18.0 Event-First Architecture (Issue #25, Phase I).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec
    from dazzle_dnr_back.events.bus import EventBus

logger = logging.getLogger("dazzle.events.topology_drift")


class DriftType(str, Enum):
    """Types of topology drift."""

    MISSING_TOPIC = "missing_topic"
    EXTRA_TOPIC = "extra_topic"
    PARTITION_MISMATCH = "partition_mismatch"
    MISSING_CONSUMER = "missing_consumer"
    EXTRA_CONSUMER = "extra_consumer"
    SCHEMA_DRIFT = "schema_drift"
    CONFIG_DRIFT = "config_drift"
    RETENTION_DRIFT = "retention_drift"


class DriftSeverity(str, Enum):
    """Severity levels for drift issues."""

    CRITICAL = "critical"  # System may not function correctly
    WARNING = "warning"  # Should be addressed but not blocking
    INFO = "info"  # Informational only


@dataclass
class DriftIssue:
    """A detected topology drift issue."""

    drift_type: DriftType
    severity: DriftSeverity
    resource: str  # Topic, consumer group, or other resource name
    message: str
    expected: Any = None
    actual: Any = None
    suggestion: str | None = None
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "drift_type": self.drift_type.value,
            "severity": self.severity.value,
            "resource": self.resource,
            "message": self.message,
            "expected": self.expected,
            "actual": self.actual,
            "suggestion": self.suggestion,
            "detected_at": self.detected_at.isoformat(),
        }


@dataclass
class TopologyFingerprint:
    """
    Fingerprint of an AppSpec's event topology.

    Used for quick comparison to detect if topology has changed.
    """

    hash: str
    topics: list[str]
    consumers: list[str]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    appspec_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "hash": self.hash,
            "topics": self.topics,
            "consumers": self.consumers,
            "created_at": self.created_at.isoformat(),
            "appspec_version": self.appspec_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TopologyFingerprint:
        """Create from dictionary."""
        return cls(
            hash=data["hash"],
            topics=data["topics"],
            consumers=data["consumers"],
            created_at=datetime.fromisoformat(data["created_at"]),
            appspec_version=data.get("appspec_version", ""),
        )


@dataclass
class ExpectedTopic:
    """Expected topic configuration from AppSpec."""

    name: str
    partitions: int = 3
    retention_days: int = 7
    events: list[str] = field(default_factory=list)  # Event types in this topic


@dataclass
class ExpectedConsumer:
    """Expected consumer group from AppSpec."""

    group_id: str
    topics: list[str]
    idempotent: bool = True


@dataclass
class ExpectedTopology:
    """Complete expected topology from AppSpec."""

    topics: list[ExpectedTopic]
    consumers: list[ExpectedConsumer]
    fingerprint: TopologyFingerprint


class TopologyExtractor:
    """
    Extracts expected topology from AppSpec.

    Analyzes the AppSpec to determine what topics, events, and consumers
    should exist in the event bus.
    """

    def extract(self, appspec: AppSpec) -> ExpectedTopology:
        """
        Extract expected topology from AppSpec.

        Args:
            appspec: Application specification

        Returns:
            ExpectedTopology with all expected resources
        """
        topics: dict[str, ExpectedTopic] = {}
        consumers: list[ExpectedConsumer] = []

        # Extract from event_model if present
        if appspec.event_model:
            for topic_spec in appspec.event_model.topics:
                topics[topic_spec.name] = ExpectedTopic(
                    name=topic_spec.name,
                    partitions=3,  # Default partition count
                    retention_days=topic_spec.retention_days,
                    events=[],
                )

            for event_spec in appspec.event_model.events:
                if event_spec.topic and event_spec.topic in topics:
                    topics[event_spec.topic].events.append(event_spec.name)

        # Extract from HLESS streams
        for stream in appspec.streams:
            topic_name = stream.name.rsplit(".", 1)[0] if "." in stream.name else stream.name
            if topic_name not in topics:
                topics[topic_name] = ExpectedTopic(
                    name=topic_name,
                    events=[stream.name],
                )
            else:
                topics[topic_name].events.append(stream.name)

        # Extract from subscriptions
        for sub in appspec.subscriptions:
            consumers.append(ExpectedConsumer(
                group_id=sub.group_id,
                topics=[sub.topic],
                idempotent=True,
            ))

        # Extract from projections
        for proj in appspec.projections:
            group_id = f"projection-{proj.name}"
            consumers.append(ExpectedConsumer(
                group_id=group_id,
                topics=[proj.source_topic],
                idempotent=True,
            ))

        # Infer entity CRUD topics
        for entity in appspec.domain.entities:
            topic_name = f"app.{entity.name}"
            if topic_name not in topics:
                topics[topic_name] = ExpectedTopic(
                    name=topic_name,
                    events=[
                        f"app.{entity.name}.created",
                        f"app.{entity.name}.updated",
                        f"app.{entity.name}.deleted",
                    ],
                )

        # Build topic and consumer lists
        topic_list = list(topics.values())
        consumer_list = consumers

        # Generate fingerprint
        fingerprint = self._generate_fingerprint(
            topic_list, consumer_list, appspec.version
        )

        return ExpectedTopology(
            topics=topic_list,
            consumers=consumer_list,
            fingerprint=fingerprint,
        )

    def _parse_retention(self, retention: str | None) -> int:
        """Parse retention string to days."""
        if not retention:
            return 7

        retention = retention.strip().lower()
        if retention.endswith("d"):
            return int(retention[:-1])
        elif retention.endswith("h"):
            return max(1, int(retention[:-1]) // 24)
        elif retention.endswith("w"):
            return int(retention[:-1]) * 7
        elif retention.endswith("m"):
            return int(retention[:-1]) * 30

        try:
            return int(retention)
        except ValueError:
            return 7

    def _generate_fingerprint(
        self,
        topics: list[ExpectedTopic],
        consumers: list[ExpectedConsumer],
        version: str,
    ) -> TopologyFingerprint:
        """Generate a fingerprint for the topology."""
        # Create canonical representation
        topic_dicts = [
            {"name": t.name, "partitions": t.partitions, "events": sorted(t.events)}
            for t in topics
        ]
        consumer_dicts = [
            {"group_id": c.group_id, "topics": sorted(c.topics)}
            for c in consumers
        ]
        canonical = {
            "topics": sorted(topic_dicts, key=lambda x: str(x["name"])),
            "consumers": sorted(consumer_dicts, key=lambda x: str(x["group_id"])),
        }

        # Generate hash
        canonical_json = json.dumps(canonical, sort_keys=True)
        hash_value = hashlib.sha256(canonical_json.encode()).hexdigest()[:16]

        return TopologyFingerprint(
            hash=hash_value,
            topics=[t.name for t in topics],
            consumers=[c.group_id for c in consumers],
            appspec_version=version,
        )


class TopologyDriftDetector:
    """
    Detects drift between expected and actual topology.

    Compares the AppSpec-defined topology with the actual state
    of the event bus and reports any discrepancies.
    """

    def __init__(
        self,
        bus: EventBus,
        ignore_internal_topics: bool = True,
        ignore_internal_consumers: bool = True,
    ) -> None:
        """
        Initialize the drift detector.

        Args:
            bus: Event bus to check
            ignore_internal_topics: Ignore topics starting with _ or __
            ignore_internal_consumers: Ignore consumer groups starting with _
        """
        self._bus = bus
        self._ignore_internal_topics = ignore_internal_topics
        self._ignore_internal_consumers = ignore_internal_consumers

    async def detect(self, expected: ExpectedTopology) -> list[DriftIssue]:
        """
        Detect topology drift.

        Args:
            expected: Expected topology from AppSpec

        Returns:
            List of drift issues found
        """
        issues: list[DriftIssue] = []

        # Check topics
        issues.extend(await self._check_topics(expected.topics))

        # Check consumers
        issues.extend(await self._check_consumers(expected))

        return issues

    async def _check_topics(
        self, expected_topics: list[ExpectedTopic]
    ) -> list[DriftIssue]:
        """Check for topic drift."""
        issues: list[DriftIssue] = []

        # Get actual topics
        actual_topics = set(await self._bus.list_topics())

        # Filter internal topics if configured
        if self._ignore_internal_topics:
            actual_topics = {
                t for t in actual_topics
                if not t.startswith("_") and not t.startswith("__")
            }

        expected_names = {t.name for t in expected_topics}

        # Check for missing topics
        for topic in expected_topics:
            if topic.name not in actual_topics:
                issues.append(DriftIssue(
                    drift_type=DriftType.MISSING_TOPIC,
                    severity=DriftSeverity.CRITICAL,
                    resource=topic.name,
                    message=f"Topic '{topic.name}' defined in AppSpec but not found in bus",
                    expected=topic.name,
                    actual=None,
                    suggestion=f"Create topic with: partitions={topic.partitions}",
                ))

        # Check for extra topics (excluding DLQ topics)
        for topic_name in actual_topics:
            if topic_name not in expected_names and not topic_name.endswith(".dlq"):
                issues.append(DriftIssue(
                    drift_type=DriftType.EXTRA_TOPIC,
                    severity=DriftSeverity.INFO,
                    resource=topic_name,
                    message=f"Topic '{topic_name}' exists but not defined in AppSpec",
                    expected=None,
                    actual=topic_name,
                    suggestion="Add topic to AppSpec or remove if unused",
                ))

        # Check topic configurations
        for topic in expected_topics:
            if topic.name in actual_topics:
                try:
                    info = await self._bus.get_topic_info(topic.name)
                    actual_partitions = info.get("partitions", 0)

                    if actual_partitions != topic.partitions:
                        issues.append(DriftIssue(
                            drift_type=DriftType.PARTITION_MISMATCH,
                            severity=DriftSeverity.WARNING,
                            resource=topic.name,
                            message=f"Topic '{topic.name}' has {actual_partitions} partitions, expected {topic.partitions}",
                            expected=topic.partitions,
                            actual=actual_partitions,
                            suggestion="Note: Kafka topics cannot reduce partitions",
                        ))
                except Exception as e:
                    logger.warning(f"Could not get info for topic {topic.name}: {e}")

        return issues

    async def _check_consumers(
        self, expected: ExpectedTopology
    ) -> list[DriftIssue]:
        """Check for consumer drift."""
        issues: list[DriftIssue] = []

        expected_groups = {c.group_id for c in expected.consumers}

        # Check each topic's consumers
        for topic in expected.topics:
            try:
                actual_groups = set(await self._bus.list_consumer_groups(topic.name))

                # Filter internal consumers
                if self._ignore_internal_consumers:
                    actual_groups = {
                        g for g in actual_groups if not g.startswith("_")
                    }

                # Find expected consumers for this topic
                topic_expected = {
                    c.group_id for c in expected.consumers
                    if topic.name in c.topics
                }

                # Check for missing consumers
                for group_id in topic_expected:
                    if group_id not in actual_groups:
                        issues.append(DriftIssue(
                            drift_type=DriftType.MISSING_CONSUMER,
                            severity=DriftSeverity.WARNING,
                            resource=f"{topic.name}/{group_id}",
                            message=f"Consumer group '{group_id}' not active on topic '{topic.name}'",
                            expected=group_id,
                            actual=None,
                            suggestion="Check if consumer is running",
                        ))

            except Exception as e:
                logger.warning(f"Could not check consumers for {topic.name}: {e}")

        return issues

    async def get_current_fingerprint(self) -> TopologyFingerprint:
        """
        Get the current fingerprint of the actual topology.

        Returns:
            TopologyFingerprint of current bus state
        """
        topics = await self._bus.list_topics()
        consumers: list[str] = []

        for topic in topics:
            try:
                groups = await self._bus.list_consumer_groups(topic)
                consumers.extend(groups)
            except Exception:
                pass

        # Deduplicate consumers
        consumers = list(set(consumers))

        # Generate hash
        canonical = json.dumps({
            "topics": sorted(topics),
            "consumers": sorted(consumers),
        }, sort_keys=True)
        hash_value = hashlib.sha256(canonical.encode()).hexdigest()[:16]

        return TopologyFingerprint(
            hash=hash_value,
            topics=topics,
            consumers=consumers,
        )


@dataclass
class DriftReport:
    """Complete drift detection report."""

    expected_fingerprint: TopologyFingerprint
    actual_fingerprint: TopologyFingerprint
    issues: list[DriftIssue]
    has_drift: bool
    critical_count: int
    warning_count: int
    info_count: int
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "expected_fingerprint": self.expected_fingerprint.to_dict(),
            "actual_fingerprint": self.actual_fingerprint.to_dict(),
            "issues": [i.to_dict() for i in self.issues],
            "has_drift": self.has_drift,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "checked_at": self.checked_at.isoformat(),
        }


async def check_topology_drift(
    bus: EventBus,
    appspec: AppSpec,
) -> DriftReport:
    """
    Check for topology drift between AppSpec and bus.

    Args:
        bus: Event bus to check
        appspec: Application specification

    Returns:
        DriftReport with all findings
    """
    # Extract expected topology
    extractor = TopologyExtractor()
    expected = extractor.extract(appspec)

    # Detect drift
    detector = TopologyDriftDetector(bus)
    issues = await detector.detect(expected)

    # Get actual fingerprint
    actual_fingerprint = await detector.get_current_fingerprint()

    # Count by severity
    critical = sum(1 for i in issues if i.severity == DriftSeverity.CRITICAL)
    warning = sum(1 for i in issues if i.severity == DriftSeverity.WARNING)
    info = sum(1 for i in issues if i.severity == DriftSeverity.INFO)

    return DriftReport(
        expected_fingerprint=expected.fingerprint,
        actual_fingerprint=actual_fingerprint,
        issues=issues,
        has_drift=len(issues) > 0,
        critical_count=critical,
        warning_count=warning,
        info_count=info,
    )
