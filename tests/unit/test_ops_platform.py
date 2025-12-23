"""
Unit tests for the Observability Platform.

Tests the ops database, health aggregator, email templates,
and API tracking functionality.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from dazzle_dnr_back.runtime.email_templates import (
    BrandConfig,
    EmailTemplate,
    EmailTemplateEngine,
)
from dazzle_dnr_back.runtime.ops_database import (
    ApiCallRecord,
    ComponentType,
    HealthCheckRecord,
    HealthStatus,
    OpsDatabase,
    RetentionConfig,
)
from dazzle_dnr_back.runtime.ops_integration import OpsConfig, OpsPlatform


class TestOpsDatabase:
    """Tests for OpsDatabase."""

    @pytest.fixture
    def ops_db(self, tmp_path: Path) -> OpsDatabase:
        """Create a temporary ops database."""
        db_path = tmp_path / "ops.db"
        return OpsDatabase(db_path=db_path)

    def test_record_health_check(self, ops_db: OpsDatabase) -> None:
        """Test recording a health check."""
        record = HealthCheckRecord(
            id=str(uuid4()),
            component="test_db",
            component_type=ComponentType.DATABASE,
            status=HealthStatus.HEALTHY,
            latency_ms=15.5,
            message="Connection OK",
            metadata={},
            checked_at=datetime.now(UTC),
        )
        ops_db.record_health_check(record)

        history = ops_db.get_health_history("test_db", hours=1)
        assert len(history) == 1
        assert history[0].status == HealthStatus.HEALTHY

    def test_record_event(self, ops_db: OpsDatabase) -> None:
        """Test recording an event."""
        event_id = ops_db.record_event(
            event_type="entity.created",
            entity_name="Task",
            entity_id="task-123",
            payload={"title": "Test Task"},
            tenant_id="tenant-1",
        )

        assert event_id is not None

        events = ops_db.get_events(entity_name="Task")
        assert len(events) == 1
        assert events[0]["entity_id"] == "task-123"

    def test_record_api_call(self, ops_db: OpsDatabase) -> None:
        """Test recording an API call."""
        record = ApiCallRecord(
            id=str(uuid4()),
            service_name="openai",
            endpoint="/v1/chat/completions",
            method="POST",
            status_code=200,
            latency_ms=850.0,
            request_size_bytes=None,
            response_size_bytes=None,
            error_message=None,
            cost_cents=5.0,
            metadata={},
            called_at=datetime.now(UTC),
            tenant_id="tenant-1",
        )
        ops_db.record_api_call(record)

        stats = ops_db.get_api_call_stats(hours=1)
        assert "openai" in stats
        assert stats["openai"]["total_calls"] == 1

    def test_retention_config(self, ops_db: OpsDatabase) -> None:
        """Test retention configuration."""
        config = RetentionConfig(
            health_checks_days=7,
            api_calls_days=30,
            analytics_days=365,
            events_days=90,
        )
        ops_db.set_retention_config(config)

        loaded = ops_db.get_retention_config()
        assert loaded.health_checks_days == 7
        assert loaded.analytics_days == 365


class TestEmailTemplateEngine:
    """Tests for EmailTemplateEngine."""

    @pytest.fixture
    def engine(self, tmp_path: Path) -> EmailTemplateEngine:
        """Create an email template engine."""
        ops_db = OpsDatabase(db_path=tmp_path / "ops.db")
        brand = BrandConfig(
            name="Test App",
            tagline="Testing made easy",
            primary_color="#0066cc",
        )
        return EmailTemplateEngine(
            ops_db=ops_db,
            tracking_base_url="https://app.example.com",
            brand_config=brand,
        )

    def test_render_welcome_email(self, engine: EmailTemplateEngine) -> None:
        """Test rendering a welcome email."""
        email = engine.render(
            template_name="welcome",
            context={
                "user_name": "John",
                "action_url": "https://app.example.com/start",
                "action_text": "Get Started",
            },
            recipient="john@example.com",
            track_opens=True,
            track_clicks=True,
        )

        assert email.recipient == "john@example.com"
        assert "John" in email.body_html
        assert "Welcome" in email.subject
        assert email.tracking_enabled is True
        # Should have tracking pixel
        assert "/_ops/email/pixel/" in email.body_html

    def test_render_without_tracking(self, engine: EmailTemplateEngine) -> None:
        """Test rendering without tracking."""
        email = engine.render(
            template_name="welcome",
            context={"user_name": "Jane"},
            recipient="jane@example.com",
            track_opens=False,
            track_clicks=False,
        )

        assert email.tracking_enabled is False
        # Should not have tracking pixel
        assert "/_ops/email/pixel/" not in email.body_html

    def test_variable_substitution(self, engine: EmailTemplateEngine) -> None:
        """Test variable substitution in templates."""
        email = engine.render(
            template_name="notification",
            context={
                "notification_title": "New Comment",
                "notification_body": "Someone commented on your post.",
            },
            recipient="user@example.com",
        )

        assert "New Comment" in email.subject
        assert "commented on your post" in email.body_html

    def test_custom_template(self, engine: EmailTemplateEngine) -> None:
        """Test registering and using custom templates."""
        engine.register_template(
            EmailTemplate(
                name="order_confirmation",
                subject="Order #{{ order_id }} Confirmed",
                body_html="<p>Thank you for order {{ order_id }}!</p>",
                body_text="Thank you for order {{ order_id }}!",
            )
        )

        email = engine.render(
            template_name="order_confirmation",
            context={"order_id": "12345"},
            recipient="customer@example.com",
        )

        assert "Order #12345 Confirmed" in email.subject

    def test_link_rewriting_for_tracking(self, engine: EmailTemplateEngine) -> None:
        """Test that links are rewritten for click tracking."""
        engine.register_template(
            EmailTemplate(
                name="link_test",
                subject="Test",
                body_html='<a href="https://example.com/page">Click here</a>',
            )
        )

        email = engine.render(
            template_name="link_test",
            context={},
            recipient="user@example.com",
            track_clicks=True,
        )

        # Should rewrite link to go through tracking
        assert "/_ops/email/click/" in email.body_html
        assert "url=https%3A%2F%2Fexample.com%2Fpage" in email.body_html

    def test_list_templates(self, engine: EmailTemplateEngine) -> None:
        """Test listing available templates."""
        templates = engine.list_templates()

        names = [t["name"] for t in templates]
        assert "welcome" in names
        assert "notification" in names
        assert "password_reset" in names


class TestOpsPlatform:
    """Tests for OpsPlatform integration."""

    @pytest.fixture
    def platform(self, tmp_path: Path) -> OpsPlatform:
        """Create an ops platform instance."""
        config = OpsConfig(
            ops_db_path=tmp_path / "ops.db",
            require_auth=False,
            brand_config=BrandConfig(name="Test App"),
            tracking_base_url="https://app.example.com",
        )
        platform = OpsPlatform(config)
        platform.configure()
        return platform

    def test_record_event(self, platform: OpsPlatform) -> None:
        """Test recording an event through the platform."""
        event_id = platform.record_event(
            event_type="user.signup",
            entity_name="User",
            entity_id="user-123",
            payload={"email": "user@example.com"},
        )

        assert event_id is not None

    def test_render_email(self, platform: OpsPlatform) -> None:
        """Test rendering an email through the platform."""
        email = platform.render_email(
            template_name="welcome",
            recipient="user@example.com",
            context={"user_name": "Test User"},
        )

        assert email.recipient == "user@example.com"
        assert "Test User" in email.body_html

    def test_create_http_client(self, platform: OpsPlatform) -> None:
        """Test creating a tracked HTTP client."""
        client = platform.create_http_client(
            service_name="stripe",
            base_url="https://api.stripe.com",
        )

        assert client is not None

    def test_create_routes(self, platform: OpsPlatform) -> None:
        """Test creating ops routes."""
        routers = platform.create_routes()

        assert len(routers) >= 1  # At least the main ops router


class TestEmailDashboardEndpoints:
    """Tests for email dashboard API endpoints."""

    @pytest.fixture
    def ops_db(self, tmp_path: Path) -> OpsDatabase:
        """Create a temporary ops database with email events."""
        db = OpsDatabase(db_path=tmp_path / "ops.db")

        # Record some email events
        for i in range(5):
            db.record_event(
                event_type="email.sent",
                entity_name="email",
                entity_id=f"email-{i}",
                payload={"recipient": f"user{i}@example.com"},
            )

        for i in range(3):
            db.record_event(
                event_type="email.opened",
                entity_name="email",
                entity_id=f"email-{i}",
                payload={"user_agent": "Mozilla/5.0"},
            )

        # Record a click event
        db.record_event(
            event_type="email.clicked",
            entity_name="email",
            entity_id="email-0",
            payload={"click_url": "https://example.com/offer"},
        )

        return db

    def test_email_stats_query(self, ops_db: OpsDatabase) -> None:
        """Test querying email statistics using the OpsDatabase API."""
        # Query all email events using the API
        events = ops_db.get_events(entity_name="email")

        stats: dict[str, int] = {}
        for event in events:
            event_type = event["event_type"].replace("email.", "")
            stats[event_type] = stats.get(event_type, 0) + 1

        assert stats["sent"] == 5
        assert stats["opened"] == 3
        assert stats["clicked"] == 1

    def test_top_links_query(self, ops_db: OpsDatabase) -> None:
        """Test querying top clicked links."""
        # Add more click events
        for _ in range(5):
            ops_db.record_event(
                event_type="email.clicked",
                entity_name="email",
                entity_id="email-1",
                payload={"click_url": "https://example.com/popular"},
            )

        # Query clicked events and aggregate
        events = ops_db.get_events(entity_name="email", event_type="email.clicked")

        link_counts: dict[str, int] = {}
        for event in events:
            payload = event.get("payload") or {}
            # payload might be a dict or JSON string depending on how it's returned
            if isinstance(payload, str):
                import json

                payload = json.loads(payload)
            url = payload.get("click_url")
            if url:
                link_counts[url] = link_counts.get(url, 0) + 1

        # Sort by count descending
        sorted_links = sorted(link_counts.items(), key=lambda x: x[1], reverse=True)

        assert len(sorted_links) == 2
        # Most clicked should be first
        assert sorted_links[0][0] == "https://example.com/popular"
        assert sorted_links[0][1] == 5


class TestHealthAggregator:
    """Tests for HealthAggregator."""

    @pytest.fixture
    def ops_db(self, tmp_path: Path) -> OpsDatabase:
        """Create a temporary ops database."""
        return OpsDatabase(db_path=tmp_path / "ops.db")

    @pytest.mark.asyncio
    async def test_check_all(self, ops_db: OpsDatabase) -> None:
        """Test running all health checks."""
        from dazzle_dnr_back.runtime.health_aggregator import (
            ComponentHealth,
            HealthAggregator,
        )

        aggregator = HealthAggregator(ops_db=ops_db)

        async def healthy_check() -> ComponentHealth:
            return ComponentHealth(
                name="service_a",
                component_type=ComponentType.EXTERNAL_API,
                status=HealthStatus.HEALTHY,
                message="OK",
                latency_ms=10.0,
            )

        async def degraded_check() -> ComponentHealth:
            return ComponentHealth(
                name="service_b",
                component_type=ComponentType.EXTERNAL_API,
                status=HealthStatus.DEGRADED,
                message="Slow",
                latency_ms=500.0,
            )

        aggregator.register("service_a", ComponentType.EXTERNAL_API, healthy_check)
        aggregator.register("service_b", ComponentType.EXTERNAL_API, degraded_check)

        result = await aggregator.check_all()

        assert len(result.components) == 2
        statuses = {c.name: c.status for c in result.components}
        assert statuses["service_a"] == HealthStatus.HEALTHY
        assert statuses["service_b"] == HealthStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_aggregate_status(self, ops_db: OpsDatabase) -> None:
        """Test aggregate status calculation."""
        from dazzle_dnr_back.runtime.health_aggregator import (
            AggregateStatus,
            ComponentHealth,
            HealthAggregator,
        )

        aggregator = HealthAggregator(ops_db=ops_db)

        async def healthy_check_a() -> ComponentHealth:
            return ComponentHealth(
                name="a",
                component_type=ComponentType.EXTERNAL_API,
                status=HealthStatus.HEALTHY,
                message="OK",
                latency_ms=5.0,
            )

        async def healthy_check_b() -> ComponentHealth:
            return ComponentHealth(
                name="b",
                component_type=ComponentType.EXTERNAL_API,
                status=HealthStatus.HEALTHY,
                message="OK",
                latency_ms=5.0,
            )

        aggregator.register("a", ComponentType.EXTERNAL_API, healthy_check_a)
        aggregator.register("b", ComponentType.EXTERNAL_API, healthy_check_b)

        result = await aggregator.check_all()
        assert result.status == AggregateStatus.ALL_HEALTHY
        assert result.healthy_count == 2


class TestApiTracker:
    """Tests for API call tracking."""

    @pytest.fixture
    def tracker(self, tmp_path: Path):
        """Create an API tracker."""
        from dazzle_dnr_back.runtime.api_tracker import ApiTracker

        ops_db = OpsDatabase(db_path=tmp_path / "ops.db")
        return ApiTracker(ops_db=ops_db)

    @pytest.mark.asyncio
    async def test_track_api_call(self, tracker) -> None:
        """Test tracking an API call using context manager."""
        from dazzle_dnr_back.runtime.api_tracker import configure_openai_tracking

        configure_openai_tracking(tracker)

        async with tracker.track("openai", "/v1/chat/completions", "POST") as ctx:
            ctx.set_response(200)
            ctx.add_metadata("model", "gpt-4")
            ctx.add_metadata("input_tokens", 100)
            ctx.add_metadata("output_tokens", 50)

        # Verify call was recorded
        stats = tracker.ops_db.get_api_call_stats(service_name="openai", hours=1)
        assert "openai" in stats
        assert stats["openai"]["total_calls"] == 1

    @pytest.mark.asyncio
    async def test_cost_calculation(self, tracker) -> None:
        """Test that costs are calculated correctly."""
        from dazzle_dnr_back.runtime.api_tracker import configure_openai_tracking

        configure_openai_tracking(tracker)

        # Track a call with known token counts
        async with tracker.track("openai", "/v1/chat/completions", "POST") as ctx:
            ctx.set_response(200)
            ctx.add_metadata("model", "gpt-4")
            ctx.add_metadata("input_tokens", 1000)  # $0.03/1K = 3 cents
            ctx.add_metadata("output_tokens", 500)  # $0.06/1K = 3 cents

        # Cost should be approximately 6 cents
        stats = tracker.ops_db.get_api_call_stats(service_name="openai", hours=1)
        assert "openai" in stats
        # Allow some floating point tolerance
        assert 5 <= stats["openai"]["total_cost_cents"] <= 7
