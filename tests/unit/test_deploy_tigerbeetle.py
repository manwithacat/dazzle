"""
Unit tests for TigerBeetle AWS deployment infrastructure.

Tests the TigerBeetle stack generation, configuration, and requirements
analysis for AWS CDK deployment.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

if TYPE_CHECKING:
    pass


# =============================================================================
# Configuration Tests
# =============================================================================


class TestTigerBeetleConfig:
    """Test TigerBeetleConfig validation."""

    def test_default_config(self) -> None:
        """Default config should have valid values."""
        from dazzle.deploy.config import TigerBeetleConfig

        config = TigerBeetleConfig()

        assert config.enabled is True
        assert config.node_count == 3  # Odd for Raft consensus
        assert config.volume_size_gb == 100
        assert config.volume_iops == 10000

    def test_node_count_must_be_odd_for_ha(self) -> None:
        """Node count must be odd when > 1 for Raft consensus."""
        from dazzle.deploy.config import TigerBeetleConfig

        # Valid: single node (dev)
        config = TigerBeetleConfig(node_count=1)
        assert config.node_count == 1

        # Valid: 3 nodes (prod HA)
        config = TigerBeetleConfig(node_count=3)
        assert config.node_count == 3

        # Valid: 5 nodes (large prod)
        config = TigerBeetleConfig(node_count=5)
        assert config.node_count == 5

        # Invalid: 2 nodes (even)
        with pytest.raises(ValueError, match="odd"):
            TigerBeetleConfig(node_count=2)

        # Invalid: 4 nodes (even)
        with pytest.raises(ValueError, match="odd"):
            TigerBeetleConfig(node_count=4)

    def test_instance_type_property(self) -> None:
        """Instance type should come from size enum."""
        from dazzle.deploy.config import TigerBeetleConfig, TigerBeetleSize

        config = TigerBeetleConfig(size=TigerBeetleSize.SMALL)
        assert config.instance_type == "t3.medium"

        config = TigerBeetleConfig(size=TigerBeetleSize.MEDIUM)
        assert config.instance_type == "r6i.large"

        config = TigerBeetleConfig(size=TigerBeetleSize.LARGE)
        assert config.instance_type == "r6i.xlarge"

    def test_volume_iops_bounds(self) -> None:
        """Volume IOPS should be within AWS gp3 limits."""
        from dazzle.deploy.config import TigerBeetleConfig

        # Valid IOPS
        config = TigerBeetleConfig(volume_iops=3000)
        assert config.volume_iops == 3000

        config = TigerBeetleConfig(volume_iops=64000)
        assert config.volume_iops == 64000

        # Invalid: below minimum
        with pytest.raises(ValueError):
            TigerBeetleConfig(volume_iops=2999)

        # Invalid: above maximum
        with pytest.raises(ValueError):
            TigerBeetleConfig(volume_iops=64001)


class TestTigerBeetleSize:
    """Test TigerBeetleSize enum values."""

    def test_size_values_are_valid_ec2_types(self) -> None:
        """Size enum values should be valid EC2 instance types."""
        from dazzle.deploy.config import TigerBeetleSize

        # All should be valid EC2 instance type patterns
        for size in TigerBeetleSize:
            assert "." in size.value  # EC2 types have a dot
            parts = size.value.split(".")
            assert len(parts) == 2


# =============================================================================
# Infrastructure Requirements Tests
# =============================================================================


class TestInfraRequirementsTigerBeetle:
    """Test TigerBeetle detection in infra_analyzer."""

    def test_needs_tigerbeetle_false_by_default(self) -> None:
        """TigerBeetle should not be needed when no ledgers."""
        from dazzle.core.infra_analyzer import InfraRequirements

        reqs = InfraRequirements()

        assert reqs.needs_tigerbeetle is False
        assert reqs.tigerbeetle_ledger_count == 0
        assert reqs.tigerbeetle_currencies == []

    def test_has_any_infra_needs_includes_tigerbeetle(self) -> None:
        """has_any_infra_needs should include TigerBeetle."""
        from dazzle.core.infra_analyzer import InfraRequirements

        reqs = InfraRequirements(needs_tigerbeetle=True)

        assert reqs.has_any_infra_needs() is True

    def test_analyze_detects_ledgers(self) -> None:
        """analyze_infra_requirements should detect ledgers."""
        from dazzle.core.infra_analyzer import analyze_infra_requirements
        from dazzle.core.ir.ledgers import AccountType, LedgerSpec

        # Create a mock appspec with ledgers
        mock_ledger = LedgerSpec(
            name="CustomerWallet",
            account_code=1001,
            ledger_id=1,
            account_type=AccountType.ASSET,
            currency="GBP",
        )

        # Build a minimal AppSpec using MagicMock without spec constraint
        mock_domain = MagicMock()
        mock_domain.entities = []

        mock_spec = MagicMock()
        mock_spec.domain = mock_domain
        mock_spec.apis = []
        mock_spec.integrations = []
        mock_spec.experiences = []
        mock_spec.surfaces = []
        mock_spec.ledgers = [mock_ledger]
        mock_spec.transactions = []
        mock_spec.channels = []

        reqs = analyze_infra_requirements(mock_spec)

        assert reqs.needs_tigerbeetle is True
        assert reqs.tigerbeetle_ledger_count == 1
        assert reqs.tigerbeetle_currencies == ["GBP"]
        assert reqs.tigerbeetle_ledger_names == ["CustomerWallet"]


# =============================================================================
# AWS Requirements Tests
# =============================================================================


class TestAWSRequirementsTigerBeetle:
    """Test TigerBeetle in AWS requirements analysis."""

    def test_tigerbeetle_cluster_spec_defaults(self) -> None:
        """TigerBeetleClusterSpec should have sensible defaults."""
        from dazzle.deploy.analyzer import TigerBeetleClusterSpec

        spec = TigerBeetleClusterSpec()

        assert spec.cluster_id == 0
        assert spec.node_count == 3
        assert spec.instance_type == "r6i.large"
        assert spec.volume_size_gb == 100
        assert spec.volume_iops == 10000

    def test_aws_requirements_summary_includes_tigerbeetle(self) -> None:
        """AWSRequirements.summary() should include TigerBeetle."""
        from dazzle.deploy.analyzer import AWSRequirements

        reqs = AWSRequirements(needs_tigerbeetle=True)
        summary = reqs.summary()

        assert "tigerbeetle" in summary
        assert summary["tigerbeetle"] is True


# =============================================================================
# Stack Generator Tests
# =============================================================================


class TestTigerBeetleStackGenerator:
    """Test TigerBeetle stack generation."""

    @pytest.fixture
    def mock_spec(self) -> MagicMock:
        """Create a mock AppSpec."""
        spec = MagicMock()
        spec.name = "Test App"
        return spec

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create a mock DeploymentConfig."""
        from dazzle.deploy.config import TigerBeetleConfig, TigerBeetleSize

        config = MagicMock()
        config.environment = "staging"
        config.tigerbeetle = TigerBeetleConfig(
            size=TigerBeetleSize.MEDIUM,
            node_count=3,
            volume_size_gb=100,
            volume_iops=10000,
        )
        return config

    def test_should_generate_when_needed(
        self, mock_spec: MagicMock, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        """Stack should generate when TigerBeetle is needed."""
        from dazzle.deploy.analyzer import AWSRequirements, TigerBeetleClusterSpec
        from dazzle.deploy.stacks.tigerbeetle import TigerBeetleStackGenerator

        aws_reqs = AWSRequirements(
            needs_tigerbeetle=True,
            tigerbeetle_spec=TigerBeetleClusterSpec(node_count=3),
        )

        generator = TigerBeetleStackGenerator(mock_spec, aws_reqs, mock_config, tmp_path)

        assert generator.should_generate() is True
        assert generator.stack_name == "TigerBeetle"

    def test_should_not_generate_when_not_needed(
        self, mock_spec: MagicMock, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        """Stack should not generate when TigerBeetle not needed."""
        from dazzle.deploy.analyzer import AWSRequirements
        from dazzle.deploy.stacks.tigerbeetle import TigerBeetleStackGenerator

        aws_reqs = AWSRequirements(needs_tigerbeetle=False)

        generator = TigerBeetleStackGenerator(mock_spec, aws_reqs, mock_config, tmp_path)

        assert generator.should_generate() is False

    def test_generated_code_includes_asg(
        self, mock_spec: MagicMock, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        """Generated code should include Auto Scaling Group."""
        from dazzle.deploy.analyzer import AWSRequirements, TigerBeetleClusterSpec
        from dazzle.deploy.stacks.tigerbeetle import TigerBeetleStackGenerator

        aws_reqs = AWSRequirements(
            needs_tigerbeetle=True,
            tigerbeetle_spec=TigerBeetleClusterSpec(node_count=3),
        )

        generator = TigerBeetleStackGenerator(mock_spec, aws_reqs, mock_config, tmp_path)
        code = generator._generate_stack_code()

        # Should have ASG configuration
        assert "AutoScalingGroup" in code
        assert "min_capacity=3" in code
        assert "max_capacity=3" in code

    def test_generated_code_includes_security_groups(
        self, mock_spec: MagicMock, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        """Generated code should include security group configuration."""
        from dazzle.deploy.analyzer import AWSRequirements, TigerBeetleClusterSpec
        from dazzle.deploy.stacks.tigerbeetle import TigerBeetleStackGenerator

        aws_reqs = AWSRequirements(
            needs_tigerbeetle=True,
            tigerbeetle_spec=TigerBeetleClusterSpec(node_count=3),
        )

        generator = TigerBeetleStackGenerator(mock_spec, aws_reqs, mock_config, tmp_path)
        code = generator._generate_stack_code()

        # Should have security group for TigerBeetle ports
        assert "SecurityGroup" in code
        assert "Port.tcp(3000)" in code  # Client port
        assert "Port.tcp(3001)" in code  # Replication port

    def test_generated_code_includes_high_iops_ebs(
        self, mock_spec: MagicMock, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        """Generated code should include high-IOPS EBS volume configuration."""
        from dazzle.deploy.analyzer import AWSRequirements, TigerBeetleClusterSpec
        from dazzle.deploy.stacks.tigerbeetle import TigerBeetleStackGenerator

        aws_reqs = AWSRequirements(
            needs_tigerbeetle=True,
            tigerbeetle_spec=TigerBeetleClusterSpec(
                node_count=3,
                volume_size_gb=100,
                volume_iops=10000,
            ),
        )

        generator = TigerBeetleStackGenerator(mock_spec, aws_reqs, mock_config, tmp_path)
        code = generator._generate_stack_code()

        # Should have EBS gp3 with IOPS
        assert "GP3" in code
        assert "iops=10000" in code

    def test_generated_code_includes_ssm_discovery(
        self, mock_spec: MagicMock, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        """Generated code should include SSM parameters for node discovery."""
        from dazzle.deploy.analyzer import AWSRequirements, TigerBeetleClusterSpec
        from dazzle.deploy.stacks.tigerbeetle import TigerBeetleStackGenerator

        aws_reqs = AWSRequirements(
            needs_tigerbeetle=True,
            tigerbeetle_spec=TigerBeetleClusterSpec(node_count=3),
        )

        generator = TigerBeetleStackGenerator(mock_spec, aws_reqs, mock_config, tmp_path)
        code = generator._generate_stack_code()

        # Should have SSM parameters
        assert "StringParameter" in code
        assert "tigerbeetle/cluster_id" in code
        assert "tigerbeetle/replica_count" in code


# =============================================================================
# Runner Integration Tests
# =============================================================================


class TestDeploymentRunnerTigerBeetle:
    """Test TigerBeetle integration in DeploymentRunner."""

    def test_plan_includes_tigerbeetle_when_needed(self) -> None:
        """Runner plan should include TigerBeetle config when ledgers present."""
        from unittest.mock import MagicMock, patch

        from dazzle.core.ir.ledgers import AccountType, LedgerSpec
        from dazzle.deploy.config import DeploymentConfig
        from dazzle.deploy.runner import DeploymentRunner

        # Create mock spec with ledger
        mock_ledger = LedgerSpec(
            name="CustomerWallet",
            account_code=1001,
            ledger_id=1,
            account_type=AccountType.ASSET,
            currency="GBP",
        )

        # Build mock without spec constraint
        mock_domain = MagicMock()
        mock_domain.entities = []

        mock_spec = MagicMock()
        mock_spec.name = "Test App"
        mock_spec.domain = mock_domain
        mock_spec.apis = []
        mock_spec.integrations = []
        mock_spec.experiences = []
        mock_spec.surfaces = []
        mock_spec.ledgers = [mock_ledger]
        mock_spec.transactions = []
        mock_spec.channels = []
        mock_spec.processes = []
        mock_spec.tenancy = None
        mock_spec.llm_config = None
        mock_spec.llm_models = []

        config = DeploymentConfig()

        with patch.object(DeploymentRunner, "__init__", lambda self, *args, **kwargs: None):
            runner = DeploymentRunner.__new__(DeploymentRunner)
            runner.spec = mock_spec
            runner.config = config
            runner.output_dir = Path("/tmp")

            from dazzle.core.infra_analyzer import analyze_infra_requirements
            from dazzle.deploy.analyzer import analyze_aws_requirements

            runner.infra_reqs = analyze_infra_requirements(mock_spec)
            runner.aws_reqs = analyze_aws_requirements(mock_spec, runner.infra_reqs, config)

            plan = runner.plan()

        # Should have TigerBeetle in plan
        assert "tigerbeetle" in plan
        assert plan["tigerbeetle"]["enabled"] is True
        assert plan["tigerbeetle"]["ledger_count"] == 1
        assert plan["tigerbeetle"]["currencies"] == ["GBP"]

    def test_tigerbeetle_stack_in_generators_list(self) -> None:
        """TigerBeetle generator should be in the generators list."""
        from dazzle.deploy.stacks import TigerBeetleStackGenerator

        # Verify the generator is exported
        assert TigerBeetleStackGenerator is not None
        assert hasattr(TigerBeetleStackGenerator, "should_generate")
        assert hasattr(TigerBeetleStackGenerator, "stack_name")


# =============================================================================
# TOML Configuration Tests
# =============================================================================


class TestTigerBeetleTOMLConfig:
    """Test TigerBeetle configuration loading from dazzle.toml."""

    def test_load_tigerbeetle_config_from_toml(self, tmp_path: Path) -> None:
        """Should load TigerBeetle config from dazzle.toml."""
        from dazzle.deploy.config import load_deployment_config

        # Size must use actual EC2 instance type values (enum values)
        toml_content = """
[deploy]
enabled = true
environment = "prod"

[deploy.tigerbeetle]
enabled = true
size = "r6i.xlarge"
node_count = 5
volume_size_gb = 200
volume_iops = 20000
"""
        toml_path = tmp_path / "dazzle.toml"
        toml_path.write_text(toml_content)

        config = load_deployment_config(toml_path)

        assert config.tigerbeetle.enabled is True
        assert config.tigerbeetle.size.value == "r6i.xlarge"
        assert config.tigerbeetle.node_count == 5
        assert config.tigerbeetle.volume_size_gb == 200
        assert config.tigerbeetle.volume_iops == 20000
