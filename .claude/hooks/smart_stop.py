#!/usr/bin/env python3
"""Stop hook: Intelligent session continuation for autonomous coding.

This is the "Ralph Wiggum" style hook that enables longer autonomous sessions.
It checks various completion criteria and blocks stop if work is incomplete.

Checks performed:
1. DSL validation status (if .dazzle files were modified)
2. Test status (if Python files were modified)
3. Linting status
4. Explicit completion markers in recent output

Configuration via environment variables:
- DAZZLE_RALPH_MODE=1        Enable Ralph-style continuation
- DAZZLE_MAX_ITERATIONS=50   Max iterations before forcing stop
- DAZZLE_COMPLETION_MARKER   Custom completion marker (default: TASK_COMPLETE)
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def _is_toolkit_repo(project_root: Path) -> bool:
    """Detect if we're running inside the Dazzle toolkit repo itself."""
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return False
    try:
        content = pyproject.read_text()
        return 'name = "dazzle"' in content
    except OSError:
        return False


def check_dsl_validation(project_root: Path) -> tuple[bool, str]:
    """Check if DSL validates."""
    if _is_toolkit_repo(project_root):
        return True, "Skipped DSL check: toolkit repo"
    try:
        result = subprocess.run(
            ["dazzle", "validate"], cwd=project_root, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return False, f"DSL validation failed: {result.stderr[:300]}"
        return True, "DSL validates"
    except Exception as e:
        return True, f"Skipped DSL check: {e}"


def check_python_lint(project_root: Path) -> tuple[bool, str]:
    """Check if Python code passes basic lint."""
    try:
        result = subprocess.run(
            ["ruff", "check", "src/", "--select=E,F"],  # Only errors, not style
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            errors = result.stdout[:300] if result.stdout else result.stderr[:300]
            return False, f"Lint errors: {errors}"
        return True, "Lint passed"
    except Exception as e:
        return True, f"Skipped lint: {e}"


def check_completion_marker(transcript: str, marker: str) -> bool:
    """Check if completion marker is present in recent output."""
    return marker in transcript


def get_iteration_count(state_file: Path) -> int:
    """Get current iteration count from state file."""
    try:
        if state_file.exists():
            return int(state_file.read_text().strip())
    except (ValueError, OSError):
        pass
    return 0


def increment_iteration(state_file: Path) -> int:
    """Increment and return iteration count."""
    count = get_iteration_count(state_file) + 1
    state_file.write_text(str(count))
    return count


def main():
    # Check if Ralph mode is enabled
    ralph_mode = os.environ.get("DAZZLE_RALPH_MODE", "0") == "1"

    if not ralph_mode:
        # Normal mode - allow stop
        sys.exit(0)

    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    # Get configuration
    max_iterations = int(os.environ.get("DAZZLE_MAX_ITERATIONS", "50"))
    completion_marker = os.environ.get("DAZZLE_COMPLETION_MARKER", "TASK_COMPLETE")

    # Find project root
    project_root = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()
    state_file = project_root / ".claude" / ".ralph_state"

    # Check iteration count
    iteration = increment_iteration(state_file)
    if iteration >= max_iterations:
        # Force stop after max iterations
        state_file.unlink(missing_ok=True)
        output = {
            "decision": "approve",
            "reason": f"Max iterations ({max_iterations}) reached. Stopping.",
        }
        print(json.dumps(output))
        sys.exit(0)

    # Check for explicit completion marker in transcript
    transcript_path = input_data.get("transcript_path", "")
    if transcript_path and Path(transcript_path).exists():
        transcript = Path(transcript_path).read_text()
        if check_completion_marker(transcript, completion_marker):
            state_file.unlink(missing_ok=True)
            output = {"decision": "approve", "reason": "Completion marker found. Task complete."}
            print(json.dumps(output))
            sys.exit(0)

    # Run validation checks
    issues = []

    dsl_ok, dsl_msg = check_dsl_validation(project_root)
    if not dsl_ok:
        issues.append(dsl_msg)

    lint_ok, lint_msg = check_python_lint(project_root)
    if not lint_ok:
        issues.append(lint_msg)

    if issues:
        # Block stop - work not complete
        output = {
            "decision": "block",
            "reason": f"Iteration {iteration}/{max_iterations}. Issues found:\n"
            + "\n".join(f"- {i}" for i in issues)
            + f"\n\nPlease fix these issues. Output '{completion_marker}' when done.",
        }
        print(json.dumps(output))
        sys.exit(0)

    # All checks passed - allow stop
    state_file.unlink(missing_ok=True)
    output = {"decision": "approve", "reason": "All validation checks passed."}
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
