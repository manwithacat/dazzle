"""
Deployment configuration models for Dazzle Deploy.

Configuration is loaded from dazzle.toml [deploy] section.
"""

from __future__ import annotations

import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class AWSRegion(StrEnum):
    """Supported AWS regions."""

    US_EAST_1 = "us-east-1"
    US_EAST_2 = "us-east-2"
    US_WEST_1 = "us-west-1"
    US_WEST_2 = "us-west-2"
    EU_WEST_1 = "eu-west-1"
    EU_WEST_2 = "eu-west-2"
    EU_CENTRAL_1 = "eu-central-1"
    AP_SOUTHEAST_1 = "ap-southeast-1"
    AP_SOUTHEAST_2 = "ap-southeast-2"
    AP_NORTHEAST_1 = "ap-northeast-1"


class ComputeSize(StrEnum):
    """ECS Fargate task sizes."""

    SMALL = "small"  # 0.25 vCPU, 512MB
    MEDIUM = "medium"  # 0.5 vCPU, 1GB
    LARGE = "large"  # 1 vCPU, 2GB
    XLARGE = "xlarge"  # 2 vCPU, 4GB


class DatabaseSize(StrEnum):
    """RDS instance sizes."""

    MICRO = "db.t3.micro"
    SMALL = "db.t3.small"
    MEDIUM = "db.t3.medium"
    LARGE = "db.t3.large"
    SERVERLESS = "serverless"  # Aurora Serverless v2


class TigerBeetleSize(StrEnum):
    """TigerBeetle instance sizes (EC2).

    TigerBeetle has no managed AWS service, so we deploy on EC2.
    Memory-optimized instances recommended for best performance.
    """

    SMALL = "t3.medium"  # Dev/test: 1 node, 4GB RAM
    MEDIUM = "r6i.large"  # Small prod: 3 nodes, 16GB RAM
    LARGE = "r6i.xlarge"  # Medium prod: 3 nodes, 32GB RAM
    XLARGE = "r6i.2xlarge"  # Large prod: 5 nodes, 64GB RAM


# =============================================================================
# Sub-configuration Models
# =============================================================================


class NetworkConfig(BaseModel):
    """VPC and networking configuration."""

    create_vpc: bool = True
    vpc_cidr: str = "10.0.0.0/16"
    availability_zones: int = Field(default=2, ge=1, le=3)
    nat_gateways: int = Field(default=1, ge=0, le=3)


class ComputeConfig(BaseModel):
    """ECS Fargate configuration."""

    size: ComputeSize = ComputeSize.SMALL
    min_capacity: int = Field(default=1, ge=0)
    max_capacity: int = Field(default=4, ge=1)
    use_spot: bool = True
    health_check_path: str = "/health"
    container_port: int = 8000

    @property
    def cpu(self) -> int:
        """Get Fargate CPU units."""
        return {
            ComputeSize.SMALL: 256,
            ComputeSize.MEDIUM: 512,
            ComputeSize.LARGE: 1024,
            ComputeSize.XLARGE: 2048,
        }[self.size]

    @property
    def memory(self) -> int:
        """Get Fargate memory in MiB."""
        return {
            ComputeSize.SMALL: 512,
            ComputeSize.MEDIUM: 1024,
            ComputeSize.LARGE: 2048,
            ComputeSize.XLARGE: 4096,
        }[self.size]


class DatabaseConfig(BaseModel):
    """RDS configuration."""

    size: DatabaseSize = DatabaseSize.SERVERLESS
    engine: str = "postgres"
    engine_version: str = "15"
    multi_az: bool = False
    backup_retention_days: int = Field(default=7, ge=1, le=35)
    deletion_protection: bool = False
    storage_encrypted: bool = True

    @property
    def is_serverless(self) -> bool:
        """Check if using Aurora Serverless."""
        return self.size == DatabaseSize.SERVERLESS


class StorageConfig(BaseModel):
    """S3 configuration."""

    versioned: bool = True
    lifecycle_expiration_days: int | None = None
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["*"])


class MessagingConfig(BaseModel):
    """SQS and EventBridge configuration."""

    queue_visibility_timeout: int = Field(default=30, ge=0, le=43200)
    dead_letter_max_receives: int = Field(default=3, ge=1, le=1000)
    message_retention_days: int = Field(default=4, ge=1, le=14)


