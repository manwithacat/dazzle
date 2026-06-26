"""Does the depth-2 closure rescue a fuzzy seed?

For each case: resolver -> top-3 seed modules -> union of their depth-2 import
closures -> does it contain a ground-truth module? This tests the real design:
approximate seed + deterministic closure, not exact seed resolution.
"""
# ruff: noqa  -- illustrative research spike script; not framework code

import ast
import re
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "src"
STOP = set("fix feat add the for into with mode path support a an of to on in render".split())


def terms(s):
    s = re.sub(r"\(#\d+\)", " ", s)
    out = set()
    for p in re.split(r"[^a-zA-Z0-9]+", s):
        for w in re.findall(r"[a-z0-9]+|[A-Z][a-z0-9]*", p):
            w = w.lower()
            if len(w) >= 3 and w not in STOP:
                out.add(w)
    return out


def path_for(mod):
    base = ROOT / Path(*mod.split("."))
    for c in (base.with_suffix(".py"), base / "__init__.py"):
        if c.exists():
            return c
    return None


def fp_imports(p):
    try:
        tree = ast.parse(p.read_text())
    except Exception:
        return set()
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[0] == "dazzle":
            out.add(n.module)
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[0] == "dazzle":
                    out.add(a.name)
    return out


def closure(seed, depth=2):
    seen = set()
    q = deque([(seed, 0)])
    while q:
        m, d = q.popleft()
        if m in seen:
            continue
        seen.add(m)
        if d >= depth:
            continue
        p = path_for(m)
        if not p:
            continue
        for imp in fp_imports(p):
            mm = imp if path_for(imp) else ".".join(imp.split(".")[:-1])
            if path_for(mm):
                q.append((mm, d + 1))
    return seen


# index
index = {}
for p in ROOT.rglob("*.py"):
    if "test" in p.name or "__pycache__" in str(p):
        continue
    mod = ".".join(p.relative_to(ROOT).with_suffix("").parts)
    if mod.endswith(".__init__"):
        mod = mod[:-9]
    st = set()
    try:
        for n in ast.walk(ast.parse(p.read_text())):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                st |= terms(n.name)
    except Exception:
        pass
    index[mod] = (terms(mod.replace(".", " ")), st)


def resolve(task, k=3):
    t = terms(task)
    scored = []
    for mod, (pt, st) in index.items():
        s = 3 * len(t & pt) + len(t & st)
        if s:
            scored.append((s, mod))
    scored.sort(reverse=True)
    return [m for _, m in scored[:k]]


CASES = [
    (
        "catalogue line/sparkline/radar/area + single-dim area fix",
        ["http.runtime.workspace_region_orchestration"],
    ),
    ("funnel_chart render path + catalogue funnel mode", ["http.runtime.workspace_region_render"]),
    (
        "box_plot render path + catalogue histogram/box_plot modes",
        ["http.runtime.workspace_region_render"],
    ),
    (
        "render stored-narrative overlay prose + confidence badge",
        ["render.fragment.region._builders_charts"],
    ),
    (
        "read stored insight into ctx provider seam + fallback",
        [
            "http.runtime.workspace_region_orchestration",
            "http.runtime.workspace_region_render",
            "render.fragment.region._context",
        ],
    ),
    (
        "StoredInsight type + insight-store provider seam",
        ["http.runtime.insight_store", "render.fragment.insight"],
    ),
    ("render rag_on band-tone badge in list cells", ["render.fragment.region._builders_tables"]),
    (
        "rag_on orchestration band tones to ctx",
        [
            "http.runtime.workspace_region_computes",
            "http.runtime.workspace_region_orchestration",
            "http.runtime.workspace_region_render",
        ],
    ),
    ("validate rag_on decorator E_RAG", ["core.lint", "core.validation.ux", "core.validator"]),
    ("parse rag_on + tone_bands region keywords", ["core.dsl_parser_impl.workspace"]),
    ("aggregate count where status in list silently returns 0", ["core.ir.condition_to_predicate"]),
]

seed_hit = clos_hit = 0
sizes = []
for task, truth in CASES:
    seeds = resolve(task, 3)
    ts = set("dazzle." + t for t in truth)
    sh = any(s in ts for s in seeds)
    union = set()
    for s in seeds:
        union |= closure(s, 2)
    ch = any(m in ts for m in union)
    sizes.append(len(union))
    seed_hit += sh
    clos_hit += ch
    print(
        f"{task[:48]:<50} seed-hit:{'Y' if sh else 'n'}  closure-hit:{'Y' if ch else 'n'}  (|closure|={len(union)})"
    )
n = len(CASES)
print(
    f"\ntop-3 seed recall: {seed_hit}/{n}={seed_hit / n:.0%}   +depth-2 closure recall: {clos_hit}/{n}={clos_hit / n:.0%}"
)
print(f"avg closure size (modules): {sum(sizes) / n:.0f}")
