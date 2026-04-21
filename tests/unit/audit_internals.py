"""On-demand audit report for half-finished internals.

Advisory only — not part of the preflight gate. Run via ``make audit-internals``
to regenerate ``dev_docs/audit-internals.md``. The loop (or a human) then reads
the report and triages into ``finding_investigation`` cycles.

Sections:

1. **IR field orphans** — public fields on IR dataclasses with zero external
   readers. Same scan as ``test_ir_field_reader_parity.py`` but without the
   ratchet — emits the full list, organised by declaring module.

2. **Module import-graph orphans** — Python modules under ``src/dazzle*/`` with
   zero in-edges from any other module. High false-positive rate (cycle 328
   measured ~83%: plugins, entry points, side-effect-import modules like
   Alembic migrations all appear orphan). Still useful — the #834 hot_reload
   finding came from this exact shape. Excludes obvious entry-point shapes:

     * ``__main__.py`` files
     * Files declared as console-script entry points in ``pyproject.toml``
     * Files with ``if __name__ == "__main__"`` and no known importer
     * Alembic migration files (``alembic/versions/*.py``)

Running this file directly writes the report (``python tests/unit/audit_internals.py``).
"""

from __future__ import annotations

import ast
import re
import tomllib
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
IR_ROOT = SRC_ROOT / "dazzle" / "core" / "ir"
SCAN_ROOTS = (SRC_ROOT / "dazzle", SRC_ROOT / "dazzle_back", SRC_ROOT / "dazzle_ui")
REPORT_PATH = REPO_ROOT / "dev_docs" / "audit-internals.md"

JINJA_ATTR_RE = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)")
GETATTR_FAMILY = {"getattr", "setattr", "hasattr", "delattr"}
PYDANTIC_META = {"model_config", "model_fields", "model_computed_fields"}


# -----------------------------------------------------------------------------
# Section 1: IR field orphans (full list, no ratchet)
# -----------------------------------------------------------------------------


def _is_scannable_field(name: str) -> bool:
    return not name.startswith("_") and name not in PYDANTIC_META


