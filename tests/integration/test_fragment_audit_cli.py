"""End-to-end test for `dazzle fragment-audit`."""

import json
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SIMPLE_TASK = _REPO_ROOT / "examples" / "simple_task"


def test_fragment_audit_text_on_simple_task() -> None:
    """The CLI emits a human-readable report for examples/simple_task."""
    result = subprocess.run(
        [
            "python",
            "-m",
            "dazzle.cli",
            "fragment-audit",
            str(_SIMPLE_TASK),
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        check=False,
    )
    # Default exit code is 0 (informational); --fail-on-blocked tested below.
    assert result.returncode == 0, f"stderr: {result.stderr!r}"
    out = result.stdout
    assert "Coverage:" in out
    assert "task_list" in out
    assert "task_detail" in out
    assert "✓" in out
    assert "✗" in out
    assert "Aggregated blockers" in out


def test_fragment_audit_json_on_simple_task() -> None:
    """The --json flag emits structured JSON."""
    result = subprocess.run(
        [
            "python",
            "-m",
            "dazzle.cli",
            "fragment-audit",
            str(_SIMPLE_TASK),
            "--json",
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, f"stderr: {result.stderr!r}"
    payload = json.loads(result.stdout)
    assert "ready_count" in payload
    assert "blocked_count" in payload
    assert "surfaces" in payload
    assert any(s["name"] == "task_list" for s in payload["surfaces"])
    assert payload["ready_count"] >= 1  # at least task_list flips


def test_fragment_audit_fail_on_blocked_returns_nonzero() -> None:
    """--fail-on-blocked exits 1 when surfaces are blocked. simple_task
    currently has blocked surfaces (CREATE/EDIT/VIEW modes), so this is
    a useful CI-gate test."""
    result = subprocess.run(
        [
            "python",
            "-m",
            "dazzle.cli",
            "fragment-audit",
            str(_SIMPLE_TASK),
            "--fail-on-blocked",
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        check=False,
    )
    assert result.returncode == 1
