"""
Stage 1: CDK Synthesis.

Runs 'cdk synth' to generate CloudFormation templates.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from ..models import (
    STAGE_SYNTH,
    Finding,
    FindingSeverity,
)
from .base import PreflightStage


class SynthStage(PreflightStage):
    """
    CDK Synthesis stage.

    Runs 'cdk synth' on the generated CDK code to produce
    CloudFormation templates for validation in subsequent stages.
    """

    @property
    def name(self) -> str:
        return STAGE_SYNTH

    def should_skip(self) -> tuple[bool, str | None]:
        """Check if synth should be skipped."""
        skip, reason = super().should_skip()
        if skip:
            return skip, reason

        # Skip if infra_dir doesn't exist (bootstrap failed)
        if not self.context.infra_dir.exists():
            return True, "Infrastructure directory not found (bootstrap failed)"

        # Check for app.py
        if not (self.context.infra_dir / "app.py").exists():
            return True, "app.py not found in infrastructure directory"

        return False, None

    def _execute(self) -> None:
        """Execute CDK synth."""
        # Create output directory for templates
        synth_output = self.context.infra_dir / "cdk.out"

        try:
            # Run cdk synth with JSON output
            result = subprocess.run(
                [
                    "cdk",
                    "synth",
                    "--output",
                    str(synth_output),
                    "--quiet",
                ],
                cwd=self.context.infra_dir,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            if result.returncode != 0:
                self._handle_synth_error(result.stderr)
                return

            # Store synth output directory
            self.context.synth_output_dir = synth_output

            # Load and validate templates
            self._load_templates(synth_output)

            # Add artifact reference
            self.add_artifact("synth_output", str(synth_output))

        except subprocess.TimeoutExpired:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.CRITICAL,
                    code="SYNTH_TIMEOUT",
                    message="CDK synthesis timed out after 5 minutes",
                    remediation="Check for infinite loops or complex constructs",
                )
            )
        except FileNotFoundError:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.CRITICAL,
                    code="CDK_NOT_FOUND",
                    message="CDK CLI not found",
                    remediation="Install with: npm install -g aws-cdk",
                )
            )
        except Exception as e:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.CRITICAL,
                    code="SYNTH_ERROR",
                    message=f"CDK synthesis failed: {e}",
                )
            )

    def _handle_synth_error(self, stderr: str) -> None:
        """Parse and report synth errors."""
        # Common error patterns
        error_patterns = [
            ("ModuleNotFoundError", "MISSING_DEPENDENCY", "Install missing Python packages"),
            (
                "Error: Cannot find module",
                "MISSING_NODE_MODULE",
                "Run 'npm install' in infra directory",
            ),
            ("ContextProvider", "CONTEXT_ERROR", "CDK context lookup failed"),
            ("jsii", "JSII_ERROR", "CDK/JSII binding error"),
            ("Construct", "CONSTRUCT_ERROR", "CDK construct error"),
        ]

        severity = FindingSeverity.CRITICAL

        for pattern, code, remediation in error_patterns:
            if pattern in stderr:
                self.add_finding(
                    Finding(
                        severity=severity,
                        code=code,
                        message=self._extract_error_message(stderr),
                        remediation=remediation,
                    )
                )
                return

        # Generic error
        self.add_finding(
            Finding(
                severity=severity,
                code="SYNTH_FAILED",
                message=self._extract_error_message(stderr),
            )
        )

    def _extract_error_message(self, stderr: str) -> str:
        """Extract a meaningful error message from stderr."""
        lines = stderr.strip().split("\n")

        # Look for the most relevant error line
        for line in lines:
            if "Error:" in line or "error:" in line:
                return line.strip()[:200]  # Truncate long messages

        # Fall back to last non-empty line
        for line in reversed(lines):
            if line.strip():
                return line.strip()[:200]

        return "Unknown synthesis error"

    def _load_templates(self, synth_output: Path) -> None:
        """Load generated CloudFormation templates into context."""
        if not synth_output.exists():
            self.add_finding(
                Finding(
                    severity=FindingSeverity.HIGH,
                    code="NO_SYNTH_OUTPUT",
                    message="CDK synth produced no output",
                )
            )
            return

        # Find all template files
        template_files = list(synth_output.glob("*.template.json"))

        if not template_files:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.HIGH,
                    code="NO_TEMPLATES",
                    message="No CloudFormation templates generated",
                )
            )
            return

        # Load each template
        for template_file in template_files:
            try:
                with open(template_file) as f:
                    template = json.load(f)

                # Store by stack name (derived from filename)
                stack_name = template_file.stem.replace(".template", "")
                self.context.templates[stack_name] = template

                # Basic template validation
                self._validate_template_structure(stack_name, template, template_file)

            except json.JSONDecodeError as e:
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.HIGH,
                        code="INVALID_TEMPLATE_JSON",
                        message=f"Invalid JSON in template: {e}",
                        file_path=str(template_file),
                    )
                )
            except Exception as e:
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.WARN,
                        code="TEMPLATE_LOAD_ERROR",
                        message=f"Could not load template: {e}",
                        file_path=str(template_file),
                    )
                )

        # Report loaded templates
        self.add_finding(
            Finding(
                severity=FindingSeverity.INFO,
                code="TEMPLATES_LOADED",
                message=f"Loaded {len(self.context.templates)} CloudFormation templates",
            )
        )

    def _validate_template_structure(
        self, stack_name: str, template: dict[str, Any], file_path: Path
    ) -> None:
        """Validate basic CloudFormation template structure."""
        # Check for required sections
        if "Resources" not in template:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.HIGH,
                    code="NO_RESOURCES",
                    message=f"Template '{stack_name}' has no Resources section",
                    file_path=str(file_path),
                )
            )
            return

        resources = template.get("Resources", {})

        if not resources:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.WARN,
                    code="EMPTY_RESOURCES",
                    message=f"Template '{stack_name}' has empty Resources section",
                    file_path=str(file_path),
                )
            )

        # Count resources by type
        resource_types: dict[str, int] = {}
        for resource in resources.values():
            rtype = resource.get("Type", "Unknown")
            resource_types[rtype] = resource_types.get(rtype, 0) + 1

        # Log resource summary
        self.add_finding(
            Finding(
                severity=FindingSeverity.INFO,
                code="RESOURCE_COUNT",
                message=(
                    f"Stack '{stack_name}': {len(resources)} resources "
                    f"({len(resource_types)} types)"
                ),
                file_path=str(file_path),
            )
        )
