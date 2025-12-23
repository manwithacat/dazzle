"""
Compute stack generator.

Generates ECS Fargate cluster, ECR repository, and ALB.
"""

from __future__ import annotations

from ..generator import CDKGeneratorResult, StackGenerator


class ComputeStackGenerator(StackGenerator):
    """Generate ECS Fargate and ALB resources."""

    @property
    def stack_name(self) -> str:
        return "Compute"

    def _generate_stack_code(self) -> str:
        """Generate the compute stack Python code."""
        app_name = self._get_app_name()
        env = self.config.environment
        cpu = self.config.compute.cpu
        memory = self.config.compute.memory
        min_capacity = self.config.compute.min_capacity
        max_capacity = self.config.compute.max_capacity
        health_check_path = self.config.compute.health_check_path
        container_port = self.config.compute.container_port
        use_spot = self.config.compute.use_spot

        # Build capacity provider strategy
        if use_spot:
            capacity_strategy = """
            capacity_provider_strategies=[
                ecs.CapacityProviderStrategy(
                    capacity_provider="FARGATE_SPOT",
                    weight=2,
                ),
                ecs.CapacityProviderStrategy(
                    capacity_provider="FARGATE",
                    weight=1,
                ),
            ],"""
        else:
            capacity_strategy = ""

        # Build environment variables
        env_vars = self._generate_environment_vars()

        # Build secrets
        secrets_code = self._generate_secrets_code()

        return f'''{self._generate_header()}
from aws_cdk import (
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_ecr as ecr,
    aws_elasticloadbalancingv2 as elbv2,
    aws_logs as logs,
)


class ComputeStack(Stack):
    """
    Compute layer resources for {self.spec.name}.

    Creates:
    - ECR repository for container images
    - ECS Fargate cluster with container insights
    - Application Load Balancer with HTTPS
    - Auto-scaling based on CPU utilization
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        network_stack,
        data_stack=None,
        messaging_stack=None,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        self.network_stack = network_stack
        self.data_stack = data_stack
        self.messaging_stack = messaging_stack

        # =====================================================================
        # ECR Repository
        # =====================================================================

        self.repository = ecr.Repository(
            self,
            "Repository",
            repository_name="{app_name}",
            removal_policy=RemovalPolicy.RETAIN,
            image_scan_on_push=True,
            lifecycle_rules=[
                ecr.LifecycleRule(
                    description="Keep last 10 images",
                    max_image_count=10,
                    rule_priority=1,
                ),
            ],
        )

        # =====================================================================
        # ECS Cluster
        # =====================================================================

        self.cluster = ecs.Cluster(
            self,
            "Cluster",
            cluster_name="{app_name}-{env}",
            vpc=network_stack.vpc,
            container_insights={"True" if self.config.observability.enable_container_insights else "False"},
            enable_fargate_capacity_providers=True,
        )

        # =====================================================================
        # CloudWatch Log Group
        # =====================================================================

        self.log_group = logs.LogGroup(
            self,
            "LogGroup",
            log_group_name="/ecs/{app_name}-{env}",
            retention=logs.RetentionDays.{"ONE_MONTH" if self.config.observability.log_retention_days == 30 else "TWO_WEEKS"},
            removal_policy=RemovalPolicy.DESTROY,
        )

        # =====================================================================
        # ECS Fargate Service with ALB
        # =====================================================================

        # Build environment variables
        environment = {{{env_vars}
        }}

        # Build secrets from Secrets Manager
        secrets = {{{secrets_code}
        }}

        self.service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "Service",
            service_name="{app_name}-{env}",
            cluster=self.cluster,
            cpu={cpu},
            memory_limit_mib={memory},
            desired_count={min_capacity},{capacity_strategy}
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_ecr_repository(self.repository, "latest"),
                container_port={container_port},
                environment=environment,
                secrets=secrets,
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="{app_name}",
                    log_group=self.log_group,
                ),
            ),
            public_load_balancer=True,
            assign_public_ip=False,
            task_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
            ),
            security_groups=[network_stack.ecs_security_group],
            circuit_breaker=ecs.DeploymentCircuitBreaker(
                rollback=True,
            ),
        )

        # =====================================================================
        # Health Check Configuration
        # =====================================================================

        self.service.target_group.configure_health_check(
            path="{health_check_path}",
            interval=Duration.seconds(30),
            timeout=Duration.seconds(5),
            healthy_threshold_count=2,
            unhealthy_threshold_count=3,
            healthy_http_codes="200",
        )

        # =====================================================================
        # Auto-scaling
        # =====================================================================

        scaling = self.service.service.auto_scale_task_count(
            min_capacity={min_capacity},
            max_capacity={max_capacity},
        )

        # Scale on CPU utilization
        scaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=70,
            scale_in_cooldown=Duration.seconds(60),
            scale_out_cooldown=Duration.seconds(60),
        )

        # Scale on memory utilization
        scaling.scale_on_memory_utilization(
            "MemoryScaling",
            target_utilization_percent=80,
            scale_in_cooldown=Duration.seconds(60),
            scale_out_cooldown=Duration.seconds(60),
        )

        # =====================================================================
        # Outputs
        # =====================================================================

        CfnOutput(
            self,
            "ServiceUrl",
            value=f"http://{{self.service.load_balancer.load_balancer_dns_name}}",
            description="Application Load Balancer URL",
            export_name="{app_name}-{env}-url",
        )

        CfnOutput(
            self,
            "RepositoryUri",
            value=self.repository.repository_uri,
            description="ECR repository URI for pushing images",
            export_name="{app_name}-{env}-ecr-uri",
        )

        CfnOutput(
            self,
            "ClusterName",
            value=self.cluster.cluster_name,
            description="ECS cluster name",
            export_name="{app_name}-{env}-cluster",
        )

        CfnOutput(
            self,
            "ServiceName",
            value=self.service.service.service_name,
            description="ECS service name",
        )
'''

    def _generate_environment_vars(self) -> str:
        """Generate environment variable mappings."""
        app_name = self._get_app_name()
        env = self.config.environment

        vars_list = [
            f'"APP_NAME": "{app_name}"',
            f'"APP_ENV": "{env}"',
            '"APP_PORT": "8000"',
        ]

        # Add S3 bucket if needed
        if self.aws_reqs.needs_s3:
            vars_list.append(
                '"ASSETS_BUCKET": self.data_stack.assets_bucket.bucket_name if self.data_stack else ""'
            )

        # Add SQS queue URLs if needed
        if self.aws_reqs.needs_sqs:
            for queue in self.aws_reqs.sqs_queues:
                var_name = f"{queue.name.upper()}_QUEUE_URL"
                vars_list.append(
                    f'"{var_name}": self.messaging_stack.queues.get("{queue.name}", {{}}).get("url", "") if self.messaging_stack else ""'
                )

        return "\n            ".join(vars_list)

    def _generate_secrets_code(self) -> str:
        """Generate secrets from Secrets Manager."""
        secrets = []

        # Database credentials
        if self.aws_reqs.needs_rds:
            secrets.append(
                '"DATABASE_URL": ecs.Secret.from_secrets_manager(self.data_stack.database_secret) if self.data_stack else None'
            )

        # Filter out None values
        if secrets:
            return "\n            " + ",\n            ".join(s for s in secrets)
        return ""

    def generate(self) -> CDKGeneratorResult:
        """Generate the compute stack and record artifacts."""
        result = super().generate()

        if result.success:
            result.add_artifact(
                "compute_stack",
                {
                    "service_ref": "compute_stack.service",
                    "cluster_ref": "compute_stack.cluster",
                    "repository_ref": "compute_stack.repository",
                    "log_group_ref": "compute_stack.log_group",
                },
            )

        return result
