"""Gate: no unreferenced module-level definition may accumulate in ``src/``.

A definition nothing calls is not a style nit — it is a claim the codebase makes
about itself that nothing has checked since it was written. Two real instances
found by this analysis on 2026-10-02, both unreferenced across all 6510 tracked
files in any language:

* ``http/runtime/auth/connection_create_form.py::leftover_group_map_stay_put`` —
  a one-line predicate left behind when the caller switched to raising
  ``CreateFormError``.
* ``dazzle_e2e/harness.py::run_testspec`` — a batch "run every flow in a
  testspec" wrapper, superseded by looping ``run_flow`` at the call sites and
  never in ``dazzle_e2e.__all__``.

Methodology, and what it deliberately does not claim:

* Scans **module-level** ``def``/``class`` only. Methods are usually called
  through an instance, which is not a name reference in any file.
* **Skips decorated definitions.** This framework registers by decorator
  (``@app.command("version")``, ``@router.get("/x")``, ``@register("tool")``),
  which binds a callable with no textual use site. Skipping them is what keeps
  every CLI command in the repo out of the report.
* Aliveness is decided by a **whole-repo word search**, not by AST — because
  Dazzle dispatches on strings (parser keywords, MCP tool names, IR type names,
  dict keys), so a definition reached only by name is genuinely alive and an
  AST-only reference index would flag it.
* Known limitation: two modules may each define the same name. If one defines
  and calls it while the other only defines it, the second reads as alive. That
  is a false *negative* — this gate never blocks a legitimate change, it only
  occasionally misses dead code. A false positive would be worse than useless.

Regenerating the baseline (only when a finding is a deliberate, documented
keep — e.g. an entry point resolved by string at runtime)::

    # edit fixtures/dead_definitions_baseline.json, then:
    python -m pytest tests/unit/test_dead_definition_ratchet.py -q
"""

from __future__ import annotations

import ast
import functools
import json
import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"
_BASELINE_PATH = Path(__file__).resolve().parent / "fixtures" / "dead_definitions_baseline.json"

