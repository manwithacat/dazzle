"""
Feedback loop infrastructure for DAZZLE UX Coverage Testing.

This module provides tracking for test regressions, corrections, and prompt
evolution. It enables a semi-automatic feedback loop where:
1. Test failures are recorded with context
2. Human corrections are tracked
3. Patterns emerge that can improve test design prompts
4. Prompt performance is tracked over time

Storage locations:
- .dazzle/test_feedback/regressions.json
- .dazzle/test_feedback/corrections.json
- .dazzle/test_feedback/prompt_versions.json
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

# Storage paths
FEEDBACK_DIR = ".dazzle/test_feedback"
REGRESSIONS_FILE = "regressions.json"
CORRECTIONS_FILE = "corrections.json"
PROMPT_VERSIONS_FILE = "prompt_versions.json"


class RegressionStatus(str, Enum):
    """Status of a regression in the resolution workflow."""

    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    WONTFIX = "wontfix"


class FailureType(str, Enum):
    """Types of test failures."""

    ASSERTION = "assertion"
    TIMEOUT = "timeout"
    CRASH = "crash"
    FLAKY = "flaky"
    INFRASTRUCTURE = "infrastructure"
    SELECTOR_NOT_FOUND = "selector_not_found"
    NAVIGATION_ERROR = "navigation_error"
    AUTH_ERROR = "auth_error"


class ChangeType(str, Enum):
    """Types of changes that can fix a regression."""

    TEST_FIX = "test_fix"
    DSL_FIX = "dsl_fix"
    PROMPT_FIX = "prompt_fix"
    INFRASTRUCTURE = "infrastructure"


class TestRegression(BaseModel):
    """
    Record of a test failure for analysis.

    Attributes:
        regression_id: Unique identifier (REG-001, REG-002, etc.)
        test_id: ID of the failing test (from TestDesignSpec or FlowSpec)
        test_path: Path to the test file
        failure_message: Error message from the test
        failure_type: Category of failure
        timestamp: When the failure occurred

        example_name: Which example project was being tested
        dsl_version: Git SHA of DSL files at failure time

        status: Current status in resolution workflow
        root_cause: Identified root cause (if known)
        resolution: How the regression was resolved
    """

    regression_id: str
    test_id: str
    test_path: str
    failure_message: str
    failure_type: FailureType
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Context
    example_name: str
    dsl_version: str | None = None  # Git SHA

    # Resolution tracking
    status: RegressionStatus = RegressionStatus.OPEN
    root_cause: str | None = None
    resolution: str | None = None


class TestCorrection(BaseModel):
    """
    Human correction applied to fix a regression.

    Attributes:
        correction_id: Unique identifier (COR-001, etc.)
        regression_id: Link to the regression being fixed

        problem_description: What was wrong
        change_type: Category of fix
        files_changed: List of files modified

        pattern_identified: Reusable insight from this fix
        prompt_improvement: Suggested improvement to test design prompt
    """

    correction_id: str
    regression_id: str

    # What was wrong
    problem_description: str

    # What was changed
    change_type: ChangeType
    files_changed: list[str] = Field(default_factory=list)

    # Learning
    pattern_identified: str | None = None
    prompt_improvement: str | None = None

    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PromptVersion(BaseModel):
    """
    Track prompt evolution for test design tools.

    Attributes:
        version: Version identifier (v1, v2, etc.)
        tool_name: Which MCP tool this prompt is for
        prompt_text: The actual prompt text
        created_at: When this version was created

        tests_generated: Total tests generated with this prompt
        tests_accepted: Tests accepted by humans
        tests_rejected: Tests rejected by humans
        acceptance_rate: Computed acceptance rate
    """

    version: str
    tool_name: str
    prompt_text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Performance tracking
    tests_generated: int = 0
    tests_accepted: int = 0
    tests_rejected: int = 0

    @property
    def acceptance_rate(self) -> float:
        """Calculate acceptance rate as a percentage."""
        if self.tests_generated == 0:
            return 0.0
        return (self.tests_accepted / self.tests_generated) * 100


class RegressionsContainer(BaseModel):
    """Container for persisting regressions."""

    version: str = "1.0"
    regressions: list[TestRegression] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CorrectionsContainer(BaseModel):
    """Container for persisting corrections."""

    version: str = "1.0"
    corrections: list[TestCorrection] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PromptVersionsContainer(BaseModel):
    """Container for persisting prompt versions."""

    version: str = "1.0"
    prompts: list[PromptVersion] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


def get_feedback_dir(project_root: Path) -> Path:
    """Get the feedback directory path."""
    return project_root / FEEDBACK_DIR


def _get_git_sha(project_root: Path) -> str | None:
    """Get the current git SHA for the project."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()[:8]  # Short SHA
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


