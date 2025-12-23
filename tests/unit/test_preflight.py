"""Tests for preflight validation system."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dazzle.deploy.preflight import (
    Finding,
    FindingSeverity,
    PreflightConfig,
    PreflightMode,
    PreflightReport,
    PreflightRunner,
    PreflightSummary,
    StageResult,
    StageStatus,
)
from dazzle.deploy.preflight.stages.base import StageContext


class TestFinding:
    """Tests for Finding dataclass."""

    def test_basic_finding(self):
        """Test creating a basic finding."""
        finding = Finding(
            severity=FindingSeverity.HIGH,
            code="TEST_CODE",
            message="Test message",
        )

        assert finding.severity == FindingSeverity.HIGH
        assert finding.code == "TEST_CODE"
        assert finding.message == "Test message"
        assert finding.resource is None
        assert finding.remediation is None

    def test_finding_with_all_fields(self):
        """Test creating a finding with all fields."""
        finding = Finding(
            severity=FindingSeverity.CRITICAL,
            code="FULL_FINDING",
            message="Full message",
            resource="AWS::S3::Bucket/MyBucket",
            remediation="Fix it this way",
            stage="assertions",
            file_path="/path/to/template.json",
            line_number=42,
        )

        assert finding.resource == "AWS::S3::Bucket/MyBucket"
        assert finding.remediation == "Fix it this way"
        assert finding.stage == "assertions"
        assert finding.file_path == "/path/to/template.json"
        assert finding.line_number == 42

    def test_finding_to_dict(self):
        """Test finding serialization."""
        finding = Finding(
            severity=FindingSeverity.WARN,
            code="DICT_TEST",
            message="Serializable message",
        )

        result = finding.to_dict()

        assert result["severity"] == "warn"
        assert result["code"] == "DICT_TEST"
        assert result["message"] == "Serializable message"


class TestStageResult:
    """Tests for StageResult dataclass."""

    def test_default_stage_result(self):
        """Test default stage result."""
        result = StageResult(name="test_stage")

        assert result.name == "test_stage"
        assert result.status == StageStatus.PENDING
        assert result.duration_ms == 0
        assert result.findings == []
        assert result.artifacts == []

    def test_passed_property(self):
        """Test passed property."""
        result = StageResult(name="test")
        assert result.passed is False

        result.status = StageStatus.PASSED
        assert result.passed is True

    def test_failed_property(self):
        """Test failed property."""
        result = StageResult(name="test")
        assert result.failed is False

        result.status = StageStatus.FAILED
        assert result.failed is True

    def test_add_finding(self):
        """Test adding findings to stage."""
        result = StageResult(name="test_stage")
        finding = Finding(
            severity=FindingSeverity.INFO,
            code="TEST",
            message="Test finding",
        )

        result.add_finding(finding)

        assert len(result.findings) == 1
        assert result.findings[0].stage == "test_stage"

    def test_add_artifact(self):
        """Test adding artifacts."""
        result = StageResult(name="test")

        result.add_artifact("template", "/path/to/template.json")

        assert len(result.artifacts) == 1
        assert result.artifacts[0]["type"] == "template"
        assert result.artifacts[0]["path"] == "/path/to/template.json"

    def test_to_dict(self):
        """Test stage result serialization."""
        result = StageResult(name="test_stage", status=StageStatus.PASSED)
        result.duration_ms = 100

        data = result.to_dict()

        assert data["name"] == "test_stage"
        assert data["status"] == "passed"
        assert data["duration_ms"] == 100


class TestPreflightSummary:
    """Tests for PreflightSummary dataclass."""

    def test_default_summary(self):
        """Test default summary values."""
        summary = PreflightSummary(status="passed")

        assert summary.status == "passed"
        assert summary.total_findings == 0
        assert summary.critical_count == 0
        assert summary.can_proceed is True

    def test_can_proceed_with_critical(self):
        """Test can_proceed is False with critical findings."""
        summary = PreflightSummary(status="failed", critical_count=1)

        assert summary.can_proceed is False

    def test_can_proceed_with_high(self):
        """Test can_proceed is False with high findings."""
        summary = PreflightSummary(status="blocked", high_count=1)

        assert summary.can_proceed is False

    def test_can_proceed_with_warn_only(self):
        """Test can_proceed is True with only warnings."""
        summary = PreflightSummary(status="passed", warn_count=5)

        assert summary.can_proceed is True


class TestPreflightReport:
    """Tests for PreflightReport dataclass."""

    def test_create_report(self):
        """Test creating a preflight report."""
        report = PreflightReport(
            run_id="pf-test123",
            timestamp_utc="2024-01-01T00:00:00Z",
            app_name="test-app",
            app_version="1.0.0",
            commit_sha="abc123",
            env_name="staging",
            account_id=None,
            region="us-east-1",
            mode=PreflightMode.STATIC_ONLY,
        )

        assert report.run_id == "pf-test123"
        assert report.app_name == "test-app"
        assert report.mode == PreflightMode.STATIC_ONLY

    def test_compute_summary(self):
        """Test computing summary from stages."""
        report = PreflightReport(
            run_id="pf-test",
            timestamp_utc="2024-01-01T00:00:00Z",
            app_name="test",
            app_version="1.0.0",
            commit_sha=None,
            env_name="staging",
            account_id=None,
            region="us-east-1",
            mode=PreflightMode.STATIC_ONLY,
        )

        # Add stages
        passed_stage = StageResult(name="stage1", status=StageStatus.PASSED)
        passed_stage.add_finding(
            Finding(severity=FindingSeverity.INFO, code="INFO", message="Info")
        )

        failed_stage = StageResult(name="stage2", status=StageStatus.FAILED)
        failed_stage.add_finding(
            Finding(severity=FindingSeverity.CRITICAL, code="CRIT", message="Critical")
        )
        failed_stage.add_finding(
            Finding(severity=FindingSeverity.HIGH, code="HIGH", message="High")
        )

        skipped_stage = StageResult(name="stage3", status=StageStatus.SKIPPED)

        report.stages = [passed_stage, failed_stage, skipped_stage]

        summary = report.compute_summary()

        assert summary.status == "failed"
        assert summary.stages_passed == 1
        assert summary.stages_failed == 1
        assert summary.stages_skipped == 1
        assert summary.total_findings == 3
        assert summary.critical_count == 1
        assert summary.high_count == 1
        assert summary.info_count == 1
        assert summary.can_proceed is False

    def test_to_dict(self):
        """Test report serialization."""
        report = PreflightReport(
            run_id="pf-dict",
            timestamp_utc="2024-01-01T00:00:00Z",
            app_name="dict-test",
            app_version="1.0.0",
            commit_sha="abc",
            env_name="staging",
            account_id="123456789012",
            region="eu-west-1",
            mode=PreflightMode.PLAN_ONLY,
        )

        data = report.to_dict()

        assert data["run_id"] == "pf-dict"
        assert data["app"]["name"] == "dict-test"
        assert data["env"]["region"] == "eu-west-1"
        assert data["mode"] == "plan_only"


class TestPreflightConfig:
    """Tests for PreflightConfig dataclass."""

    def test_default_config(self):
        """Test default configuration."""
        config = PreflightConfig()

        assert config.mode == PreflightMode.STATIC_ONLY
        assert config.fail_on_high is True
        assert config.fail_on_warn is False
        assert config.skip_stages == []

    def test_custom_config(self):
        """Test custom configuration."""
        config = PreflightConfig(
            mode=PreflightMode.SANDBOX_APPLY,
            fail_on_high=False,
            skip_stages=["lint", "guardrails"],
        )

        assert config.mode == PreflightMode.SANDBOX_APPLY
        assert config.fail_on_high is False
        assert "lint" in config.skip_stages


class TestStageContext:
    """Tests for StageContext."""

    def test_create_context(self):
        """Test creating stage context."""
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            infra = project / "infra"
            config = PreflightConfig()

            context = StageContext(
                project_root=project,
                infra_dir=infra,
                config=config,
            )

            assert context.project_root == project
            assert context.infra_dir == infra
            assert context.app_name == ""
            assert context.templates == {}


class TestPreflightRunner:
    """Tests for PreflightRunner."""

    def test_runner_initialization(self):
        """Test runner initialization."""
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir).resolve()

            runner = PreflightRunner(project_root=project)

            assert runner.project_root == project
            assert runner.infra_dir == project / "infra"
            assert runner.run_id.startswith("pf-")

    def test_runner_with_custom_infra_dir(self):
        """Test runner with custom infra directory."""
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir).resolve()
            infra = project / "custom_infra"

            runner = PreflightRunner(
                project_root=project,
                infra_dir=infra,
            )

            assert runner.infra_dir == infra

    @patch("dazzle.deploy.preflight.stages.bootstrap.shutil.which")
    def test_runner_run_basic(self, mock_which):
        """Test basic runner execution."""
        mock_which.return_value = None  # No tools found

        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            infra = project / "infra"
            infra.mkdir()

            runner = PreflightRunner(project_root=project)
            report = runner.run()

            assert report is not None
            assert report.run_id == runner.run_id
            assert len(report.stages) > 0
            assert report.summary is not None


class TestAssertionsStage:
    """Tests for template assertions."""

    def test_rds_public_access_finding(self):
        """Test detection of public RDS instance."""
        from dazzle.deploy.preflight.stages.assertions import AssertionsStage

        with TemporaryDirectory() as tmpdir:
            context = StageContext(
                project_root=Path(tmpdir),
                infra_dir=Path(tmpdir) / "infra",
                config=PreflightConfig(),
            )

            # Add a template with public RDS
            context.templates["TestStack"] = {
                "Resources": {
                    "Database": {
                        "Type": "AWS::RDS::DBInstance",
                        "Properties": {
                            "PubliclyAccessible": True,
                            "StorageEncrypted": False,
                        },
                    }
                }
            }

            stage = AssertionsStage(context)
            result = stage.run()

            # Should have findings for public access and no encryption
            codes = [f.code for f in result.findings]
            assert "RDS_PUBLIC_ACCESS" in codes
            assert "RDS_NOT_ENCRYPTED" in codes

    def test_s3_no_public_block_finding(self):
        """Test detection of S3 without public access block."""
        from dazzle.deploy.preflight.stages.assertions import AssertionsStage

        with TemporaryDirectory() as tmpdir:
            context = StageContext(
                project_root=Path(tmpdir),
                infra_dir=Path(tmpdir) / "infra",
                config=PreflightConfig(),
            )

            context.templates["TestStack"] = {
                "Resources": {
                    "Bucket": {
                        "Type": "AWS::S3::Bucket",
                        "Properties": {},
                    }
                }
            }

            stage = AssertionsStage(context)
            result = stage.run()

            codes = [f.code for f in result.findings]
            assert "S3_NO_PUBLIC_ACCESS_BLOCK" in codes

    def test_security_group_open_ssh(self):
        """Test detection of security group with open SSH."""
        from dazzle.deploy.preflight.stages.assertions import AssertionsStage

        with TemporaryDirectory() as tmpdir:
            context = StageContext(
                project_root=Path(tmpdir),
                infra_dir=Path(tmpdir) / "infra",
                config=PreflightConfig(),
            )

            context.templates["TestStack"] = {
                "Resources": {
                    "SG": {
                        "Type": "AWS::EC2::SecurityGroup",
                        "Properties": {
                            "SecurityGroupIngress": [
                                {
                                    "CidrIp": "0.0.0.0/0",
                                    "FromPort": 22,
                                    "ToPort": 22,
                                    "IpProtocol": "tcp",
                                }
                            ]
                        },
                    }
                }
            }

            stage = AssertionsStage(context)
            result = stage.run()

            codes = [f.code for f in result.findings]
            assert "SG_SSH_OPEN" in codes


class TestReportGenerator:
    """Tests for report generation."""

    def test_generate_json(self):
        """Test JSON report generation."""
        from dazzle.deploy.preflight.report import ReportGenerator

        report = PreflightReport(
            run_id="pf-json",
            timestamp_utc="2024-01-01T00:00:00Z",
            app_name="json-test",
            app_version="1.0.0",
            commit_sha=None,
            env_name="staging",
            account_id=None,
            region="us-east-1",
            mode=PreflightMode.STATIC_ONLY,
        )
        report.compute_summary()

        generator = ReportGenerator(report)
        json_str = generator.generate_json()

        data = json.loads(json_str)
        assert data["run_id"] == "pf-json"
        assert data["app"]["name"] == "json-test"

    def test_generate_markdown(self):
        """Test Markdown report generation."""
        from dazzle.deploy.preflight.report import ReportGenerator

        report = PreflightReport(
            run_id="pf-md",
            timestamp_utc="2024-01-01T00:00:00Z",
            app_name="md-test",
            app_version="1.0.0",
            commit_sha="abc123",
            env_name="staging",
            account_id=None,
            region="us-east-1",
            mode=PreflightMode.STATIC_ONLY,
        )

        stage = StageResult(name="test_stage", status=StageStatus.PASSED)
        stage.add_finding(
            Finding(
                severity=FindingSeverity.WARN,
                code="TEST_WARN",
                message="Test warning message",
            )
        )
        report.stages.append(stage)
        report.compute_summary()

        generator = ReportGenerator(report)
        md = generator.generate_markdown()

        assert "# Pre-Flight Validation Report" in md
        assert "pf-md" in md
        assert "md-test" in md
        assert "TEST_WARN" in md

    def test_generate_report_files(self):
        """Test saving reports to files."""
        from dazzle.deploy.preflight import generate_report

        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "reports"

            report = PreflightReport(
                run_id="pf-file",
                timestamp_utc="2024-01-01T00:00:00Z",
                app_name="file-test",
                app_version="1.0.0",
                commit_sha=None,
                env_name="staging",
                account_id=None,
                region="us-east-1",
                mode=PreflightMode.STATIC_ONLY,
            )
            report.compute_summary()

            result = generate_report(report, output_dir)

            assert "json" in result
            assert "md" in result
            assert result["json"].exists()
            assert result["md"].exists()
