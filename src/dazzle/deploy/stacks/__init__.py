"""
CDK stack generators.

Each module generates a specific CDK stack:
- network: VPC, subnets, security groups
- data: RDS, S3
- compute: ECS Fargate, ECR, ALB
- messaging: SQS, EventBridge
- dns: Route53, ACM
- observability: CloudWatch dashboards, alarms
- tigerbeetle: Self-hosted TigerBeetle ledger cluster
"""

from .compute import ComputeStackGenerator
from .data import DataStackGenerator
from .messaging import MessagingStackGenerator
from .network import NetworkStackGenerator
from .observability import ObservabilityStackGenerator
from .tigerbeetle import TigerBeetleStackGenerator

__all__ = [
    "NetworkStackGenerator",
    "DataStackGenerator",
    "ComputeStackGenerator",
    "MessagingStackGenerator",
    "ObservabilityStackGenerator",
    "TigerBeetleStackGenerator",
]