class DNSConfig(BaseModel):
    """Route53 and TLS configuration."""

    domain_name: str | None = None
    hosted_zone_id: str | None = None
    create_certificate: bool = True
    redirect_http_to_https: bool = True

    @property
    def is_configured(self) -> bool:
        """Check if custom domain is configured."""
        return self.domain_name is not None and self.hosted_zone_id is not None


class ObservabilityConfig(BaseModel):
    """CloudWatch configuration."""

    create_dashboard: bool = True
    log_retention_days: int = Field(default=30, ge=1, le=3653)
    alarm_email: str | None = None
    enable_container_insights: bool = True
    enable_xray: bool = False


class TigerBeetleConfig(BaseModel):
    """TigerBeetle cluster configuration.

    TigerBeetle has no managed AWS service, so we deploy self-hosted
    EC2 instances with high-IOPS EBS volumes.

    Node count must be odd (1, 3, or 5) for Raft consensus.
    Production deployments require at least 3 nodes for HA.
    """

    enabled: bool = True
    size: TigerBeetleSize = TigerBeetleSize.MEDIUM
    node_count: int = Field(default=3, ge=1, le=5)
    volume_size_gb: int = Field(default=100, ge=50, le=1000)
    volume_iops: int = Field(default=10000, ge=3000, le=64000)
    volume_throughput_mbps: int = Field(default=500, ge=125, le=1000)
    backup_enabled: bool = True
    backup_retention_days: int = Field(default=7, ge=1, le=35)

    @property
    def instance_type(self) -> str:
        """Get the EC2 instance type."""
        return self.size.value

    def model_post_init(self, __context: Any) -> None:
        """Validate node count is odd for Raft consensus."""
        if self.node_count > 1 and self.node_count % 2 == 0:
            raise ValueError(
                f"TigerBeetle node_count must be odd for HA (1, 3, or 5), got {self.node_count}"
            )


class OutputConfig(BaseModel):
    """Output configuration."""

    directory: str = "infra"
    stack_name_prefix: str = ""

    def get_output_path(self, project_root: Path) -> Path:
        """Get the absolute output path."""
        return project_root / self.directory


# =============================================================================
# Main Configuration Model
# =============================================================================


class DeploymentConfig(BaseModel):
    """Complete deployment configuration."""

    enabled: bool = False
    provider: str = "aws"
    environment: str = "staging"
    region: AWSRegion = AWSRegion.US_EAST_1

    network: NetworkConfig = Field(default_factory=NetworkConfig)
    compute: ComputeConfig = Field(default_factory=ComputeConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    messaging: MessagingConfig = Field(default_factory=MessagingConfig)
    dns: DNSConfig = Field(default_factory=DNSConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    tigerbeetle: TigerBeetleConfig = Field(default_factory=TigerBeetleConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)

    def get_stack_name(self, stack_type: str) -> str:
        """Get the full stack name with prefix and environment."""
        prefix = self.output.stack_name_prefix
        if prefix:
            return f"{prefix}-{stack_type}-{self.environment}"
        return f"{stack_type}-{self.environment}"


# =============================================================================
# Configuration Loading
# =============================================================================


def load_deployment_config(toml_path: Path) -> DeploymentConfig:
    """
    Load deployment configuration from dazzle.toml.

    Args:
        toml_path: Path to dazzle.toml file

    Returns:
        DeploymentConfig with values from file or defaults
    """
    if not toml_path.exists():
        return DeploymentConfig()

    try:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return DeploymentConfig()

    deploy_section = data.get("deploy", {})
    if not deploy_section:
        return DeploymentConfig()

    return _parse_config(deploy_section)


def _parse_config(data: dict[str, Any]) -> DeploymentConfig:
    """Parse config dict into DeploymentConfig."""
    # Handle nested sections
    config_data: dict[str, Any] = {}

    # Top-level fields
    for field in ["enabled", "provider", "environment", "region"]:
        if field in data:
            config_data[field] = data[field]

    # Nested config sections
    nested_sections = [
        "network",
        "compute",
        "database",
        "storage",
        "messaging",
        "dns",
        "observability",
        "tigerbeetle",
        "output",
    ]

    for section in nested_sections:
        if section in data:
            config_data[section] = data[section]

    return DeploymentConfig.model_validate(config_data)
