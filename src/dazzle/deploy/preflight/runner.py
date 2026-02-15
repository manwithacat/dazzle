"""
Pre-flight validation runner.

Orchestrates the execution of all preflight stages.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .models import (
    PreflightConfig,
    PreflightMode,
    PreflightReport,
    StageStatus,
)
from .stages import (
    AssertionsStage,
    BootstrapStage,
    GuardrailsStage,
    LintStage,
    SynthStage,
)
from .stages.base import PreflightStage, StageContext

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PreflightRunner:
    """
    Orchestrates preflight validation stages.

    Runs stages in sequence, building up context as each stage
    completes, and generates a final report.
    """

    def __init__(
        self,
        project_root: Path,
        infra_dir: Path | None = None,
        config: PreflightConfig | None = None,
    ):
        """
        Initialize the runner.

        Args:
            project_root: Project root directory
            infra_dir: Infrastructure directory (defaults to project_root/infra)
            config: Preflight configuration
        """
        self.project_root = project_root.resolve()
        self.infra_dir = infra_dir.resolve() if infra_dir else self.project_root / "infra"
        self.config = config or PreflightConfig()

        # Generate run ID
        self.run_id = f"pf-{uuid.uuid4().hex[:8]}"

        # Initialize context
        self.context = StageContext(
            project_root=self.project_root,
            infra_dir=self.infra_dir,
            config=self.config,
        )

    def run(self) -> PreflightReport:
        """
        Execute all preflight stages.

        Returns:
            PreflightReport with all stage results and summary
        """
        # Create report
        report = PreflightReport(
            run_id=self.run_id,
            timestamp_utc=datetime.now(UTC).isoformat(),
            app_name=self.context.app_name or "unknown",
            app_version=self.context.app_version or "0.0.0",
            commit_sha=self.context.commit_sha,
            env_name=self._get_env_name(),
            account_id=self.context.account_id,
            region=self.context.region,
            mode=self.config.mode,
        )

        # Get stages for this mode
        stages = self._get_stages()

        # Run each stage
        failed = False
        for stage in stages:
            if failed and not self._should_run_after_failure(stage):
                # Skip remaining stages after critical failure
                result = stage.result
                result.status = StageStatus.SKIPPED
                result.error_message = "Skipped due to previous stage failure"
                report.stages.append(result)
                continue

            result = stage.run()
            report.stages.append(result)

            # Check if we should stop
            if result.failed:
                failed = True

            # Update context from stage results
            self._update_context_from_stage(stage)

        # Update report with final context
        report.app_name = self.context.app_name or "unknown"
        report.app_version = self.context.app_version or "0.0.0"
        report.commit_sha = self.context.commit_sha
        report.toolchain = self.context.toolchain

        # Compute summary
        report.compute_summary()

        return report

    def _get_stages(self) -> list[PreflightStage]:
        """Get stages to run based on mode."""
        # Static stages (always run)
        stages: list[PreflightStage] = [
            BootstrapStage(self.context),
            SynthStage(self.context),
            AssertionsStage(self.context),
            LintStage(self.context),
            GuardrailsStage(self.context),
        ]

        # Add AWS-dependent stages for plan_only and sandbox modes
        if self.config.mode == PreflightMode.PLAN_ONLY:
            # Add IAM validation, diff stages (future implementation)
            pass
        elif self.config.mode == PreflightMode.SANDBOX_APPLY:
            # Add changeset, sandbox apply stages (future implementation)
            pass

        return stages

    def _should_run_after_failure(self, stage: PreflightStage) -> bool:
        """Check if a stage should run even after previous failure."""
        # Some stages should always attempt to run for visibility
        # In the current implementation, we stop on critical failures
        return False

    def _update_context_from_stage(self, stage: PreflightStage) -> None:
        """Update context with data gathered from a stage."""
        # Context is updated in-place by stages
        pass

    def _get_env_name(self) -> str:
        """Get environment name from config or defaults."""
        # Try to determine from deploy config
        toml_path = self.project_root / "dazzle.toml"
        if toml_path.exists():
            try:
                import tomllib

                with open(toml_path, "rb") as f:
                    config = tomllib.load(f)
                deploy = config.get("deploy", {})
                if isinstance(deploy, dict):
                    env = deploy.get("environment", "staging")
                    if isinstance(env, str):
                        return env
            except Exception:
                logger.debug("Failed to read deploy environment from dazzle.toml", exc_info=True)
        return "staging"


def run_preflight(
    project_root: Path,
    infra_dir: Path | None = None,
    mode: PreflightMode = PreflightMode.STATIC_ONLY,
    skip_stages: list[str] | None = None,
    fail_on_high: bool = True,
    fail_on_warn: bool = False,
) -> PreflightReport:
    """
    Convenience function to run preflight validation.

    Args:
        project_root: Project root directory
        infra_dir: Infrastructure directory (defaults to project_root/infra)
        mode: Preflight mode
        skip_stages: List of stage names to skip
        fail_on_high: Whether to fail on HIGH severity findings
        fail_on_warn: Whether to fail on WARN severity findings

    Returns:
        PreflightReport with all stage results and summary
    """
    config = PreflightConfig(
        mode=mode,
        skip_stages=skip_stages or [],
        fail_on_high=fail_on_high,
        fail_on_warn=fail_on_warn,
    )

    runner = PreflightRunner(
        project_root=project_root,
        infra_dir=infra_dir,
        config=config,
    )

    return runner.run()