def _extract_ir_fields() -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for py_path in sorted(IR_ROOT.glob("*.py")):
        if py_path.name.startswith("_"):
            continue
        tree = ast.parse(py_path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            base_names = {
                (
                    b.attr
                    if isinstance(b, ast.Attribute)
                    else (b.id if isinstance(b, ast.Name) else "")
                )
                for b in node.bases
            }
            if (base_names & {"StrEnum", "IntEnum", "Enum"}) and not (base_names & {"BaseModel"}):
                continue
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    fname = item.target.id
                    if _is_scannable_field(fname):
                        results.append((py_path.stem, node.name, fname))
    return results


def _collect_python_readers(py_path: Path) -> set[str]:
    try:
        tree = ast.parse(py_path.read_text())
    except SyntaxError:
        return set()
    attrs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            attrs.add(node.attr)
        elif isinstance(node, ast.Call):
            func_name = None
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
            if func_name in GETATTR_FAMILY and len(node.args) >= 2:
                arg = node.args[1]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    attrs.add(arg.value)
    return attrs


def _collect_jinja_readers(html_path: Path) -> set[str]:
    return set(JINJA_ATTR_RE.findall(html_path.read_text(errors="ignore")))


def ir_orphans_by_module() -> dict[str, list[tuple[str, str]]]:
    """Return {module: [(class, field), ...]} for IR fields with zero external readers."""
    readers: defaultdict[str, set[str]] = defaultdict(set)
    ir_rel = IR_ROOT.relative_to(SRC_ROOT.parent)
    for py_path in SRC_ROOT.rglob("*.py"):
        rel = py_path.relative_to(SRC_ROOT.parent)
        if str(rel).startswith(str(ir_rel)) or "__pycache__" in py_path.parts:
            continue
        for attr in _collect_python_readers(py_path):
            readers[attr].add(str(rel))
    for html_path in SRC_ROOT.rglob("*.html"):
        if "__pycache__" in html_path.parts:
            continue
        for attr in _collect_jinja_readers(html_path):
            readers[attr].add(str(html_path.relative_to(SRC_ROOT.parent)))

    by_module: defaultdict[str, list[tuple[str, str]]] = defaultdict(list)
    for mod, cls, field in _extract_ir_fields():
        if not readers.get(field):
            by_module[mod].append((cls, field))
    return dict(by_module)


# -----------------------------------------------------------------------------
# Section 2: Module import-graph orphans
# -----------------------------------------------------------------------------


def _resolve_import(imp: str) -> str:
    """Normalise an `import X` or `from X import Y` target to its module path."""
    return imp.split(".")[0] + ("." + ".".join(imp.split(".")[1:]) if "." in imp else "")


def _module_name_from_path(p: Path) -> str:
    """`src/dazzle/core/ir/workspaces.py` -> `dazzle.core.ir.workspaces`."""
    rel = p.relative_to(SRC_ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _string_literals_in_file(py_path: Path) -> set[str]:
    """Every top-level string literal in a Python file.

    Used to detect dynamic-import patterns: modules registered via path
    strings (``_MOD_DSL = "dazzle.mcp.server.handlers.dsl"``) or loaded
    via ``importlib.import_module("dazzle.x.y")`` / subprocess
    ``python -c "from dazzle.x import y"``. The audit intersects these
    strings with ``all_modules`` to find dynamic edges that the AST
    import pass misses.
    """
    try:
        tree = ast.parse(py_path.read_text())
    except SyntaxError:
        return set()
    strings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Only interested in dotted strings that could plausibly be module paths.
            if "." in node.value and all(part.isidentifier() for part in node.value.split(".")):
                strings.add(node.value)
    return strings


def _imports_in_file(py_path: Path) -> set[str]:
    """Module names imported by this file.

    Captures all three forms:

    * ``import A.B.C`` → ``A.B.C``
    * ``from A.B import C`` → ``A.B`` AND ``A.B.C`` (C may be a submodule
      or a name; we emit both so a submodule import resolves correctly).
    * ``from .sub import C`` / ``from ..pkg import C`` — **relative imports**
      are resolved to their absolute module path using the file's own package
      path, then treated as the absolute form above.

    **Relative-import resolution matters.** Without it, a sibling import
    like ``src/dazzle/core/dsl_parser_impl/entity.py`` doing
    ``from .fitness import parse_fitness_block`` would not register
    ``dazzle.core.dsl_parser_impl.fitness`` as imported — the audit would
    then flag fitness.py as orphan despite it being actively used.
    Surfaced cycle 371 while investigating a suspected fitness-parser gap.
    """
    try:
        tree = ast.parse(py_path.read_text())
    except SyntaxError:
        return set()
    imports: set[str] = set()
    # Resolve relative imports using the file's own package path.
    try:
        module_parts = _module_name_from_path(py_path).split(".")
    except ValueError:
        module_parts = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            base: str | None = None
            if node.level == 0 and node.module:
                base = node.module
            elif node.level > 0 and module_parts:
                # Resolve relative import to absolute module path.
                # For __init__.py: module_parts already equals the package path,
                #   so level=1 ("current package") → keep all parts.
                # For foo.py:     module_parts ends in "foo", so level=1 → strip "foo".
                # General rule: anchor length = len(module_parts) - level + (1 if __init__ else 0).
                init_adj = 1 if py_path.name == "__init__.py" else 0
                anchor_len = len(module_parts) - node.level + init_adj
                anchor_parts = module_parts[:anchor_len] if anchor_len > 0 else []
                if node.module:
                    base = ".".join([*anchor_parts, node.module]) if anchor_parts else node.module
                elif anchor_parts:
                    base = ".".join(anchor_parts)
            if base:
                imports.add(base)
                for alias in node.names:
                    if alias.name != "*":
                        imports.add(f"{base}.{alias.name}")
    return imports


def _has_main_guard(py_path: Path) -> bool:
    text = py_path.read_text()
    return 'if __name__ == "__main__"' in text or "if __name__ == '__main__'" in text


def _console_script_modules() -> set[str]:
    py = REPO_ROOT / "pyproject.toml"
    try:
        data = tomllib.loads(py.read_text())
    except Exception:
        return set()
    scripts = data.get("project", {}).get("scripts", {}) or {}
    modules: set[str] = set()
    for _, target in scripts.items():
        # "dazzle.cli:main" -> "dazzle.cli"
        module = target.split(":")[0]
        modules.add(module)
    return modules


def _package_reexports(init_path: Path) -> list[str]:
    """For a package __init__, return relative submodule names re-exported via
    ``from .submod import foo``.

    Re-exports mean ``from pkg import foo`` elsewhere implicitly imports
    ``pkg.submod`` at runtime, even though the AST only records ``pkg`` as the
    import target. Without this pre-pass, every submodule behind a re-export
    looks like an orphan.
    """
    try:
        tree = ast.parse(init_path.read_text())
    except SyntaxError:
        return []
    result: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
            result.append(node.module)
    return result


def module_orphans() -> list[tuple[str, Path]]:
    """Return [(module_name, path)] for modules with zero importers under SCAN_ROOTS."""
    # Path-substring excludes: vendored code, build artefacts, generated tests.
    # Third-party packages under node_modules are orphan by definition from
    # Dazzle's perspective — not worth reporting. Build artefacts under
    # `src/**/build/` are generated copies, not source. Generated tests under
    # `examples/**/tests/e2e/test_*_generated.py` are collected by pytest, not
    # imported. All three showed up as noise in the 65-orphan list post cycle
    # 371; adding them here reduces the list further without losing real signal.
    EXCLUDED_PATH_PARTS: tuple[str, ...] = (
        "__pycache__",
        "node_modules",
        "alembic/versions",
    )
    EXCLUDED_PATH_GLOBS: tuple[str, ...] = (
        "*/build/*",
        "*/tests/e2e/test_*_generated.py",
    )

    all_modules: dict[str, Path] = {}
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if any(part in EXCLUDED_PATH_PARTS for part in p.parts):
                continue
            if any(p.match(g) for g in EXCLUDED_PATH_GLOBS):
                continue
            if p.name == "__main__.py":
                continue
            all_modules[_module_name_from_path(p)] = p

    # Pre-pass: build re-export chains. If pkg/__init__.py does
    # `from .sub import foo`, mark pkg.sub as importer-equivalent to pkg.
    reexports: defaultdict[str, set[str]] = defaultdict(set)  # pkg → {pkg.sub, …}
    for mod, p in all_modules.items():
        if p.name != "__init__.py":
            continue
        for sub in _package_reexports(p):
            reexports[mod].add(f"{mod}.{sub}")

    # Build reverse-import set: set of modules imported from anywhere under src/
    importers: defaultdict[str, set[str]] = defaultdict(set)
    known_modules = set(all_modules.keys())
    for mod, p in all_modules.items():
        for target in _imports_in_file(p):
            # Strip the leaf to bubble imports up the hierarchy so
            # `from pkg.sub import foo` counts as importing `pkg.sub` AND `pkg`.
            parts = target.split(".")
            for i in range(len(parts), 0, -1):
                ancestor = ".".join(parts[:i])
                importers[ancestor].add(mod)
                # Propagate to re-exported submodules of this ancestor.
                for reexp in reexports.get(ancestor, ()):
                    importers[reexp].add(mod)
        # Dynamic-import detection: any string literal that exactly matches
        # a known module path counts as an import edge. Catches handlers
        # registered via `_MOD_X = "dazzle.pkg.mod"` and loaded via
        # importlib.import_module, subprocess `python -c "from X import Y"`
        # (the literal appears as a string), and similar indirection.
        for literal in _string_literals_in_file(p):
            if literal in known_modules:
                importers[literal].add(mod)

    script_modules = _console_script_modules()
    orphans: list[tuple[str, Path]] = []
    for mod, p in sorted(all_modules.items()):
        if mod in script_modules:
            continue
        # __init__ modules reached via the package path don't show up by dotted
        # name alone — they're imported as the parent package. Skip them.
        if p.name == "__init__.py":
            continue
        if importers.get(mod):
            continue
        # Treat `if __name__ == "__main__"` files as scripts (not orphan bugs).
        if _has_main_guard(p):
            continue
        orphans.append((mod, p))
    return orphans


# -----------------------------------------------------------------------------
# Report writer
# -----------------------------------------------------------------------------


def render_report() -> str:
    ir_by_mod = ir_orphans_by_module()
    ir_total = sum(len(v) for v in ir_by_mod.values())
    mod_orphans = module_orphans()

    lines: list[str] = []
    lines.append("# Half-finished-internals audit")
    lines.append("")
    lines.append(f"Generated: {date.today().isoformat()} (on-demand via `make audit-internals`)")
    lines.append("")
    lines.append("## Section 1 — IR field orphans")
    lines.append("")
    lines.append(
        f"{ir_total} public IR field(s) across {len(ir_by_mod)} module(s) have zero external readers."
    )
    lines.append(
        "See `tests/unit/test_ir_field_reader_parity.py` for detection details. Baselined as debt; "
        "listed here for triage:"
    )
    lines.append("")
    for mod in sorted(ir_by_mod):
        lines.append(f"### `{mod}` ({len(ir_by_mod[mod])})")
        for cls, field in sorted(ir_by_mod[mod]):
            lines.append(f"- `{cls}.{field}`")
        lines.append("")

    lines.append("## Section 2 — Module import-graph orphans")
    lines.append("")
    lines.append(
        f"{len(mod_orphans)} module(s) under `src/dazzle*/` have zero importers and no "
        "`__main__` guard. Known to be noisy (cycle 328 FP rate ~83% — utility modules, "
        "side-effect-import code like CLI command collectors, etc.). Real findings tend to "
        "surface as modules with specific-sounding names that suggest they were meant to be "
        "called from somewhere. Examples found this way: `hot_reload.py` → #834."
    )
    lines.append("")
    for mod, path in mod_orphans:
        rel = path.relative_to(REPO_ROOT)
        lines.append(f"- `{mod}` (`{rel}`)")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = render_report()
    REPORT_PATH.write_text(report)
    first = report.split("\n")[:6]
    print("\n".join(first))
    ir_lines = [line for line in report.split("\n") if line.startswith("- ")]
    print(f"\nWrote {REPORT_PATH} ({len(ir_lines)} line items total).")


if __name__ == "__main__":
    main()
