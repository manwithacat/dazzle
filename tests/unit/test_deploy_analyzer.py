"""Tests for AWS requirements analyzer."""

from unittest.mock import MagicMock

from dazzle.deploy.analyzer import (
    AWSRequirements,
    EventBridgeBusSpec,
    EventBridgeRuleSpec,
    S3BucketSpec,
    SQSQueueSpec,
    analyze_aws_requirements,
)
from dazzle.deploy.config import DeploymentConfig


def create_mock_spec(
    *,
    entities: list | None = None,
    channels: list | None = None,
    processes: list | None = None,
    domain: MagicMock | None = None,
):
    """Create a mock AppSpec for testing."""
    spec = MagicMock()
    spec.name = "test-app"

    # Domain with entities
    if domain is None:
        domain = MagicMock()
        domain.entities = entities or []
    spec.domain = domain

    # Channels
    spec.channels = channels or []

    # Processes
    spec.processes = processes or []

    # APIs
    spec.apis = []

    # LLM config
    spec.llm_config = None
    spec.llm_models = []

    # Tenancy
    spec.tenancy = None

    return spec


def create_mock_infra_reqs(
    *,
    needs_database: bool = True,
    needs_storage: bool = False,
    needs_queues: bool = False,
    needs_events: bool = False,
    needs_email: bool = False,
    needs_cache: bool = False,
    needs_secrets: bool = False,
    entity_names: list[str] | None = None,
):
    """Create mock infrastructure requirements."""
    reqs = MagicMock()
    reqs.needs_database = needs_database
    reqs.needs_storage = needs_storage
    reqs.needs_queues = needs_queues
    reqs.needs_events = needs_events
    reqs.needs_email = needs_email
    reqs.needs_cache = needs_cache
    reqs.needs_secrets = needs_secrets
    reqs.entity_names = entity_names or []
    return reqs


class TestAWSRequirements:
    """Tests for AWSRequirements dataclass."""

    def test_default_values(self):
        """Test default AWS requirements."""
        reqs = AWSRequirements()

        assert reqs.needs_vpc is True  # Always needed
        assert reqs.needs_ecs is True  # Always needed
        assert reqs.needs_ecr is True  # Always needed
        assert reqs.needs_rds is False
        assert reqs.needs_s3 is False
        assert reqs.needs_sqs is False
        assert reqs.needs_eventbridge is False
        assert reqs.needs_ses is False
        assert reqs.needs_elasticache is False

    def test_summary(self):
        """Test summary dictionary generation."""
        reqs = AWSRequirements(
            needs_rds=True,
            needs_s3=True,
            needs_sqs=True,
        )

        summary = reqs.summary()

        assert summary["vpc"] is True
        assert summary["ecs"] is True
        assert summary["ecr"] is True
        assert summary["rds"] is True
        assert summary["s3"] is True
        assert summary["sqs"] is True
        assert summary["eventbridge"] is False
        assert summary["ses"] is False
        assert summary["elasticache"] is False

    def test_queue_specs(self):
        """Test SQS queue specs."""
        reqs = AWSRequirements(
            needs_sqs=True,
            sqs_queues=[
                SQSQueueSpec(name="orders"),
                SQSQueueSpec(name="notifications", visibility_timeout=600),
            ],
        )

        assert len(reqs.sqs_queues) == 2
        assert reqs.sqs_queues[0].name == "orders"
        assert reqs.sqs_queues[0].visibility_timeout == 30  # Default
        assert reqs.sqs_queues[1].visibility_timeout == 600

    def test_eventbridge_specs(self):
        """Test EventBridge specs."""
        reqs = AWSRequirements(
            needs_eventbridge=True,
            eventbridge_buses=[
                EventBridgeBusSpec(name="domain-events"),
            ],
            eventbridge_rules=[
                EventBridgeRuleSpec(
                    name="daily-report",
                    bus_name="default",
                    schedule_expression="cron(0 8 * * ? *)",
                ),
            ],
        )

        assert len(reqs.eventbridge_buses) == 1
        assert len(reqs.eventbridge_rules) == 1
        assert reqs.eventbridge_rules[0].schedule_expression == "cron(0 8 * * ? *)"


