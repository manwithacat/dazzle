"""
AWS infrastructure requirements analyzer.

Maps AppSpec IR to AWS-specific service requirements,
building on the generic InfraRequirements from infra_analyzer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle.core import ir
    from dazzle.core.infra_analyzer import InfraRequirements

    from .config import DeploymentConfig


# =============================================================================
# AWS Service Specifications
# =============================================================================


@dataclass
class SQSQueueSpec:
    """Specification for an SQS queue."""

    name: str
    visibility_timeout: int = 30
    dead_letter_queue: bool = True
    max_receive_count: int = 3
    fifo: bool = False
    content_based_deduplication: bool = False
    delay_seconds: int = 0


@dataclass
class EventBridgeBusSpec:
    """Specification for an EventBridge event bus."""

    name: str
    description: str | None = None


@dataclass
class EventBridgeRuleSpec:
    """Specification for an EventBridge rule."""

    name: str
    bus_name: str
    event_pattern: dict[str, list[str]] | None = None
    schedule_expression: str | None = None
    description: str | None = None


@dataclass
class S3BucketSpec:
    """Specification for an S3 bucket."""

    name: str
    versioned: bool = True
    lifecycle_expiration_days: int | None = None
    cors_enabled: bool = True
    public_access_blocked: bool = True


@dataclass
class SESConfigSpec:
    """Specification for SES email configuration."""

    identity_domain: str | None = None
    send_from_address: str | None = None
    templates: list[str] = field(default_factory=list)


@dataclass
class IAMPolicySpec:
    """Specification for an IAM policy."""

    name: str
    statements: list[dict] = field(default_factory=list)
    description: str | None = None


# =============================================================================
# AWS Requirements
# =============================================================================


@dataclass
class AWSRequirements:
    """AWS-specific infrastructure requirements."""

    # Network
    needs_vpc: bool = True

    # Compute
    needs_ecs: bool = True
    needs_ecr: bool = True
    container_count: int = 1

    # Database
    needs_rds: bool = False
    rds_tables: list[str] = field(default_factory=list)
    rds_estimated_rows: str = "small"  # small (<10k), medium (<100k), large (>100k)

    # Storage
    needs_s3: bool = False
    s3_buckets: list[S3BucketSpec] = field(default_factory=list)

    # Messaging
    needs_sqs: bool = False
    needs_eventbridge: bool = False
    needs_ses: bool = False
    sqs_queues: list[SQSQueueSpec] = field(default_factory=list)
    eventbridge_buses: list[EventBridgeBusSpec] = field(default_factory=list)
    eventbridge_rules: list[EventBridgeRuleSpec] = field(default_factory=list)
    ses_config: SESConfigSpec | None = None

    # Caching
    needs_elasticache: bool = False

    # Secrets
    secrets: list[str] = field(default_factory=list)

    # IAM
    iam_policies: list[IAMPolicySpec] = field(default_factory=list)

    # Tenancy
    tenant_isolation_mode: str = "shared"  # shared, schema, database

    def summary(self) -> dict[str, bool | int]:
        """Get a summary of requirements."""
        return {
            "vpc": self.needs_vpc,
            "ecs": self.needs_ecs,
            "ecr": self.needs_ecr,
            "rds": self.needs_rds,
            "s3": self.needs_s3,
            "sqs": self.needs_sqs,
            "eventbridge": self.needs_eventbridge,
            "ses": self.needs_ses,
            "elasticache": self.needs_elasticache,
            "tables": len(self.rds_tables),
            "queues": len(self.sqs_queues),
            "buckets": len(self.s3_buckets),
        }


# =============================================================================
# Analyzer Function
# =============================================================================


def analyze_aws_requirements(
    appspec: ir.AppSpec,
    infra_reqs: InfraRequirements,
    config: DeploymentConfig,
) -> AWSRequirements:
    """
    Map AppSpec to AWS-specific requirements.

    Args:
        appspec: The application specification
        infra_reqs: Generic infrastructure requirements
        config: Deployment configuration

    Returns:
        AWSRequirements with AWS service specifications
    """
    reqs = AWSRequirements()

    # -------------------------------------------------------------------------
    # Database (RDS)
    # -------------------------------------------------------------------------
    if infra_reqs.needs_database:
        reqs.needs_rds = True
        reqs.rds_tables = infra_reqs.entity_names or []

        # Estimate database size based on entity count
        entity_count = len(reqs.rds_tables)
        if entity_count > 20:
            reqs.rds_estimated_rows = "large"
        elif entity_count > 10:
            reqs.rds_estimated_rows = "medium"
        else:
            reqs.rds_estimated_rows = "small"

    # -------------------------------------------------------------------------
    # Storage (S3)
    # -------------------------------------------------------------------------
    if infra_reqs.needs_storage:
        reqs.needs_s3 = True
        reqs.s3_buckets.append(
            S3BucketSpec(
                name="assets",
                versioned=config.storage.versioned,
                lifecycle_expiration_days=config.storage.lifecycle_expiration_days,
            )
        )

    # -------------------------------------------------------------------------
    # Messaging Channels
    # -------------------------------------------------------------------------
    for channel in appspec.channels:
        _analyze_channel(channel, reqs, config)

    # -------------------------------------------------------------------------
    # Processes → EventBridge Rules
    # -------------------------------------------------------------------------
    for process in appspec.processes:
        _analyze_process(process, reqs)

    # -------------------------------------------------------------------------
    # Caching
    # -------------------------------------------------------------------------
    if infra_reqs.needs_cache:
        reqs.needs_elasticache = True

    # -------------------------------------------------------------------------
    # Tenancy
    # -------------------------------------------------------------------------
    if appspec.tenancy:
        reqs.tenant_isolation_mode = appspec.tenancy.isolation.mode.value

    # -------------------------------------------------------------------------
    # Secrets
    # -------------------------------------------------------------------------
    reqs.secrets = _infer_secrets(appspec, infra_reqs)

    return reqs


def _analyze_channel(
    channel: ir.messaging.ChannelSpec,
    reqs: AWSRequirements,
    config: DeploymentConfig,
) -> None:
    """Analyze a messaging channel and update requirements."""
    from dazzle.core.ir.messaging import ChannelKind

    if channel.kind == ChannelKind.QUEUE:
        reqs.needs_sqs = True

        # Get config from channel
        visibility_timeout = config.messaging.queue_visibility_timeout
        max_receive = config.messaging.dead_letter_max_receives

        if channel.config.options:
            if "visibility_timeout" in channel.config.options:
                try:
                    visibility_timeout = int(channel.config.options["visibility_timeout"])
                except ValueError:
                    pass

        reqs.sqs_queues.append(
            SQSQueueSpec(
                name=channel.name,
                visibility_timeout=visibility_timeout,
                dead_letter_queue=True,
                max_receive_count=max_receive,
            )
        )

    elif channel.kind == ChannelKind.STREAM:
        # Use EventBridge for streams (simpler than MSK)
        reqs.needs_eventbridge = True
        reqs.eventbridge_buses.append(
            EventBridgeBusSpec(
                name=channel.name,
                description=channel.title,
            )
        )

    elif channel.kind == ChannelKind.EMAIL:
        reqs.needs_ses = True
        if reqs.ses_config is None:
            reqs.ses_config = SESConfigSpec()

        # Add templates from send operations
        for send_op in channel.send_operations:
            if send_op.message_name not in reqs.ses_config.templates:
                reqs.ses_config.templates.append(send_op.message_name)


def _analyze_process(process: ir.process.ProcessSpec, reqs: AWSRequirements) -> None:
    """Analyze a process and create EventBridge rules for scheduled triggers."""
    from dazzle.core.ir.process import ProcessTriggerKind

    if process.trigger:
        trigger = process.trigger

        # Scheduled processes → EventBridge scheduled rules
        if trigger.kind == ProcessTriggerKind.SCHEDULE_CRON:
            reqs.needs_eventbridge = True
            reqs.eventbridge_rules.append(
                EventBridgeRuleSpec(
                    name=f"{process.name}-schedule",
                    bus_name="default",
                    schedule_expression=f"cron({trigger.cron_expression})",
                    description=f"Scheduled trigger for {process.name}",
                )
            )

        elif trigger.kind == ProcessTriggerKind.SCHEDULE_INTERVAL:
            reqs.needs_eventbridge = True
            minutes = (trigger.interval_seconds or 60) // 60
            reqs.eventbridge_rules.append(
                EventBridgeRuleSpec(
                    name=f"{process.name}-interval",
                    bus_name="default",
                    schedule_expression=f"rate({minutes} minutes)",
                    description=f"Interval trigger for {process.name}",
                )
            )


def _infer_secrets(appspec: ir.AppSpec, infra_reqs: InfraRequirements) -> list[str]:
    """Infer secrets that need to be stored in Secrets Manager."""
    secrets = []

    # Database credentials
    if infra_reqs.needs_database:
        secrets.append("database-credentials")

    # External API credentials
    for api in appspec.apis:
        secrets.append(f"api-{api.name}-credentials")

    # LLM API keys
    if appspec.llm_config or appspec.llm_models:
        secrets.append("llm-api-key")

    return secrets


__all__ = [
    "AWSRequirements",
    "SQSQueueSpec",
    "EventBridgeBusSpec",
    "EventBridgeRuleSpec",
    "S3BucketSpec",
    "SESConfigSpec",
    "IAMPolicySpec",
    "analyze_aws_requirements",
]
