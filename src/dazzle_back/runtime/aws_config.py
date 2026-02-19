"""
Centralized AWS configuration for Dazzle.

Single source of truth for AWS credentials, region, and session management.
Used by S3 storage, SES email, and any future AWS integrations.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cache
from typing import Any


@dataclass(frozen=True)
class AWSConfig:
    """AWS configuration from environment variables.

    Attributes:
        region: AWS region (from DAZZLE_AWS_REGION or AWS_DEFAULT_REGION)
        access_key_id: AWS access key ID (optional if using IAM roles)
        secret_access_key: AWS secret access key (optional if using IAM roles)
        endpoint_url: Custom endpoint for LocalStack/testing
    """

    region: str
    access_key_id: str | None = None
    secret_access_key: str | None = None
    endpoint_url: str | None = None

    def to_boto3_kwargs(self) -> dict[str, Any]:
        """Build kwargs dict suitable for boto3 client/session creation."""
        kwargs: dict[str, Any] = {"region_name": self.region}
        if self.access_key_id:
            kwargs["aws_access_key_id"] = self.access_key_id
        if self.secret_access_key:
            kwargs["aws_secret_access_key"] = self.secret_access_key
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        return kwargs


@cache
def get_aws_config() -> AWSConfig:
    """Load AWS configuration from environment variables.

    Environment variables (checked in order):
        - DAZZLE_AWS_REGION / AWS_DEFAULT_REGION / AWS_REGION → region
        - AWS_ACCESS_KEY_ID → access_key_id
        - AWS_SECRET_ACCESS_KEY → secret_access_key
        - DAZZLE_AWS_ENDPOINT_URL / AWS_ENDPOINT_URL → endpoint_url (for LocalStack)

    Returns:
        AWSConfig with validated settings.
    """
    region = (
        os.environ.get("DAZZLE_AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or os.environ.get("AWS_REGION")
        or "us-east-1"
    )

    return AWSConfig(
        region=region,
        access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        endpoint_url=os.environ.get("DAZZLE_AWS_ENDPOINT_URL")
        or os.environ.get("AWS_ENDPOINT_URL"),
    )


def get_boto3_session(config: AWSConfig | None = None) -> Any:
    """Create a boto3 Session with credentials from config.

    Args:
        config: AWS config (uses get_aws_config() if None)

    Returns:
        boto3.Session instance
    """
    try:
        import boto3
    except ImportError:
        raise ImportError(
            "boto3 is required for AWS services. Install with: pip install dazzle-dsl[aws]"
        )

    if config is None:
        config = get_aws_config()

    kwargs: dict[str, str] = {"region_name": config.region}
    if config.access_key_id:
        kwargs["aws_access_key_id"] = config.access_key_id
    if config.secret_access_key:
        kwargs["aws_secret_access_key"] = config.secret_access_key

    return boto3.Session(**kwargs)


def get_aioboto3_session(config: AWSConfig | None = None) -> Any:
    """Create an aioboto3 Session with credentials from config.

    Args:
        config: AWS config (uses get_aws_config() if None)

    Returns:
        aioboto3.Session instance
    """
    try:
        import aioboto3
    except ImportError:
        raise ImportError(
            "aioboto3 is required for async AWS services. Install with: pip install dazzle-dsl[aws]"
        )

    if config is None:
        config = get_aws_config()

    kwargs: dict[str, str] = {"region_name": config.region}
    if config.access_key_id:
        kwargs["aws_access_key_id"] = config.access_key_id
    if config.secret_access_key:
        kwargs["aws_secret_access_key"] = config.secret_access_key

    return aioboto3.Session(**kwargs)
