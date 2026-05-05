"""Tests for CDK stack generators."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

from dazzle.deploy.analyzer import AWSRequirements, EventBridgeBusSpec, SQSQueueSpec
from dazzle.deploy.config import DeploymentConfig
from dazzle.deploy.generator import CDKGeneratorResult
from dazzle.deploy.stacks import (
    ComputeStackGenerator,
    DataStackGenerator,
    MessagingStackGenerator,
    NetworkStackGenerator,
    ObservabilityStackGenerator,
)


def create_mock_spec(name: str = "test-app"):
    """Create a mock AppSpec for testing."""
    spec = MagicMock()
    spec.name = name
    spec.domain = MagicMock()
    spec.domain.entities = []
    spec.channels = []
    spec.processes = []
    return spec


class TestCDKGeneratorResult:
    """Tests for CDKGeneratorResult."""

    def test_default_state_and_mutators(self):
        """Default state plus add_file/add_stack/add_error/add_artifact behaviour."""
        result = CDKGeneratorResult()
        # Default state
        assert result.success is True
        assert result.files_created == []
        assert result.stack_names == []
        assert result.errors == []
        assert result.warnings == []
        assert result.artifacts == {}

        # add_file
        result.add_file(Path("/test/stack.py"))
        assert len(result.files_created) == 1
        assert result.files_created[0] == Path("/test/stack.py")

        # add_stack
        result.add_stack("Network")
        assert "Network" in result.stack_names

        # add_artifact
        result.add_artifact("vpc_ref", "network_stack.vpc")
        assert result.artifacts["vpc_ref"] == "network_stack.vpc"

        # add_error flips success
        result.add_error("Failed to generate")
        assert result.success is False
        assert "Failed to generate" in result.errors


class TestNetworkStackGenerator:
    """Tests for NetworkStackGenerator."""

    def test_stack_name_and_always_generates(self):
        """Network stack has correct name and always generates."""
        spec = create_mock_spec()
        aws_reqs = AWSRequirements()
        config = DeploymentConfig()

        with TemporaryDirectory() as tmpdir:
            generator = NetworkStackGenerator(spec, aws_reqs, config, Path(tmpdir))
            assert generator.stack_name == "Network"
            assert generator.should_generate() is True

    def test_generate_creates_file(self):
        """Test generation creates stack file."""
        spec = create_mock_spec()
        aws_reqs = AWSRequirements()
        config = DeploymentConfig()

        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / "stacks").mkdir()

            generator = NetworkStackGenerator(spec, aws_reqs, config, output_dir)
            result = generator.generate()

            assert result.success is True
            assert len(result.files_created) == 1
            assert "network_stack.py" in str(result.files_created[0])

    def test_generated_code_has_vpc(self):
        """Test generated code includes VPC."""
        spec = create_mock_spec()
        aws_reqs = AWSRequirements()
        config = DeploymentConfig()

        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / "stacks").mkdir()

            generator = NetworkStackGenerator(spec, aws_reqs, config, output_dir)
            generator.generate()

            stack_file = output_dir / "stacks" / "network_stack.py"
            content = stack_file.read_text()

            assert "class NetworkStack" in content
            assert "ec2.Vpc" in content
            assert "SecurityGroup" in content


class TestDataStackGenerator:
    """Tests for DataStackGenerator."""

    def test_stack_name_and_should_generate_branches(self):
        """Data stack name plus should_generate=True for needs_rds/needs_s3 and False otherwise."""
        spec = create_mock_spec()
        config = DeploymentConfig()

        with TemporaryDirectory() as tmpdir:
            generator = DataStackGenerator(spec, AWSRequirements(), config, Path(tmpdir))
            assert generator.stack_name == "Data"

            assert (
                DataStackGenerator(
                    spec, AWSRequirements(needs_rds=True), config, Path(tmpdir)
                ).should_generate()
                is True
            )
            assert (
                DataStackGenerator(
                    spec, AWSRequirements(needs_s3=True), config, Path(tmpdir)
                ).should_generate()
                is True
            )
            assert (
                DataStackGenerator(
                    spec,
                    AWSRequirements(needs_rds=False, needs_s3=False),
                    config,
                    Path(tmpdir),
                ).should_generate()
                is False
            )

    def test_skip_generation_when_not_needed(self):
        """Test generation is skipped when not needed."""
        spec = create_mock_spec()
        aws_reqs = AWSRequirements(needs_rds=False, needs_s3=False)
        config = DeploymentConfig()

        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / "stacks").mkdir()

            generator = DataStackGenerator(spec, aws_reqs, config, output_dir)
            result = generator.generate()

            assert result.success is True
            assert len(result.files_created) == 0

    def test_generated_code_has_rds(self):
        """Test generated code includes RDS when needed."""
        spec = create_mock_spec()
        aws_reqs = AWSRequirements(needs_rds=True)
        config = DeploymentConfig()

        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / "stacks").mkdir()

            generator = DataStackGenerator(spec, aws_reqs, config, output_dir)
            generator.generate()

            stack_file = output_dir / "stacks" / "data_stack.py"
            content = stack_file.read_text()

            assert "class DataStack" in content
            assert "rds." in content or "Database" in content


class TestComputeStackGenerator:
    """Tests for ComputeStackGenerator."""

    def test_stack_name_and_always_generates(self):
        """Compute stack name and should_generate=True invariant."""
        spec = create_mock_spec()
        aws_reqs = AWSRequirements()
        config = DeploymentConfig()
        with TemporaryDirectory() as tmpdir:
            generator = ComputeStackGenerator(spec, aws_reqs, config, Path(tmpdir))
            assert generator.stack_name == "Compute"
            assert generator.should_generate() is True

    def test_generated_code_has_ecs(self):
        """Test generated code includes ECS."""
        spec = create_mock_spec()
        aws_reqs = AWSRequirements()
        config = DeploymentConfig()

        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / "stacks").mkdir()

            generator = ComputeStackGenerator(spec, aws_reqs, config, output_dir)
            generator.generate()

            stack_file = output_dir / "stacks" / "compute_stack.py"
            content = stack_file.read_text()

            assert "class ComputeStack" in content
            assert "ecs.Cluster" in content or "FargateService" in content


class TestMessagingStackGenerator:
    """Tests for MessagingStackGenerator."""

    def test_stack_name_and_should_generate_branches(self):
        """Messaging stack name plus SQS/EventBridge enable + all-disabled disable."""
        spec = create_mock_spec()
        config = DeploymentConfig()

        with TemporaryDirectory() as tmpdir:
            base = MessagingStackGenerator(spec, AWSRequirements(), config, Path(tmpdir))
            assert base.stack_name == "Messaging"

            assert (
                MessagingStackGenerator(
                    spec, AWSRequirements(needs_sqs=True), config, Path(tmpdir)
                ).should_generate()
                is True
            )
            assert (
                MessagingStackGenerator(
                    spec,
                    AWSRequirements(needs_eventbridge=True),
                    config,
                    Path(tmpdir),
                ).should_generate()
                is True
            )
            assert (
                MessagingStackGenerator(
                    spec,
                    AWSRequirements(needs_sqs=False, needs_eventbridge=False, needs_ses=False),
                    config,
                    Path(tmpdir),
                ).should_generate()
                is False
            )

    def test_generated_code_has_sqs(self):
        """Test generated code includes SQS when needed."""
        spec = create_mock_spec()
        aws_reqs = AWSRequirements(
            needs_sqs=True,
            sqs_queues=[SQSQueueSpec(name="orders")],
        )
        config = DeploymentConfig()

        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / "stacks").mkdir()

            generator = MessagingStackGenerator(spec, aws_reqs, config, output_dir)
            generator.generate()

            stack_file = output_dir / "stacks" / "messaging_stack.py"
            content = stack_file.read_text()

            assert "class MessagingStack" in content
            assert "sqs.Queue" in content

    def test_generated_code_has_eventbridge(self):
        """Test generated code includes EventBridge when needed."""
        spec = create_mock_spec()
        aws_reqs = AWSRequirements(
            needs_eventbridge=True,
            eventbridge_buses=[EventBridgeBusSpec(name="domain-events")],
        )
        config = DeploymentConfig()

        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / "stacks").mkdir()

            generator = MessagingStackGenerator(spec, aws_reqs, config, output_dir)
            generator.generate()

            stack_file = output_dir / "stacks" / "messaging_stack.py"
            content = stack_file.read_text()

            assert "class MessagingStack" in content
            assert "events.EventBus" in content


class TestObservabilityStackGenerator:
    """Tests for ObservabilityStackGenerator."""

    def test_stack_name_and_dashboard_toggle(self):
        """Observability name plus dashboard enabled/disabled controls should_generate."""
        spec = create_mock_spec()
        aws_reqs = AWSRequirements()

        with TemporaryDirectory() as tmpdir:
            base_cfg = DeploymentConfig()
            assert (
                ObservabilityStackGenerator(spec, aws_reqs, base_cfg, Path(tmpdir)).stack_name
                == "Observability"
            )

            cfg_on = DeploymentConfig()
            cfg_on.observability.create_dashboard = True
            assert (
                ObservabilityStackGenerator(spec, aws_reqs, cfg_on, Path(tmpdir)).should_generate()
                is True
            )

            cfg_off = DeploymentConfig()
            cfg_off.observability.create_dashboard = False
            assert (
                ObservabilityStackGenerator(spec, aws_reqs, cfg_off, Path(tmpdir)).should_generate()
                is False
            )

    def test_generated_code_has_dashboard(self):
        """Test generated code includes CloudWatch dashboard."""
        spec = create_mock_spec()
        aws_reqs = AWSRequirements()
        config = DeploymentConfig()
        config.observability.create_dashboard = True

        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / "stacks").mkdir()

            generator = ObservabilityStackGenerator(spec, aws_reqs, config, output_dir)
            generator.generate()

            stack_file = output_dir / "stacks" / "observability_stack.py"
            content = stack_file.read_text()

            assert "class ObservabilityStack" in content
            assert "cloudwatch.Dashboard" in content

    def test_generated_code_has_alarms_with_email(self):
        """Test generated code includes alarms when email configured."""
        spec = create_mock_spec()
        aws_reqs = AWSRequirements()
        config = DeploymentConfig()
        config.observability.create_dashboard = True
        config.observability.alarm_email = "ops@example.com"

        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / "stacks").mkdir()

            generator = ObservabilityStackGenerator(spec, aws_reqs, config, output_dir)
            generator.generate()

            stack_file = output_dir / "stacks" / "observability_stack.py"
            content = stack_file.read_text()

            assert "cloudwatch.Alarm" in content
            assert "sns.Topic" in content
            assert "ops@example.com" in content


class TestStackGeneratorHeader:
    """Tests for stack generator header generation."""

    def test_header_contains_warning_and_cdk_imports(self):
        """Generated stack file contains both auto-gen marker and AWS CDK imports."""
        spec = create_mock_spec()
        aws_reqs = AWSRequirements()
        config = DeploymentConfig()

        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / "stacks").mkdir()

            generator = NetworkStackGenerator(spec, aws_reqs, config, output_dir)
            generator.generate()

            content = (output_dir / "stacks" / "network_stack.py").read_text()
            assert "AUTO-GENERATED" in content or "Generated by" in content
            assert "from aws_cdk import" in content
            assert "Stack" in content
            assert "Construct" in content
