"""
Messaging stack generator.

Generates SQS queues and EventBridge event buses.
"""

from __future__ import annotations

from ..generator import CDKGeneratorResult, StackGenerator


class MessagingStackGenerator(StackGenerator):
    """Generate SQS, EventBridge, and SES resources."""

    @property
    def stack_name(self) -> str:
        return "Messaging"

    def should_generate(self) -> bool:
        """Only generate if messaging is needed."""
        return self.aws_reqs.needs_sqs or self.aws_reqs.needs_eventbridge or self.aws_reqs.needs_ses

    def _generate_stack_code(self) -> str:
        """Generate the messaging stack Python code."""
        # Build imports
        imports = []
        if self.aws_reqs.needs_sqs:
            imports.append("from aws_cdk import aws_sqs as sqs")
        if self.aws_reqs.needs_eventbridge:
            imports.append("from aws_cdk import aws_events as events")
            imports.append("from aws_cdk import aws_events_targets as targets")
        if self.aws_reqs.needs_ses:
            imports.append("from aws_cdk import aws_ses as ses")

        imports_code = "\n".join(imports)

        # Generate SQS code
        sqs_code = self._generate_sqs_code() if self.aws_reqs.needs_sqs else ""

        # Generate EventBridge code
        eventbridge_code = (
            self._generate_eventbridge_code() if self.aws_reqs.needs_eventbridge else ""
        )

        # Generate outputs
        outputs_code = self._generate_outputs_code()

        return f'''{self._generate_header()}
{imports_code}


class MessagingStack(Stack):
    """
    Messaging layer resources for {self.spec.name}.

    Creates:
    {"- SQS queues with dead-letter queues" if self.aws_reqs.needs_sqs else ""}
    {"- EventBridge event buses and rules" if self.aws_reqs.needs_eventbridge else ""}
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # Dictionaries to store queue and bus references
        self.queues: dict = {{}}
        self.buses: dict = {{}}
{sqs_code}
{eventbridge_code}
{outputs_code}
'''

    def _generate_sqs_code(self) -> str:
        """Generate SQS queue code."""
        app_name = self._get_app_name()
        env = self.config.environment
        retention_days = self.config.messaging.message_retention_days

        lines = [
            "\n        # ====================================================================="
        ]
        lines.append("        # SQS Queues")
        lines.append(
            "        # =====================================================================\n"
        )

        for queue_spec in self.aws_reqs.sqs_queues:
            queue_name = queue_spec.name
            queue_var = queue_name.replace("-", "_")
            visibility_timeout = queue_spec.visibility_timeout
            max_receive = queue_spec.max_receive_count

            # Dead letter queue
            lines.append(f'''
        # Queue: {queue_name}
        {queue_var}_dlq = sqs.Queue(
            self,
            "{queue_name.title().replace("_", "")}Dlq",
            queue_name="{app_name}-{env}-{queue_name}-dlq",
            retention_period=Duration.days(14),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
        )

        {queue_var}_queue = sqs.Queue(
            self,
            "{queue_name.title().replace("_", "")}Queue",
            queue_name="{app_name}-{env}-{queue_name}",
            visibility_timeout=Duration.seconds({visibility_timeout}),
            retention_period=Duration.days({retention_days}),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            dead_letter_queue=sqs.DeadLetterQueue(
                queue={queue_var}_dlq,
                max_receive_count={max_receive},
            ),
        )

        self.queues["{queue_name}"] = {{
            "queue": {queue_var}_queue,
            "dlq": {queue_var}_dlq,
            "url": {queue_var}_queue.queue_url,
            "arn": {queue_var}_queue.queue_arn,
        }}
''')

        return "\n".join(lines)

    def _generate_eventbridge_code(self) -> str:
        """Generate EventBridge event bus and rule code."""
        app_name = self._get_app_name()
        env = self.config.environment

        lines = [
            "\n        # ====================================================================="
        ]
        lines.append("        # EventBridge Event Buses")
        lines.append(
            "        # =====================================================================\n"
        )

        # Generate buses
        for bus_spec in self.aws_reqs.eventbridge_buses:
            bus_name = bus_spec.name
            bus_var = bus_name.replace("-", "_")
            description = bus_spec.description or f"Event bus for {bus_name}"

            lines.append(f'''
        # Event Bus: {bus_name}
        {bus_var}_bus = events.EventBus(
            self,
            "{bus_name.title().replace("_", "")}Bus",
            event_bus_name="{app_name}-{env}-{bus_name}",
        )

        self.buses["{bus_name}"] = {{
            "bus": {bus_var}_bus,
            "name": {bus_var}_bus.event_bus_name,
            "arn": {bus_var}_bus.event_bus_arn,
        }}
''')

        # Generate rules
        if self.aws_reqs.eventbridge_rules:
            lines.append(
                "\n        # ====================================================================="
            )
            lines.append("        # EventBridge Rules")
            lines.append(
                "        # =====================================================================\n"
            )

            for rule_spec in self.aws_reqs.eventbridge_rules:
                rule_name = rule_spec.name
                rule_var = rule_name.replace("-", "_")
                description = rule_spec.description or f"Rule: {rule_name}"

                if rule_spec.schedule_expression:
                    lines.append(f'''
        # Scheduled Rule: {rule_name}
        {rule_var}_rule = events.Rule(
            self,
            "{rule_name.title().replace("_", "").replace("-", "")}Rule",
            rule_name="{app_name}-{env}-{rule_name}",
            description="{description}",
            schedule=events.Schedule.expression("{rule_spec.schedule_expression}"),
        )
''')

        return "\n".join(lines)

    def _generate_outputs_code(self) -> str:
        """Generate CloudFormation outputs."""
        app_name = self._get_app_name()
        env = self.config.environment

        outputs = []

        # SQS queue outputs
        for queue_spec in self.aws_reqs.sqs_queues:
            queue_name = queue_spec.name
            queue_var = queue_name.replace("-", "_")
            output_name = queue_name.title().replace("_", "").replace("-", "")

            outputs.append(f'''
        CfnOutput(
            self,
            "{output_name}QueueUrl",
            value={queue_var}_queue.queue_url,
            description="{queue_name} queue URL",
            export_name="{app_name}-{env}-{queue_name}-queue-url",
        )''')

        # EventBridge bus outputs
        for bus_spec in self.aws_reqs.eventbridge_buses:
            bus_name = bus_spec.name
            bus_var = bus_name.replace("-", "_")
            output_name = bus_name.title().replace("_", "").replace("-", "")

            outputs.append(f'''
        CfnOutput(
            self,
            "{output_name}BusArn",
            value={bus_var}_bus.event_bus_arn,
            description="{bus_name} event bus ARN",
            export_name="{app_name}-{env}-{bus_name}-bus-arn",
        )''')

        return "\n".join(outputs) if outputs else ""

    def generate(self) -> CDKGeneratorResult:
        """Generate the messaging stack and record artifacts."""
        result = super().generate()

        if result.success and self.should_generate():
            result.add_artifact(
                "messaging_stack",
                {
                    "queues_ref": "messaging_stack.queues",
                    "buses_ref": "messaging_stack.buses",
                },
            )

        return result
