"""
Runtime-URLs API surface snapshot — cycle 5 of #961.

Walks the framework runtime route modules under
`src/dazzle/http/runtime/*_routes.py` via AST and snapshots every
`@router.<method>(...)` decoration: HTTP method, path template, handler
function name, and parameter signature.

Static analysis (no app build, no DB connection) is the right tool here —
the alternative would require constructing a fully-bound `FastAPI` app
from a dummy AppSpec, which the runtime refuses to build without a real
PostgreSQL connection. The static lens captures every route the framework
*can* register; runtime conditionals (e.g., dev-mode-only) are visible in
the source but their gating logic is out of scope for an API-surface
snapshot.
"""

import ast
from pathlib import Path

from .dsl_constructs import REPO_ROOT

BASELINE_PATH = REPO_ROOT / "docs" / "api-surface" / "runtime-urls.txt"

ROUTES_DIR = REPO_ROOT / "src" / "dazzle" / "http" / "runtime"

# Additional route modules outside `back/runtime/`. Anything added here
# is AST-walked alongside the canonical `*_routes.py` files so the API
# surface gate covers it. Used when a feature ships routes that
# logically live in their own package (e.g. `dazzle/signing/routes.py`
# for the #1283 signing primitive).
EXTRA_ROUTE_FILES: tuple[Path, ...] = (REPO_ROOT / "src" / "dazzle" / "signing" / "routes.py",)

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "websocket"}

# Production routes registered *dynamically* (via `router.add_api_route(...)`),
# which the AST decorator walk above cannot see — it only matches
# `@router.<method>` decorations. Entries here are pattern rows the api-surface
# gate would otherwise miss.
#
# Scope: only genuinely *public, production* dynamic surfaces belong here.
# `debug_routes.py` / `test_routes.py` / `metrics_routes.py` also call
# `add_api_route`, but those are dev/test-mode-only and are intentionally NOT
# part of the public surface — so this is a curated allowlist, not a blanket
# `add_api_route` recogniser (which would over-capture them).
#
# Atomic-flow routes (#1228/#1313, ADR-0029): `atomic_flow_routes.py`
# `_register_one` registers one `POST /api/atomic/<flow>` endpoint per parsed
# `AtomicFlowSpec` via `router.add_api_route(f"/{flow.name}", ...)`. Flow names
# are per-app, so the framework-level baseline pins the route as a
# `{flow_name}` pattern (#1314). The `/api/atomic` prefix comes from
# `APIRouter(prefix="/api/atomic")` in `build_atomic_flow_router`; the handler
# name mirrors `handler.__name__ = f"atomic_{flow.name}"`.
_DYNAMIC_ROUTES: tuple[dict[str, str], ...] = (
    {
        "method": "POST",
        "path": "/api/atomic/{flow_name}",
        "handler": "atomic_{flow_name}",
        "signature": "(body, user) -> dict",
        "module": "atomic_flow_routes",
    },
)


def _path_from_decorator(call: ast.Call) -> str | None:
    if not call.args:
        return None
    arg0 = call.args[0]
    if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
        return arg0.value
    return None


def _decorator_method(decorator: ast.expr) -> str | None:
    if not isinstance(decorator, ast.Call):
        return None
    func = decorator.func
    if not isinstance(func, ast.Attribute):
        return None
    if func.attr.lower() not in HTTP_METHODS:
        return None
    return func.attr.lower()


