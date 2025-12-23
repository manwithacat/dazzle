"""
Deployment configuration models for Dazzle Deploy.

Configuration is loaded from dazzle.toml [deploy] section.
"""

from __future__ import annotations

import tomllib
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class AWSRegion(str, Enum):
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


class ComputeSize(str, Enum):
    """ECS Fargate task sizes."""

    SMALL = "small"  # 0.25 vCPU, 512MB
    MEDIUM = "medium"  # 0.5 vCPU, 1GB
    LARGE = "large"  # 1 vCPU, 2GB
    XLARGE = "xlarge"  # 2 vCPU, 4GB


class DatabaseSize(str, Enum):
    """RDS instance sizes."""

    MICRO = "db.t3.micro"
    SMALL = "db.t3.small"
    MEDIUM = "db.t3.medium"
    LARGE = "db.t3.large"
    SERVERLESS = "serverless"  # Aurora Serverless v2


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
        "output",
    ]

    for section in nested_sections:
        if section in data:
            config_data[section] = data[section]

    return DeploymentConfig.model_validate(config_data)
