"""
Operations Simulator.

Generates synthetic operational events for dashboard demonstration.
Allows founders to see the system in action without real traffic.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from dazzle_back.events.bus import EventBus
    from dazzle_back.runtime.ops_database import OpsDatabase

logger = logging.getLogger(__name__)


# =============================================================================
# Synthetic Data Generators
# =============================================================================

# Entity types with realistic names
ENTITY_TYPES = {
    "Task": [
        "Review quarterly report",
        "Update documentation",
        "Fix login bug",
        "Deploy to production",
        "Customer onboarding call",
        "Design system review",
        "API integration testing",
        "Performance optimization",
    ],
    "User": [
        "alice@example.com",
        "bob@techstart.io",
        "carol@acme.corp",
        "dave@globalservices.com",
        "eve@startup.inc",
    ],
    "Order": [
        "Premium subscription",
        "Enterprise license",
        "Starter plan",
        "Add-on package",
        "Annual renewal",
    ],
    "Invoice": [
        "Monthly billing",
        "One-time purchase",
        "Service fee",
        "Consulting hours",
    ],
    "Product": [
        "Analytics Dashboard",
        "API Access",
        "Premium Support",
        "Data Export",
        "Custom Integrations",
    ],
    "Customer": [
        "Acme Corporation",
        "TechStart Inc",
        "Global Services Ltd",
        "Innovative Solutions",
        "Digital Ventures",
    ],
}

# API services with endpoints and cost ranges
API_SERVICES: dict[str, dict[str, Any]] = {
    "openai": {
        "endpoints": ["/v1/chat/completions", "/v1/embeddings", "/v1/moderations"],
        "latency_range": (200, 2000),
        "cost_range": (0.5, 15.0),  # cents
        "error_rate": 0.02,
    },
    "anthropic": {
        "endpoints": ["/v1/messages", "/v1/complete"],
        "latency_range": (300, 2500),
        "cost_range": (1.0, 20.0),
        "error_rate": 0.01,
    },
    "stripe": {
        "endpoints": [
            "/v1/charges",
            "/v1/customers",
            "/v1/subscriptions",
            "/v1/invoices",
        ],
        "latency_range": (50, 300),
        "cost_range": (0, 0),  # No per-call cost
        "error_rate": 0.005,
    },
    "sendgrid": {
        "endpoints": ["/v3/mail/send", "/v3/contactdb/recipients"],
        "latency_range": (100, 500),
        "cost_range": (0, 0.1),
        "error_rate": 0.01,
    },
    "twilio": {
        "endpoints": ["/Messages.json", "/Calls.json"],
        "latency_range": (150, 600),
        "cost_range": (0.5, 2.0),
        "error_rate": 0.02,
    },
}

# Tenants for multi-tenant simulation
TENANTS = (
    {"id": "tenant-acme", "name": "Acme Corporation"},
    {"id": "tenant-techstart", "name": "TechStart Inc"},
    {"id": "tenant-global", "name": "Global Services"},
)

# Health components
HEALTH_COMPONENTS: list[dict[str, str | int]] = [
    {"name": "app_database", "type": "database", "base_latency": 5},
    {"name": "ops_database", "type": "database", "base_latency": 3},
    {"name": "event_bus", "type": "event_bus", "base_latency": 1},
    {"name": "redis_cache", "type": "cache", "base_latency": 2},
]

# Email templates
EMAIL_TEMPLATES = ("welcome", "notification", "password_reset", "invoice", "alert")


@dataclass
class SimulatorStats:
    """Statistics for the running simulation."""

    started_at: datetime | None = None
    events_generated: int = 0
    health_checks: int = 0
    api_calls: int = 0
    emails: int = 0


class OpsSimulator:
    """
    Generates synthetic operational events for dashboard demonstration.

    When enabled, generates a stream of realistic events:
    - Health check updates
    - Entity lifecycle events (create, update, delete)
    - External API call tracking
    - Email tracking events
    - Analytics events

    Events are recorded to OpsDatabase and published to EventBus
    for real-time SSE streaming to the dashboard.
    """

    def __init__(
        self,
        ops_db: OpsDatabase,
        event_bus: EventBus | None = None,
    ):
        """
        Initialize the simulator.

        Args:
            ops_db: Operations database for recording events
            event_bus: Optional event bus for SSE streaming
        """
        self.ops_db = ops_db
        self.event_bus = event_bus
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._stats = SimulatorStats()

    @property
    def running(self) -> bool:
        """Check if simulation is running."""
        return self._running

    @property
    def stats(self) -> SimulatorStats:
        """Get current simulation statistics."""
        return self._stats

    async def start(self) -> None:
        """Start the simulation."""
        if self._running:
            logger.warning("Simulation already running")
            return

        self._running = True
        self._stats = SimulatorStats(started_at=datetime.now(UTC))
        self._task = asyncio.create_task(self._simulation_loop())
        logger.info("Simulation started")

    async def stop(self) -> None:
        """Stop the simulation."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info(
            "Simulation stopped after %d events",
            self._stats.events_generated,
        )

    async def _simulation_loop(self) -> None:
        """Main simulation loop."""
        # Track next scheduled time for each event type
        next_health = 0.0
        next_entity = 0.0
        next_api = 0.0
        next_email = 0.0

        while self._running:
            try:
                now = asyncio.get_event_loop().time()

                # Health checks every 5 seconds
                if now >= next_health:
                    await self._generate_health_event()
                    next_health = now + 5.0

                # Entity events every 2-5 seconds
                if now >= next_entity:
                    await self._generate_entity_event()
                    next_entity = now + random.uniform(2.0, 5.0)

                # API calls every 5-10 seconds
                if now >= next_api:
                    await self._generate_api_call()
                    next_api = now + random.uniform(5.0, 10.0)

                # Email events every 10-15 seconds
                if now >= next_email:
                    await self._generate_email_event()
                    next_email = now + random.uniform(10.0, 15.0)

                # Small sleep to prevent tight loop
                await asyncio.sleep(0.5)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Simulation error: %s", e)
                await asyncio.sleep(1.0)

    async def _generate_health_event(self) -> None:
        """Generate a health check event."""
        from dazzle_back.runtime.ops_database import (
            ComponentType,
            HealthCheckRecord,
            HealthStatus,
        )

        component = random.choice(HEALTH_COMPONENTS)
        comp_name = str(component["name"])
        comp_type = str(component["type"])
        base_latency = float(component["base_latency"])

        # Mostly healthy, occasionally degraded or unhealthy
        roll = random.random()
        if roll < 0.85:
            status = HealthStatus.HEALTHY
            latency = base_latency * random.uniform(0.8, 1.5)
            message = "OK"
        elif roll < 0.95:
            status = HealthStatus.DEGRADED
            latency = base_latency * random.uniform(3.0, 10.0)
            message = "Slow response"
        else:
            status = HealthStatus.UNHEALTHY
            latency = base_latency * random.uniform(10.0, 30.0)
            message = "Connection timeout"

        # Map component type string to enum
        type_map: dict[str, ComponentType] = {
            "database": ComponentType.DATABASE,
            "event_bus": ComponentType.EVENT_BUS,
            "cache": ComponentType.CACHE,
        }

        record = HealthCheckRecord(
            id=str(uuid4()),
            component=comp_name,
            component_type=type_map.get(comp_type, ComponentType.DATABASE),
            status=status,
            latency_ms=latency,
            message=message,
            metadata={},
            checked_at=datetime.now(UTC),
        )

        self.ops_db.record_health_check(record)
        self._stats.health_checks += 1
        self._stats.events_generated += 1

        # Publish to event bus for SSE
        if self.event_bus:
            await self._publish_event(
                "ops.health",
                {
                    "component": comp_name,
                    "status": status.value,
                    "latency_ms": latency,
                    "message": message,
                },
            )

    async def _generate_entity_event(self) -> None:
        """Generate an entity lifecycle event."""
        entity_type = random.choice(list(ENTITY_TYPES.keys()))
        entity_names = ENTITY_TYPES[entity_type]
        tenant = random.choice(TENANTS)

        # Weighted event types: more creates and updates than deletes
        event_type = random.choices(
            ["created", "updated", "deleted"],
            weights=[0.4, 0.5, 0.1],
        )[0]

        entity_id = str(uuid4())
        entity_name = random.choice(entity_names)

        # Build payload based on entity type
        payload: dict[str, Any] = {"name": entity_name}
        if entity_type == "Task":
            payload["status"] = random.choice(["pending", "in_progress", "completed", "blocked"])
        elif entity_type == "Order":
            payload["status"] = random.choice(["pending", "processing", "shipped", "delivered"])
            payload["amount"] = round(random.uniform(10, 500), 2)
        elif entity_type == "Invoice":
            payload["amount"] = round(random.uniform(50, 2000), 2)
            payload["status"] = random.choice(["draft", "sent", "paid", "overdue"])

        self.ops_db.record_event(
            event_type=f"entity.{event_type}",
            entity_name=entity_type,
            entity_id=entity_id,
            payload=payload,
            tenant_id=tenant["id"],
        )

        self._stats.events_generated += 1

        # Publish to event bus for SSE
        if self.event_bus:
            await self._publish_event(
                f"entity.{event_type}",
                {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "payload": payload,
                    "tenant_id": tenant["id"],
                },
            )

    async def _generate_api_call(self) -> None:
        """Generate an API call tracking event."""
        from dazzle_back.runtime.ops_database import ApiCallRecord

        service_name = random.choice(list(API_SERVICES.keys()))
        service = API_SERVICES[service_name]
        endpoint = random.choice(service["endpoints"])
        tenant = random.choice(TENANTS)

        # Determine success/failure
        is_error = random.random() < service["error_rate"]
        if is_error:
            status_code = random.choice([429, 500, 502, 503])
            error_message = random.choice(
                ["Rate limited", "Internal server error", "Service unavailable"]
            )
        else:
            status_code = 200
            error_message = None

        latency = random.uniform(*service["latency_range"])
        cost = random.uniform(*service["cost_range"]) if service["cost_range"][1] else 0

        record = ApiCallRecord(
            id=str(uuid4()),
            service_name=service_name,
            endpoint=endpoint,
            method="POST",
            status_code=status_code,
            latency_ms=latency,
            request_size_bytes=random.randint(100, 5000),
            response_size_bytes=random.randint(500, 50000),
            error_message=error_message,
            cost_cents=cost,
            metadata={},
            called_at=datetime.now(UTC),
            tenant_id=tenant["id"],
        )

        self.ops_db.record_api_call(record)
        self._stats.api_calls += 1
        self._stats.events_generated += 1

        # Publish to event bus for SSE
        if self.event_bus:
            await self._publish_event(
                "ops.api_call",
                {
                    "service": service_name,
                    "endpoint": endpoint,
                    "status_code": status_code,
                    "latency_ms": latency,
                    "cost_cents": cost,
                },
            )

    async def _generate_email_event(self) -> None:
        """Generate an email tracking event."""
        tenant = random.choice(TENANTS)
        template = random.choice(EMAIL_TEMPLATES)
        email_id = str(uuid4())
        recipient = f"user{random.randint(1, 100)}@example.com"

        # Weighted email event types
        event_type = random.choices(
            ["email.sent", "email.opened", "email.clicked", "email.bounced"],
            weights=[0.5, 0.3, 0.15, 0.05],
        )[0]

        payload: dict[str, Any] = {
            "email_id": email_id,
            "template": template,
            "recipient": recipient,
        }

        if event_type == "email.clicked":
            payload["click_url"] = random.choice(
                [
                    "https://app.example.com/dashboard",
                    "https://app.example.com/settings",
                    "https://app.example.com/upgrade",
                    "https://docs.example.com",
                ]
            )
        elif event_type == "email.opened":
            payload["user_agent"] = "Mozilla/5.0"

        self.ops_db.record_event(
            event_type=event_type,
            entity_name="email",
            entity_id=email_id,
            payload=payload,
            tenant_id=tenant["id"],
        )

        self._stats.emails += 1
        self._stats.events_generated += 1

    async def _publish_event(self, topic: str, data: dict[str, Any]) -> None:
        """Publish event to EventBus for SSE streaming."""
        if not self.event_bus:
            return

        try:
            from dazzle_back.events.envelope import EventEnvelope

            envelope = EventEnvelope(
                event_id=uuid4(),
                event_type=topic,
                timestamp=datetime.now(UTC),
                payload=data,
                headers={"source": "simulator"},
                producer="ops_simulator",
            )
            await self.event_bus.publish(topic, envelope)
        except Exception as e:
            logger.debug("Failed to publish to event bus: %s", e)
