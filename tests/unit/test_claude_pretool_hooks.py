"""Regression: project PreToolUse hooks must not crash under Grok + system Python.

Background: every ``search_replace`` was logging
``pre_tool_use[1] failed with exit code 1`` because ``file_protection.py`` used
PEP 604 ``str | None`` annotations evaluated under PATH ``python3`` 3.9.
Grok fail-opens non-0/2 exits, so edits still ran but the TUI spammed errors.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HOOKS = REPO / ".claude" / "hooks"


def _run_hook(
    script: str, payload: dict, *, python: str | None = None
) -> subprocess.CompletedProcess[str]:
    py = python or sys.executable
    return subprocess.run(
        [py, str(HOOKS / script)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=15,
        cwd=str(REPO),
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(REPO)},
    )


def test_all_hook_scripts_compile() -> None:
    scripts = sorted(HOOKS.glob("*.py"))
    assert scripts, "expected .claude/hooks/*.py"
    for script in scripts:
        proc = subprocess.run(
            [sys.executable, "-m", "py_compile", str(script)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert proc.returncode == 0, f"{script.name}: {proc.stderr}"


def test_file_protection_accepts_grok_search_replace() -> None:
    """Grok tool name + camelCase keys must exit 0 (allow)."""
    proc = _run_hook(
        "file_protection.py",
        {
            "toolName": "search_replace",
            "toolInput": {"file_path": str(REPO / "README.md")},
        },
    )
    assert proc.returncode == 0, proc.stderr
    assert "BLOCKED" not in proc.stderr


def test_file_protection_accepts_claude_edit_snake_case() -> None:
    proc = _run_hook(
        "file_protection.py",
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(REPO / "README.md")},
        },
    )
    assert proc.returncode == 0, proc.stderr


def test_file_protection_blocks_auto_generated(tmp_path: Path) -> None:
    target = tmp_path / "gen.py"
    target.write_text("# AUTO-GENERATED\nvalue = 1\n", encoding="utf-8")
    proc = _run_hook(
        "file_protection.py",
        {"tool_name": "Edit", "tool_input": {"file_path": str(target)}},
    )
    assert proc.returncode == 2
    assert "AUTO-GENERATED" in proc.stderr


def test_bash_validator_allows_safe_command() -> None:
    proc = _run_hook(
        "bash_validator.py",
        {
            "toolName": "run_terminal_command",
            "toolInput": {"command": "echo hi"},
        },
    )
    assert proc.returncode == 0, proc.stderr


def test_bash_validator_rewrites_bare_dazzle() -> None:
    proc = _run_hook(
        "bash_validator.py",
        {"tool_name": "Bash", "tool_input": {"command": "dazzle validate"}},
    )
    assert proc.returncode == 0, proc.stderr
    assert "python -m dazzle validate" in proc.stdout


def test_bash_validator_blocks_rm_rf_root() -> None:
    proc = _run_hook(
        "bash_validator.py",
        {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}},
    )
    assert proc.returncode == 2
    assert "BLOCKED" in proc.stderr


def test_bash_validator_allows_rm_rf_under_tmp() -> None:
    """Regression: old pattern matched any absolute path as 'root'."""
    proc = _run_hook(
        "bash_validator.py",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /tmp/dazzle-hook-test-xyz"},
        },
    )
    assert proc.returncode == 0, proc.stderr


def test_run_hook_sh_prefers_venv() -> None:
    runner = HOOKS / "run_hook.sh"
    assert runner.is_file()
    proc = subprocess.run(
        ["bash", str(runner), "file_protection.py"],
        input=json.dumps(
            {
                "toolName": "search_replace",
                "toolInput": {"file_path": str(REPO / "README.md")},
            }
        ),
        text=True,
        capture_output=True,
        timeout=15,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(REPO)},
    )
    assert proc.returncode == 0, proc.stderr


@pytest.mark.skipif(
    not Path("/usr/bin/python3").is_file(),
    reason="no /usr/bin/python3 for 3.9 regression probe",
)
def test_file_protection_does_not_crash_on_system_python3() -> None:
    """PATH python3 may be 3.9 — hooks must still load (future annotations)."""
    ver = subprocess.run(
        ["/usr/bin/python3", "-c", "import sys; print(sys.version_info[:2])"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if ver.returncode != 0:
        pytest.skip("system python3 unusable")
    proc = _run_hook(
        "file_protection.py",
        {
            "toolName": "search_replace",
            "toolInput": {"file_path": str(REPO / "README.md")},
        },
        python="/usr/bin/python3",
    )
    assert proc.returncode == 0, proc.stderr
