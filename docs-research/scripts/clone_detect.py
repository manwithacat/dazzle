"""Cheap near-duplicate function detector (the B(ii) reuse-feasibility spike).

For every function in src/dazzle, build a structural signature that blanks local
names / args / literals but keeps the *shape* plus the called-method and keyword
names (the API skeleton). Functions sharing a signature are Type-2 clones —
re-implemented capability. Measure the duplication rate and show the clusters.

The same index, queried with an about-to-be-written function's signature, is the
pre-write 'does this already exist?' check (the reinvented-capability counter-prior,
automated).

Run: python docs/research/scripts/clone_detect.py   (stdlib only; portable root)
"""

# ruff: noqa  -- illustrative research spike script; not framework code
import ast
import hashlib
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "src" / "dazzle"
MIN_STMTS = 5  # skip trivial stubs / properties


def signature(fn):
    """Structural token stream: node types + API names; local identifiers blanked."""
    toks = []

    def emit(node):
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
            toks.append(f"C:{type(node.value).__name__}")  # literal -> its type
        elif isinstance(node, ast.keyword):
            toks.append(f"K:{node.arg}")
        else:
            toks.append(type(node).__name__)
        for child in ast.iter_child_nodes(node):
            emit(child)

    for stmt in getattr(fn, "body", []):  # signature over the body only
        emit(stmt)
    return hashlib.md5("|".join(toks).encode()).hexdigest()


functions = []
for p in ROOT.rglob("*.py"):
    if "test" in p.name or "/examples/" in str(p) or "__pycache__" in str(p):
        continue
    try:
        tree = ast.parse(p.read_text())
    except Exception:
        continue
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            n = sum(1 for x in ast.walk(node) if isinstance(x, ast.stmt)) - 1
            if n >= MIN_STMTS:
                functions.append(
                    (signature(node), node.name, f"{p.relative_to(ROOT.parent)}:{node.lineno}", n)
                )

clusters = defaultdict(list)
for sig, name, loc, n in functions:
    clusters[sig].append((name, loc, n))
dup = {k: v for k, v in clusters.items() if len(v) >= 2}
in_clusters = sum(len(v) for v in dup.values())
total = len(functions)

print(f"functions analysed (>= {MIN_STMTS} stmts): {total}")
print(f"near-duplicate clusters (size >= 2):       {len(dup)}")
print(f"functions in a clone cluster:              {in_clusters}  ({in_clusters / total:.1%})\n")
print("Largest clusters:")
for sig, members in sorted(dup.items(), key=lambda kv: -len(kv[1]))[:12]:
    names = sorted({m[0] for m in members})
    print(f"  x{len(members):>2}  names={names[:5]}{' ...' if len(names) > 5 else ''}")
    for name, loc, n in members[:2]:
        print(f"        {loc}")
