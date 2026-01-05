"""
Unit tests for TigerBeetle preflight validation stage.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


class TestTigerBeetleStage:
    """Test TigerBeetleStage validation logic."""

    @pytest.fixture
    def mock_context(self, tmp_path: Path) -> MagicMock:
        """Create a mock stage context."""
        from dazzle.deploy.preflight.models import PreflightConfig

        context = MagicMock()
        context.project_root = tmp_path
        context.infra_dir = tmp_path / "cdk"
        context.synth_output_dir = tmp_path / "cdk.out"
        context.config = PreflightConfig()
        context.app_name = "test-app"
        context.region = "us-east-1"
        return context

    @pytest.fixture
    def sample_template(self) -> dict:
        """Create a sample TigerBeetle CloudFormation template."""
        return {
            "Resources": {
                "TigerBeetleASG": {
                    "Type": "AWS::AutoScaling::AutoScalingGroup",
                    "Properties": {
                        "MinSize": 3,
                        "MaxSize": 3,
                        "DesiredCapacity": 3,
                    },
                },
                "TigerBeetleLaunchTemplate": {
                    "Type": "AWS::EC2::LaunchTemplate",
                    "Properties": {
                        "LaunchTemplateData": {
                            "BlockDeviceMappings": [
                                {
                                    "DeviceName": "/dev/xvda",
                                    "Ebs": {"VolumeType": "gp3", "VolumeSize": 20},
                                },
                                {
                                    "DeviceName": "/dev/xvdb",
                                    "Ebs": {
                                        "VolumeType": "gp3",
                                        "VolumeSize": 100,
                                        "Iops": 10000,
                                    },
                                },
                            ],
                        },
                    },
                },
                "TigerBeetleSecurityGroup": {
                    "Type": "AWS::EC2::SecurityGroup",
                    "Properties": {
                        "GroupDescription": "Security group for TigerBeetle cluster",
                        "SecurityGroupIngress": [
                            {
                                "IpProtocol": "tcp",
                                "FromPort": 3000,
                                "ToPort": 3000,
                                "SourceSecurityGroupId": {"Ref": "EcsSecurityGroup"},
                            },
                            {
                                "IpProtocol": "tcp",
                                "FromPort": 3001,
                                "ToPort": 3001,
                                "SourceSecurityGroupId": {"Ref": "TigerBeetleSecurityGroup"},
                            },
                        ],
                    },
                },
            },
        }

    def test_stage_name(self, mock_context: MagicMock) -> None:
        """Stage name should be 'tigerbeetle'."""
        from dazzle.deploy.preflight.stages.tigerbeetle import TigerBeetleStage

        stage = TigerBeetleStage(mock_context)
        assert stage.name == "tigerbeetle"

    def test_should_skip_when_no_synth_output(self, mock_context: MagicMock) -> None:
        """Should skip when synth output doesn't exist."""
        from dazzle.deploy.preflight.stages.tigerbeetle import TigerBeetleStage

        mock_context.synth_output_dir = None

        stage = TigerBeetleStage(mock_context)
        should_skip, reason = stage.should_skip()

        assert should_skip is True
        assert "No synth output" in reason

    def test_should_skip_when_no_tigerbeetle_template(
        self, mock_context: MagicMock, tmp_path: Path
    ) -> None:
        """Should skip when no TigerBeetle template exists."""
        from dazzle.deploy.preflight.stages.tigerbeetle import TigerBeetleStage

        # Create synth output dir without TigerBeetle template
        synth_dir = tmp_path / "cdk.out"
        synth_dir.mkdir()
        (synth_dir / "NetworkStack.template.json").write_text("{}")

        mock_context.synth_output_dir = synth_dir

        stage = TigerBeetleStage(mock_context)
        should_skip, reason = stage.should_skip()

        assert should_skip is True
        assert "No TigerBeetle stack" in reason

    def test_should_not_skip_when_tigerbeetle_template_exists(
        self, mock_context: MagicMock, tmp_path: Path, sample_template: dict
    ) -> None:
        """Should not skip when TigerBeetle template exists."""
        from dazzle.deploy.preflight.stages.tigerbeetle import TigerBeetleStage

        # Create synth output dir with TigerBeetle template
        synth_dir = tmp_path / "cdk.out"
        synth_dir.mkdir()
        (synth_dir / "TigerBeetleStack.template.json").write_text(json.dumps(sample_template))

        mock_context.synth_output_dir = synth_dir

        stage = TigerBeetleStage(mock_context)
        should_skip, _ = stage.should_skip()

        assert should_skip is False


