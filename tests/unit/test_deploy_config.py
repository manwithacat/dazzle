"""Tests for deploy configuration models."""

from pathlib import Path
from tempfile import TemporaryDirectory

from dazzle.deploy.config import (
    AWSRegion,
    ComputeConfig,
    ComputeSize,
    DatabaseSize,
    DeploymentConfig,
    OutputConfig,
    load_deployment_config,
)


class TestDeploymentConfig:
    """Tests for DeploymentConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = DeploymentConfig()

        assert config.enabled is False
        assert config.provider == "aws"
        assert config.environment == "staging"
        assert config.region == AWSRegion.US_EAST_1

    def test_compute_defaults(self):
        """Test default compute configuration."""
        config = DeploymentConfig()

        assert config.compute.size == ComputeSize.SMALL
        assert config.compute.min_capacity == 1
        assert config.compute.max_capacity == 4
        assert config.compute.use_spot is True
        assert config.compute.cpu == 256
        assert config.compute.memory == 512

    def test_database_defaults(self):
        """Test default database configuration."""
        config = DeploymentConfig()

        assert config.database.size == DatabaseSize.SERVERLESS
        assert config.database.multi_az is False
        assert config.database.backup_retention_days == 7
        assert config.database.deletion_protection is False
        assert config.database.is_serverless is True

    def test_database_size_mapping(self):
        """Test database size to instance type mapping."""
        config = DeploymentConfig()

        # Serverless
        config.database.size = DatabaseSize.SERVERLESS
        assert config.database.is_serverless is True

        # Non-serverless sizes
        for size in [DatabaseSize.SMALL, DatabaseSize.MEDIUM, DatabaseSize.LARGE]:
            config.database.size = size
            assert config.database.is_serverless is False

    def test_network_defaults(self):
        """Test default network configuration."""
        config = DeploymentConfig()

        assert config.network.availability_zones == 2
        assert config.network.nat_gateways == 1
        assert config.network.vpc_cidr == "10.0.0.0/16"

    def test_messaging_defaults(self):
        """Test default messaging configuration."""
        config = DeploymentConfig()

        assert config.messaging.message_retention_days == 4
        assert config.messaging.queue_visibility_timeout == 30
        assert config.messaging.dead_letter_max_receives == 3

    def test_observability_defaults(self):
        """Test default observability configuration."""
        config = DeploymentConfig()

        assert config.observability.create_dashboard is True
        assert config.observability.alarm_email is None
        assert config.observability.log_retention_days == 30

    def test_storage_defaults(self):
        """Test default storage configuration."""
        config = DeploymentConfig()

        assert config.storage.versioned is True
        assert config.storage.lifecycle_expiration_days is None
        assert config.storage.cors_allowed_origins == ["*"]

    def test_output_defaults(self):
        """Test default output configuration."""
        config = DeploymentConfig()

        assert config.output.directory == "infra"


class TestLoadDeploymentConfig:
    """Tests for loading configuration from dazzle.toml."""

    def test_load_missing_file_returns_defaults(self):
        """Test loading from non-existent file returns defaults."""
        config = load_deployment_config(Path("/nonexistent/dazzle.toml"))

        assert config.enabled is False
        assert config.provider == "aws"

    def test_load_file_without_deploy_section(self):
        """Test loading from file without [deploy] section."""
        with TemporaryDirectory() as tmpdir:
            toml_path = Path(tmpdir) / "dazzle.toml"
            toml_path.write_text("[project]\nname = 'test'\n")

            config = load_deployment_config(toml_path)

            assert config.enabled is False

    def test_load_file_with_deploy_section(self):
        """Test loading from file with [deploy] section."""
        with TemporaryDirectory() as tmpdir:
            toml_path = Path(tmpdir) / "dazzle.toml"
            toml_path.write_text("""
[deploy]
enabled = true
provider = "aws"
environment = "production"
region = "eu-west-1"

[deploy.compute]
size = "medium"
min_capacity = 2
max_capacity = 8
use_spot = false

[deploy.database]
size = "db.t3.small"
multi_az = true

[deploy.observability]
create_dashboard = true
alarm_email = "ops@example.com"
""")

            config = load_deployment_config(toml_path)

            assert config.enabled is True
            assert config.environment == "production"
            assert config.region == AWSRegion.EU_WEST_1
            assert config.compute.size == ComputeSize.MEDIUM
            assert config.compute.min_capacity == 2
            assert config.compute.max_capacity == 8
            assert config.compute.use_spot is False
            assert config.database.size == DatabaseSize.SMALL  # db.t3.small
            assert config.database.multi_az is True
            assert config.observability.alarm_email == "ops@example.com"


class TestOutputConfig:
    """Tests for OutputConfig."""

    def test_get_output_path(self):
        """Test output path resolution."""
        config = OutputConfig(directory="infra")
        project_root = Path("/project")

        path = config.get_output_path(project_root)

        assert path == Path("/project/infra")

    def test_get_output_path_absolute(self):
        """Test output path with absolute directory."""
        config = OutputConfig(directory="/absolute/path")
        project_root = Path("/project")

        path = config.get_output_path(project_root)

        assert path == Path("/absolute/path")


class TestAWSRegion:
    """Tests for AWSRegion enum."""

    def test_all_regions_have_values(self):
        """Test that all regions have string values."""
        for region in AWSRegion:
            assert isinstance(region.value, str)
            assert len(region.value) > 0

    def test_common_regions_exist(self):
        """Test that common regions are available."""
        assert AWSRegion.US_EAST_1.value == "us-east-1"
        assert AWSRegion.EU_WEST_1.value == "eu-west-1"
        assert AWSRegion.AP_SOUTHEAST_1.value == "ap-southeast-1"


class TestComputeSize:
    """Tests for ComputeSize enum."""

    def test_compute_sizes(self):
        """Test compute size values."""
        assert ComputeSize.SMALL.value == "small"
        assert ComputeSize.MEDIUM.value == "medium"
        assert ComputeSize.LARGE.value == "large"
        assert ComputeSize.XLARGE.value == "xlarge"


class TestComputeConfig:
    """Tests for ComputeConfig cpu/memory properties."""

    def test_small_size(self):
        """Test small compute size."""
        config = ComputeConfig(size=ComputeSize.SMALL)
        assert config.cpu == 256
        assert config.memory == 512

    def test_medium_size(self):
        """Test medium compute size."""
        config = ComputeConfig(size=ComputeSize.MEDIUM)
        assert config.cpu == 512
        assert config.memory == 1024

    def test_large_size(self):
        """Test large compute size."""
        config = ComputeConfig(size=ComputeSize.LARGE)
        assert config.cpu == 1024
        assert config.memory == 2048

    def test_xlarge_size(self):
        """Test xlarge compute size."""
        config = ComputeConfig(size=ComputeSize.XLARGE)
        assert config.cpu == 2048
        assert config.memory == 4096
