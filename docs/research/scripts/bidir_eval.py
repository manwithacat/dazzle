"""Cheap bidirectional closure: forward deps + direct dependents + siblings.

The #1472 miss (resolver picked aggregate_where_parser, truth was
condition_to_predicate — siblings under a common importer) needs reverse edges.
Add ONLY: direct dependents of the seed, and the seed's siblings (the direct
forward-imports of those dependents). Bounded — no transitive reverse explosion.
Re-measure recall vs forward-only.
"""
# ruff: noqa  -- illustrative research spike script; not framework code

import ast
import re
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "src"
STOP = set("fix feat add the for into with mode path support a an of to on in render".split())


def terms(s):
    out = set()
    for p in re.split(r"[^a-zA-Z0-9]+", re.sub(r"\(#\d+\)", " ", s)):
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


# ---- single pass: forward imports (resolved to modules), reverse map, symbol terms ----
fwd = defaultdict(set)
rev = defaultdict(set)
index = {}
allmods = []
for p in ROOT.rglob("*.py"):
    if "test" in p.name or "__pycache__" in str(p):
        continue
    mod = ".".join(p.relative_to(ROOT).with_suffix("").parts)
    if mod.endswith(".__init__"):
        mod = mod[:-9]
    allmods.append((mod, p))

for mod, p in allmods:
    st = set()
    raw = set()
    try:
        tree = ast.parse(p.read_text())
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                st |= terms(n.name)
            elif isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[0] == "dazzle":
                raw.add(n.module)
            elif isinstance(n, ast.Import):
                for a in n.names:
                    if a.name.split(".")[0] == "dazzle":
                        raw.add(a.name)
    except Exception:
        pass
    index[mod] = (terms(mod.replace(".", " ")), st)
    for imp in raw:
        m = imp if path_for(imp) else ".".join(imp.split(".")[:-1])
        if path_for(m):
            fwd[mod].add(m)
            rev[m].add(mod)


def fwd_closure(seed, depth=2):
    seen = set()
    q = deque([(seed, 0)])
    while q:
        m, d = q.popleft()
        if m in seen:
            continue
        seen.add(m)
        if d < depth:
            for nb in fwd.get(m, ()):
                q.append((nb, d + 1))
    return seen


def bidir(seed, depth=2):
    base = fwd_closure(seed, depth)
    deps = rev.get(seed, set())  # who imports the seed (direct)
    base |= deps
    for dep in deps:  # the seed's siblings = dep's direct forward imports
        base |= fwd.get(dep, set())
    return base


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
        ["dazzle.http.runtime.workspace_region_orchestration"],
    ),
    (
        "funnel_chart render path + catalogue funnel mode",
        ["dazzle.http.runtime.workspace_region_render"],
    ),
    (
        "box_plot render path + catalogue histogram/box_plot modes",
        ["dazzle.http.runtime.workspace_region_render"],
    ),
    (
        "render stored-narrative overlay prose + confidence badge",
        ["dazzle.render.fragment.region._builders_charts"],
    ),
    (
        "read stored insight into ctx provider seam + fallback",
        [
            "dazzle.http.runtime.workspace_region_orchestration",
            "dazzle.http.runtime.workspace_region_render",
            "dazzle.render.fragment.region._context",
        ],
    ),
    (
        "StoredInsight type + insight-store provider seam",
        ["dazzle.http.runtime.insight_store", "dazzle.render.fragment.insight"],
    ),
    (
        "render rag_on band-tone badge in list cells",
        ["dazzle.render.fragment.region._builders_tables"],
    ),
    (
        "rag_on orchestration band tones to ctx",
        [
            "dazzle.http.runtime.workspace_region_computes",
            "dazzle.http.runtime.workspace_region_orchestration",
            "dazzle.http.runtime.workspace_region_render",
        ],
    ),
    (
        "validate rag_on decorator E_RAG",
        ["dazzle.core.lint", "dazzle.core.validation.ux", "dazzle.core.validator"],
    ),
    ("parse rag_on + tone_bands region keywords", ["dazzle.core.dsl_parser_impl.workspace"]),
    (
        "aggregate count where status in list silently returns 0",
        ["dazzle.core.ir.condition_to_predicate"],
    ),
]

fc = bc = 0
fs = []
bs = []
for task, truth in CASES:
    seeds = resolve(task, 3)
    ts = set(truth)
    fu = set()
    bu = set()
    for s in seeds:
        fu |= fwd_closure(s, 2)
        bu |= bidir(s, 2)
    fh = any(m in ts for m in fu)
    bh = any(m in ts for m in bu)
    fc += fh
    bc += bh
    fs.append(len(fu))
    bs.append(len(bu))
    flag = "  <-- rescued by bidir" if (bh and not fh) else ""
    print(
        f"{task[:44]:<46} fwd:{'Y' if fh else 'n'} bidir:{'Y' if bh else 'n'}  (|f|={len(fu)} |b|={len(bu)}){flag}"
    )
n = len(CASES)
print(f"\nforward closure recall:       {fc}/{n}={fc / n:.0%}  (avg {sum(fs) / n:.0f} modules)")
print(f"bidirectional closure recall: {bc}/{n}={bc / n:.0%}  (avg {sum(bs) / n:.0f} modules)")
