"""Vitality — static connectedness analysis (Phase 1 of the Vitality thesis, #1521).

Builds an AST call graph over the source tree and asks, for each function: *is it
reachable from a real entry point, and how many callers does it have?* — the
topological half of the Vitality thesis (`dev_docs/dazzle-vitality-thesis.md`).

**The Dazzle-specific correction (thesis §6).** A naive static call graph
over-reports dead code here, because Dazzle's dispatch is registry/decorator-driven
(the renderer/primitive registries, parser keyword dispatchers, route/CLI/MCP
registrations) — real call edges a pure AST walk can't see. This module recovers
them cheaply from the *code itself*: a function that is **referenced as a value**
(decorated, passed as an argument, stored in a dict — i.e. handed to a registry)
is treated as dispatch-reachable. The **augmentation delta** — how many functions
that recovery rescues from the "unreachable" set — is the Phase-1 acceptance
signal: if augmentation changes nothing, the recovery isn't working.

Report-only, no runtime, no coverage, no deletion (per the thesis non-goals). AST
resolution is deliberately conservative: an unresolved call is *counted* (a
graph-completeness signal), never guessed. griffe/jedi could sharpen resolution
later; the registry-reference augmentation is what makes the current cut honest
for Dazzle.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

# Dunder methods are called by the interpreter/protocols, never "dead".
_PROTOCOL_METHODS = frozenset(
    {
        "__init__",
        "__call__",
        "__enter__",
        "__exit__",
        "__aenter__",
        "__aexit__",
        "__iter__",
        "__next__",
        "__getitem__",
        "__setitem__",
        "__post_init__",
        "__repr__",
        "__str__",
        "__eq__",
        "__hash__",
        "__len__",
        "__contains__",
    }
)


@dataclass
class _ModuleFacts:
    module: str
    functions: dict[str, ast.AST]  # qualname -> def node
    imports: dict[str, str]  # local alias -> target dotted path (from-imports + import-as)
    import_modules: set[str]  # local aliases that are modules (import x / import x as y)
    exported: set[str]  # simple names in __all__


@dataclass
class ConnectednessReport:
    total_functions: int
    entry_points: int
    reachable_raw: int  # reachable from entry points over CALL edges only
    reachable_augmented: int  # + registry/decorator-referenced functions
    augmentation_delta: int  # functions rescued by the reference augmentation
    unresolved_calls: int  # call sites the AST walk couldn't resolve (completeness signal)
    candidates: list[str] = field(default_factory=list)  # isolated: 0 callers, unreachable


def _module_name(path: Path, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = [p for p in rel.parts if p != "__init__"]
    return ".".join(parts)


def _py_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _import_prefix(module: str, is_package: bool, node: ast.ImportFrom) -> str | None:
    """Absolute dotted prefix a ``from … import`` targets (relative imports resolved).

    Dazzle uses relative intra-package imports (``from ._shared import x``); without
    resolving ``node.level`` to an absolute path, those edges never match a callee's
    absolute qualname and every relatively-imported function false-reads as an islet.
    """
    if not node.level:
        return node.module
    parts = module.split(".")
    cut = node.level - (1 if is_package else 0)  # a package __init__ anchors at itself
    if cut > len(parts):
        return None
    base = ".".join(parts[: len(parts) - cut])
    return f"{base}.{node.module}" if node.module else base


def _scan_module(path: Path, root: Path) -> _ModuleFacts | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return None
    module = _module_name(path, root)
    is_package = path.name == "__init__.py"
    functions: dict[str, ast.AST] = {}
    imports: dict[str, str] = {}
    import_modules: set[str] = set()
    exported: set[str] = set()

    class _Collect(ast.NodeVisitor):
        def __init__(self) -> None:
            self._cls: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self._cls.append(node.name)
            self.generic_visit(node)
            self._cls.pop()

        def _add_fn(self, node: ast.AST, name: str) -> None:
            qual = ".".join([module, *self._cls, name])
            functions[qual] = node

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._add_fn(node, node.name)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._add_fn(node, node.name)
            self.generic_visit(node)

    _Collect().visit(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            prefix = _import_prefix(module, is_package, node)
            if prefix:
                for alias in node.names:
                    imports[alias.asname or alias.name] = f"{prefix}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                import_modules.add(alias.asname or alias.name.split(".")[0])
                imports[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if (
                    isinstance(tgt, ast.Name)
                    and tgt.id == "__all__"
                    and isinstance(node.value, ast.List | ast.Tuple)
                ):
                    exported |= {
                        el.value
                        for el in node.value.elts
                        if isinstance(el, ast.Constant) and isinstance(el.value, str)
                    }
    return _ModuleFacts(module, functions, imports, import_modules, exported)


def _class_of(qualname: str, module: str) -> str | None:
    """The class name for a method qualname (``module.Class.method``), else None."""
    tail = qualname[len(module) + 1 :] if qualname.startswith(module + ".") else qualname
    parts = tail.split(".")
    return parts[0] if len(parts) == 2 else None


def _resolve_call(
    call: ast.Call, facts: _ModuleFacts, cls: str | None, functions: set[str]
) -> str | None:
    """Best-effort resolve a call site to a callee qualname in ``functions``, or None."""
    fn = call.func
    if isinstance(fn, ast.Name):
        local = f"{facts.module}.{fn.id}"
        if local in functions:
            return local
        tgt = facts.imports.get(fn.id)
        return tgt if tgt in functions else None
    if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
        base = fn.value.id
        if base in ("self", "cls") and cls is not None:
            cand = f"{facts.module}.{cls}.{fn.attr}"
            return cand if cand in functions else None
        if base in facts.import_modules:
            cand = f"{facts.imports.get(base, base)}.{fn.attr}"
            return cand if cand in functions else None
    return None


def _dispatch_reference_names(tree: ast.AST) -> set[str]:
    """Simple names that are dispatched somewhere a pure AST call-graph can't pin.

    Three cheap recoveries, all name-based:
    - **passed as a value** — a bare ``Name`` handed to a call (``register(handler)`` /
      ``Depends(dep)``) → registry/DI dispatch.
    - **decorator** — a bare-``Name`` decorator.
    - **attribute call** — ``x.method()`` anywhere: with duck typing you can't know
      ``x``'s type statically, but the method name being *called as an attribute* means
      a method of that name is reached. Without this, every method that's invoked on an
      instance (the common case) falsely reads as uncalled — the AST-only over-report.

    Coarse (name-keyed, so a shared name over-rescues), which is the right bias for a
    *"review these"* report: we'd rather miss a real islet than flag 4000 false ones.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            args = list(node.args) + [k.value for k in node.keywords]
            names |= {a.id for a in args if isinstance(a, ast.Name)}
            if isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)  # x.method() → 'method' is dispatched
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            names |= {d.id for d in node.decorator_list if isinstance(d, ast.Name)}
    return names


