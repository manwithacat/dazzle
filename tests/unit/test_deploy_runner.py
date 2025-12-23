"""Tests for DeploymentRunner."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from dazzle.deploy.config import DeploymentConfig
from dazzle.deploy.runner import DEPLOY_VERSION, DeploymentResult, DeploymentRunner


def create_mock_spec(name: str = "test-app"):
    """Create a mock AppSpec for testing."""
    spec = MagicMock()
    spec.name = name
    spec.domain = MagicMock()
    spec.domain.entities = []
    spec.channels = []
    spec.processes = []
    spec.apis = []
    spec.llm_config = None
    spec.llm_models = []
    spec.tenancy = None
    return spec


def create_mock_infra_reqs():
    """Create mock infrastructure requirements."""
    reqs = MagicMock()
    reqs.needs_database = True
    reqs.needs_storage = False
    reqs.needs_queues = False
    reqs.needs_events = False
    reqs.needs_email = False
    reqs.needs_cache = False
    reqs.needs_secrets = False
    reqs.entity_names = []
    return reqs


def create_mock_aws_reqs():
    """Create mock AWS requirements."""
    reqs = MagicMock()
    reqs.needs_rds = True
    reqs.needs_s3 = False
    reqs.needs_sqs = False
    reqs.needs_eventbridge = False
    reqs.needs_ses = False
    reqs.summary.return_value = {
        "vpc": True,
        "ecs": True,
        "ecr": True,
        "rds": True,
        "s3": False,
        "sqs": False,
        "eventbridge": False,
        "ses": False,
        "elasticache": False,
    }
    return reqs


class TestDeploymentResult:
    """Tests for DeploymentResult dataclass."""

    def test_default_state(self):
        """Test default result state."""
        result = DeploymentResult()

        assert result.success is True  # No errors = success
        assert result.files_created == []
        assert result.stacks_generated == []
        assert result.errors == []
        assert result.warnings == []
        assert result.verified is False

    def test_success_with_no_errors(self):
        """Test success property with no errors."""
        result = DeploymentResult()
        result.files_created.append(Path("/test/file.py"))

        assert result.success is True

    def test_failure_with_errors(self):
        """Test success property with errors."""
        result = DeploymentResult()
        result.add_error("Something went wrong")

        assert result.success is False
        assert "Something went wrong" in result.errors

    def test_add_warning(self):
        """Test adding warnings."""
        result = DeploymentResult()
        result.add_warning("This is a warning")

        assert result.success is True  # Warnings don't affect success
        assert "This is a warning" in result.warnings

    def test_summary(self):
        """Test summary generation."""
        result = DeploymentResult()
        result.files_created.append(Path("/test/file.py"))
        result.stacks_generated.append("Network")
        result.add_warning("A warning")

        summary = result.summary()

        assert summary["success"] is True
        assert summary["files_created"] == 1
        assert summary["stacks_generated"] == ["Network"]
        assert summary["warnings"] == ["A warning"]


class TestDeploymentRunner:
    """Tests for DeploymentRunner."""

    @patch("dazzle.deploy.analyzer.analyze_aws_requirements")
    @patch("dazzle.core.infra_analyzer.analyze_infra_requirements")
    def test_initialization(self, mock_infra_analyze, mock_aws_analyze):
        """Test runner initialization."""
        mock_infra_analyze.return_value = create_mock_infra_reqs()
        mock_aws_analyze.return_value = create_mock_aws_reqs()

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            spec = create_mock_spec()
            config = DeploymentConfig()

            runner = DeploymentRunner(spec, project_root, config)

            assert runner.spec == spec
            assert runner.project_root == project_root
            assert runner.config == config
            assert runner.output_dir == project_root / "infra"

    @patch("dazzle.deploy.analyzer.analyze_aws_requirements")
    @patch("dazzle.core.infra_analyzer.analyze_infra_requirements")
    def test_get_app_name_sanitization(self, mock_infra_analyze, mock_aws_analyze):
        """Test app name sanitization."""
        mock_infra_analyze.return_value = create_mock_infra_reqs()
        mock_aws_analyze.return_value = create_mock_aws_reqs()

        with TemporaryDirectory() as tmpdir:
            spec = create_mock_spec(name="My Test App!")
            runner = DeploymentRunner(spec, Path(tmpdir), DeploymentConfig())

            app_name = runner._get_app_name()

            assert app_name == "my-test-app"
            assert " " not in app_name
            assert "!" not in app_name

    @patch("dazzle.deploy.analyzer.analyze_aws_requirements")
    @patch("dazzle.core.infra_analyzer.analyze_infra_requirements")
    def test_get_app_name_removes_double_dashes(self, mock_infra_analyze, mock_aws_analyze):
        """Test app name removes consecutive dashes."""
        mock_infra_analyze.return_value = create_mock_infra_reqs()
        mock_aws_analyze.return_value = create_mock_aws_reqs()

        with TemporaryDirectory() as tmpdir:
            spec = create_mock_spec(name="Test--App")
            runner = DeploymentRunner(spec, Path(tmpdir), DeploymentConfig())

            app_name = runner._get_app_name()

            assert "--" not in app_name
            assert app_name == "test-app"

    @patch("dazzle.deploy.analyzer.analyze_aws_requirements")
    @patch("dazzle.core.infra_analyzer.analyze_infra_requirements")
    def test_plan(self, mock_infra_analyze, mock_aws_analyze):
        """Test infrastructure plan generation."""
        mock_infra_analyze.return_value = create_mock_infra_reqs()
        mock_aws_analyze.return_value = create_mock_aws_reqs()

        with TemporaryDirectory() as tmpdir:
            spec = create_mock_spec()
            config = DeploymentConfig(environment="staging")
            runner = DeploymentRunner(spec, Path(tmpdir), config)

            plan = runner.plan()

            assert plan["app_name"] == "test-app"
            assert plan["environment"] == "staging"
            assert plan["region"] == "us-east-1"
            assert "requirements" in plan
            assert "stacks" in plan
            assert "config" in plan

    @patch("dazzle.deploy.analyzer.analyze_aws_requirements")
    @patch("dazzle.core.infra_analyzer.analyze_infra_requirements")
    def test_dry_run(self, mock_infra_analyze, mock_aws_analyze):
        """Test dry run mode."""
        mock_infra_analyze.return_value = create_mock_infra_reqs()
        mock_aws_analyze.return_value = create_mock_aws_reqs()

        with TemporaryDirectory() as tmpdir:
            spec = create_mock_spec()
            runner = DeploymentRunner(spec, Path(tmpdir), DeploymentConfig())

            result = runner.run(dry_run=True)

            assert result.success is True
            assert "DRY RUN" in result.warnings[0]
            assert "estimated_files" in result.artifacts
            assert len(result.files_created) == 0  # No files written in dry run

    @patch("dazzle.deploy.analyzer.analyze_aws_requirements")
    @patch("dazzle.core.infra_analyzer.analyze_infra_requirements")
    def test_verify_output_no_dazzle_imports(self, mock_infra_analyze, mock_aws_analyze):
        """Test that verification catches dazzle imports."""
        mock_infra_analyze.return_value = create_mock_infra_reqs()
        mock_aws_analyze.return_value = create_mock_aws_reqs()

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            output_dir = project_root / "infra"
            output_dir.mkdir()

            # Create a file with dazzle import
            bad_file = output_dir / "bad_stack.py"
            bad_file.write_text("from dazzle import something\n")

            spec = create_mock_spec()
            runner = DeploymentRunner(spec, project_root, DeploymentConfig())
            runner.output_dir = output_dir

            assert runner._verify_output() is False

    @patch("dazzle.deploy.analyzer.analyze_aws_requirements")
    @patch("dazzle.core.infra_analyzer.analyze_infra_requirements")
    def test_verify_output_clean(self, mock_infra_analyze, mock_aws_analyze):
        """Test verification passes for clean output."""
        mock_infra_analyze.return_value = create_mock_infra_reqs()
        mock_aws_analyze.return_value = create_mock_aws_reqs()

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            output_dir = project_root / "infra"
            output_dir.mkdir()

            # Create a clean file
            good_file = output_dir / "good_stack.py"
            good_file.write_text("from aws_cdk import Stack\n")

            spec = create_mock_spec()
            runner = DeploymentRunner(spec, project_root, DeploymentConfig())
            runner.output_dir = output_dir

            assert runner._verify_output() is True


class TestDeployVersion:
    """Tests for deploy version constant."""

    def test_version_format(self):
        """Test version format is semantic."""
        parts = DEPLOY_VERSION.split(".")

        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)


class TestDeploymentRunnerGenerators:
    """Tests for DeploymentRunner generator management."""

    @patch("dazzle.deploy.analyzer.analyze_aws_requirements")
    @patch("dazzle.core.infra_analyzer.analyze_infra_requirements")
    def test_get_generators_order(self, mock_infra_analyze, mock_aws_analyze):
        """Test generators are returned in dependency order."""
        mock_infra_analyze.return_value = create_mock_infra_reqs()

        aws_reqs = create_mock_aws_reqs()
        aws_reqs.needs_s3 = True
        aws_reqs.needs_sqs = True
        aws_reqs.needs_eventbridge = True
        mock_aws_analyze.return_value = aws_reqs

        with TemporaryDirectory() as tmpdir:
            spec = create_mock_spec()
            runner = DeploymentRunner(spec, Path(tmpdir), DeploymentConfig())

            generators = runner._get_generators()

            # Check order: Network -> Data -> Messaging -> Compute -> Observability
            names = [g.stack_name for g in generators]
            assert names == ["Network", "Data", "Messaging", "Compute", "Observability"]
