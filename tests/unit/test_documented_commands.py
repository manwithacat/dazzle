"""The commands `AGENTS.md` tells an agent to copy must work where the agent is.

An agent working in this repo sits at the **framework root**, which is not a
Dazzle project — there is no `dazzle.toml` here. `AGENTS.md`'s Commands block
documented `uv run dazzle validate` and `uv run dazzle lint`, which both
"operate in CURRENT directory (must contain dazzle.toml)". Copying the documented
command from the repo root produced:

    Error: No dazzle.toml found at /Volumes/SSD/Dazzle/dazzle.toml.

so an alternate agent's first DSL action failed and it had to guess a `cd`. The
fix was to add `-p/--project` (the convention `dazzle db` and `dazzle demo
quality` already use) — but nothing would have caught the regression, because no
test ran a documented command from the framework root.

This gate runs the documented surface the way the doc presents it: from the repo
root, against a real example.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
AGENTS = REPO / "AGENTS.md"
EXAMPLE = "examples/simple_task"


def _documented_commands() -> list[str]:
    """Commands AGENTS.md presents as copyable, in fenced bash blocks."""
    text = AGENTS.read_text(encoding="utf-8")
    blocks = re.findall(r"^```bash\n(.*?)^```", text, re.MULTILINE | re.DOTALL)
    out: list[str] = []
    for block in blocks:
        for line in block.splitlines():
            line = line.strip()
            if line.startswith(("uv run dazzle", "make ")):
                out.append(line.split("#")[0].strip())
    return out


def test_the_document_has_copyable_commands() -> None:
    """Falsification guard — the extractor must find the surface it claims to."""
    cmds = _documented_commands()
    assert any(c.startswith("uv run dazzle validate") for c in cmds), cmds[:8]
    assert any(c.startswith("uv run dazzle lint") for c in cmds), cmds[:8]


def test_dsl_commands_are_documented_with_a_project_argument() -> None:
    """`dazzle validate` / `dazzle lint` need `-p` outside a project root, so the
    documented form must carry it — otherwise the doc teaches a command that
    cannot work from the framework repo."""
    for command in _documented_commands():
        if not command.startswith(("uv run dazzle validate", "uv run dazzle lint")):
            continue
        assert " -p " in command or command.endswith(" -p"), (
            f"{command!r} cannot run from the framework root — add `-p <example>`"
        )


@pytest.mark.parametrize("command", ["validate", "lint"])
def test_dsl_command_runs_from_the_framework_root(command: str) -> None:
    """The check that would have caught it: the documented invocation, from the
    repo root, against a real example."""
    proc = subprocess.run(
        [sys.executable, "-m", "dazzle", command, "-p", EXAMPLE],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    combined = f"{proc.stdout}\n{proc.stderr}"
    assert "No dazzle.toml found" not in combined, (
        f"`dazzle {command} -p {EXAMPLE}` still cannot find a project from the "
        f"framework root:\n{combined[-500:]}"
    )
    assert proc.returncode == 0, (
        f"`dazzle {command} -p {EXAMPLE}` exited {proc.returncode}:\n{combined[-500:]}"
    )


@pytest.mark.parametrize("command", ["validate", "lint"])
def test_dsl_command_still_works_inside_a_project(command: str) -> None:
    """`-p` is additive: the cwd-relative form other docs and scripts use must be
    untouched."""
    proc = subprocess.run(
        [sys.executable, "-m", "dazzle", command],
        cwd=REPO / EXAMPLE,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert proc.returncode == 0, (
        f"`dazzle {command}` inside {EXAMPLE} exited {proc.returncode}:\n"
        f"{proc.stdout[-400:]}{proc.stderr[-400:]}"
    )


def test_cli_commands_are_callable_in_process_without_typer_defaults() -> None:
    """Tests and internal code call these functions directly, where typer's
    default is still an `OptionInfo` — not `None`. `Path | None` options are the
    trap: `project / "dazzle.toml"` raised `TypeError` under a direct call until
    `_resolve_manifest` learned to treat "not a Path" as "no project".
    """
    from typer._click import exceptions as click_exceptions

    from dazzle.cli.project import _resolve_manifest, lint_command, validate_command

    manifest = REPO / EXAMPLE / "dazzle.toml"
    # Either call shape works. `lint` exits non-zero on this example's findings,
    # so SystemExit is expected — the point is that it is *not* a TypeError.
    validate_command(manifest=str(manifest), format="human")
    validate_command(manifest="dazzle.toml", project=REPO / EXAMPLE, format="human")
    try:
        lint_command(manifest=str(manifest), format="human")
    except (SystemExit, click_exceptions.Exit):
        pass

    assert _resolve_manifest("dazzle.toml", None).name == "dazzle.toml"
    assert (
        _resolve_manifest("dazzle.toml", REPO / EXAMPLE)
        == (REPO / EXAMPLE / "dazzle.toml").resolve()
    )
