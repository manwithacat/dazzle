"""
Stage 3: Static Linting.

Runs cfn-lint on synthesized CloudFormation templates.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..models import (
    STAGE_LINT,
    Finding,
    FindingSeverity,
)
from .base import PreflightStage


class LintStage(PreflightStage):
    """
    Static linting stage using cfn-lint.

    Runs cfn-lint on the synthesized CloudFormation templates
    to catch common errors and best practice violations.
    """

    @property
    def name(self) -> str:
        return STAGE_LINT

    def should_skip(self) -> tuple[bool, str | None]:
        """Check if linting should be skipped."""
        skip, reason = super().should_skip()
        if skip:
            return skip, reason

        # Skip if no synth output
        if not self.context.synth_output_dir:
            return True, "No synth output available"

        if not self.context.synth_output_dir.exists():
            return True, "Synth output directory does not exist"

        # Check if cfn-lint is available
        if not shutil.which("cfn-lint"):
            # Try to install it
            self.add_finding(
                Finding(
                    severity=FindingSeverity.WARN,
                    code="CFN_LINT_NOT_FOUND",
                    message="cfn-lint not found, skipping lint stage",
                    remediation="Install with: pip install cfn-lint",
                )
            )
            return True, "cfn-lint not installed"

        return False, None

    def _execute(self) -> None:
        """Execute cfn-lint on templates."""
        synth_dir = self.context.synth_output_dir
        if not synth_dir:
            return

        # Find all template files
        template_files = list(synth_dir.glob("*.template.json"))

        if not template_files:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.INFO,
                    code="NO_TEMPLATES_TO_LINT",
                    message="No CloudFormation templates found to lint",
                )
            )
            return

        # Run cfn-lint on each template
        for template_file in template_files:
            self._lint_template(template_file)

    def _lint_template(self, template_path: Path) -> None:
        """Run cfn-lint on a single template."""
        try:
            result = subprocess.run(
                [
                    "cfn-lint",
                    str(template_path),
                    "--format",
                    "json",
                    # Ignore some noisy rules that CDK generates
                    "--ignore-checks",
                    "W3002",  # Local path not available during transform
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.stdout:
                self._parse_cfn_lint_output(result.stdout, template_path)

        except subprocess.TimeoutExpired:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.WARN,
                    code="LINT_TIMEOUT",
                    message=f"cfn-lint timed out on {template_path.name}",
                    file_path=str(template_path),
                )
            )
        except FileNotFoundError:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.WARN,
                    code="CFN_LINT_ERROR",
                    message="cfn-lint not found",
                    remediation="Install with: pip install cfn-lint",
                )
            )
        except Exception as e:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.WARN,
                    code="LINT_ERROR",
                    message=f"cfn-lint error: {e}",
                    file_path=str(template_path),
                )
            )

    def _parse_cfn_lint_output(self, output: str, template_path: Path) -> None:
        """Parse cfn-lint JSON output and create findings."""
        try:
            issues = json.loads(output)
        except json.JSONDecodeError:
            return

        for issue in issues:
            # Map cfn-lint levels to our severity
            level = issue.get("Level", "Warning")
            severity = self._map_severity(level)

            # Extract location info
            filename = issue.get("Filename", str(template_path))
            location = issue.get("Location", {})
            line_number = None
            if location.get("Start"):
                line_number = location["Start"].get("LineNumber")

            # Create finding
            self.add_finding(
                Finding(
                    severity=severity,
                    code=issue.get("Rule", {}).get("Id", "CFN_LINT"),
                    message=issue.get("Message", "Unknown lint issue"),
                    resource=self._format_path(location.get("Path", [])),
                    file_path=filename,
                    line_number=line_number,
                    remediation=issue.get("Rule", {}).get("Description"),
                )
            )

    def _map_severity(self, cfn_lint_level: str) -> FindingSeverity:
        """Map cfn-lint levels to our severity enum."""
        mapping = {
            "Error": FindingSeverity.HIGH,
            "Warning": FindingSeverity.WARN,
            "Informational": FindingSeverity.INFO,
        }
        return mapping.get(cfn_lint_level, FindingSeverity.WARN)

    def _format_path(self, path: list[Any]) -> str | None:
        """Format a cfn-lint path array to a readable string."""
        if not path:
            return None
        return "/".join(str(p) for p in path)
