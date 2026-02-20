"""
Stage 0: Bootstrap & Context Load.

Validates toolchain versions and loads project context.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

from ..models import (
    STAGE_BOOTSTRAP,
    Finding,
    FindingSeverity,
)
from .base import PreflightStage

logger = logging.getLogger(__name__)


class BootstrapStage(PreflightStage):
    """
    Bootstrap stage that validates the environment and loads context.

    Checks:
    - CDK CLI availability and version
    - Node.js version
    - Python version
    - AWS CLI (optional, for plan_only and sandbox modes)
    - Project structure and configuration
    """

    @property
    def name(self) -> str:
        return STAGE_BOOTSTRAP

    def _execute(self) -> None:
        """Execute bootstrap checks."""
        self._check_cdk_cli()
        self._check_node_version()
        self._check_python_version()
        self._check_aws_cli()
        self._load_project_context()
        self._validate_infra_directory()

    def _check_cdk_cli(self) -> None:
        """Check CDK CLI availability and version."""
        cdk_path = shutil.which("cdk")

        if not cdk_path:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.CRITICAL,
                    code="CDK_NOT_FOUND",
                    message="AWS CDK CLI not found in PATH",
                    remediation="Install with: npm install -g aws-cdk",
                )
            )
            return

        try:
            result = subprocess.run(
                ["cdk", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            version_output = result.stdout.strip()

            # Parse version (format: "2.x.x (build xxxxx)")
            version = version_output.split()[0] if version_output else "unknown"
            self.context.toolchain["cdk"] = version

            # Check minimum version if specified
            if self.context.config.required_cdk_version:
                if not self._version_satisfies(version, self.context.config.required_cdk_version):
                    self.add_finding(
                        Finding(
                            severity=FindingSeverity.HIGH,
                            code="CDK_VERSION_MISMATCH",
                            message=(
                                f"CDK version {version} does not satisfy "
                                f"requirement {self.context.config.required_cdk_version}"
                            ),
                            remediation="Update CDK: npm install -g aws-cdk@latest",
                        )
                    )

        except subprocess.TimeoutExpired:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.HIGH,
                    code="CDK_TIMEOUT",
                    message="CDK version check timed out",
                )
            )
        except Exception as e:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.WARN,
                    code="CDK_VERSION_ERROR",
                    message=f"Could not determine CDK version: {e}",
                )
            )

    def _check_node_version(self) -> None:
        """Check Node.js version."""
        node_path = shutil.which("node")

        if not node_path:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.CRITICAL,
                    code="NODE_NOT_FOUND",
                    message="Node.js not found in PATH",
                    remediation="Install Node.js 18 or higher",
                )
            )
            return

        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            version = result.stdout.strip().lstrip("v")
            self.context.toolchain["node"] = version

            # Check minimum version
            if self.context.config.required_node_version:
                if not self._version_satisfies(version, self.context.config.required_node_version):
                    self.add_finding(
                        Finding(
                            severity=FindingSeverity.HIGH,
                            code="NODE_VERSION_MISMATCH",
                            message=(
                                f"Node.js version {version} does not satisfy "
                                f"requirement {self.context.config.required_node_version}"
                            ),
                        )
                    )

        except Exception as e:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.WARN,
                    code="NODE_VERSION_ERROR",
                    message=f"Could not determine Node.js version: {e}",
                )
            )

    def _check_python_version(self) -> None:
        """Check Python version."""
        import sys

        version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        self.context.toolchain["python"] = version

        # Check minimum version
        if self.context.config.required_python_version:
            if not self._version_satisfies(version, self.context.config.required_python_version):
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.HIGH,
                        code="PYTHON_VERSION_MISMATCH",
                        message=(
                            f"Python version {version} does not satisfy "
                            f"requirement {self.context.config.required_python_version}"
                        ),
                    )
                )

    def _check_aws_cli(self) -> None:
        """Check AWS CLI availability (optional for static_only mode)."""
        from ..models import PreflightMode

        aws_path = shutil.which("aws")

        if not aws_path:
            # Only critical for non-static modes
            if self.context.config.mode != PreflightMode.STATIC_ONLY:
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.CRITICAL,
                        code="AWS_CLI_NOT_FOUND",
                        message="AWS CLI not found (required for plan/sandbox modes)",
                        remediation="Install AWS CLI: https://aws.amazon.com/cli/",
                    )
                )
            else:
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.INFO,
                        code="AWS_CLI_NOT_FOUND",
                        message="AWS CLI not found (optional for static_only mode)",
                    )
                )
            return

        try:
            result = subprocess.run(
                ["aws", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # Parse "aws-cli/2.x.x Python/3.x.x ..."
            version_parts = result.stdout.strip().split()
            if version_parts:
                version = version_parts[0].split("/")[1]
                self.context.toolchain["aws_cli"] = version

        except Exception:
            logger.debug("AWS CLI version check failed", exc_info=True)

    def _load_project_context(self) -> None:
        """Load project context from configuration files."""
        # Try to get git commit SHA
        if (self.context.project_root / ".git").exists():
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=self.context.project_root,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    self.context.commit_sha = result.stdout.strip()[:12]
            except Exception:
                logger.debug("Failed to get git commit SHA", exc_info=True)

        # Try to load app info from dazzle.toml
        toml_path = self.context.project_root / "dazzle.toml"
        if toml_path.exists():
            try:
                import tomllib

                with open(toml_path, "rb") as f:
                    config = tomllib.load(f)

                project = config.get("project", {})
                self.context.app_name = project.get("name", "unknown")
                self.context.app_version = project.get("version", "0.0.0")

                deploy = config.get("deploy", {})
                if deploy.get("region"):
                    self.context.region = deploy["region"]

            except Exception as e:
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.WARN,
                        code="CONFIG_PARSE_ERROR",
                        message=f"Could not parse dazzle.toml: {e}",
                        file_path=str(toml_path),
                    )
                )

    def _validate_infra_directory(self) -> None:
        """Validate the infrastructure directory exists and has expected files."""
        if not self.context.infra_dir.exists():
            self.add_finding(
                Finding(
                    severity=FindingSeverity.CRITICAL,
                    code="INFRA_DIR_NOT_FOUND",
                    message=f"Infrastructure directory not found: {self.context.infra_dir}",
                    remediation="Run 'dazzle deploy generate' first",
                )
            )
            return

        # Check for required files
        required_files = ["app.py", "cdk.json"]
        for filename in required_files:
            filepath = self.context.infra_dir / filename
            if not filepath.exists():
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.HIGH,
                        code="REQUIRED_FILE_MISSING",
                        message=f"Required file not found: {filename}",
                        file_path=str(filepath),
                        remediation="Run 'dazzle deploy generate' to regenerate",
                    )
                )

        # Check for stacks directory
        stacks_dir = self.context.infra_dir / "stacks"
        if not stacks_dir.exists():
            self.add_finding(
                Finding(
                    severity=FindingSeverity.HIGH,
                    code="STACKS_DIR_MISSING",
                    message="Stacks directory not found",
                    remediation="Run 'dazzle deploy generate' to regenerate",
                )
            )

    def _version_satisfies(self, version: str, requirement: str) -> bool:
        """
        Check if a version satisfies a requirement.

        Simple implementation supporting:
        - Exact match: "2.100.0"
        - Minimum: ">=2.100.0"
        """
        try:
            # Parse version tuple
            def parse_version(v: str) -> tuple[int, ...]:
                return tuple(int(x) for x in v.split(".")[:3])

            if requirement.startswith(">="):
                req_version = parse_version(requirement[2:])
                return parse_version(version) >= req_version
            elif requirement.startswith(">"):
                req_version = parse_version(requirement[1:])
                return parse_version(version) > req_version
            elif requirement.startswith("<="):
                req_version = parse_version(requirement[2:])
                return parse_version(version) <= req_version
            elif requirement.startswith("<"):
                req_version = parse_version(requirement[1:])
                return parse_version(version) < req_version
            else:
                # Exact match
                return parse_version(version) == parse_version(requirement)

        except (ValueError, IndexError):
            return False
