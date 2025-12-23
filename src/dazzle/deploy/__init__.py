"""
Dazzle Deploy - AWS CDK Infrastructure Generator.

This package generates standalone AWS CDK (Python) code to deploy
Dazzle applications to AWS using the "boring stack":
- VPC, ALB, Security Groups
- ECS Fargate, ECR
- RDS Postgres / Aurora Serverless
- S3
- SQS, EventBridge
- CloudWatch

Usage:
    dazzle deploy generate    # Generate CDK code
    dazzle deploy plan        # Preview infrastructure
    dazzle deploy status      # Check configuration
    dazzle deploy preflight   # Pre-flight validation
"""

# Re-export preflight module for convenience
from . import preflight
from .analyzer import AWSRequirements, analyze_aws_requirements
from .config import DeploymentConfig, load_deployment_config
from .generator import CDKGenerator, CDKGeneratorResult
from .runner import DeploymentResult, DeploymentRunner

__all__ = [
    # Configuration
    "DeploymentConfig",
    "load_deployment_config",
    # Analysis
    "AWSRequirements",
    "analyze_aws_requirements",
    # Generation
    "CDKGenerator",
    "CDKGeneratorResult",
    # Orchestration
    "DeploymentRunner",
    "DeploymentResult",
    # Preflight (module)
    "preflight",
]
