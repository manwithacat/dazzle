"""Cycle 198 subagent-driven explore: helpers for the outer assistant.

This module intentionally does NOT export an async orchestrator function
that "invokes" the Task tool. Claude Code's Task tool is only reachable
from the outer assistant's cognitive loop — it's a tool instruction, not
a library callable. Trying to abstract it into a single function creates
impedance mismatch.

Instead, cycle 198 ships four small helpers that the outer assistant
composes during a /ux-cycle Step 6 run:

    1. ``init_explore_run(...)`` — create the per-run state directory,
       write the initial findings file, write the ModeRunner background
       script, return a context object holding every path the assistant
       needs.

    2. ``ExploreRunContext`` — dataclass with example/persona/run_id and
       every absolute path (state_dir, findings_path, runner_script_path,
       helper_command). JSON-serializable if the assistant wants to stash
       it across tool calls.

    3. ``read_findings(ctx)`` — read and lightly-validate the findings
       JSON after the subagent's Task-tool run completes.

    4. ``write_runner_script(...)`` — generate the standalone Python
       script that wraps ModeRunner and blocks on a shutdown signal. The
       assistant runs this via Bash(run_in_background=true), polls for
       conn.json, and eventually kills it with pkill.

The outer assistant's playbook (documented in .claude/commands/ux-cycle.md
Step 6) walks through these helpers in order, interleaving them with Bash
commands and the Task tool invocation.

Storage policy: state_dir lives under dev_docs/ux_cycle_runs/ which is
gitignored. Artefacts are local-only and ephemeral (per-run directory
naming means concurrent runs don't collide).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_RUNS_DIR_RELATIVE = Path("dev_docs") / "ux_cycle_runs"

HELPER_COMMAND = "python -m dazzle.agent.playwright_helper"


@dataclass
class ExploreRunContext:
    """Per-run state + paths for one subagent-driven explore cycle.

    All paths are absolute so the outer assistant can pass them into
    Bash commands without relative-path ambiguity. ``run_id`` is unique
    per invocation; two concurrent runs against the same example+persona
    get distinct contexts.
    """

    example_root: Path
    example_name: str
    persona_id: str
    run_id: str
    state_dir: Path
    findings_path: Path
    conn_path: Path
    runner_script_path: Path
    helper_command: str = HELPER_COMMAND

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation for debugging / log capture."""
        return {
            "example_name": self.example_name,
            "persona_id": self.persona_id,
            "run_id": self.run_id,
            "state_dir": str(self.state_dir),
            "findings_path": str(self.findings_path),
            "conn_path": str(self.conn_path),
            "runner_script_path": str(self.runner_script_path),
            "helper_command": self.helper_command,
            "example_root": str(self.example_root),
        }


