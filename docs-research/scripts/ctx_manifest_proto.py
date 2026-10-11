"""Throwaway prototype: B(i) dependency closure + A capacity prediction.

Given a seed module, compute the first-party import closure over src/dazzle via
AST (deterministic), estimate tokens, and report what a pre-flight 'context
manifest' would say. Purpose: measure the ORDER empirically — does the closure
explode? do you need a relevance cut?
"""
# ruff: noqa  -- illustrative research spike script; not framework code

import ast
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "src"
PKG = "dazzle"


def mod_name(p: Path) -> str:
    rel = p.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def path_for(mod: str) -> Path | None:
    base = ROOT / Path(*mod.split("."))
    for cand in (base.with_suffix(".py"), base / "__init__.py"):
        if cand.exists():
            return cand
    return None


def first_party_imports(p: Path) -> set[str]:
    """Module names this file imports from within `dazzle` (top-level + lazy)."""
    try:
        tree = ast.parse(p.read_text(), filename=str(p))
    except Exception:
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == PKG:
            out.add(node.module)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] == PKG:
                    out.add(a.name)
    return out


def tokens(p: Path) -> int:
    try:
        return len(p.read_text()) // 4  # ~4 chars/token heuristic
    except Exception:
        return 0


def closure(seed_mod: str, max_depth: int):
    """BFS forward import closure with depth tracking."""
    seen: dict[str, int] = {}
    q = deque([(seed_mod, 0)])
    while q:
        mod, d = q.popleft()
        if mod in seen and seen[mod] <= d:
            continue
        seen[mod] = d
        if d >= max_depth:
            continue
        p = path_for(mod)
        if not p:
            continue
        for imp in first_party_imports(p):
            # normalize: an import of dazzle.x.y might be a symbol in dazzle.x
            m = imp
            if not path_for(m):
                m = ".".join(imp.split(".")[:-1])
            if path_for(m):
                q.append((m, d + 1))
    return seen


def report(seed_mod: str):
    p = path_for(seed_mod)
    if not p:
        print(f"seed {seed_mod} not found")
        return
    print(f"\n{'=' * 70}\nSEED: {seed_mod}  ({tokens(p)} tok)")
    for depth in (1, 2, 3, 999):
        seen = closure(seed_mod, depth)
        mods = [m for m in seen if path_for(m)]
        tot = sum(tokens(path_for(m)) for m in mods if path_for(m))
        label = f"depth {depth}" if depth != 999 else "full closure"
        print(f"  {label:>13}: {len(mods):>4} modules, ~{tot:>7,} tokens")


for seed in [
    "dazzle.http.runtime.workspace_region_render",  # the file from the #1473 task
    "dazzle.core.ir.condition_to_predicate",  # the #1472 fix file
    "dazzle.render.svg",  # the multi-series SVG file
]:
    report(seed)
