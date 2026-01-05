"""
TigerBeetle stack generator.

Generates EC2-based TigerBeetle cluster with:
- Auto Scaling Group for node management
- EBS gp3 volumes with high IOPS for WAL
- Security groups for cluster communication
- IAM role with SSM access for node discovery
- SSM parameters for service discovery
- CloudWatch alarms for health monitoring

TigerBeetle has no managed AWS service, so we deploy self-hosted
EC2 instances. Node count must be odd (1, 3, 5) for Raft consensus.
"""

from __future__ import annotations

from ..generator import CDKGeneratorResult, StackGenerator


class TigerBeetleStackGenerator(StackGenerator):
    """Generate TigerBeetle cluster resources."""

    @property
    def stack_name(self) -> str:
        return "TigerBeetle"

    def should_generate(self) -> bool:
        """Only generate if TigerBeetle is needed."""
        return self.aws_reqs.needs_tigerbeetle

    def _generate_stack_code(self) -> str:
        """Generate the TigerBeetle stack Python code."""
        app_name = self._get_app_name()
        env = self.config.environment

        # Get TigerBeetle configuration
        tb_config = self.config.tigerbeetle
        tb_spec = self.aws_reqs.tigerbeetle_spec

        # Use spec values if available, otherwise fall back to config
        node_count = tb_spec.node_count if tb_spec else tb_config.node_count
        instance_type = tb_config.instance_type
        volume_size = tb_config.volume_size_gb
        volume_iops = tb_config.volume_iops
        volume_throughput = tb_config.volume_throughput_mbps

        # Generate ledger info for documentation
        ledger_info = ""
        if tb_spec and tb_spec.ledger_names:
            ledger_info = f"Ledgers: {', '.join(tb_spec.ledger_names)}"

        return f'''{self._generate_header()}
from aws_cdk import (
    aws_ec2 as ec2,
    aws_autoscaling as autoscaling,
    aws_iam as iam,
    aws_ssm as ssm,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cloudwatch_actions,
    aws_sns as sns,
)


class TigerBeetleStack(Stack):
    """
    TigerBeetle ledger cluster for {self.spec.name}.

    Creates:
    - Auto Scaling Group with {node_count} EC2 instances
    - High-IOPS EBS gp3 volumes ({volume_size}GB, {volume_iops} IOPS)
    - Security groups for cluster communication (ports 3000, 3001)
    - SSM parameters for service discovery
    - CloudWatch alarms for health monitoring

    {ledger_info}

    TigerBeetle requires odd node count for Raft consensus.
    Production deployments should use 3+ nodes for HA.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        network_stack,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        self.network_stack = network_stack

        # =====================================================================
        # TigerBeetle Security Group
        # =====================================================================

        self.security_group = ec2.SecurityGroup(
            self,
            "SecurityGroup",
            vpc=network_stack.vpc,
            security_group_name="{app_name}-{env}-tigerbeetle",
            description="Security group for TigerBeetle cluster",
            allow_all_outbound=True,
        )

        # Allow cluster communication - client port
        self.security_group.add_ingress_rule(
            self.security_group,
            ec2.Port.tcp(3000),
            "TigerBeetle client port (cluster internal)",
        )

        # Allow cluster communication - replication port
        self.security_group.add_ingress_rule(
            self.security_group,
            ec2.Port.tcp(3001),
            "TigerBeetle replication port",
        )

        # Allow ECS to connect to TigerBeetle
        self.security_group.add_ingress_rule(
            network_stack.ecs_security_group,
            ec2.Port.tcp(3000),
            "Allow ECS services to connect to TigerBeetle",
        )

        # =====================================================================
        # IAM Role
        # =====================================================================

        self.instance_role = iam.Role(
            self,
            "InstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "CloudWatchAgentServerPolicy"
                ),
            ],
        )

        # Allow reading/writing SSM parameters for discovery
        self.instance_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ssm:GetParameter",
                    "ssm:GetParameters",
                    "ssm:GetParametersByPath",
                    "ssm:PutParameter",
                ],
                resources=[
                    f"arn:aws:ssm:*:*:parameter/{app_name}/{env}/tigerbeetle/*"
                ],
            )
        )

        # Allow EC2 describe for node discovery
        self.instance_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ec2:DescribeInstances",
                    "autoscaling:DescribeAutoScalingGroups",
                ],
                resources=["*"],
            )
        )

        # =====================================================================
        # Instance Profile
        # =====================================================================

        self.instance_profile = iam.CfnInstanceProfile(
            self,
            "InstanceProfile",
            instance_profile_name="{app_name}-{env}-tigerbeetle",
            roles=[self.instance_role.role_name],
        )

        # =====================================================================
        # Launch Template
        # =====================================================================

        # User data script for TigerBeetle setup
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "#!/bin/bash",
            "set -e",
            "",
            "# Install dependencies",
            "yum install -y unzip jq",
            "",
            "# Install TigerBeetle",
            "ARCH=$(uname -m)",
            "if [ \\"$ARCH\\" = \\"x86_64\\" ]; then",
            "    TB_ARCH=\\"x86_64\\"",
            "elif [ \\"$ARCH\\" = \\"aarch64\\" ]; then",
            "    TB_ARCH=\\"aarch64\\"",
            "fi",
            "curl -L https://github.com/tigerbeetle/tigerbeetle/releases/latest/download/tigerbeetle-$TB_ARCH-linux.zip -o /tmp/tb.zip",
            "unzip /tmp/tb.zip -d /usr/local/bin/",
            "chmod +x /usr/local/bin/tigerbeetle",
            "",
            "# Create data directory",
            "mkdir -p /data/tigerbeetle",
            "",
            "# Wait for EBS data volume",
            "while [ ! -b /dev/nvme1n1 ] && [ ! -b /dev/xvdb ]; do sleep 1; done",
            "DEVICE=$(test -b /dev/nvme1n1 && echo /dev/nvme1n1 || echo /dev/xvdb)",
            "",
            "# Format if needed and mount",
            "if ! blkid $DEVICE; then",
            "    mkfs.xfs $DEVICE",
            "fi",
            "mount $DEVICE /data/tigerbeetle || true",
            "echo \\"$DEVICE /data/tigerbeetle xfs defaults,nofail 0 2\\" >> /etc/fstab",
            "",
            "# Get instance metadata",
            'TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")',
            'INSTANCE_ID=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id)',
            'PRIVATE_IP=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/local-ipv4)',
            'REGION=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)',
            "",
            "# Register in SSM for discovery",
            "aws ssm put-parameter \\\\",
            "    --name \\"/{app_name}/{env}/tigerbeetle/nodes/$INSTANCE_ID\\" \\\\",
            "    --value \\"$PRIVATE_IP:3000\\" \\\\",
            "    --type String \\\\",
            "    --overwrite \\\\",
            "    --region $REGION",
            "",
            "# Wait for all nodes to register",
            "sleep 30",
            "",
            "# Get all node addresses for cluster formation",
            "ADDRESSES=$(aws ssm get-parameters-by-path \\\\",
            "    --path \\"/{app_name}/{env}/tigerbeetle/nodes\\" \\\\",
            "    --query \\"Parameters[*].Value\\" \\\\",
            "    --output text \\\\",
            "    --region $REGION | tr \\"\\\\t\\" \\",\\")",
            "",
            "# Determine replica index based on sorted IP order",
            "NODE_COUNT=$(echo $ADDRESSES | tr \\",\\" \\"\\\\n\\" | wc -l)",
            "REPLICA_INDEX=$(echo $ADDRESSES | tr \\",\\" \\"\\\\n\\" | sort | grep -n \\"$PRIVATE_IP\\" | cut -d: -f1)",
            "REPLICA_INDEX=$((REPLICA_INDEX - 1))",
            "",
            "# Format data file if not exists",
            "if [ ! -f /data/tigerbeetle/0_0.tigerbeetle ]; then",
            "    /usr/local/bin/tigerbeetle format \\\\",
            "        --cluster=0 \\\\",
            "        --replica=$REPLICA_INDEX \\\\",
            "        --replica-count={node_count} \\\\",
            "        /data/tigerbeetle/0_0.tigerbeetle",
            "fi",
            "",
            "# Create systemd service",
            "cat > /etc/systemd/system/tigerbeetle.service << EOF",
            "[Unit]",
            "Description=TigerBeetle Ledger",
            "After=network.target",
            "",
            "[Service]",
            "Type=simple",
            "ExecStart=/usr/local/bin/tigerbeetle start --addresses=$ADDRESSES /data/tigerbeetle/0_0.tigerbeetle",
            "Restart=always",
            "RestartSec=10",
            "User=root",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "EOF",
            "",
            "systemctl daemon-reload",
            "systemctl enable tigerbeetle",
            "systemctl start tigerbeetle",
        )

        self.launch_template = ec2.LaunchTemplate(
            self,
            "LaunchTemplate",
            launch_template_name="{app_name}-{env}-tigerbeetle",
            instance_type=ec2.InstanceType("{instance_type}"),
            machine_image=ec2.AmazonLinuxImage(
                generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2023,
            ),
            security_group=self.security_group,
            role=self.instance_role,
            user_data=user_data,
            block_devices=[
                # Root volume
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=20,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        encrypted=True,
                    ),
                ),
                # Data volume for TigerBeetle
                ec2.BlockDevice(
                    device_name="/dev/xvdb",
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size={volume_size},
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        iops={volume_iops},
                        throughput={volume_throughput},
                        encrypted=True,
                        delete_on_termination=False,  # Preserve data on instance termination
                    ),
                ),
            ],
        )

        # =====================================================================
        # Auto Scaling Group
        # =====================================================================

        self.asg = autoscaling.AutoScalingGroup(
            self,
            "AutoScalingGroup",
            auto_scaling_group_name="{app_name}-{env}-tigerbeetle",
            vpc=network_stack.vpc,
            launch_template=self.launch_template,
            min_capacity={node_count},
            max_capacity={node_count},
            desired_capacity={node_count},
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
            ),
            health_check=autoscaling.HealthCheck.ec2(
                grace=Duration.minutes(10),
            ),
            update_policy=autoscaling.UpdatePolicy.rolling_update(
                max_batch_size=1,
                min_instances_in_service={node_count - 1 if node_count > 1 else 0},
                pause_time=Duration.minutes(5),
            ),
            signals=autoscaling.Signals.wait_for_count(
                count={node_count},
                timeout=Duration.minutes(15),
            ),
        )

        # =====================================================================
        # SSM Parameters for Service Discovery
        # =====================================================================

        ssm.StringParameter(
            self,
            "ClusterIdParam",
            parameter_name="/{app_name}/{env}/tigerbeetle/cluster_id",
            string_value="0",
            description="TigerBeetle cluster ID",
        )

        ssm.StringParameter(
            self,
            "ReplicaCountParam",
            parameter_name="/{app_name}/{env}/tigerbeetle/replica_count",
            string_value="{node_count}",
            description="TigerBeetle replica count",
        )

        # =====================================================================
        # CloudWatch Alarms
        # =====================================================================

        # Create SNS topic for alerts
        self.alert_topic = sns.Topic(
            self,
            "AlertTopic",
            topic_name="{app_name}-{env}-tigerbeetle-alerts",
            display_name="TigerBeetle Cluster Alerts",
        )

        # CPU utilization alarm
        cloudwatch.Alarm(
            self,
            "CpuAlarm",
            alarm_name="{app_name}-{env}-tigerbeetle-cpu-high",
            metric=cloudwatch.Metric(
                namespace="AWS/EC2",
                metric_name="CPUUtilization",
                dimensions_map={{
                    "AutoScalingGroupName": self.asg.auto_scaling_group_name,
                }},
                statistic="Average",
                period=Duration.minutes(5),
            ),
            threshold=80,
            evaluation_periods=3,
            alarm_description="TigerBeetle CPU utilization high",
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        ).add_alarm_action(
            cloudwatch_actions.SnsAction(self.alert_topic)
        )

        # Instance health alarm
        cloudwatch.Alarm(
            self,
            "HealthAlarm",
            alarm_name="{app_name}-{env}-tigerbeetle-unhealthy",
            metric=cloudwatch.Metric(
                namespace="AWS/AutoScaling",
                metric_name="GroupInServiceInstances",
                dimensions_map={{
                    "AutoScalingGroupName": self.asg.auto_scaling_group_name,
                }},
                statistic="Average",
                period=Duration.minutes(1),
            ),
            threshold={node_count - 1 if node_count > 1 else 0},
            evaluation_periods=2,
            alarm_description="TigerBeetle cluster has unhealthy instances",
            comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_OR_EQUAL_TO_THRESHOLD,
        ).add_alarm_action(
            cloudwatch_actions.SnsAction(self.alert_topic)
        )

        # =====================================================================
        # Outputs
        # =====================================================================

        CfnOutput(
            self,
            "SecurityGroupId",
            value=self.security_group.security_group_id,
            description="TigerBeetle security group ID",
            export_name="{app_name}-{env}-tigerbeetle-sg",
        )

        CfnOutput(
            self,
            "AsgName",
            value=self.asg.auto_scaling_group_name,
            description="TigerBeetle Auto Scaling Group name",
            export_name="{app_name}-{env}-tigerbeetle-asg",
        )

        CfnOutput(
            self,
            "DiscoveryPath",
            value="/{app_name}/{env}/tigerbeetle/nodes",
            description="SSM path for TigerBeetle node discovery",
        )

        CfnOutput(
            self,
            "AlertTopicArn",
            value=self.alert_topic.topic_arn,
            description="SNS topic for TigerBeetle alerts",
        )
'''

    def generate(self) -> CDKGeneratorResult:
        """Generate the TigerBeetle stack and record artifacts."""
        result = super().generate()

        if result.success and self.should_generate():
            app_name = self._get_app_name()
            env = self.config.environment

            result.add_artifact(
                "tigerbeetle_stack",
                {
                    "security_group_ref": "tigerbeetle_stack.security_group",
                    "asg_ref": "tigerbeetle_stack.asg",
                    "discovery_path": f"/{app_name}/{env}/tigerbeetle/nodes",
                    "alert_topic_ref": "tigerbeetle_stack.alert_topic",
                },
            )

        return result