@dataclass
class SubagentExploreFindings:
    """Validated findings JSON read back from a completed subagent run.

    Loose validation: we only enforce that ``proposals`` and ``observations``
    are top-level lists. Individual items are passed through as-is so the
    subagent can add extra metadata without tripping the reader.
    """

    proposals: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SubagentExploreFindings:
        proposals = data.get("proposals") or []
        observations = data.get("observations") or []
        if not isinstance(proposals, list):
            raise ValueError(f"findings.proposals must be a list, got {type(proposals).__name__}")
        if not isinstance(observations, list):
            raise ValueError(
                f"findings.observations must be a list, got {type(observations).__name__}"
            )
        return cls(proposals=list(proposals), observations=list(observations), raw=data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def init_explore_run(
    example_root: Path,
    persona_id: str,
    *,
    run_id: str | None = None,
    base_runs_dir: Path | None = None,
    project_root: Path | None = None,
) -> ExploreRunContext:
    """Create the state directory, findings file, and runner script.

    Synchronous — no ModeRunner launch yet. The assistant calls this
    first, then runs the generated runner script via Bash to actually
    boot the example app.

    Args:
        example_root: Path to the example app directory (e.g.
            ``examples/contact_manager``).
        persona_id: DSL persona id the subagent will walk as.
        run_id: Unique identifier for this run. Defaults to an
            ISO-style timestamp.
        base_runs_dir: Directory under which per-run state lives.
            Defaults to ``<project_root>/dev_docs/ux_cycle_runs``.
        project_root: Dazzle repo root used to resolve
            ``base_runs_dir`` default. If None, inferred as
            ``example_root.parents[1]`` (i.e. the parent of ``examples/``).

    Returns:
        A fully-populated ``ExploreRunContext`` with the findings file
        and runner script already written to disk.
    """
    if run_id is None:
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")

    if project_root is None:
        # examples/<name>/ → repo root is parents[1]
        project_root = example_root.resolve().parents[1]

    if base_runs_dir is None:
        base_runs_dir = project_root / DEFAULT_RUNS_DIR_RELATIVE

    example_name = example_root.name
    run_dir_name = f"{example_name}_{persona_id}_{run_id}"
    state_dir = base_runs_dir / run_dir_name
    state_dir.mkdir(parents=True, exist_ok=True)

    findings_path = state_dir / "findings.json"
    if not findings_path.exists():
        findings_path.write_text(json.dumps({"proposals": [], "observations": []}, indent=2) + "\n")

    conn_path = state_dir / "conn.json"
    runner_script_path = state_dir / "runner.py"

    ctx = ExploreRunContext(
        example_root=example_root.resolve(),
        example_name=example_name,
        persona_id=persona_id,
        run_id=run_id,
        state_dir=state_dir.resolve(),
        findings_path=findings_path.resolve(),
        conn_path=conn_path.resolve(),
        runner_script_path=runner_script_path.resolve(),
    )

    write_runner_script(ctx)
    return ctx


def write_runner_script(ctx: ExploreRunContext) -> Path:
    """Write a self-contained runner script to ``ctx.runner_script_path``.

    The script, when executed, loads the example's .env, boots
    ``ModeRunner``, writes connection info to ``ctx.conn_path``, then
    blocks on a shutdown signal (SIGTERM/SIGINT). The outer assistant
    runs it via ``Bash(run_in_background=true)``, polls for ``conn.json``,
    then proceeds with the login + subagent + teardown sequence.

    Generated as a script rather than imported as a module because
    ``Bash(run_in_background=true)`` launches a shell subprocess — it
    can't share Python state with the assistant's context.
    """
    script = _RUNNER_SCRIPT_TEMPLATE.format(
        example_root=repr(str(ctx.example_root)),
        persona_id=repr(ctx.persona_id),
        conn_path=repr(str(ctx.conn_path)),
    )
    ctx.runner_script_path.write_text(script)
    return ctx.runner_script_path


def read_findings(ctx: ExploreRunContext) -> SubagentExploreFindings:
    """Read and validate the findings JSON after a subagent run.

    Raises:
        FileNotFoundError: if the findings file doesn't exist (meaning
            the orchestration broke before the subagent could write it).
        ValueError: if the findings JSON is malformed or has wrong
            top-level structure.
    """
    if not ctx.findings_path.exists():
        raise FileNotFoundError(f"findings not found at {ctx.findings_path}")
    raw = json.loads(ctx.findings_path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"findings top-level must be a dict, got {type(raw).__name__}")
    return SubagentExploreFindings.from_dict(raw)


_RUNNER_SCRIPT_TEMPLATE = '''\
"""Cycle 198 subagent-driven explore: ModeRunner background runner.

Generated by dazzle.cli.runtime_impl.ux_cycle_impl.subagent_explore
.write_runner_script. Do not edit by hand — regenerated per run.

Loads the example app's .env, boots ModeRunner, writes connection info,
blocks until SIGTERM. The outer assistant runs this via Bash with
run_in_background=true, polls for the conn file, and eventually kills
this process with pkill.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from pathlib import Path

EXAMPLE_ROOT = Path({example_root})
PERSONA_ID = {persona_id}
CONN_PATH = Path({conn_path})

SAFETY_TIMEOUT_SEC = 1200  # 20 minutes


async def main() -> None:
    env_path = EXAMPLE_ROOT / ".env"
    if env_path.exists():
        for raw in env_path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            k, _, v = line.partition("=")
            os.environ[k] = v

    from dazzle.e2e.modes import get_mode
    from dazzle.e2e.runner import ModeRunner

    shutdown_event = asyncio.Event()

    def _shutdown_handler(signum: int, frame: object) -> None:
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    async with ModeRunner(
        mode_spec=get_mode("a"),
        project_root=EXAMPLE_ROOT,
        personas=[PERSONA_ID],
        db_policy="preserve",
    ) as conn:
        CONN_PATH.write_text(
            json.dumps(
                {{
                    "site_url": conn.site_url,
                    "api_url": conn.api_url,
                    "ready": True,
                }},
                indent=2,
            )
        )
        print(f"[subagent-explore-runner] ready: {{conn.site_url}}", flush=True)

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=SAFETY_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            print(
                "[subagent-explore-runner] timeout reached, shutting down",
                flush=True,
            )

    CONN_PATH.unlink(missing_ok=True)
    print("[subagent-explore-runner] torn down", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    sys.exit(0)
'''
