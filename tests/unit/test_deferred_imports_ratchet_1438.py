"""#1438: function-level `dazzle.*` imports — ratchet down, never up.

2126 `dazzle.*` imports sit inside function bodies (not module top) as cycle-avoidance
workarounds — `dazzle/__init__` eagerly imports `http`, so a top-level import would trip
a real boot cycle, and the import-linter contracts run `allow_indirect_imports` as a
result. Each deferred import hides a dependency edge, defers `ImportError` to first call,
and marks the host module as an over-central hub.

This gate freezes the per-file counts and lets them only **shrink**: it forbids a net
increase per file and forbids a *new* file growing a function-level `dazzle.*` import.
Burning the count down is the long campaign (break the underlying cycle by extracting a
shared leaf — the `route_support`/`app_paths` pattern — then hoist the import; or inject
the dependency via RuntimeServices/ServerState). As a module drops below its baseline,
**lower its entry in `fixtures/deferred_imports_baseline.json`** to lock the win.

**Test-coupling convention (the #1438 unblock).** Many deferred imports are NOT real
cycles — they're pinned by tests that `@patch("<source-module>.X")` and rely on the
function-local import late-binding at call time. Hoisting such an import to module-top
binds it at LOAD time, so a source patch misses. To hoist it, **migrate the test to
patch-in-namespace**: patch `"<consumer-module>.X"` (where the hoisted import lands and
is called), not the source module — in the SAME change as the hoist. Note: this only
applies to imported *names that are called* (a class/function instantiation); patching a
*method* on a class (`@patch("mod.Cls.method")`) is import-location-independent and never
needs migration. High-breadth utilities patched across many files (e.g. `pg_backend`,
`auth`, `token_store`) are deliberately left deferred — migrating a dozen test files to
hoist a handful of imports is poor value; their baseline entries are the accepted residue.

Methodology note: counts function-body `ImportFrom`/`Import` whose top package is
`dazzle` (matching the baseline generator). Module-top imports and non-`dazzle` deferred
imports are out of scope.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src" / "dazzle"
_BASELINE_PATH = Path(__file__).resolve().parent / "fixtures" / "deferred_imports_baseline.json"


def _is_dazzle_import(node: ast.AST) -> bool:
    if isinstance(node, ast.ImportFrom):
        return bool(node.module) and node.module.split(".")[0] == "dazzle"
    if isinstance(node, ast.Import):
        return any(alias.name.split(".")[0] == "dazzle" for alias in node.names)
    return False


def _deferred_dazzle_imports(path: Path) -> int:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return 0
    count = 0
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(fn):
                if _is_dazzle_import(node):
                    count += 1
    return count


def _current_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in _SRC.rglob("*.py"):
        n = _deferred_dazzle_imports(p)
        if n:
            counts[str(p.relative_to(_REPO))] = n
    return counts


def test_no_file_exceeds_its_deferred_import_baseline() -> None:
    baseline: dict[str, int] = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    current = _current_counts()
    regressions: list[str] = []
    for rel, n in sorted(current.items()):
        cap = baseline.get(rel, 0)
        if n > cap:
            regressions.append(f"{rel}: {n} function-level dazzle.* imports (baseline {cap})")
    assert not regressions, (
        "Function-level `dazzle.*` imports grew (#1438). Don't add a deferred import — break "
        "the underlying cycle (extract the shared types/leaf to a lower layer, then hoist to "
        "module top) or inject the dependency via RuntimeServices/ServerState. If this is an "
        "unavoidable new cycle workaround, raise the file's entry in "
        "`fixtures/deferred_imports_baseline.json` with justification:\n  "
        + "\n  ".join(regressions)
    )


def test_baseline_has_no_stale_entries() -> None:
    """A file that dropped below its baseline (a win) must have its entry lowered/removed —
    keeps the ratchet honest and the campaign's progress visible."""
    baseline: dict[str, int] = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    current = _current_counts()
    stale: list[str] = []
    for rel, cap in sorted(baseline.items()):
        n = current.get(rel, 0)
        if n < cap:
            stale.append(f"{rel}: now {n}, baseline still {cap}")
    assert not stale, (
        "`deferred_imports_baseline.json` is ahead of the tree — these files dropped below "
        "baseline; lower their entries (or remove at 0) to lock in the burn-down:\n  "
        + "\n  ".join(stale)
    )