def _build_call_edges(
    facts_by_file: dict[Path, _ModuleFacts], functions: set[str]
) -> tuple[dict[str, set[str]], int]:
    """Resolve every call site to a callee qualname. Returns (edges, unresolved_count)."""
    edges: dict[str, set[str]] = {q: set() for q in functions}
    unresolved = 0
    for facts in facts_by_file.values():
        for qual, node in facts.functions.items():
            cls = _class_of(qual, facts.module)
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Call):
                    continue
                callee = _resolve_call(sub, facts, cls, functions)
                if callee is not None:
                    edges[qual].add(callee)
                else:
                    unresolved += 1
    return edges, unresolved


def analyze_connectedness(root: Path) -> ConnectednessReport:
    """Build the AST call graph over ``root`` and compute the Phase-1 report."""
    facts_by_file: dict[Path, _ModuleFacts] = {}
    dispatch_names: set[str] = set()
    for path in _py_files(root):
        facts = _scan_module(path, root)
        if facts is None:
            continue
        facts_by_file[path] = facts
        try:
            dispatch_names |= _dispatch_reference_names(ast.parse(path.read_text(encoding="utf-8")))
        except (SyntaxError, UnicodeDecodeError):
            pass

    functions: set[str] = set()
    exported_simple: set[str] = set()
    decorated: set[str] = set()
    for facts in facts_by_file.values():
        functions |= set(facts.functions)
        exported_simple |= facts.exported
        for qual, node in facts.functions.items():
            if getattr(node, "decorator_list", None):
                decorated.add(qual)

    # Call edges (caller qualname -> set of callee qualnames).
    edges, unresolved = _build_call_edges(facts_by_file, functions)

    fan_in: dict[str, int] = dict.fromkeys(functions, 0)
    for callers in edges.values():
        for callee in callers:
            fan_in[callee] += 1

    def _leaf(q: str) -> str:
        return q.rsplit(".", 1)[-1]

    # Entry points: exported names, decorated functions, main/cli, protocol methods.
    entry_points = {
        q
        for q in functions
        if _leaf(q) in exported_simple
        or q in decorated
        or _leaf(q) in ("main", "cli")
        or _leaf(q).startswith("test_")  # pytest invokes these
        or _leaf(q) in _PROTOCOL_METHODS
    }
    # Augmentation roots: entry points + functions handed to a registry by reference.
    referenced = {q for q in functions if _leaf(q) in dispatch_names} | decorated

    def _reach(roots: set[str]) -> set[str]:
        seen = set(roots)
        stack = list(roots)
        while stack:
            for nxt in edges.get(stack.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen & functions

    reachable_raw = _reach(entry_points)
    reachable_augmented = _reach(entry_points | referenced)

    candidates = sorted(
        q
        for q in functions
        if fan_in[q] == 0
        and q not in reachable_augmented
        and q not in entry_points
        and _leaf(q) not in _PROTOCOL_METHODS
    )

    return ConnectednessReport(
        total_functions=len(functions),
        entry_points=len(entry_points),
        reachable_raw=len(reachable_raw),
        reachable_augmented=len(reachable_augmented),
        augmentation_delta=len(reachable_augmented) - len(reachable_raw),
        unresolved_calls=unresolved,
        candidates=candidates,
    )


def render_report_md(report: ConnectednessReport, *, top: int = 40) -> str:
    """Render the Phase-1 connectedness report as markdown."""
    pct = (
        100 * report.reachable_augmented / report.total_functions if report.total_functions else 0.0
    )
    lines = [
        "# Vitality — static connectedness (Phase 1, #1521)",
        "",
        f"- Functions analysed: **{report.total_functions}**",
        f"- Entry points (routes/CLI/exports/protocol): **{report.entry_points}**",
        f"- Reachable (raw call graph): **{report.reachable_raw}**",
        f"- Reachable (+registry/decorator augmentation): **{report.reachable_augmented}** "
        f"({pct:.0f}%)",
        f"- **Augmentation delta (functions rescued from 'unreachable'): {report.augmentation_delta}**",
        f"- Unresolved call sites (graph-completeness signal): {report.unresolved_calls}",
        f"- Islet candidates (0 callers, unreachable, non-protocol): **{len(report.candidates)}**",
        "",
        "> Report-only, AST-based, conservative (unresolved calls are counted, never "
        "guessed). A high augmentation delta means registry/decorator dispatch is the "
        "dominant reachability path — expected for Dazzle. Candidates are *review prompts*, "
        "not dead code: an AST-only graph still misses some dynamic dispatch.",
        "",
        "## Islet candidates (review these)",
        "",
    ]
    if not report.candidates:
        lines.append("_None — every function is reached or referenced._")
    else:
        for q in report.candidates[:top]:
            lines.append(f"- `{q}`")
        if len(report.candidates) > top:
            lines.append(f"- …and {len(report.candidates) - top} more")
    return "\n".join(lines) + "\n"
