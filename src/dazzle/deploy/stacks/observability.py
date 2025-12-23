"""
Observability stack generator.

Generates CloudWatch dashboards and alarms.
"""

from __future__ import annotations

from ..generator import CDKGeneratorResult, StackGenerator


class ObservabilityStackGenerator(StackGenerator):
    """Generate CloudWatch dashboards and alarms."""

    @property
    def stack_name(self) -> str:
        return "Observability"

    def should_generate(self) -> bool:
        """Only generate if observability is enabled."""
        return self.config.observability.create_dashboard

    def _generate_stack_code(self) -> str:
        """Generate the observability stack Python code."""
        app_name = self._get_app_name()
        env = self.config.environment
        alarm_email = self.config.observability.alarm_email

        # SNS imports if alarm email is configured
        sns_imports = ""
        sns_topic_code = ""
        if alarm_email:
            sns_imports = """from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as sns_subs
from aws_cdk import aws_cloudwatch_actions as cw_actions"""
            sns_topic_code = f'''
        # Alarm notification topic
        self.alarm_topic = sns.Topic(
            self,
            "AlarmTopic",
            topic_name="{app_name}-{env}-alarms",
            display_name="{self.spec.name} Alarms",
        )
        self.alarm_topic.add_subscription(
            sns_subs.EmailSubscription("{alarm_email}")
        )
'''

        # Generate dashboard widgets
        dashboard_widgets = self._generate_dashboard_widgets()

        # Generate alarms
        alarms_code = self._generate_alarms_code()

        return f'''{self._generate_header()}
from aws_cdk import (
    aws_cloudwatch as cloudwatch,
)
{sns_imports}


class ObservabilityStack(Stack):
    """
    Observability resources for {self.spec.name}.

    Creates:
    - CloudWatch dashboard with ECS, RDS, and SQS metrics
    - Alarms for critical metrics
    {"- SNS topic for alarm notifications" if alarm_email else ""}
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        compute_stack,
        data_stack=None,
        messaging_stack=None,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        self.compute_stack = compute_stack
        self.data_stack = data_stack
        self.messaging_stack = messaging_stack
{sns_topic_code}
        # =====================================================================
        # CloudWatch Dashboard
        # =====================================================================

        self.dashboard = cloudwatch.Dashboard(
            self,
            "Dashboard",
            dashboard_name="{app_name}-{env}",
        )
{dashboard_widgets}
{alarms_code}
        # =====================================================================
        # Outputs
        # =====================================================================

        CfnOutput(
            self,
            "DashboardUrl",
            value=f"https://{self.config.region.value}.console.aws.amazon.com/cloudwatch/home?region={self.config.region.value}#dashboards:name={app_name}-{env}",
            description="CloudWatch dashboard URL",
        )
'''

    def _generate_dashboard_widgets(self) -> str:
        """Generate CloudWatch dashboard widgets."""
        env = self.config.environment
        widgets = []

        # Title widget
        widgets.append(f"""
        # Title row
        self.dashboard.add_widgets(
            cloudwatch.TextWidget(
                markdown="# {self.spec.name} - {env.title()} Environment",
                width=24,
                height=1,
            ),
        )
""")

        # ECS metrics row
        widgets.append("""
        # ECS Service Metrics
        self.dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="ECS CPU Utilization",
                left=[
                    compute_stack.service.service.metric_cpu_utilization(
                        period=Duration.minutes(1),
                    ),
                ],
                width=8,
                height=6,
            ),
            cloudwatch.GraphWidget(
                title="ECS Memory Utilization",
                left=[
                    compute_stack.service.service.metric_memory_utilization(
                        period=Duration.minutes(1),
                    ),
                ],
                width=8,
                height=6,
            ),
            cloudwatch.GraphWidget(
                title="Running Tasks",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/ECS",
                        metric_name="RunningTaskCount",
                        dimensions_map={
                            "ClusterName": compute_stack.cluster.cluster_name,
                            "ServiceName": compute_stack.service.service.service_name,
                        },
                        period=Duration.minutes(1),
                    ),
                ],
                width=8,
                height=6,
            ),
        )
""")

        # ALB metrics row
        widgets.append("""
        # ALB Metrics
        self.dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Request Count",
                left=[
                    compute_stack.service.load_balancer.metric_request_count(
                        period=Duration.minutes(1),
                    ),
                ],
                width=8,
                height=6,
            ),
            cloudwatch.GraphWidget(
                title="Target Response Time (ms)",
                left=[
                    compute_stack.service.target_group.metric_target_response_time(
                        period=Duration.minutes(1),
                    ),
                ],
                width=8,
                height=6,
            ),
            cloudwatch.GraphWidget(
                title="HTTP Errors",
                left=[
                    compute_stack.service.load_balancer.metric_http_code_target(
                        code=cloudwatch.HttpCodeTarget.TARGET_5XX_COUNT,
                        period=Duration.minutes(1),
                    ),
                    compute_stack.service.load_balancer.metric_http_code_target(
                        code=cloudwatch.HttpCodeTarget.TARGET_4XX_COUNT,
                        period=Duration.minutes(1),
                    ),
                ],
                width=8,
                height=6,
            ),
        )
""")

        # Database metrics if RDS is used
        if self.aws_reqs.needs_rds:
            widgets.append("""
        # Database Metrics (if data_stack exists)
        if data_stack:
            self.dashboard.add_widgets(
                cloudwatch.TextWidget(
                    markdown="## Database",
                    width=24,
                    height=1,
                ),
            )
            self.dashboard.add_widgets(
                cloudwatch.GraphWidget(
                    title="Database Connections",
                    left=[
                        cloudwatch.Metric(
                            namespace="AWS/RDS",
                            metric_name="DatabaseConnections",
                            dimensions_map={
                                "DBClusterIdentifier": data_stack.database.cluster_identifier
                                if hasattr(data_stack.database, "cluster_identifier")
                                else data_stack.database.instance_identifier,
                            },
                            period=Duration.minutes(1),
                        ),
                    ],
                    width=8,
                    height=6,
                ),
                cloudwatch.GraphWidget(
                    title="CPU Utilization",
                    left=[
                        cloudwatch.Metric(
                            namespace="AWS/RDS",
                            metric_name="CPUUtilization",
                            dimensions_map={
                                "DBClusterIdentifier": data_stack.database.cluster_identifier
                                if hasattr(data_stack.database, "cluster_identifier")
                                else data_stack.database.instance_identifier,
                            },
                            period=Duration.minutes(1),
                        ),
                    ],
                    width=8,
                    height=6,
                ),
                cloudwatch.GraphWidget(
                    title="Read/Write Latency",
                    left=[
                        cloudwatch.Metric(
                            namespace="AWS/RDS",
                            metric_name="ReadLatency",
                            dimensions_map={
                                "DBClusterIdentifier": data_stack.database.cluster_identifier
                                if hasattr(data_stack.database, "cluster_identifier")
                                else data_stack.database.instance_identifier,
                            },
                            period=Duration.minutes(1),
                            label="Read",
                        ),
                        cloudwatch.Metric(
                            namespace="AWS/RDS",
                            metric_name="WriteLatency",
                            dimensions_map={
                                "DBClusterIdentifier": data_stack.database.cluster_identifier
                                if hasattr(data_stack.database, "cluster_identifier")
                                else data_stack.database.instance_identifier,
                            },
                            period=Duration.minutes(1),
                            label="Write",
                        ),
                    ],
                    width=8,
                    height=6,
                ),
            )
""")

        # SQS metrics if queues are used
        if self.aws_reqs.needs_sqs:
            widgets.append("""
        # Queue Metrics (if messaging_stack exists)
        if messaging_stack and messaging_stack.queues:
            self.dashboard.add_widgets(
                cloudwatch.TextWidget(
                    markdown="## Message Queues",
                    width=24,
                    height=1,
                ),
            )

            # Create widgets for each queue
            for queue_name, queue_info in messaging_stack.queues.items():
                self.dashboard.add_widgets(
                    cloudwatch.GraphWidget(
                        title=f"{queue_name} - Messages",
                        left=[
                            cloudwatch.Metric(
                                namespace="AWS/SQS",
                                metric_name="ApproximateNumberOfMessagesVisible",
                                dimensions_map={"QueueName": queue_info["queue"].queue_name},
                                period=Duration.minutes(1),
                                label="Visible",
                            ),
                            cloudwatch.Metric(
                                namespace="AWS/SQS",
                                metric_name="ApproximateNumberOfMessagesNotVisible",
                                dimensions_map={"QueueName": queue_info["queue"].queue_name},
                                period=Duration.minutes(1),
                                label="In Flight",
                            ),
                        ],
                        width=12,
                        height=6,
                    ),
                    cloudwatch.GraphWidget(
                        title=f"{queue_name} - Age",
                        left=[
                            cloudwatch.Metric(
                                namespace="AWS/SQS",
                                metric_name="ApproximateAgeOfOldestMessage",
                                dimensions_map={"QueueName": queue_info["queue"].queue_name},
                                period=Duration.minutes(1),
                            ),
                        ],
                        width=12,
                        height=6,
                    ),
                )
""")

        return "\n".join(widgets)

    def _generate_alarms_code(self) -> str:
        """Generate CloudWatch alarms."""
        if not self.config.observability.alarm_email:
            return ""

        return """
        # =====================================================================
        # CloudWatch Alarms
        # =====================================================================

        # High CPU alarm
        cpu_alarm = cloudwatch.Alarm(
            self,
            "HighCpuAlarm",
            alarm_name=f"{self._get_app_name()}-{self.config.environment}-high-cpu",
            metric=compute_stack.service.service.metric_cpu_utilization(),
            threshold=80,
            evaluation_periods=3,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="CPU utilization is above 80%",
        )
        cpu_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))

        # High memory alarm
        memory_alarm = cloudwatch.Alarm(
            self,
            "HighMemoryAlarm",
            alarm_name=f"{self._get_app_name()}-{self.config.environment}-high-memory",
            metric=compute_stack.service.service.metric_memory_utilization(),
            threshold=85,
            evaluation_periods=3,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Memory utilization is above 85%",
        )
        memory_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))

        # 5xx errors alarm
        error_alarm = cloudwatch.Alarm(
            self,
            "High5xxErrorsAlarm",
            alarm_name=f"{self._get_app_name()}-{self.config.environment}-5xx-errors",
            metric=compute_stack.service.load_balancer.metric_http_code_target(
                code=cloudwatch.HttpCodeTarget.TARGET_5XX_COUNT,
            ),
            threshold=10,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="High number of 5xx errors",
        )
        error_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))
"""

    def generate(self) -> CDKGeneratorResult:
        """Generate the observability stack."""
        result = super().generate()

        if result.success and self.should_generate():
            result.add_artifact(
                "observability_stack",
                {
                    "dashboard_ref": "observability_stack.dashboard",
                },
            )

        return result