class TestSQSQueueSpec:
    """Tests for SQSQueueSpec."""

    def test_defaults(self):
        """Test default queue spec values."""
        spec = SQSQueueSpec(name="test-queue")

        assert spec.name == "test-queue"
        assert spec.visibility_timeout == 30
        assert spec.max_receive_count == 3
        assert spec.dead_letter_queue is True
        assert spec.fifo is False

    def test_custom_values(self):
        """Test custom queue spec values."""
        spec = SQSQueueSpec(
            name="orders",
            visibility_timeout=600,
            max_receive_count=5,
            fifo=True,
        )

        assert spec.visibility_timeout == 600
        assert spec.max_receive_count == 5
        assert spec.fifo is True


class TestEventBridgeBusSpec:
    """Tests for EventBridgeBusSpec."""

    def test_defaults(self):
        """Test default bus spec values."""
        spec = EventBridgeBusSpec(name="events")

        assert spec.name == "events"
        assert spec.description is None

    def test_with_description(self):
        """Test bus spec with description."""
        spec = EventBridgeBusSpec(
            name="domain-events",
            description="Domain event bus for the application",
        )

        assert spec.description == "Domain event bus for the application"


class TestEventBridgeRuleSpec:
    """Tests for EventBridgeRuleSpec."""

    def test_schedule_rule(self):
        """Test scheduled rule spec."""
        spec = EventBridgeRuleSpec(
            name="daily-cleanup",
            bus_name="default",
            schedule_expression="cron(0 0 * * ? *)",
            description="Daily cleanup job",
        )

        assert spec.name == "daily-cleanup"
        assert spec.bus_name == "default"
        assert spec.schedule_expression == "cron(0 0 * * ? *)"
        assert spec.event_pattern is None

    def test_event_pattern_rule(self):
        """Test event pattern rule spec."""
        spec = EventBridgeRuleSpec(
            name="order-created",
            bus_name="orders",
            event_pattern={"source": ["order-service"], "detail-type": ["OrderCreated"]},
        )

        assert spec.name == "order-created"
        assert spec.event_pattern is not None
        assert spec.schedule_expression is None


class TestS3BucketSpec:
    """Tests for S3BucketSpec."""

    def test_defaults(self):
        """Test default bucket spec values."""
        spec = S3BucketSpec(name="assets")

        assert spec.name == "assets"
        assert spec.versioned is True
        assert spec.public_access_blocked is True

    def test_custom_values(self):
        """Test custom bucket spec values."""
        spec = S3BucketSpec(
            name="uploads",
            versioned=False,
            lifecycle_expiration_days=30,
        )

        assert spec.versioned is False
        assert spec.lifecycle_expiration_days == 30


