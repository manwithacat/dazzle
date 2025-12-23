"""
Stage 4: Policy Guardrails.

Validates templates against cfn-guard policy rules.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from ..models import (
    STAGE_GUARDRAILS,
    Finding,
    FindingSeverity,
)
from .base import PreflightStage


class GuardrailsStage(PreflightStage):
    """
    Policy guardrails stage using cfn-guard.

    Validates CloudFormation templates against policy rules
    defined in cfn-guard rule files.
    """

    @property
    def name(self) -> str:
        return STAGE_GUARDRAILS

    def should_skip(self) -> tuple[bool, str | None]:
        """Check if guardrails should be skipped."""
        skip, reason = super().should_skip()
        if skip:
            return skip, reason

        # Skip if no synth output
        if not self.context.synth_output_dir:
            return True, "No synth output available"

        if not self.context.synth_output_dir.exists():
            return True, "Synth output directory does not exist"

        # Check for policy files
        policy_paths = self._get_policy_paths()
        if not policy_paths:
            # Use built-in policies if available
            builtin_policies = self._get_builtin_policies()
            if not builtin_policies:
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.INFO,
                        code="NO_GUARDRAIL_POLICIES",
                        message="No guardrail policies configured",
                        remediation="Add policy files in .dazzle/policies/ or specify in config",
                    )
                )
                return True, "No policy files available"

        # Check if cfn-guard is available
        if not shutil.which("cfn-guard"):
            self.add_finding(
                Finding(
                    severity=FindingSeverity.INFO,
                    code="CFN_GUARD_NOT_FOUND",
                    message="cfn-guard not found, using built-in assertions only",
                    remediation="Install cfn-guard: https://github.com/aws-cloudformation/cloudformation-guard",
                )
            )
            return True, "cfn-guard not installed"

        return False, None

    def _execute(self) -> None:
        """Execute cfn-guard on templates."""
        synth_dir = self.context.synth_output_dir
        if not synth_dir:
            return

        # Get policy files
        policy_paths = self._get_policy_paths()
        if not policy_paths:
            policy_paths = self._get_builtin_policies()

        if not policy_paths:
            return

        # Find all template files
        template_files = list(synth_dir.glob("*.template.json"))

        if not template_files:
            return

        # Run cfn-guard on each template with each policy
        for template_file in template_files:
            for policy_path in policy_paths:
                self._validate_template(template_file, policy_path)

    def _get_policy_paths(self) -> list[Path]:
        """Get policy file paths from config."""
        paths = []

        # From config
        for p in self.context.config.policy_paths:
            if p.exists():
                paths.append(p)

        # From project directory
        project_policies = self.context.project_root / ".dazzle" / "policies"
        if project_policies.exists():
            paths.extend(project_policies.glob("*.guard"))

        return paths

    def _get_builtin_policies(self) -> list[Path]:
        """Get built-in policy files bundled with Dazzle."""
        # Look for policies in the package
        import dazzle.deploy.preflight

        package_dir = Path(dazzle.deploy.preflight.__file__).parent
        policies_dir = package_dir / "policies"

        if policies_dir.exists():
            return list(policies_dir.glob("*.guard"))

        return []

    def _validate_template(self, template_path: Path, policy_path: Path) -> None:
        """Validate a template against a policy file."""
        try:
            result = subprocess.run(
                [
                    "cfn-guard",
                    "validate",
                    "--data",
                    str(template_path),
                    "--rules",
                    str(policy_path),
                    "--output-format",
                    "json",
                    "--show-summary",
                    "none",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Parse output
            self._parse_guard_output(result.stdout, template_path, policy_path, result.returncode)

        except subprocess.TimeoutExpired:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.WARN,
                    code="GUARD_TIMEOUT",
                    message=f"cfn-guard timed out validating {template_path.name}",
                    file_path=str(template_path),
                )
            )
        except FileNotFoundError:
            pass  # Already handled in should_skip
        except Exception as e:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.WARN,
                    code="GUARD_ERROR",
                    message=f"cfn-guard error: {e}",
                    file_path=str(template_path),
                )
            )

    def _parse_guard_output(
        self,
        output: str,
        template_path: Path,
        policy_path: Path,
        return_code: int,
    ) -> None:
        """Parse cfn-guard JSON output and create findings."""
        if not output.strip():
            # No output means no violations (or error)
            if return_code == 0:
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.INFO,
                        code="GUARD_PASSED",
                        message=f"Template {template_path.name} passed policy {policy_path.name}",
                    )
                )
            return

        try:
            # cfn-guard v3 output format
            results = json.loads(output)

            for file_result in results.get("data", []):
                rules = file_result.get("rules", [])

                for rule in rules:
                    rule_name = rule.get("name", "unknown_rule")
                    status = rule.get("status", "FAIL")

                    if status == "PASS":
                        continue

                    # Get failed checks
                    checks = rule.get("checks", [])
                    for check in checks:
                        if check.get("status") == "PASS":
                            continue

                        # Extract violation details
                        clause = check.get("clause", {})
                        message = clause.get("messages", {}).get(
                            "error_message", check.get("message", "Policy violation")
                        )

                        # Get the resource path
                        path = check.get("value", {}).get("path", "")

                        self.add_finding(
                            Finding(
                                severity=FindingSeverity.HIGH,
                                code=f"GUARD_{rule_name.upper()}",
                                message=message,
                                resource=path,
                                file_path=str(template_path),
                            )
                        )

        except json.JSONDecodeError:
            # Fallback: parse non-JSON output
            self._parse_guard_text_output(output, template_path, policy_path)

    def _parse_guard_text_output(self, output: str, template_path: Path, policy_path: Path) -> None:
        """Parse text output from cfn-guard (fallback)."""
        lines = output.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Look for FAIL indicators
            if "FAIL" in line or "FAILED" in line:
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.HIGH,
                        code="GUARD_VIOLATION",
                        message=line[:200],
                        file_path=str(template_path),
                    )
                )
