"""Framework structural-fitness: Type-2 function-clone detection.

The **layer-3 filter** for the ``reinvented-capability`` counter-prior
(``docs/counter-priors/reinvented-capability.md``). Two functions are a Type-2
clone when they share a *structural signature* — the same argument arity, the same
control-flow shape, and the same called-method / keyword names, modulo local
identifier names and literal values. A cluster of such functions is re-implemented
capability: the same logic typed more than once, the duplication agentic
production over-produces because the existing copy wasn't in the context window.

``compute_clone_index`` finds the clusters keyed by signature;
``build_clone_baseline`` freezes the accepted set; ``compare_clones`` flags a
*new* or *grown* cluster. The committed baseline feeds
``tests/unit/test_clone_ratchet.py`` (the duplication creep gate), mirroring the
complexity ratchet in :mod:`dazzle.fitness.code`.

The ratchet is keyed on the **signature**, not on function names, so a rename or
file-move of an already-clustered function does NOT trip it (the structure is
unchanged) — only genuine new duplication does. A cluster that is
parallel-by-design (a family of CLI sub-commands, route handlers) rather than a
single capability re-derived is *accepted residue*; it lives in the baseline and
the gate only forbids growth beyond it.
"""

from __future__ import annotations

import ast
import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any

#: Functions with fewer statements than this are skipped — trivial stubs,
#: properties, and one-liners cluster spuriously and carry no reuse signal.
MIN_STMTS = 5


def _py_files(root: Path) -> list[Path]:
    """Framework .py files under ``root``, excluding tests, examples, caches.

    The test exclusion is anchored (``test_*`` / a ``tests/`` dir) so production
    modules whose name merely contains "test" — ``testing/``, ``test_design.py``,
    ``*_test_generator.py`` — are *covered*, not silently skipped.
    """
    out: list[Path] = []
    for p in sorted(root.rglob("*.py")):
        s = str(p)
        if p.name.startswith("test_") or "/tests/" in s:
            continue
        if "/examples/" in s or "__pycache__" in s:
            continue
        out.append(p)
    return out


def _arg_arity(fn: ast.AST) -> int:
    args = getattr(fn, "args", None)
    if args is None:
        return 0
    return (
        len(getattr(args, "posonlyargs", []))
        + len(args.args)
        + len(args.kwonlyargs)
        + (1 if args.vararg else 0)
        + (1 if args.kwarg else 0)
    )


def _signature(fn: ast.AST) -> str:
    """Structural token stream of a function: arg arity + body shape + API names.

    Blanks local names (``ast.Name`` → ``N``), arguments (``A``), and literals
    (kept as their *type*), but retains the argument arity, the node-type shape,
    and the called method / keyword names — the "API skeleton". Two functions with
    the same signature differ only in local names and literal values.
    """
    toks: list[str] = [f"ARITY:{_arg_arity(fn)}"]

    def emit(node: ast.AST) -> None:
        if isinstance(node, ast.Name):
            toks.append("N")
            return
        if isinstance(node, ast.arg):
            toks.append("A")
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            toks.append("DEF")  # blank the def name
        elif isinstance(node, ast.Attribute):
            toks.append(f"AT:{node.attr}")  # keep method/attr name (API surface)
        elif isinstance(node, ast.Constant):
            toks.append(f"C:{type(node.value).__name__}")  # literal → its type
        elif isinstance(node, ast.keyword):
            toks.append(f"K:{node.arg}")
        else:
            toks.append(type(node).__name__)
        for child in ast.iter_child_nodes(node):
            emit(child)

    for stmt in getattr(fn, "body", []):
        emit(stmt)
    return hashlib.md5("|".join(toks).encode(), usedforsecurity=False).hexdigest()


def _stmt_count(fn: ast.AST) -> int:
    return sum(1 for x in ast.walk(fn) if isinstance(x, ast.stmt)) - 1


def compute_clone_index(root: Path, min_stmts: int = MIN_STMTS) -> dict[str, list[str]]:
    """Map each Type-2 clone signature to its members under ``root``.

    Members are stable identities ``"<relpath>::<funcname>"`` (no line numbers).
    Only signatures with ≥ 2 distinct members (a clone cluster) are returned.
    """
    by_sig: dict[str, list[str]] = defaultdict(list)
    for p in _py_files(root):
        try:
            tree = ast.parse(p.read_text())
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = p.relative_to(root.parent)
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and _stmt_count(node) >= min_stmts
            ):
                by_sig[_signature(node)].append(f"{rel}::{node.name}")
    return {sig: sorted(set(m)) for sig, m in by_sig.items() if len(set(m)) >= 2}


def build_clone_baseline(root: Path) -> list[dict[str, Any]]:
    """The committed baseline: one entry per accepted clone cluster.

    A list (sorted by first member name for readable diffs) of
    ``{"signature", "count", "names"}``. ``signature`` is the ratchet key
    (rename/move-invariant); ``count`` is what may not grow; ``names`` are for
    human review only.
    """
    idx = compute_clone_index(root)
    entries = [
        {"signature": sig, "count": len(members), "names": members} for sig, members in idx.items()
    ]
    return sorted(entries, key=lambda e: e["names"][0])


def compare_clones(baseline: list[dict[str, Any]], current: dict[str, list[str]]) -> list[str]:
    """Return violations: signatures that are new, or whose cluster grew.

    Keyed on signature, so renames/moves (same structure) never trip it; only a
    new structural duplicate, or a new member joining a known family, does.
    """
    base_count = {e["signature"]: e["count"] for e in baseline}
    violations: list[str] = []
    for sig, members in sorted(current.items(), key=lambda kv: kv[1][0]):
        prior = base_count.get(sig)
        if prior is None:
            violations.append("new clone cluster: " + ", ".join(members))
        elif len(members) > prior:
            violations.append(f"clone cluster grew {prior}→{len(members)}: " + ", ".join(members))
    return violations


def stale_baseline_clusters(
    baseline: list[dict[str, Any]], current: dict[str, list[str]]
) -> list[str]:
    """Return baseline clusters that shrank or were deduped away (wins to lock in)."""
    stale: list[str] = []
    for e in baseline:
        now = len(current.get(e["signature"], []))
        if now < e["count"]:
            stale.append(f"{', '.join(e['names'])} (baseline {e['count']}, now {now})")
    return stale