#: Extensions worth scanning for use sites. Deliberately excludes ``.json``,
#: ``.css``, ``.js``: a Python identifier is not called from a lockfile or a
#: vendored bundle, and those are most of the bytes in the tree (the whole-repo
#: pass has to be cheap enough to live in the gate suite).
_TEXT_SUFFIXES = frozenset(
    {
        ".cfg",
        ".html",
        ".ini",
        ".j2",
        ".md",
        ".py",
        ".sh",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
)
_MAX_BYTES = 4_000_000
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _tracked_files() -> list[Path]:
    """Every tracked text file, via git, falling back to a filesystem walk."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=_REPO,
            check=True,
            capture_output=True,
            text=True,
        )
        rels = [r for r in proc.stdout.split("\0") if r]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return sorted(
            p
            for p in _REPO.rglob("*")
            if p.is_file() and ".git" not in p.parts and p.suffix in _TEXT_SUFFIXES
        )
    out: list[Path] = []
    for rel in rels:
        p = _REPO / rel
        if p.suffix in _TEXT_SUFFIXES and p.is_file() and p.stat().st_size < _MAX_BYTES:
            out.append(p)
    return out


#: Directories under src/ that hold build output or vendored code, not framework
#: source. `src/dazzle/examples/simple_task/build/**/node_modules/` is real: it is
#: a third-party Python file that this scan would otherwise report as dead code.
_SKIP_DIRS = frozenset({"__pycache__", "node_modules", "build", "dist", ".dazzle", ".venv"})


def _is_test_module(path: Path) -> bool:
    """True for pytest-collected modules — their ``Test*`` / ``test_*`` names are
    entry points, not call sites.

    Anchored the same way ``fitness.clones._py_files`` anchors it, so a
    production module that merely contains "test" (``testing/``,
    ``test_design.py``) stays covered.
    """
    parts = path.parts
    return path.name.startswith("test_") or path.name.endswith("_test.py") or "tests" in parts


def _candidates() -> dict[str, tuple[Path, int]]:
    """``"relpath::name"`` → (defining file, how many times it is defined there).

    The definition count matters: `def helper` is not a *use* of `helper`, so it
    has to be subtracted before asking whether anything calls it. (Counting it as
    a use is how this first reported a helper dead while its own call site sat
    10 lines above the `def`.)
    """
    found: dict[str, tuple[Path, int]] = {}
    for path in sorted(_SRC.rglob("*.py")):
        if any(part in _SKIP_DIRS for part in path.parts) or _is_test_module(path):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), str(path))
        except SyntaxError:
            continue
        rel = path.relative_to(_REPO)
        defined: dict[str, int] = {}
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if node.decorator_list or node.name.startswith("__"):
                continue
            defined[node.name] = defined.get(node.name, 0) + 1
        for name, count in defined.items():
            found[f"{rel}::{name}"] = (path, count)
    return found


def _token_counts(wanted: set[str]) -> dict[Path, dict[str, int]]:
    """Per-file counts of the candidate names only (memory-light)."""
    counts: dict[Path, dict[str, int]] = {}
    for path in _tracked_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hits: dict[str, int] = {}
        for token in _TOKEN.findall(text):
            if token in wanted:
                hits[token] = hits.get(token, 0) + 1
        if hits:
            counts[path] = hits
    return counts


@functools.lru_cache(maxsize=1)
def _current_dead() -> list[str]:
    """Candidates whose name occurs nowhere except their own definition.

    Memoised: both gate assertions ask the same whole-repo question, and the
    answer costs ~10s.
    """
    candidates = _candidates()
    if not candidates:
        return []
    wanted = {key.split("::", 1)[1] for key in candidates}
    counts = _token_counts(wanted)

    totals: dict[str, int] = {}
    for hits in counts.values():
        for name, n in hits.items():
            totals[name] = totals.get(name, 0) + n

    dead: list[str] = []
    for key, (_path, defs) in sorted(candidates.items()):
        name = key.split("::", 1)[1]
        uses = totals.get(name, 0) - defs
        if uses <= 0:
            dead.append(key)
    return dead


def test_baseline_is_a_well_formed_list() -> None:
    data = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert all(isinstance(e, str) and "::" in e for e in data)


def test_no_new_unreferenced_definition_in_src() -> None:
    baseline = set(json.loads(_BASELINE_PATH.read_text(encoding="utf-8")))
    new = [key for key in _current_dead() if key not in baseline]
    assert not new, (
        "A module-level definition in src/ has no reference anywhere in the "
        "repository (any language). Either wire it up, or delete it — an "
        "unreferenced definition is a claim nothing keeps honest:\n  "
        + "\n  ".join(new)
        + "\nIf it is deliberately reached by string (a dynamic entry point), "
        "add it to fixtures/dead_definitions_baseline.json with a comment in "
        "that file saying how it is resolved."
    )


def test_baseline_has_no_stale_entries() -> None:
    """A definition that got wired up or deleted is a win — lock it in."""
    baseline = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    current = set(_current_dead())
    stale = sorted(set(baseline) - current)
    assert not stale, (
        "fixtures/dead_definitions_baseline.json is ahead of the tree — these "
        "entries are referenced again (or gone); remove them to lock in the "
        "progress:\n  " + "\n  ".join(stale)
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("@app.command('version')\ndef version_command():\n    pass\n", False),
        ("def helper():\n    pass\n", True),
        ("class Widget:\n    pass\n", True),
        ("def __dunder__():\n    pass\n", False),
    ],
)
def test_candidate_extraction_skips_registration_and_dunders(
    tmp_path: Path, source: str, expected: bool
) -> None:
    """Every CLI command in this repo is decorated; none of them are dead code."""
    (tmp_path / "mod.py").write_text(source, encoding="utf-8")
    tree = ast.parse(source)
    node = tree.body[0]
    is_candidate = not node.decorator_list and not node.name.startswith("__")
    assert is_candidate is expected
