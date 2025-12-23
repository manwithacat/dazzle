"""
Network stack generator.

Generates VPC, subnets, and security groups.
"""

from __future__ import annotations

from ..generator import CDKGeneratorResult, StackGenerator


class NetworkStackGenerator(StackGenerator):
    """Generate VPC and networking resources."""

    @property
    def stack_name(self) -> str:
        return "Network"

    def _generate_stack_code(self) -> str:
        """Generate the network stack Python code."""
        app_name = self._get_app_name()
        env = self.config.environment
        azs = self.config.network.availability_zones
        nat_gateways = self.config.network.nat_gateways
        vpc_cidr = self.config.network.vpc_cidr

        return f'''{self._generate_header()}
from aws_cdk import aws_ec2 as ec2


class NetworkStack(Stack):
    """
    VPC and networking resources for {self.spec.name}.

    Creates:
    - VPC with public, private, and isolated subnets
    - NAT Gateway(s) for private subnet internet access
    - Security groups for ALB, ECS, and RDS
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # =====================================================================
        # VPC
        # =====================================================================

        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            vpc_name="{app_name}-{env}",
            max_azs={azs},
            nat_gateways={nat_gateways},
            ip_addresses=ec2.IpAddresses.cidr("{vpc_cidr}"),
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        # =====================================================================
        # Security Groups
        # =====================================================================

        # ALB Security Group - allows inbound HTTPS from internet
        self.alb_security_group = ec2.SecurityGroup(
            self,
            "AlbSecurityGroup",
            vpc=self.vpc,
            security_group_name="{app_name}-{env}-alb",
            description="Security group for Application Load Balancer",
            allow_all_outbound=True,
        )
        self.alb_security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(443),
            "Allow HTTPS from internet",
        )
        self.alb_security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(80),
            "Allow HTTP from internet (redirect to HTTPS)",
        )

        # ECS Security Group - allows traffic from ALB only
        self.ecs_security_group = ec2.SecurityGroup(
            self,
            "EcsSecurityGroup",
            vpc=self.vpc,
            security_group_name="{app_name}-{env}-ecs",
            description="Security group for ECS Fargate tasks",
            allow_all_outbound=True,
        )
        self.ecs_security_group.add_ingress_rule(
            self.alb_security_group,
            ec2.Port.tcp(8000),
            "Allow traffic from ALB",
        )

        # RDS Security Group - allows traffic from ECS only
        self.rds_security_group = ec2.SecurityGroup(
            self,
            "RdsSecurityGroup",
            vpc=self.vpc,
            security_group_name="{app_name}-{env}-rds",
            description="Security group for RDS database",
            allow_all_outbound=False,
        )
        self.rds_security_group.add_ingress_rule(
            self.ecs_security_group,
            ec2.Port.tcp(5432),
            "Allow PostgreSQL from ECS",
        )

        # =====================================================================
        # Outputs
        # =====================================================================

        CfnOutput(
            self,
            "VpcId",
            value=self.vpc.vpc_id,
            description="VPC ID",
            export_name=f"{app_name}-{env}-vpc-id",
        )

        CfnOutput(
            self,
            "VpcCidr",
            value=self.vpc.vpc_cidr_block,
            description="VPC CIDR block",
        )
'''

    def generate(self) -> CDKGeneratorResult:
        """Generate the network stack and record VPC artifact."""
        result = super().generate()

        # Add artifact for other stacks to reference
        if result.success:
            result.add_artifact(
                "network_stack",
                {
                    "vpc_ref": "network_stack.vpc",
                    "alb_sg_ref": "network_stack.alb_security_group",
                    "ecs_sg_ref": "network_stack.ecs_security_group",
                    "rds_sg_ref": "network_stack.rds_security_group",
                },
            )

        return result