def _signature_summary(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Render the function signature as `name(arg: Type, ...) -> Ret`."""
    args = []
    pos = node.args.posonlyargs + node.args.args
    defaults_offset = len(pos) - len(node.args.defaults)
    for i, arg in enumerate(pos):
        annotation = ast.unparse(arg.annotation) if arg.annotation else ""
        default_idx = i - defaults_offset
        default = f" = {ast.unparse(node.args.defaults[default_idx])}" if default_idx >= 0 else ""
        annotation_str = f": {annotation}" if annotation else ""
        args.append(f"{arg.arg}{annotation_str}{default}")
    if node.args.vararg:
        args.append(f"*{node.args.vararg.arg}")
    for kwarg, kw_default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=False):
        kw_annotation = ast.unparse(kwarg.annotation) if kwarg.annotation else ""
        kw_default_str = f" = {ast.unparse(kw_default)}" if kw_default is not None else ""
        kw_annotation_str = f": {kw_annotation}" if kw_annotation else ""
        args.append(f"{kwarg.arg}{kw_annotation_str}{kw_default_str}")
    if node.args.kwarg:
        args.append(f"**{node.args.kwarg.arg}")
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"({', '.join(args)}){returns}"


def _module_label(path: Path) -> str:
    """Stable, baseline-friendly module label.

    Files in the canonical `back/runtime/` directory use their stem
    directly (e.g. `bulk_routes`). Files registered via
    ``EXTRA_ROUTE_FILES`` outside that directory get a
    ``<parent>_<stem>`` form so the label still sorts deterministically
    and stays unique even if two extra files share a stem.
    """
    if path.parent == ROUTES_DIR:
        return path.stem
    return f"{path.parent.name}_{path.stem}"


def _walk_module(path: Path) -> list[dict[str, str]]:
    """Extract every decorated route from a module file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    routes: list[dict[str, str]] = []
    label = _module_label(path)
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for dec in node.decorator_list:
            method = _decorator_method(dec)
            if method is None:
                continue
            # _decorator_method already validated dec.func is ast.Attribute
            assert isinstance(dec, ast.Call)
            url = _path_from_decorator(dec)
            if url is None:
                continue
            routes.append(
                {
                    "method": method.upper(),
                    "path": url,
                    "handler": node.name,
                    "signature": _signature_summary(node),
                    "module": label,
                }
            )
    return routes


def _collect_routes() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for path in sorted(ROUTES_DIR.glob("*_routes.py")):
        out.extend(_walk_module(path))
    for extra in EXTRA_ROUTE_FILES:
        if extra.exists():
            out.extend(_walk_module(extra))
    # Curated dynamic routes the AST walk structurally can't see.
    out.extend(dict(r) for r in _DYNAMIC_ROUTES)
    out.sort(key=lambda r: (r["module"], r["path"], r["method"], r["handler"]))
    return out


def snapshot_runtime_urls() -> str:
    """Render the deterministic runtime-URLs API-surface snapshot."""
    routes = _collect_routes()
    by_module: dict[str, list[dict[str, str]]] = {}
    for r in routes:
        by_module.setdefault(r["module"], []).append(r)

    lines: list[str] = []
    lines.append("# DAZZLE Runtime URLs — API Surface (cycle 5 of #961)")
    lines.append("#")
    lines.append(
        "# Source of truth: AST walk of src/dazzle/http/runtime/*_routes.py "
        "(+ EXTRA_ROUTE_FILES, + curated _DYNAMIC_ROUTES)"
    )
    lines.append("# Regenerate: dazzle inspect api runtime-urls --write")
    lines.append("# Drift gate: tests/unit/test_api_surface_drift.py")
    lines.append("#")
    lines.append("# Static analysis — no app build, no DB connection. Captures every")
    lines.append("# route the framework *can* register; runtime gating (dev-mode-only,")
    lines.append("# conditional on AppSpec content) is out of scope for an API-surface")
    lines.append("# lens. Adding/removing a route, changing its path template, HTTP")
    lines.append("# method, handler name, or signature all fire the drift gate.")
    lines.append("")
    lines.append(f"# Counts: {len(routes)} routes across {len(by_module)} modules")
    lines.append("")

    for module in sorted(by_module):
        lines.append(f"module: {module}")
        for r in by_module[module]:
            # Render empty paths as `(root)` so the line has no trailing
            # whitespace (pre-commit strips it, which would otherwise drift
            # the baseline on every commit).
            path_display = r["path"] if r["path"] else "(root)"
            lines.append(f"  {r['method']} | {path_display}")
            lines.append(f"    handler: {r['handler']}{r['signature']}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def diff_against_baseline(snapshot: str | None = None) -> str:
    """Unified diff between baseline and live snapshot. Empty = no drift."""
    import difflib

    if snapshot is None:
        snapshot = snapshot_runtime_urls()
    if not BASELINE_PATH.exists():
        return f"(no baseline at {BASELINE_PATH} — run `dazzle inspect api runtime-urls --write`)\n"
    baseline = BASELINE_PATH.read_text(encoding="utf-8")
    if baseline == snapshot:
        return ""
    diff = difflib.unified_diff(
        baseline.splitlines(keepends=True),
        snapshot.splitlines(keepends=True),
        fromfile=str(BASELINE_PATH.relative_to(REPO_ROOT)),
        tofile="(live)",
        n=3,
    )
    return "".join(diff)


__all__ = [
    "BASELINE_PATH",
    "ROUTES_DIR",
    "diff_against_baseline",
    "snapshot_runtime_urls",
]