class TestNodeCountValidation:
    """Test node count validation."""

    @pytest.fixture
    def mock_context(self, tmp_path: Path) -> MagicMock:
        """Create a mock stage context."""
        from dazzle.deploy.preflight.models import PreflightConfig

        context = MagicMock()
        context.project_root = tmp_path
        context.synth_output_dir = tmp_path / "cdk.out"
        context.config = PreflightConfig()
        context.app_name = "test-app"
        context.region = "us-east-1"
        return context

    def test_even_node_count_critical_finding(
        self, mock_context: MagicMock, tmp_path: Path
    ) -> None:
        """Even node count should produce critical finding."""
        from dazzle.deploy.preflight.models import FindingSeverity
        from dazzle.deploy.preflight.stages.tigerbeetle import TigerBeetleStage

        template = {
            "Resources": {
                "TigerBeetleASG": {
                    "Type": "AWS::AutoScaling::AutoScalingGroup",
                    "Properties": {
                        "MinSize": 2,
                        "MaxSize": 2,
                        "DesiredCapacity": 2,
                    },
                },
            },
        }

        synth_dir = tmp_path / "cdk.out"
        synth_dir.mkdir()
        (synth_dir / "TigerBeetleStack.template.json").write_text(json.dumps(template))
        mock_context.synth_output_dir = synth_dir

        stage = TigerBeetleStage(mock_context)
        result = stage.run()

        # Should have critical finding for even node count
        critical_findings = [f for f in result.findings if f.severity == FindingSeverity.CRITICAL]
        assert len(critical_findings) >= 1
        assert any("odd" in f.message.lower() for f in critical_findings)

    def test_odd_node_count_no_critical_finding(
        self, mock_context: MagicMock, tmp_path: Path
    ) -> None:
        """Odd node count should not produce critical finding."""
        from dazzle.deploy.preflight.models import FindingSeverity
        from dazzle.deploy.preflight.stages.tigerbeetle import TigerBeetleStage

        template = {
            "Resources": {
                "TigerBeetleASG": {
                    "Type": "AWS::AutoScaling::AutoScalingGroup",
                    "Properties": {
                        "MinSize": 3,
                        "MaxSize": 3,
                        "DesiredCapacity": 3,
                    },
                },
            },
        }

        synth_dir = tmp_path / "cdk.out"
        synth_dir.mkdir()
        (synth_dir / "TigerBeetleStack.template.json").write_text(json.dumps(template))
        mock_context.synth_output_dir = synth_dir

        stage = TigerBeetleStage(mock_context)
        result = stage.run()

        # Should not have critical finding for odd node count
        critical_findings = [
            f
            for f in result.findings
            if f.severity == FindingSeverity.CRITICAL and "even" in f.code.lower()
        ]
        assert len(critical_findings) == 0


class TestVolumeIOPSValidation:
    """Test EBS volume IOPS validation."""

    @pytest.fixture
    def mock_context(self, tmp_path: Path) -> MagicMock:
        """Create a mock stage context."""
        from dazzle.deploy.preflight.models import PreflightConfig

        context = MagicMock()
        context.project_root = tmp_path
        context.synth_output_dir = tmp_path / "cdk.out"
        context.config = PreflightConfig()
        context.app_name = "test-app"
        context.region = "us-east-1"
        return context

    def test_low_iops_high_finding(self, mock_context: MagicMock, tmp_path: Path) -> None:
        """Low IOPS should produce high severity finding."""
        from dazzle.deploy.preflight.models import FindingSeverity
        from dazzle.deploy.preflight.stages.tigerbeetle import TigerBeetleStage

        template = {
            "Resources": {
                "TigerBeetleLaunchTemplate": {
                    "Type": "AWS::EC2::LaunchTemplate",
                    "Properties": {
                        "LaunchTemplateData": {
                            "BlockDeviceMappings": [
                                {
                                    "DeviceName": "/dev/xvdb",
                                    "Ebs": {
                                        "VolumeType": "gp3",
                                        "VolumeSize": 100,
                                        "Iops": 3000,  # Below minimum
                                    },
                                },
                            ],
                        },
                    },
                },
            },
        }

        synth_dir = tmp_path / "cdk.out"
        synth_dir.mkdir()
        (synth_dir / "TigerBeetleStack.template.json").write_text(json.dumps(template))
        mock_context.synth_output_dir = synth_dir

        stage = TigerBeetleStage(mock_context)
        result = stage.run()

        # Should have high severity finding for low IOPS
        high_findings = [
            f
            for f in result.findings
            if f.severity == FindingSeverity.HIGH and "iops" in f.code.lower()
        ]
        assert len(high_findings) >= 1

    def test_sufficient_iops_info_finding(self, mock_context: MagicMock, tmp_path: Path) -> None:
        """Sufficient IOPS should produce info finding."""
        from dazzle.deploy.preflight.models import FindingSeverity
        from dazzle.deploy.preflight.stages.tigerbeetle import TigerBeetleStage

        template = {
            "Resources": {
                "TigerBeetleLaunchTemplate": {
                    "Type": "AWS::EC2::LaunchTemplate",
                    "Properties": {
                        "LaunchTemplateData": {
                            "BlockDeviceMappings": [
                                {
                                    "DeviceName": "/dev/xvdb",
                                    "Ebs": {
                                        "VolumeType": "gp3",
                                        "VolumeSize": 100,
                                        "Iops": 10000,  # Meets recommended
                                    },
                                },
                            ],
                        },
                    },
                },
            },
        }

        synth_dir = tmp_path / "cdk.out"
        synth_dir.mkdir()
        (synth_dir / "TigerBeetleStack.template.json").write_text(json.dumps(template))
        mock_context.synth_output_dir = synth_dir

        stage = TigerBeetleStage(mock_context)
        result = stage.run()

        # Should have info finding for sufficient IOPS
        info_findings = [
            f
            for f in result.findings
            if f.severity == FindingSeverity.INFO and "iops_ok" in f.code.lower()
        ]
        assert len(info_findings) >= 1