class TestAnalyzeAWSRequirements:
    """Tests for analyze_aws_requirements function."""

    def test_minimal_spec(self):
        """Test analysis of minimal spec."""
        spec = create_mock_spec()
        infra_reqs = create_mock_infra_reqs()
        config = DeploymentConfig()

        aws_reqs = analyze_aws_requirements(spec, infra_reqs, config)

        # Always needed
        assert aws_reqs.needs_vpc is True
        assert aws_reqs.needs_ecs is True
        assert aws_reqs.needs_ecr is True

        # Database needed by default
        assert aws_reqs.needs_rds is True

    def test_database_requirement(self):
        """Test database requirement mapping."""
        spec = create_mock_spec()
        infra_reqs = create_mock_infra_reqs(needs_database=True)
        config = DeploymentConfig()

        aws_reqs = analyze_aws_requirements(spec, infra_reqs, config)

        assert aws_reqs.needs_rds is True

    def test_storage_requirement(self):
        """Test storage requirement mapping."""
        spec = create_mock_spec()
        infra_reqs = create_mock_infra_reqs(needs_storage=True)
        config = DeploymentConfig()

        aws_reqs = analyze_aws_requirements(spec, infra_reqs, config)

        assert aws_reqs.needs_s3 is True
        assert len(aws_reqs.s3_buckets) == 1
        assert aws_reqs.s3_buckets[0].name == "assets"

    def test_queue_channels(self):
        """Test queue channel mapping to SQS."""
        from dazzle.core.ir.messaging import ChannelKind

        channel = MagicMock()
        channel.name = "orders"
        channel.kind = ChannelKind.QUEUE
        channel.config = MagicMock()
        channel.config.options = {}

        spec = create_mock_spec(channels=[channel])
        infra_reqs = create_mock_infra_reqs(needs_queues=True)
        config = DeploymentConfig()

        aws_reqs = analyze_aws_requirements(spec, infra_reqs, config)

        assert aws_reqs.needs_sqs is True
        assert len(aws_reqs.sqs_queues) == 1
        assert aws_reqs.sqs_queues[0].name == "orders"

    def test_stream_channels(self):
        """Test stream channel mapping to EventBridge."""
        from dazzle.core.ir.messaging import ChannelKind

        channel = MagicMock()
        channel.name = "domain-events"
        channel.kind = ChannelKind.STREAM
        channel.title = "Domain Events"

        spec = create_mock_spec(channels=[channel])
        infra_reqs = create_mock_infra_reqs(needs_events=True)
        config = DeploymentConfig()

        aws_reqs = analyze_aws_requirements(spec, infra_reqs, config)

        assert aws_reqs.needs_eventbridge is True
        assert len(aws_reqs.eventbridge_buses) == 1
        assert aws_reqs.eventbridge_buses[0].name == "domain-events"

    def test_email_channels(self):
        """Test email channel mapping to SES."""
        from dazzle.core.ir.messaging import ChannelKind

        channel = MagicMock()
        channel.name = "notifications"
        channel.kind = ChannelKind.EMAIL
        channel.send_operations = []

        spec = create_mock_spec(channels=[channel])
        infra_reqs = create_mock_infra_reqs(needs_email=True)
        config = DeploymentConfig()

        aws_reqs = analyze_aws_requirements(spec, infra_reqs, config)

        assert aws_reqs.needs_ses is True

    def test_cache_requirement(self):
        """Test cache requirement mapping."""
        spec = create_mock_spec()
        infra_reqs = create_mock_infra_reqs(needs_cache=True)
        config = DeploymentConfig()

        aws_reqs = analyze_aws_requirements(spec, infra_reqs, config)

        assert aws_reqs.needs_elasticache is True

    def test_scheduled_processes(self):
        """Test scheduled process mapping to EventBridge rules."""
        from dazzle.core.ir.process import ProcessTriggerKind

        trigger = MagicMock()
        trigger.kind = ProcessTriggerKind.SCHEDULE_CRON
        trigger.cron = "0 8 * * ?"

        process = MagicMock()
        process.name = "daily-report"
        process.trigger = trigger

        spec = create_mock_spec(processes=[process])
        infra_reqs = create_mock_infra_reqs()
        config = DeploymentConfig()

        aws_reqs = analyze_aws_requirements(spec, infra_reqs, config)

        assert aws_reqs.needs_eventbridge is True
        assert len(aws_reqs.eventbridge_rules) == 1
        assert aws_reqs.eventbridge_rules[0].name == "daily-report-schedule"
        assert "cron(0 8 * * ?)" in aws_reqs.eventbridge_rules[0].schedule_expression

    def test_multiple_channels(self):
        """Test multiple channel types."""
        from dazzle.core.ir.messaging import ChannelKind

        queue_channel = MagicMock()
        queue_channel.name = "orders"
        queue_channel.kind = ChannelKind.QUEUE
        queue_channel.config = MagicMock()
        queue_channel.config.options = {}

        stream_channel = MagicMock()
        stream_channel.name = "events"
        stream_channel.kind = ChannelKind.STREAM
        stream_channel.title = "Events"

        email_channel = MagicMock()
        email_channel.name = "mail"
        email_channel.kind = ChannelKind.EMAIL
        email_channel.send_operations = []

        spec = create_mock_spec(channels=[queue_channel, stream_channel, email_channel])
        infra_reqs = create_mock_infra_reqs(needs_queues=True, needs_events=True, needs_email=True)
        config = DeploymentConfig()

        aws_reqs = analyze_aws_requirements(spec, infra_reqs, config)

        assert aws_reqs.needs_sqs is True
        assert aws_reqs.needs_eventbridge is True
        assert aws_reqs.needs_ses is True
