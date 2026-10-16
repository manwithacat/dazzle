"""The core wheel must boot the CLI without any optional extra installed.

The v0.120.0 "Publish to PyPI" run failed in its smoke-test job: ``dazzle --help`` on a
bare ``pip install dazzle_dsl-*.whl`` raised ``ModuleNotFoundError: No module named
'click'`` because ``cli/auth_connection.py`` imported click at module top, and click is
not a core dependency (typer >= 0.20 vendors its own). Tier 0 never saw it because the dev
venv carries every extra. This gate reproduces the smoke test in-process: it blocks the
import of every top-level package that only an optional extra would bring in, then imports
the CLI, the IR, and runs ``dazzle validate`` on ``examples/simple_task``.

The blocked set is derived, not hand-listed: the transitive closure of
``[project.optional-dependencies]`` minus the transitive closure of
``[project].dependencies`` (click arrives through ``uvicorn[standard]`` and the dev
tools, never directly), mapped to import names through the installed metadata.
"""

from __future__ import annotations

import importlib.metadata as md
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _dist_name(requirement: str) -> str:
    match = _NAME_RE.match(requirement)
    assert match, requirement
    return md.Prepared.normalize(match.group(1))  # type: ignore[attr-defined]


def _closure(core: set[str]) -> set[str]:
    """Normalised names of the given distributions and everything they require."""
    seen: set[str] = set()
    todo = list(core)
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        try:
            reqs = md.requires(name) or []
        except md.PackageNotFoundError:
            continue
        for req in reqs:
            if "extra ==" in req:
                continue
            todo.append(_dist_name(req))
    return seen


def optional_only_import_names() -> set[str]:
    pyproject = tomllib.load((REPO / "pyproject.toml").open("rb"))
    core = {_dist_name(r) for r in pyproject["project"]["dependencies"]}
    closure = _closure(core)
    optional = _closure(
        {
            _dist_name(r)
            for reqs in pyproject["project"]["optional-dependencies"].values()
            for r in reqs
        }
    )
    optional_only = {name for name in optional - closure if not name.startswith("dazzle")}
    by_import: dict[str, list[str]] = md.packages_distributions()
    # A namespace package shared by a core and an optional distribution (``opentelemetry``:
    # fastapi needs the api, the perf extra adds the sdk) is importable in the core wheel,
    # so an import name is blocked only when none of its distributions is core.
    blocked = {
        imp
        for imp, dists in by_import.items()
        if {md.Prepared.normalize(d) for d in dists} <= optional_only  # type: ignore[attr-defined]
    }
    return blocked


_SMOKE = r"""
import json, sys
blocked = set(json.loads(sys.argv[1]))

class _Block:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in blocked:
            raise ModuleNotFoundError(f"blocked optional-extra import: {name}", name=name)
        return None

sys.meta_path.insert(0, _Block())
from dazzle.cli import main  # noqa: E402  (the console script's import)
from dazzle.core import ir  # noqa: E402,F401
sys.argv = ["dazzle", "validate", "-p", sys.argv[2]]
try:
    main()
except SystemExit as exc:
    sys.exit(exc.code or 0)
"""


@pytest.mark.xdist_group("examples_simple_task")
def test_cli_boots_with_every_optional_extra_blocked() -> None:
    blocked = optional_only_import_names()
    assert "click" in blocked, "click must be optional-only for this gate to mean anything"
    assert "authlib" in blocked
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            _SMOKE,
            json.dumps(sorted(blocked)),
            str(REPO / "examples" / "simple_task"),
        ],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=120,
    )
    assert proc.returncode == 0, (
        "the core wheel cannot boot the CLI without an optional extra "
        f"(blocked={sorted(blocked)}):\n{proc.stderr[-3000:]}"
    )