# ============================================================================
# Regressions
# ============================================================================


def load_regressions(project_root: Path) -> list[TestRegression]:
    """Load all regressions from storage."""
    feedback_dir = get_feedback_dir(project_root)
    regressions_file = feedback_dir / REGRESSIONS_FILE

    if not regressions_file.exists():
        return []

    try:
        content = regressions_file.read_text(encoding="utf-8")
        data = json.loads(content)
        container = RegressionsContainer.model_validate(data)
        return list(container.regressions)
    except (json.JSONDecodeError, ValueError):
        return []


def save_regressions(project_root: Path, regressions: list[TestRegression]) -> Path:
    """Save regressions to storage."""
    feedback_dir = get_feedback_dir(project_root)
    feedback_dir.mkdir(parents=True, exist_ok=True)

    container = RegressionsContainer(
        regressions=regressions,
        updated_at=datetime.utcnow(),
    )

    regressions_file = feedback_dir / REGRESSIONS_FILE
    regressions_file.write_text(
        json.dumps(
            container.model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )

    return regressions_file


def get_next_regression_id(project_root: Path) -> str:
    """Generate the next regression ID (REG-001, REG-002, etc.)."""
    existing = load_regressions(project_root)

    if not existing:
        return "REG-001"

    max_num = 0
    for reg in existing:
        if reg.regression_id.startswith("REG-"):
            try:
                num = int(reg.regression_id[4:])
                max_num = max(max_num, num)
            except ValueError:
                continue

    return f"REG-{max_num + 1:03d}"


def record_regression(
    project_root: Path,
    test_id: str,
    test_path: str,
    failure_message: str,
    failure_type: FailureType | str,
    example_name: str,
) -> TestRegression:
    """Record a new test regression."""
    regressions = load_regressions(project_root)

    # Convert string to enum if needed
    if isinstance(failure_type, str):
        failure_type = FailureType(failure_type)

    regression = TestRegression(
        regression_id=get_next_regression_id(project_root),
        test_id=test_id,
        test_path=test_path,
        failure_message=failure_message,
        failure_type=failure_type,
        example_name=example_name,
        dsl_version=_get_git_sha(project_root),
    )

    regressions.append(regression)
    save_regressions(project_root, regressions)

    return regression


def update_regression_status(
    project_root: Path,
    regression_id: str,
    status: RegressionStatus | str,
    *,
    root_cause: str | None = None,
    resolution: str | None = None,
) -> TestRegression | None:
    """Update the status of a regression."""
    regressions = load_regressions(project_root)

    # Convert string to enum if needed
    if isinstance(status, str):
        status = RegressionStatus(status)

    for i, reg in enumerate(regressions):
        if reg.regression_id == regression_id:
            # Create updated regression
            updated = TestRegression(
                regression_id=reg.regression_id,
                test_id=reg.test_id,
                test_path=reg.test_path,
                failure_message=reg.failure_message,
                failure_type=reg.failure_type,
                timestamp=reg.timestamp,
                example_name=reg.example_name,
                dsl_version=reg.dsl_version,
                status=status,
                root_cause=root_cause if root_cause is not None else reg.root_cause,
                resolution=resolution if resolution is not None else reg.resolution,
            )
            regressions[i] = updated
            save_regressions(project_root, regressions)
            return updated

    return None


def get_regressions_by_status(
    project_root: Path,
    status: RegressionStatus | str | None = None,
) -> list[TestRegression]:
    """Get regressions filtered by status."""
    regressions = load_regressions(project_root)

    if status is None:
        return regressions

    if isinstance(status, str):
        status = RegressionStatus(status)

    return [r for r in regressions if r.status == status]


# ============================================================================
# Corrections
# ============================================================================


def load_corrections(project_root: Path) -> list[TestCorrection]:
    """Load all corrections from storage."""
    feedback_dir = get_feedback_dir(project_root)
    corrections_file = feedback_dir / CORRECTIONS_FILE

    if not corrections_file.exists():
        return []

    try:
        content = corrections_file.read_text(encoding="utf-8")
        data = json.loads(content)
        container = CorrectionsContainer.model_validate(data)
        return list(container.corrections)
    except (json.JSONDecodeError, ValueError):
        return []


def save_corrections(project_root: Path, corrections: list[TestCorrection]) -> Path:
    """Save corrections to storage."""
    feedback_dir = get_feedback_dir(project_root)
    feedback_dir.mkdir(parents=True, exist_ok=True)

    container = CorrectionsContainer(
        corrections=corrections,
        updated_at=datetime.utcnow(),
    )

    corrections_file = feedback_dir / CORRECTIONS_FILE
    corrections_file.write_text(
        json.dumps(
            container.model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )

    return corrections_file


def get_next_correction_id(project_root: Path) -> str:
    """Generate the next correction ID (COR-001, COR-002, etc.)."""
    existing = load_corrections(project_root)

    if not existing:
        return "COR-001"

    max_num = 0
    for cor in existing:
        if cor.correction_id.startswith("COR-"):
            try:
                num = int(cor.correction_id[4:])
                max_num = max(max_num, num)
            except ValueError:
                continue

    return f"COR-{max_num + 1:03d}"


def record_correction(
    project_root: Path,
    regression_id: str,
    problem_description: str,
    change_type: ChangeType | str,
    files_changed: list[str] | None = None,
    *,
    pattern_identified: str | None = None,
    prompt_improvement: str | None = None,
) -> TestCorrection:
    """Record a new correction for a regression."""
    corrections = load_corrections(project_root)

    # Convert string to enum if needed
    if isinstance(change_type, str):
        change_type = ChangeType(change_type)

    correction = TestCorrection(
        correction_id=get_next_correction_id(project_root),
        regression_id=regression_id,
        problem_description=problem_description,
        change_type=change_type,
        files_changed=files_changed or [],
        pattern_identified=pattern_identified,
        prompt_improvement=prompt_improvement,
    )

    corrections.append(correction)
    save_corrections(project_root, corrections)

    # Also update the regression status to resolved
    update_regression_status(
        project_root,
        regression_id,
        RegressionStatus.RESOLVED,
        resolution=f"Fixed via {correction.correction_id}",
    )

    return correction


def get_corrections_for_regression(
    project_root: Path,
    regression_id: str,
) -> list[TestCorrection]:
    """Get all corrections for a specific regression."""
    corrections = load_corrections(project_root)
    return [c for c in corrections if c.regression_id == regression_id]


def get_pattern_insights(project_root: Path) -> list[str]:
    """Get all identified patterns from corrections."""
    corrections = load_corrections(project_root)
    return [c.pattern_identified for c in corrections if c.pattern_identified]


def get_prompt_improvements(project_root: Path) -> list[str]:
    """Get all suggested prompt improvements from corrections."""
    corrections = load_corrections(project_root)
    return [c.prompt_improvement for c in corrections if c.prompt_improvement]


# ============================================================================
# Prompt Versions
# ============================================================================


def load_prompt_versions(project_root: Path) -> list[PromptVersion]:
    """Load all prompt versions from storage."""
    feedback_dir = get_feedback_dir(project_root)
    prompts_file = feedback_dir / PROMPT_VERSIONS_FILE

    if not prompts_file.exists():
        return []

    try:
        content = prompts_file.read_text(encoding="utf-8")
        data = json.loads(content)
        container = PromptVersionsContainer.model_validate(data)
        return list(container.prompts)
    except (json.JSONDecodeError, ValueError):
        return []


def save_prompt_versions(project_root: Path, prompts: list[PromptVersion]) -> Path:
    """Save prompt versions to storage."""
    feedback_dir = get_feedback_dir(project_root)
    feedback_dir.mkdir(parents=True, exist_ok=True)

    container = PromptVersionsContainer(
        prompts=prompts,
        updated_at=datetime.utcnow(),
    )

    prompts_file = feedback_dir / PROMPT_VERSIONS_FILE
    prompts_file.write_text(
        json.dumps(
            container.model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )

    return prompts_file


def register_prompt_version(
    project_root: Path,
    tool_name: str,
    prompt_text: str,
    version: str | None = None,
) -> PromptVersion:
    """Register a new prompt version for tracking."""
    prompts = load_prompt_versions(project_root)

    # Auto-generate version if not provided
    if version is None:
        existing_versions = [p for p in prompts if p.tool_name == tool_name]
        if not existing_versions:
            version = "v1"
        else:
            max_num = max(
                int(p.version[1:]) for p in existing_versions if p.version.startswith("v")
            )
            version = f"v{max_num + 1}"

    prompt = PromptVersion(
        version=version,
        tool_name=tool_name,
        prompt_text=prompt_text,
    )

    prompts.append(prompt)
    save_prompt_versions(project_root, prompts)

    return prompt


def update_prompt_stats(
    project_root: Path,
    tool_name: str,
    version: str,
    *,
    tests_generated: int = 0,
    tests_accepted: int = 0,
    tests_rejected: int = 0,
) -> PromptVersion | None:
    """Update statistics for a prompt version."""
    prompts = load_prompt_versions(project_root)

    for i, p in enumerate(prompts):
        if p.tool_name == tool_name and p.version == version:
            updated = PromptVersion(
                version=p.version,
                tool_name=p.tool_name,
                prompt_text=p.prompt_text,
                created_at=p.created_at,
                tests_generated=p.tests_generated + tests_generated,
                tests_accepted=p.tests_accepted + tests_accepted,
                tests_rejected=p.tests_rejected + tests_rejected,
            )
            prompts[i] = updated
            save_prompt_versions(project_root, prompts)
            return updated

    return None


def get_prompt_version(
    project_root: Path,
    tool_name: str,
    version: str | None = None,
) -> PromptVersion | None:
    """Get a specific prompt version, or latest if version not specified."""
    prompts = load_prompt_versions(project_root)
    tool_prompts = [p for p in prompts if p.tool_name == tool_name]

    if not tool_prompts:
        return None

    if version is None:
        # Return latest
        return max(tool_prompts, key=lambda p: p.created_at)

    for p in tool_prompts:
        if p.version == version:
            return p

    return None


def compare_prompt_versions(
    project_root: Path,
    tool_name: str,
) -> list[dict[str, float | str]]:
    """Compare all prompt versions for a tool by acceptance rate."""
    prompts = load_prompt_versions(project_root)
    tool_prompts = [p for p in prompts if p.tool_name == tool_name]

    return [
        {
            "version": p.version,
            "tests_generated": p.tests_generated,
            "tests_accepted": p.tests_accepted,
            "tests_rejected": p.tests_rejected,
            "acceptance_rate": p.acceptance_rate,
        }
        for p in sorted(tool_prompts, key=lambda x: x.version)
    ]


# ============================================================================
# Summary Statistics
# ============================================================================


class FeedbackSummary(BaseModel):
    """Summary of feedback loop state."""

    total_regressions: int = 0
    open_regressions: int = 0
    resolved_regressions: int = 0

    total_corrections: int = 0
    patterns_identified: int = 0
    prompt_improvements_suggested: int = 0

    prompt_versions: dict[str, int] = Field(default_factory=dict)  # tool -> count

    top_failure_types: list[tuple[str, int]] = Field(default_factory=list)


def get_feedback_summary(project_root: Path) -> FeedbackSummary:
    """Get a summary of the feedback loop state."""
    regressions = load_regressions(project_root)
    corrections = load_corrections(project_root)
    prompts = load_prompt_versions(project_root)

    # Count failure types
    failure_counts: dict[str, int] = {}
    for reg in regressions:
        ft = reg.failure_type.value
        failure_counts[ft] = failure_counts.get(ft, 0) + 1

    top_failures = sorted(failure_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    # Count prompt versions by tool
    prompt_counts: dict[str, int] = {}
    for p in prompts:
        prompt_counts[p.tool_name] = prompt_counts.get(p.tool_name, 0) + 1

    return FeedbackSummary(
        total_regressions=len(regressions),
        open_regressions=len([r for r in regressions if r.status == RegressionStatus.OPEN]),
        resolved_regressions=len(
            [r for r in regressions if r.status == RegressionStatus.RESOLVED]
        ),
        total_corrections=len(corrections),
        patterns_identified=len([c for c in corrections if c.pattern_identified]),
        prompt_improvements_suggested=len([c for c in corrections if c.prompt_improvement]),
        prompt_versions=prompt_counts,
        top_failure_types=top_failures,
    )
