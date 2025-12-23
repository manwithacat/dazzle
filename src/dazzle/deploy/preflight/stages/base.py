"""
Base class for preflight validation stages.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..models import Finding, StageResult, StageStatus

if TYPE_CHECKING:
    from ..models import PreflightConfig


@dataclass
class StageContext:
    """Shared context passed between stages."""

    project_root: Path
    infra_dir: Path
    config: PreflightConfig
    app_name: str = ""
    app_version: str = ""
    commit_sha: str | None = None
    account_id: str | None = None
    region: str = "us-east-1"
    toolchain: dict[str, str] = field(default_factory=dict)
    synth_output_dir: Path | None = None
    templates: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Path] = field(default_factory=dict)


class PreflightStage(ABC):
    """Base class for preflight validation stages."""

    def __init__(self, context: StageContext):
        """Initialize the stage with shared context."""
        self.context = context
        self._result: StageResult | None = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the stage name."""
        ...

    @property
    def result(self) -> StageResult:
        """Get the stage result."""
        if self._result is None:
            self._result = StageResult(name=self.name)
        return self._result

    def should_skip(self) -> tuple[bool, str | None]:
        """
        Check if this stage should be skipped.

        Returns:
            Tuple of (should_skip, reason)
        """
        if self.name in self.context.config.skip_stages:
            return True, f"Stage '{self.name}' explicitly skipped in configuration"
        return False, None

    def run(self) -> StageResult:
        """
        Execute the stage.

        Returns:
            StageResult with status and findings
        """
        self._result = StageResult(name=self.name)

        # Check if skipped
        should_skip, skip_reason = self.should_skip()
        if should_skip:
            self._result.status = StageStatus.SKIPPED
            self._result.error_message = skip_reason
            return self._result

        # Run the stage
        self._result.status = StageStatus.RUNNING
        start_time = time.time()

        try:
            self._execute()

            # Check for critical findings
            has_critical = any(f.severity.value == "critical" for f in self._result.findings)
            has_high = any(f.severity.value == "high" for f in self._result.findings)

            if has_critical:
                self._result.status = StageStatus.FAILED
            elif has_high and self.context.config.fail_on_high:
                self._result.status = StageStatus.FAILED
            else:
                self._result.status = StageStatus.PASSED

        except Exception as e:
            self._result.status = StageStatus.FAILED
            self._result.error_message = str(e)

        finally:
            elapsed = time.time() - start_time
            self._result.duration_ms = int(elapsed * 1000)

        return self._result

    @abstractmethod
    def _execute(self) -> None:
        """
        Execute the stage logic.

        Implementations should add findings to self.result.
        """
        ...

    def add_finding(self, finding: Finding) -> None:
        """Add a finding to the stage result."""
        self.result.add_finding(finding)

    def add_artifact(self, artifact_type: str, path: str) -> None:
        """Add an artifact to the stage result."""
        self.result.add_artifact(artifact_type, path)
