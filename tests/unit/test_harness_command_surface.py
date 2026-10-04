"""The harness's *command surface* must resolve — not just its prose.

`test_improve_harness_paths.py` checks paths named in playbook prose. This
checks the layer above it: the commands a cycle actually runs.

Cycle 2411 stopped at the driver's mandatory Step 0b because
`make test-ux-preflight` exited 4 — its recipe named
`tests/unit/test_template_none_safety.py`, deleted earlier the same day by
#1720. Nothing noticed for the ~30 cycles the loop had been parked, because the
loop is that target's only caller, and CI does not run it.

Two directions:

* **Every file a `make` recipe names exists.** A dangling path in a recipe is
  how a gate becomes unrunnable: pytest exits 4 on a missing file, so the gate
  fails for a reason unrelated to what it guards, and a human reads that as
  "the preflight is broken" rather than "a name rotted".
* **Every command the `/improve` driver names resolves.** Fenced code blocks
  only — prose like "make progress" is not a command, and `docs/research/
  scripts/x.py` must not be read as `scripts/x.py`.

Part of the agent-cognition programme (W1).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
MAKEFILE = REPO / "Makefile"
IMPROVE = REPO / ".agents" / "skills" / "improve"

_FENCE = re.compile(r"^```(?:bash|sh|console)?\s*$(.*?)^```\s*$", re.MULTILINE | re.DOTALL)

# A path reference: no partial matches, so `docs/research/scripts/x.py` is one
# path and not a hit for `scripts/x.py`.
_FILE_REF = re.compile(
    r"(?<![\w/.])((?:tests|scripts|src|docs|examples|fixtures|packages)/[\w./-]+\.(?:py|sh|md|toml|txt|yml|yaml|json))"
)
_MAKE_TARGET = re.compile(r"(?<![\w-])make ([a-z][a-z0-9-]*)")
_MAKE_TARGET_DEF = re.compile(r"^([a-z][a-z0-9-]*):", re.MULTILINE)


def _fenced_blocks() -> list[str]:
    return [m.group(1) for m in _FENCE.finditer(MAKEFILE.read_text(encoding="utf-8"))]


def _recipe_of(target: str) -> str:
    """The recipe lines of one Makefile target (tab-indented body)."""
    lines = MAKEFILE.read_text(encoding="utf-8").splitlines()
    pattern = re.compile(rf"^{re.escape(target)}:")
    start = next((i for i, line in enumerate(lines) if pattern.match(line)), None)
    if start is None:
        return ""
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace() and not line.startswith("#"):
            break
        body.append(line)
    return "\n".join(body)


def _playbooks() -> list[Path]:
    return [
        IMPROVE / "SKILL.md",
        *sorted((IMPROVE / "lanes").glob("*.md")),
        *sorted((IMPROVE / "strategies").glob("*.md")),
    ]


def _harness_commands() -> tuple[set[str], set[str]]:
    """(make targets, script paths) named in fenced code blocks of the harness."""
    targets: set[str] = set()
    scripts: set[str] = set()
    for playbook in _playbooks():
        if not playbook.is_file():
            continue
        for block in _FENCE.findall(playbook.read_text(encoding="utf-8")):
            targets |= set(_MAKE_TARGET.findall(block))
            scripts |= {
                m.group(1) for m in _FILE_REF.finditer(block) if m.group(1).startswith("scripts/")
            }
    return targets, scripts


# --- direction 1: a recipe that names a file must name a file that exists -----


def test_no_make_recipe_references_a_missing_file() -> None:
    """The failure cycle 2411 hit: a recipe naming a deleted test file.

    pytest exits 4 (`file not found`) rather than reporting the drift the gate
    exists to catch, so the gate fails for the wrong reason — and a target whose
    only caller is the parked loop stays broken until the loop runs again.
    """
    defined = set(_MAKE_TARGET_DEF.findall(MAKEFILE.read_text(encoding="utf-8")))
    problems: list[str] = []
    for target in sorted(defined):
        for path in sorted({m.group(1) for m in _FILE_REF.finditer(_recipe_of(target))}):
            if not (REPO / path).exists():
                problems.append(f"make {target} names a missing file: {path}")
    assert not problems, "\n".join(problems)


def test_the_recipe_scan_actually_scanned() -> None:
    """Falsification guard: if the recipe extraction returned nothing, direction 1
    would pass vacuously — exactly the state this gate exists to prevent."""
    defined = _MAKE_TARGET_DEF.findall(MAKEFILE.read_text(encoding="utf-8"))
    assert len(defined) > 20, f"only {len(defined)} targets parsed from the Makefile"
    scanned = {m.group(1) for t in defined for m in _FILE_REF.finditer(_recipe_of(t))}
    assert len(scanned) > 5, f"only {len(scanned)} file references found in recipes"


# --- direction 2: the driver's own commands resolve ---------------------------


def test_every_make_target_the_driver_names_exists() -> None:
    defined = set(_MAKE_TARGET_DEF.findall(MAKEFILE.read_text(encoding="utf-8")))
    named, _scripts = _harness_commands()
    assert named, "no make targets parsed from the harness — the fence regex is wrong"
    missing = sorted(named - defined)
    assert not missing, f"the harness names make targets that do not exist: {missing}"


def test_every_script_the_driver_names_exists() -> None:
    _targets, scripts = _harness_commands()
    assert scripts, "no scripts parsed from the harness — the fence regex is wrong"
    missing = sorted(p for p in scripts if not (REPO / p).is_file())
    assert not missing, f"the harness names scripts that do not exist: {missing}"


def test_the_players_own_preflight_targets_run() -> None:
    """The two targets Step 0b declares mandatory, invoked the way the driver
    invokes them. `test-ux-preflight` is here because it is the one that was
    broken for ~30 cycles — a smoke that runs is the cheapest possible fence
    against the same class returning."""
    import subprocess

    for target in ("test-ux-preflight",):
        proc = subprocess.run(
            ["make", target], cwd=REPO, capture_output=True, text=True, timeout=600, check=False
        )
        assert proc.returncode == 0, (
            f"`make {target}` exited {proc.returncode}. Step 0b declares it mandatory, so a "
            f"cycle cannot start:\n{proc.stdout[-800:]}{proc.stderr[-400:]}"
        )


@pytest.mark.parametrize(
    "script",
    [
        "scripts/improve_policy.py",
        "scripts/improve_example_probes.py",
        "scripts/qa_smoke_bar.py",
        "scripts/improve_github_inbox.py",
        "scripts/improve_compact.py",
        "scripts/push_gate.py",
    ],
)
def test_driver_scripts_answer_help(script: str) -> None:
    """A driver step that cannot print its own usage is a step an agent cannot
    recover from."""
    import subprocess
    import sys

    assert (REPO / script).is_file(), f"{script} is missing"
    proc = subprocess.run(
        [sys.executable, script, "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 0, f"{script} --help exited {proc.returncode}: {proc.stderr[-300:]}"
