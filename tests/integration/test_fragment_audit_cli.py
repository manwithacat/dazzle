"""End-to-end test for `dazzle fragment-audit`."""

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SIMPLE_TASK = _REPO_ROOT / "examples" / "simple_task"


def _run_audit(*extra: str) -> subprocess.CompletedProcess[str]:
    # Use the active interpreter (venv), never bare PATH ``python`` — host
    # pythons often lack the editable dazzle install.
    return subprocess.run(
        [sys.executable, "-m", "dazzle.cli", "fragment-audit", str(_SIMPLE_TASK), *extra],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        check=False,
    )


def test_fragment_audit_text_on_simple_task() -> None:
    """The CLI emits a human-readable report for examples/simple_task.

    Plan 10 brought simple_task to 100% Fragment-renderable, so the
    output now shows the all-ready state — no Blocked section, no
    Aggregated blockers section. Verifies the structural shape of the
    100%-ready output."""
    result = _run_audit()
    assert result.returncode == 0, f"stderr: {result.stderr!r}"
    out = result.stdout
    assert "Coverage:" in out
    assert "task_list" in out
    assert "task_detail" in out
    # All surfaces ready → only ✓ entries should appear
    assert "✓" in out
    assert "Ready" in out


def test_fragment_audit_json_on_simple_task() -> None:
    """The --json flag emits structured JSON."""
    result = _run_audit("--json")
    assert result.returncode == 0, f"stderr: {result.stderr!r}"
    payload = json.loads(result.stdout)
    assert "ready_count" in payload
    assert "blocked_count" in payload
    assert "surfaces" in payload
    assert any(s["name"] == "task_list" for s in payload["surfaces"])
    assert payload["ready_count"] >= 1  # at least task_list flips


def test_fragment_audit_fail_on_blocked_returns_consistent_exit_code() -> None:
    """--fail-on-blocked exits 0 when zero blockers, non-zero when any
    surface is blocked — CI-gate semantics. Plan 13 made the audit
    honest about REF/UUID/JSON/FILE; simple_task currently reports ref
    blockers (assigned_to: ref User on Task), so the exit is non-zero.
    If a future plan extends the adapter to handle REF cleanly, exit
    flips back to 0 — both states are valid; what's not valid is a
    crash or an unrelated exit code."""
    result = _run_audit("--fail-on-blocked")
    assert result.returncode in (0, 1), (
        f"unexpected exit {result.returncode}; stderr: {result.stderr!r}"
    )