class TestNetworkIsolationValidation:
    """Test network isolation validation."""

    @pytest.fixture
    def mock_context(self, tmp_path: Path) -> MagicMock:
        """Create a mock stage context."""
        from dazzle.deploy.preflight.models import PreflightConfig

        context = MagicMock()
        context.project_root = tmp_path
        context.synth_output_dir = tmp_path / "cdk.out"
        context.config = PreflightConfig()
        context.app_name = "test-app"
        context.region = "us-east-1"
        return context

    def test_public_access_critical_finding(self, mock_context: MagicMock, tmp_path: Path) -> None:
        """Public access to TigerBeetle ports should produce critical finding."""
        from dazzle.deploy.preflight.models import FindingSeverity
        from dazzle.deploy.preflight.stages.tigerbeetle import TigerBeetleStage

        template = {
            "Resources": {
                "TigerBeetleSecurityGroup": {
                    "Type": "AWS::EC2::SecurityGroup",
                    "Properties": {
                        "GroupDescription": "Security group for TigerBeetle",
                        "SecurityGroupIngress": [
                            {
                                "IpProtocol": "tcp",
                                "FromPort": 3000,
                                "ToPort": 3000,
                                "CidrIp": "0.0.0.0/0",  # Public access!
                            },
                        ],
                    },
                },
            },
        }

        synth_dir = tmp_path / "cdk.out"
        synth_dir.mkdir()
        (synth_dir / "TigerBeetleStack.template.json").write_text(json.dumps(template))
        mock_context.synth_output_dir = synth_dir

        stage = TigerBeetleStage(mock_context)
        result = stage.run()

        # Should have critical finding for public access
        critical_findings = [
            f
            for f in result.findings
            if f.severity == FindingSeverity.CRITICAL and "public" in f.code.lower()
        ]
        assert len(critical_findings) >= 1

    def test_private_access_no_critical_finding(
        self, mock_context: MagicMock, tmp_path: Path
    ) -> None:
        """Private access should not produce critical finding."""
        from dazzle.deploy.preflight.models import FindingSeverity
        from dazzle.deploy.preflight.stages.tigerbeetle import TigerBeetleStage

        template = {
            "Resources": {
                "TigerBeetleSecurityGroup": {
                    "Type": "AWS::EC2::SecurityGroup",
                    "Properties": {
                        "GroupDescription": "Security group for TigerBeetle",
                        "SecurityGroupIngress": [
                            {
                                "IpProtocol": "tcp",
                                "FromPort": 3000,
                                "ToPort": 3000,
                                "SourceSecurityGroupId": {"Ref": "EcsSecurityGroup"},
                            },
                        ],
                    },
                },
            },
        }

        synth_dir = tmp_path / "cdk.out"
        synth_dir.mkdir()
        (synth_dir / "TigerBeetleStack.template.json").write_text(json.dumps(template))
        mock_context.synth_output_dir = synth_dir

        stage = TigerBeetleStage(mock_context)
        result = stage.run()

        # Should not have critical finding for private access
        public_findings = [
            f
            for f in result.findings
            if f.severity == FindingSeverity.CRITICAL and "public" in f.code.lower()
        ]
        assert len(public_findings) == 0


class TestStageIntegration:
    """Test TigerBeetle stage integration."""

    def test_stage_exported_from_package(self) -> None:
        """TigerBeetleStage should be exported from stages package."""
        from dazzle.deploy.preflight.stages import TigerBeetleStage

        assert TigerBeetleStage is not None
        assert hasattr(TigerBeetleStage, "name")
        assert hasattr(TigerBeetleStage, "run")

    def test_stage_constant_defined(self) -> None:
        """STAGE_TIGERBEETLE constant should be defined."""
        from dazzle.deploy.preflight.models import STAGE_TIGERBEETLE

        assert STAGE_TIGERBEETLE == "tigerbeetle"
